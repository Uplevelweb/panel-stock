"""
CATALOGO CONVENIO MARCO — lo que cada suscriptor tiene publicado, sacado del
dato oficial de ChileCompra
=============================================================================

Serling lo pidio el 16-09-2026, viendo la tarjeta "Tus alertas" del panel de
Territorio: cruzar lo que compra el Estado contra el catalogo REAL de cada
suscriptor, no contra un archivo que alguien suba ni solo contra lo que ya
vendio antes.

DE DONDE SALE
--------------
ChileCompra publica, sin clave y gratis, el catalogo completo de los 18
convenios marco vigentes -que vende cada proveedor, con su RUT y el ID exacto
de cada producto-, actualizado todos los martes:
https://datos-abiertos.chilecompra.cl/descargas/convenio-marco

El indice de esos 18 archivos vive en un solo CSV chico, comprobado a mano el
16-09-2026:
https://transparenciachc.blob.core.windows.net/maestrascm/CM_publicados.csv

Cada fila de un convenio trae, entre otras, estas columnas -los nombres son
los que ChileCompra usa, con tilde y todo-:
    RUT PROVEEDOR, ID PRODUCTO, PRODUCTO, CONVENIO MARCO, NUMERO LICITACION,
    REGION

QUE HACE ESTE SCRIPT
---------------------
1. Lee los RUT de los suscriptores activos de Territorio (misma consulta que
   ya usa `alertador.configuracion`).
2. Baja el indice y, de ahi, cada uno de los convenios (son zips con un CSV
   adentro).
3. Se queda SOLO con las filas cuyo RUT PROVEEDOR es de un suscriptor -el
   resto del catalogo, cientos de miles de lineas de otros proveedores, se
   descarta al vuelo y no se guarda-.
4. Sube lo que quedo a `convenio_marco_publicado` en Supabase (upsert: no
   duplica si se corre dos veces).

Corre solo, una vez por semana, un dia despues de que ChileCompra actualiza
(miercoles). Ver `.github/workflows/catalogo.yml`.

NO GASTA EL TICKET DE MERCADO PUBLICO. Esto es un archivo publico de
ChileCompra, no la API con cupo diario.

COMO SE PRUEBA
---------------
    python catalogo_convenio_marco.py --prueba

Baja todo y cuenta cuantas filas calzarian, pero no escribe nada en Supabase.
"""
from __future__ import annotations

import csv
import io
import json
import os
import sys
import urllib.request
import zipfile

from alertador import configuracion, solo_digitos_rut

MAESTRA_URL = "https://transparenciachc.blob.core.windows.net/maestrascm/CM_publicados.csv"

CABECERA = {"User-Agent": "Mozilla/5.0 (compatible; UplevelTerritorio/1.0)"}


def _bajar(url: str, timeout: int = 120) -> bytes:
    peticion = urllib.request.Request(url, headers=CABECERA)
    with urllib.request.urlopen(peticion, timeout=timeout) as respuesta:
        return respuesta.read()


def indice_de_convenios() -> list[str]:
    """Las URL de cada uno de los zip de productos, desde la maestra."""
    crudo = _bajar(MAESTRA_URL).decode("utf-8-sig")
    filas = list(csv.DictReader(io.StringIO(crudo), delimiter=";"))
    return [f["link_archivo"] for f in filas if f.get("link_archivo", "").strip()]


def ruts_de_suscriptores() -> set[str]:
    """Los RUT que algun suscriptor activo de Territorio puso en su filtro."""
    return {
        solo_digitos_rut(s.get("rut_proveedor") or "")
        for s in configuracion()
        if s.get("rut_proveedor")
    }


def _valor(fila: dict, *nombres: str) -> str:
    """El CSV trae encabezados con tilde; se prueban variantes por si algun
    convenio viene sin ella (paso con otros archivos de ChileCompra)."""
    for nombre in nombres:
        if nombre in fila and fila[nombre] is not None:
            return str(fila[nombre]).strip()
    return ""


def filas_del_convenio(url_zip: str, ruts: set[str]) -> list[dict]:
    """Descarga un convenio entero y devuelve solo las filas de RUT conocidos."""
    crudo = _bajar(url_zip)
    encontradas: list[dict] = []
    with zipfile.ZipFile(io.BytesIO(crudo)) as zf:
        for nombre_interno in zf.namelist():
            if not nombre_interno.lower().endswith(".csv"):
                continue
            with zf.open(nombre_interno) as f:
                texto = io.TextIOWrapper(f, encoding="utf-8-sig", errors="replace")
                for fila in csv.DictReader(texto):
                    rut = solo_digitos_rut(_valor(fila, "RUT PROVEEDOR", "RUT PROVEEDOR "))
                    if rut not in ruts:
                        continue
                    id_producto = _valor(fila, "ID PRODUCTO")
                    if not id_producto:
                        continue
                    encontradas.append({
                        "rut_proveedor": rut,
                        "codigo_convenio": _valor(fila, "NÚMERO LICITACIÓN", "NUMERO LICITACION") or "SIN-CODIGO",
                        "convenio_marco": _valor(fila, "CONVENIO MARCO"),
                        "id_producto": id_producto,
                        "producto": _valor(fila, "PRODUCTO")[:400],
                        "region": _valor(fila, "REGIÓN", "REGION"),
                    })
    return encontradas


def subir_a_supabase(filas: list[dict]) -> None:
    url = os.environ.get("SUPABASE_URL", "").strip()
    clave = os.environ.get("SUPABASE_SECRET_KEY", "").strip()
    if not (url and clave):
        print("Faltan SUPABASE_URL / SUPABASE_SECRET_KEY, no se sube nada.")
        return
    if not filas:
        print("No hay filas que subir.")
        return

    # De a 500: Supabase/PostgREST corta los cuerpos muy grandes.
    tanda = 500
    for inicio in range(0, len(filas), tanda):
        trozo = filas[inicio:inicio + tanda]
        cuerpo = json.dumps(trozo).encode("utf-8")
        peticion = urllib.request.Request(
            f"{url}/rest/v1/convenio_marco_publicado?on_conflict=codigo_convenio,id_producto",
            data=cuerpo, method="POST",
            headers={
                "apikey": clave,
                "Authorization": f"Bearer {clave}",
                "Content-Type": "application/json",
                "Prefer": "resolution=merge-duplicates,return=minimal",
            },
        )
        with urllib.request.urlopen(peticion, timeout=120) as respuesta:
            respuesta.read()
        print(f"  subidas {min(inicio + tanda, len(filas))} de {len(filas)}")


def main() -> None:
    prueba = "--prueba" in sys.argv

    ruts = ruts_de_suscriptores()
    if not ruts:
        print("No hay suscriptores con RUT en su filtro. Nada que hacer.")
        return
    print(f"{len(ruts)} RUT de suscriptores con filtro por RUT.")

    urls = indice_de_convenios()
    print(f"{len(urls)} convenios en la maestra de ChileCompra.\n")

    todas: list[dict] = []
    for url_zip in urls:
        nombre = url_zip.rsplit("/", 1)[-1]
        try:
            filas = filas_del_convenio(url_zip, ruts)
        except Exception as error:
            print(f"  {nombre}: fallo ({error})")
            continue
        if filas:
            print(f"  {nombre}: {len(filas)} productos de nuestros suscriptores")
        todas.extend(filas)

    print(f"\nTotal: {len(todas)} productos encontrados en {len(ruts)} RUT revisados.")

    if prueba:
        print("Modo prueba: no se sube nada a Supabase.")
        return

    subir_a_supabase(todas)
    print("Listo, subido a Supabase.")


if __name__ == "__main__":
    main()
