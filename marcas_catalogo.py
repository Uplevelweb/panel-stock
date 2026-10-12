"""
Marca de cada producto de Convenio Marco (12-10-2026, Mercado total).

La marca NO viene en las ordenes de compra: solo existe en el catalogo de los
convenios marco que ChileCompra publica (sin clave, gratis, actualizado los
martes). Se cruza con las compras por ID de producto, y por eso la marca solo
se puede medir dentro de Convenio Marco.

Deja `bodega/marcas_cm.parquet`: id_producto, marca, modelo, convenio. Una
fila por ID. Se baja como mucho una vez por semana; si el archivo es mas
nuevo que eso, no hace nada (no cuesta una descarga mas en la corrida de
cada madrugada).

    python marcas_catalogo.py            # baja si hace falta
    python marcas_catalogo.py --forzar   # baja siempre
"""
from __future__ import annotations
import csv, io, sys, time, urllib.request, zipfile
from pathlib import Path
import pandas as pd

AQUI = Path(__file__).parent
SALIDA = AQUI / "bodega" / "marcas_cm.parquet"
MAESTRA_URL = "https://transparenciachc.blob.core.windows.net/maestrascm/CM_publicados.csv"
CABECERA = {"User-Agent": "Mozilla/5.0 (compatible; UplevelTerritorio/1.0)"}
SEMANA = 6 * 24 * 3600
SIN_MARCA = {"", "SIN MARCA", "S/M", "NO APLICA", "N/A", "NA", "-", "SIN INFORMACION", "SIN INFORMACIÓN"}


def _bajar(url: str, timeout: int = 300) -> bytes:
    with urllib.request.urlopen(urllib.request.Request(url, headers=CABECERA), timeout=timeout) as r:
        return r.read()


def _valor(fila: dict, *nombres: str) -> str:
    # Los encabezados traen tilde y a veces espacios: se prueban variantes.
    limpio = {str(k).strip().upper(): v for k, v in fila.items()}
    for n in nombres:
        v = limpio.get(n.upper())
        if v is not None:
            return str(v).strip()
    return ""


def filas_de_zip(contenido: bytes) -> list[dict]:
    salida = []
    with zipfile.ZipFile(io.BytesIO(contenido)) as z:
        for nombre in z.namelist():
            if not nombre.lower().endswith(".csv"):
                continue
            with z.open(nombre) as f:
                texto = io.TextIOWrapper(f, encoding="utf-8-sig", errors="replace")
                for fila in csv.DictReader(texto):
                    idp = _valor(fila, "ID PRODUCTO")
                    if not idp:
                        continue
                    marca = _valor(fila, "MARCA")
                    salida.append({"id_producto": idp,
                                   "marca": "" if marca.upper() in SIN_MARCA else marca,
                                   "modelo": _valor(fila, "MODELO")[:120],
                                   "convenio": _valor(fila, "CONVENIO MARCO")})
    return salida


def construir() -> pd.DataFrame:
    crudo = _bajar(MAESTRA_URL).decode("utf-8-sig")
    enlaces = [f["link_archivo"] for f in csv.DictReader(io.StringIO(crudo), delimiter=";")
               if f.get("link_archivo", "").strip()]
    partes = []
    for url in enlaces:
        try:
            filas = filas_de_zip(_bajar(url))
        except Exception as e:
            print(f"   no se pudo leer {url.split('/')[-1]}: {type(e).__name__}")
            continue
        if filas:
            t = pd.DataFrame(filas)
            # Una fila por ID: si el mismo ID tiene varias, gana la que trae marca.
            t = t.sort_values("marca", ascending=False).drop_duplicates("id_producto")
            partes.append(t)
        print(f"   {url.split('/')[-1]}: {len(filas):,} filas")
    if not partes:
        return pd.DataFrame(columns=["id_producto", "marca", "modelo", "convenio"])
    return pd.concat(partes).sort_values("marca", ascending=False).drop_duplicates("id_producto")


if __name__ == "__main__":
    if SALIDA.exists() and "--forzar" not in sys.argv and time.time() - SALIDA.stat().st_mtime < SEMANA:
        print("marcas_cm.parquet es de esta semana: no se vuelve a bajar.")
        sys.exit(0)
    t = construir()
    if t.empty:
        print("No se pudo armar el catalogo de marcas; se deja el anterior.")
        sys.exit(0)
    t.to_parquet(SALIDA, index=False, compression="zstd")
    print(f"{len(t):,} productos, {(t['marca'] != '').mean():.0%} con marca -> {SALIDA}")
