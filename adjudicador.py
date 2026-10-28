"""
ADJUDICADOR — lleva a Supabase lo que cada empresa cliente oferto y gano
=======================================================================

Lee la bodega de licitaciones (`bodega/licitaciones/*.parquet`, la que llena
`licitador.py`) y deja en la tabla `adjudicaciones_publicas` una fila por
licitacion x RUT, SOLO para los RUT de los suscriptores. Con eso CupidoLicita
calcula el ROI (`roi_tablero`) sin tener que leer la bodega.

Corre dentro del workflow «Bodega de Licitaciones», despues del licitador.
Recalcula TODO lo que hay en la bodega en cada corrida: una licitacion que
estaba «Cerrada» pasa a «Adjudicada» meses despues, y asi se actualiza sola.

Lo que se comprobo en el archivo real (2026-08, 142.292 filas):

- `monto_adjudicado` es el TOTAL de la linea ganada: monto unitario por
  cantidad adjudicada (calza en el 100% de las filas seleccionadas). Se suma.
- Una adjudicacion parcial (se ofertaron 750, se adjudicaron 515) existe: por
  eso lo ganado se toma de `monto_adjudicado` y no de `total_ofertado`.
- «Cerrada» es que todavia no se adjudica: va como PENDIENTE, no como perdida.

Necesita en el entorno SUPABASE_URL y SUPABASE_SECRET_KEY.

    python adjudicador.py              # sube a Supabase
    python adjudicador.py --prueba     # solo muestra lo que subiria
"""
import argparse
import json
import os
import re
import sys
import urllib.request
from pathlib import Path

import pandas as pd

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

AQUI = Path(__file__).parent
BODEGA = AQUI / "bodega" / "licitaciones"
COLUMNAS = ["codigo", "nombre", "estado", "nombre_organismo", "nombre_unidad", "region",
            "fecha_cierre", "fecha_adjudicacion", "rut_proveedor", "n_oferentes",
            "seleccionada", "total_ofertado", "monto_adjudicado"]
TANDA = 500


def rut_norm(rut) -> str:
    """Solo numeros y K: «77.711.959-1» y «777119591» son el mismo RUT."""
    return re.sub(r"[^0-9K]", "", str(rut or "").upper())


def _pedir(metodo: str, ruta: str, cuerpo=None, extra: dict | None = None):
    url = os.environ["SUPABASE_URL"].strip().rstrip("/")
    clave = os.environ["SUPABASE_SECRET_KEY"].strip()
    cabeceras = {"apikey": clave, "Authorization": f"Bearer {clave}",
                 "Content-Type": "application/json", "Accept": "application/json"}
    cabeceras.update(extra or {})
    datos = json.dumps(cuerpo).encode("utf-8") if cuerpo is not None else None
    peticion = urllib.request.Request(f"{url}/rest/v1/{ruta}", data=datos,
                                      headers=cabeceras, method=metodo)
    with urllib.request.urlopen(peticion, timeout=120) as respuesta:
        texto = respuesta.read().decode("utf-8")
        return json.loads(texto) if texto else None


def ruts_clientes() -> set[str]:
    filas = _pedir("GET", "suscriptores?select=rut_empresa&rut_empresa=not.is.null")
    return {r for r in (rut_norm(f.get("rut_empresa")) for f in filas) if r}


def _fecha(serie: pd.Series) -> pd.Series:
    """ChileCompra usa 1900-01-01 como «sin fecha»."""
    fechas = pd.to_datetime(serie, errors="coerce")
    return fechas.where(fechas.dt.year >= 2000)


def resultado(estado: str, ganadas: int) -> str:
    """Manda la oferta elegida, no el estado de la licitacion.

    En 2026-08 hay 993 lineas «Seleccionada» en licitaciones que siguen
    «Cerrada»: el licitador solo refresca dos meses y el estado final se queda
    atras (ver `meses_por_procesar`). Si la oferta fue elegida, se gano.
    """
    estado = (estado or "").lower()
    if estado.startswith(("desierta", "revocada", "suspendida")):
        return "SIN_ADJUDICAR"
    if ganadas > 0:
        return "GANADA"
    if estado.startswith("adjudicada"):
        return "PERDIDA"
    return "PENDIENTE"


