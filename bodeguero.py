"""
BODEGUERO MASIVO — llena la bodega desde los datos abiertos de ChileCompra
==========================================================================

Reemplaza al bodeguero que consultaba la API orden por orden. La diferencia:

  API           1 consulta por orden, 10.000 al dia -> 51 dias para 2025-2026
  DATOS ABIERTOS 1 archivo por mes (~80 MB) con TODAS las ordenes -> minutos

Los archivos viven en `oc-da/AAAA-M.zip` y se actualizan a diario con un dia de
desfase. Traen una fila por producto comprado, con el **convenio marco** de cada
orden, que la API nunca entrego.

OJO: el archivo de un mes agrupa por fecha de ENVIO, pero la fecha que importa
para vender es la de CREACION, y una orden enviada en enero pudo crearse en
diciembre. Por eso las filas se reparten al parquet del mes en que se CREARON,
no al del archivo de donde salieron.
"""
import argparse
import csv, io, json, os, sys, time, urllib.request
from datetime import date
from pathlib import Path

import pandas as pd

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

BASE = "https://transparenciachc.blob.core.windows.net/oc-da/"
AQUI = Path(__file__).parent
BODEGA = AQUI / "bodega" / "detalle"
DESCARGAS = AQUI / "descargas_temporales"
PRIMER_MES = (2025, 1)

COLUMNAS = ["dia", "fecha", "orden", "estado", "unidad", "organismo", "convenio",
            "convenio_marco", "contacto", "proveedor", "rut_proveedor",
            "id_producto", "producto", "cantidad", "precio", "total"]


def meses_hasta_hoy():
    """(2025,1), (2025,2)... hasta el mes en curso."""
    hoy = date.today()
    año, mes = PRIMER_MES
    while (año, mes) <= (hoy.year, hoy.month):
        yield año, mes
        mes += 1
        if mes > 12:
            año, mes = año + 1, 1


def bajar(año: int, mes: int) -> Path | None:
    """Baja el zip del mes si no esta ya en disco."""
    DESCARGAS.mkdir(exist_ok=True)
    destino = DESCARGAS / f"{año}-{mes}.zip"
    if destino.exists():
        return destino
    url = f"{BASE}{año}-{mes}.zip"
    try:
        peticion = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(peticion, timeout=900) as respuesta:
            destino.write_bytes(respuesta.read())
        return destino
    except Exception as error:
        print(f"    no se pudo bajar {año}-{mes}: {type(error).__name__}", flush=True)
        return None


def filas_de_convenio_marco(archivo: Path):
    """Las lineas de Convenio Marco del archivo, ya en el formato de la bodega."""
    import zipfile
    z = zipfile.ZipFile(archivo)
    with z.open(z.namelist()[0]) as bruto:
        texto = io.TextIOWrapper(bruto, encoding="latin-1", newline="")
        for fila in csv.DictReader(texto, delimiter=";"):
            codigo = str(fila.get("Codigo") or "")
            tramos = codigo.split("-")
            if len(tramos) < 3 or not tramos[-1].upper().startswith("CM"):
                continue
            fecha = str(fila.get("FechaCreacion") or "")[:10]
            if len(fecha) != 10 or not fecha[:4].isdigit():
                continue
            # El ID de Convenio Marco viene entre parentesis, igual que en la API.
            especificacion = str(fila.get("EspecificacionComprador") or "").lstrip()
            identificador = ""
            if especificacion.startswith("("):
                posible = especificacion[1:].split(")")[0]
                identificador = posible if posible.isdigit() else ""
            yield {
                "dia": fecha, "fecha": fecha, "orden": codigo,
                "estado": str(fila.get("Estado") or "").strip(),
                # OJO: la unidad es el PREFIJO DEL CODIGO de la orden, no la
                # columna CodigoUnidadCompra del archivo. Son dos numeros
                # distintos y solo coinciden en el 37% de los casos; el resto
                # del sistema (catalogo, filtros, API) usa el prefijo.
                "unidad": tramos[0].strip(),
                "organismo": str(fila.get("CodigoOrganismoPublico") or "").strip(),
                "convenio": tramos[-1].upper(),
                "convenio_marco": str(fila.get("Codigo_ConvenioMarco") or "").strip(),
                "contacto": "",
                "proveedor": str(fila.get("NombreProveedor") or "").strip(),
                "rut_proveedor": str(fila.get("RutSucursal") or "").strip(),
                "id_producto": identificador,
                "producto": str(fila.get("EspecificacionComprador") or "").strip(),
                "cantidad": fila.get("cantidad"),
                "precio": fila.get("precioNeto"),
                "total": fila.get("totalLineaNeto"),
            }


def nombres_de_convenios(codigos: set[str]) -> dict[str, str]:
    """«2239-9-LR24» -> «Convenio Marco para la adquisición de Alimentos».

    Cada convenio marco es una licitacion, y su nombre se pide a la API de
    licitaciones. Son ~28 consultas una sola vez: el nombre no cambia.
    """
    guardados = {}
    archivo = BODEGA.parent / "convenios.json"
    if archivo.exists():
        guardados = json.loads(archivo.read_text(encoding="utf-8"))

    faltan = sorted(c for c in codigos if c and c not in guardados)
    if not faltan:
        return guardados

    ticket = os.environ.get("TICKET_MP", "").strip()
    if not ticket:
        local = Path.home() / "ticket-mp.txt"
        ticket = local.read_text(encoding="utf-8-sig").strip() if local.exists() else ""
    if not ticket:
        return guardados

    print(f"NOMBRES: preguntando por {len(faltan)} convenios", flush=True)
    for codigo in faltan:
        url = (f"https://api.mercadopublico.cl/servicios/v1/publico/"
               f"licitaciones.json?codigo={codigo}&ticket={ticket}")
        try:
            peticion = urllib.request.Request(url, headers={"User-Agent": "panel"})
            with urllib.request.urlopen(peticion, timeout=60) as respuesta:
                datos = json.loads(respuesta.read().decode("utf-8"))
            listado = datos.get("Listado") or []
            if listado:
                guardados[codigo] = str(listado[0].get("Nombre") or "").strip()
        except Exception:
            pass
        time.sleep(1)
    archivo.write_text(json.dumps(guardados, indent=1, ensure_ascii=False), encoding="utf-8")
    return guardados


def guardar(por_mes: dict[str, list[dict]]) -> None:
    """Escribe cada mes, mezclando con lo que ya hubiera y sin repetir lineas."""
    BODEGA.mkdir(exist_ok=True)
    for mes, filas in por_mes.items():
        nuevas = pd.DataFrame(filas, columns=COLUMNAS)
        for c in ("cantidad", "precio", "total"):
            nuevas[c] = pd.to_numeric(nuevas[c], errors="coerce")
        archivo = BODEGA / f"{mes}.parquet"
        if archivo.exists():
            nuevas = pd.concat([pd.read_parquet(archivo), nuevas], ignore_index=True)
        # Una linea es unica por orden + producto + correlativo de precio.
        nuevas = nuevas.drop_duplicates(
            subset=["orden", "id_producto", "producto", "cantidad", "precio"])
        nuevas.to_parquet(archivo, index=False, compression="zstd")


def meses_por_procesar(completo: bool) -> list[tuple[int, int]]:
    """Que meses bajar en esta corrida.

    La primera vez hay que bajarlos todos (~50 minutos). Despues basta el mes en
    curso y el anterior: los archivos se rehacen a diario, y una orden puede
    aparecer con retraso, pero no cambia meses hacia atras. Bajar los 20 cada
    noche serian 50 minutos para nada.
    """
    todos = list(meses_hasta_hoy())
    if completo or not any(BODEGA.glob("*.parquet")):
        return todos
    return todos[-2:]


def main() -> None:
    argumentos = argparse.ArgumentParser(description="Llena la bodega desde datos abiertos")
    argumentos.add_argument("--completo", action="store_true",
                            help="rehacer toda la historia, no solo los últimos meses")
    opciones = argumentos.parse_args()

    t0 = time.time()
    total = 0
    procesados = []
    pendientes = meses_por_procesar(opciones.completo)
    print(f"BODEGUERO · {len(pendientes)} mes/es por procesar\n", flush=True)
    for año, mes in pendientes:
        inicio = time.time()
        archivo = bajar(año, mes)
        if archivo is None:
            continue
        por_mes: dict[str, list[dict]] = {}
        n = 0
        for fila in filas_de_convenio_marco(archivo):
            por_mes.setdefault(fila["fecha"][:7], []).append(fila)
            n += 1
        guardar(por_mes)
        total += n
        procesados.append(f"{año}-{mes:02d}")
        print(f"  {año}-{mes:02d}: {n:>7,} líneas de Convenio Marco · "
              f"{archivo.stat().st_size/1e6:.0f} MB · {time.time()-inicio:.0f}s", flush=True)

    convenios = set()
    for archivo in BODEGA.glob("*.parquet"):
        convenios |= set(pd.read_parquet(archivo, columns=["convenio_marco"])["convenio_marco"])
    nombres = nombres_de_convenios(convenios)
    print(f"  convenios con nombre: {len(nombres)} de {len(convenios)}")

    for zip_viejo in DESCARGAS.glob("*.zip"):
        zip_viejo.unlink()          # pesan 100 MB cada uno, no se guardan

    peso = sum(p.stat().st_size for p in BODEGA.glob("*.parquet"))
    BODEGA.mkdir(exist_ok=True)
    (BODEGA / "estado.json").write_text(json.dumps({
        "fuente": "datos abiertos ChileCompra (oc-da)",
        "meses": procesados,
        "lineas": total,
        "actualizado": time.strftime("%Y-%m-%dT%H:%M:%S"),
    }, indent=1, ensure_ascii=False), encoding="utf-8")

    print()
    print(f"{'='*60}")
    print(f"  meses procesados : {len(procesados)}")
    print(f"  líneas guardadas : {total:,}")
    print(f"  peso de la bodega: {peso/1e6:.1f} MB")
    print(f"  tiempo total     : {(time.time()-t0)/60:.1f} minutos")


if __name__ == "__main__":
    main()