def armar_filas(ruts: set[str], carpeta: Path = BODEGA) -> list[dict]:
    trozos = []
    for parquet in sorted(carpeta.glob("*.parquet")):
        d = pd.read_parquet(parquet, columns=COLUMNAS)
        d["rut"] = d["rut_proveedor"].map(rut_norm)
        trozos.append(d[d["rut"].isin(ruts)])
    if not trozos:
        return []
    d = pd.concat(trozos, ignore_index=True)
    if d.empty:
        return []

    d["gano"] = d["seleccionada"].astype(str).str.strip().str.lower() == "seleccionada"
    d["adjudicado"] = d["monto_adjudicado"].where(d["gano"], 0).fillna(0)
    d["fecha_cierre"] = _fecha(d["fecha_cierre"])
    d["fecha_adjudicacion"] = _fecha(d["fecha_adjudicacion"])

    g = d.groupby(["codigo", "rut"], sort=False)
    t = g.agg(nombre=("nombre", "last"), organismo=("nombre_organismo", "last"),
              unidad=("nombre_unidad", "last"), region=("region", "last"),
              estado_licitacion=("estado", "last"), fecha_cierre=("fecha_cierre", "max"),
              fecha_adjudicacion=("fecha_adjudicacion", "max"),
              lineas_ofertadas=("gano", "size"), lineas_ganadas=("gano", "sum"),
              n_oferentes=("n_oferentes", "max"),
              monto_ofertado=("total_ofertado", "sum"),
              monto_adjudicado=("adjudicado", "sum")).reset_index()

    filas = []
    for f in t.itertuples(index=False):
        filas.append({
            "codigo_licitacion": f.codigo, "rut": f.rut,
            "nombre": f.nombre or None, "organismo": f.organismo or None,
            "unidad": f.unidad or None, "region": f.region or None,
            "estado_licitacion": f.estado_licitacion or None,
            "resultado": resultado(f.estado_licitacion, int(f.lineas_ganadas)),
            "fecha_cierre": f.fecha_cierre.date().isoformat() if pd.notna(f.fecha_cierre) else None,
            "fecha_adjudicacion": (f.fecha_adjudicacion.date().isoformat()
                                   if pd.notna(f.fecha_adjudicacion) else None),
            "lineas_ofertadas": int(f.lineas_ofertadas),
            "lineas_ganadas": int(f.lineas_ganadas),
            "n_oferentes": int(f.n_oferentes) if pd.notna(f.n_oferentes) else None,
            # Peso entero: el peso chileno no tiene centavos.
            "monto_ofertado": int(round(f.monto_ofertado or 0)),
            "monto_adjudicado": int(round(f.monto_adjudicado or 0)),
        })
    return filas


def subir(filas: list[dict]) -> None:
    for i in range(0, len(filas), TANDA):
        _pedir("POST", "adjudicaciones_publicas?on_conflict=codigo_licitacion,rut",
               filas[i:i + TANDA],
               {"Prefer": "resolution=merge-duplicates,return=minimal"})


def main() -> None:
    argumentos = argparse.ArgumentParser(description="Lleva las adjudicaciones a Supabase")
    argumentos.add_argument("--prueba", action="store_true", help="mostrar sin subir")
    argumentos.add_argument("--rut", action="append", help="RUT a mirar en --prueba")
    argumentos.add_argument("--carpeta", default=str(BODEGA))
    opciones = argumentos.parse_args()

    ruts = ({rut_norm(r) for r in opciones.rut} if opciones.rut else ruts_clientes())
    print(f"ADJUDICADOR · {len(ruts)} RUT de clientes", flush=True)
    filas = armar_filas(ruts, Path(opciones.carpeta))
    ganadas = [f for f in filas if f["resultado"] == "GANADA"]
    print(f"  {len(filas)} participaciones · {len(ganadas)} ganadas · "
          f"${sum(f['monto_adjudicado'] for f in ganadas):,.0f} adjudicados".replace(",", "."))
    if opciones.prueba:
        for f in sorted(ganadas, key=lambda f: -f["monto_adjudicado"])[:5]:
            print("   ", f["codigo_licitacion"], f["fecha_adjudicacion"], f["monto_adjudicado"],
                  (f["nombre"] or "")[:60])
        return
    subir(filas)
    print("  subidas a adjudicaciones_publicas", flush=True)


if __name__ == "__main__":
    main()
