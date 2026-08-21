"""
BODEGUERO — descarga Mercado Publico y lo guarda en la bodega
==============================================================

Corre de madrugada en GitHub Actions (ver .github/workflows/bodega.yml) y deja
los datos listos para que el Panel Oportunidades los consulte al instante, sin
tocar la API.

Dos capas, porque cuestan cosas muy distintas (medido el 17-08-2026):

  MAPA     El listado de un dia completo de Chile cuesta UNA consulta y trae
           ~16.000 ordenes (2.000 de Convenio Marco) con su codigo y estado.
           Del codigo sale la unidad compradora. 594 dias = 594 consultas.

  DETALLE  Los productos, precios y proveedores hay que pedirlos orden por
           orden: ~2.000 consultas por dia de calendario, a 1,16 s cada una
           (la API rechaza casi la mitad de las peticiones y hay que reintentar).

Por eso el mapa se completa en una noche y el detalle se va llenando de a poco,
empezando por lo mas reciente, que es lo que sirve para vender.

Se puede cortar en cualquier momento: `estado.json` recuerda que dias estan
listos y la corrida siguiente sigue donde quedo.

Uso:
    python bodeguero.py                 # respeta el presupuesto por defecto
    python bodeguero.py --consultas 500 # una corrida corta, para probar
"""

from __future__ import annotations

import argparse
import json
import os
import time
import urllib.error
import urllib.request
from datetime import date, datetime, timedelta
from pathlib import Path

import pandas as pd

API = "https://api.mercadopublico.cl/servicios/v1/publico/"
CARPETA = Path(__file__).parent
BODEGA = CARPETA / "bodega"
ESTADO = BODEGA / "estado.json"

# Desde donde se guarda historia. Antes de esto no se baja nada.
PRIMER_DIA = date(2025, 1, 1)

# El ticket permite 10.000 consultas al dia. Se deja un margen chico por si ella
# consulta desde la app mientras el bodeguero trabaja; mientras mas alto, antes
# se termina de llenar la bodega.
PRESUPUESTO = 9800

# Pausa entre consultas. Medido el 18-08: sin pausa la API rechaza el 34% de las
# peticiones y con 0,6 s baja al 22%, **sin que el tiempo por orden cambie**
# (1,15 s en ambos casos, porque cada rechazo obliga a reintentar). Si los
# rechazos consumen cupo del ticket, esto son ~15% mas ordenes por noche; si no
# lo consumen, no cuesta nada. Por eso conviene igual.
PAUSA_ENTRE_CONSULTAS = 0.6

# Tope de tiempo de una corrida. GitHub Actions corta a las 6 horas; se para
# antes para alcanzar a guardar.
HORAS_MAXIMO = 5.0


def ticket() -> str:
    """En GitHub viene del secreto TICKET_MP; en el PC, del archivo de siempre."""
    del_entorno = os.environ.get("TICKET_MP", "").strip()
    if del_entorno:
        return del_entorno
    local = Path.home() / "ticket-mp.txt"
    if local.exists():
        return local.read_text(encoding="utf-8-sig").strip()
    raise SystemExit("Falta el ticket: define TICKET_MP o deja ~/ticket-mp.txt")


class CuotaAgotada(Exception):
    """Se acabaron las consultas del dia. Hay que parar, no seguir intentando."""


class Contador:
    """Lleva la cuenta de lo gastado para no pasarse del presupuesto ni del reloj."""

    def __init__(self, presupuesto: int, horas: float):
        self.presupuesto = presupuesto
        self.horas = horas
        self.consultas = 0
        self.reintentos = 0
        self.inicio = time.time()

    @property
    def transcurrido(self) -> float:
        return time.time() - self.inicio

    def queda(self) -> bool:
        return (self.consultas < self.presupuesto
                and self.transcurrido < self.horas * 3600)

    def resumen(self) -> str:
        return (f"{self.consultas} consultas ({self.reintentos} reintentos) "
                f"en {self.transcurrido / 60:.1f} min")


def pedir(recurso: str, contador: Contador) -> dict | None:
    """Una consulta a la API, reintentando el 429.

    La URL lleva el ticket pegado, asi que nunca se imprime en los mensajes.
    """
    separador = "&" if "?" in recurso else "?"
    url = f"{API}{recurso}{separador}ticket={ticket()}"
    espera = 1.5
    for _ in range(6):
        try:
            peticion = urllib.request.Request(
                url, headers={"User-Agent": "panel-oportunidades"})
            with urllib.request.urlopen(peticion, timeout=120) as respuesta:
                contador.consultas += 1
                datos = json.loads(respuesta.read().decode("utf-8"))
            # La cuota agotada llega como HTTP 203 (un codigo de EXITO) con
            # {"Codigo":203,...}. Si no se detecta, el bodeguero cree que el dia
            # no tuvo ordenes, lo marca como listo y deja un hueco para siempre.
            if datos.get("Codigo") == 203 or ("Listado" not in datos and datos.get("Mensaje")):
                raise CuotaAgotada(str(datos.get("Mensaje") or "cuota diaria agotada"))
            time.sleep(PAUSA_ENTRE_CONSULTAS)
            return datos
        except CuotaAgotada:
            raise
        except urllib.error.HTTPError as error:
            contador.reintentos += 1
            if error.code not in (429, 500, 502, 503):
                print(f"    HTTP {error.code} en {recurso.split('?')[0]}", flush=True)
                return None
            time.sleep(espera)
            espera = min(espera * 2, 30)
        except Exception:
            contador.reintentos += 1
            time.sleep(espera)
            espera = min(espera * 2, 30)
    return None


def es_convenio_marco(codigo: str) -> bool:
    """«2950-485-CM26» si; «1002584-259-AG26» no."""
    tramos = str(codigo).split("-")
    return len(tramos) >= 3 and tramos[-1].strip().upper().startswith("CM")


def leer_estado() -> dict:
    if ESTADO.exists():
        return json.loads(ESTADO.read_text(encoding="utf-8"))
    return {"mapa": [], "detalle": [], "actualizado": None}


def guardar_estado(estado: dict) -> None:
    BODEGA.mkdir(exist_ok=True)
    estado["actualizado"] = datetime.now().isoformat(timespec="seconds")
    ESTADO.write_text(json.dumps(estado, indent=1, ensure_ascii=False), encoding="utf-8")


def guardar_mes(filas: list[dict], capa: str, mes: str) -> None:
    """Agrega filas al parquet del mes, reemplazando los dias que se reprocesan.

    Un archivo por mes porque un año entero pasa de los 100 MB que admite
    GitHub; por mes son ~10 MB.
    """
    if not filas:
        return
    carpeta = BODEGA / capa
    carpeta.mkdir(parents=True, exist_ok=True)
    archivo = carpeta / f"{mes}.parquet"

    nuevas = pd.DataFrame(filas)
    if archivo.exists():
        viejas = pd.read_parquet(archivo)
        nuevas = pd.concat([viejas[~viejas["dia"].isin(set(nuevas["dia"]))], nuevas],
                           ignore_index=True)
    nuevas.to_parquet(archivo, index=False, compression="zstd")


def bajar_mapa(dia: date, contador: Contador) -> list[dict] | None:
    """El listado de un dia: UNA consulta para todo Chile."""
    datos = pedir(f"ordenesdecompra.json?fecha={dia:%d%m%Y}", contador)
    if datos is None:
        return None
    filas = []
    for orden in datos.get("Listado") or []:
        codigo = str(orden.get("Codigo") or "")
        if not es_convenio_marco(codigo):
            continue
        filas.append({
            "dia": dia.isoformat(),
            "orden": codigo,
            "unidad": codigo.split("-")[0],
            "convenio": codigo.split("-")[-1].upper(),
            "estado_codigo": orden.get("CodigoEstado"),
        })
    return filas


def filas_de_orden(codigo: str, dia: date, orden: dict) -> list[dict]:
    """Una fila por producto comprado.

    Los nombres de unidad y organismo NO se guardan: ya viajan en
    catalogo_unidades.csv y repetirlos millones de veces engorda la bodega.
    """
    comprador = orden.get("Comprador") or {}
    proveedor = orden.get("Proveedor") or {}
    fechas = orden.get("Fechas") or {}
    comun = {
        "dia": dia.isoformat(),
        "fecha": (fechas.get("FechaCreacion") or "")[:10],
        "orden": codigo,
        "estado": str(orden.get("Estado") or "").strip(),
        "unidad": str(comprador.get("CodigoUnidad") or "").strip(),
        "organismo": str(comprador.get("CodigoOrganismo") or "").strip(),
        "convenio": codigo.split("-")[-1].upper(),
        "contacto": str(comprador.get("NombreContacto") or "").strip(),
        "proveedor": str(proveedor.get("Nombre") or "").strip(),
        "rut_proveedor": str(proveedor.get("RutSucursal") or "").strip(),
    }

    items = (orden.get("Items") or {}).get("Listado") or []
    if not items:
        return [comun | {"id_producto": "", "producto": "", "cantidad": None,
                         "precio": None, "total": orden.get("Total")}]

    filas = []
    for item in items:
        # El ID de Convenio Marco viene entre parentesis: «(4427537) GOMA...»
        especificacion = str(item.get("EspecificacionComprador") or "").lstrip()
        identificador = ""
        if especificacion.startswith("("):
            posible = especificacion[1:].split(")")[0]
            identificador = posible if posible.isdigit() else ""
        filas.append(comun | {
            "id_producto": identificador,
            "producto": str(item.get("Producto") or "").strip(),
            "cantidad": item.get("Cantidad"),
            "precio": item.get("PrecioNeto"),
            "total": item.get("Total"),
        })
    return filas


def bajar_detalle(dia: date, ordenes: list[str],
                  contador: Contador) -> tuple[list[dict], bool]:
    """El detalle de cada orden. Devuelve (filas, si alcanzo a terminar el dia)."""
    filas: list[dict] = []
    for codigo in ordenes:
        if not contador.queda():
            return filas, False
        datos = pedir(f"ordenesdecompra.json?codigo={codigo}", contador)
        listado = (datos or {}).get("Listado") or []
        if listado:
            filas.extend(filas_de_orden(codigo, dia, listado[0]))
    return filas, True


def unidades_conocidas() -> pd.DataFrame:
    """Las unidades cuyo nombre ya se averiguo."""
    archivo = BODEGA / "unidades.parquet"
    if archivo.exists():
        return pd.read_parquet(archivo)
    return pd.DataFrame(columns=["codigo_unidad", "nombre_unidad", "codigo_organismo",
                                 "nombre_organismo", "region", "comuna"])


def completar_nombres(mapa: pd.DataFrame, contador: Contador) -> int:
    """Averigua como se llama cada unidad nueva, con UNA consulta por unidad.

    El mapa trae solo el codigo de la unidad («2950»), pero para buscarla hay que
    saber que es la Escuela Naval. El nombre esta en el detalle de cualquiera de
    sus ordenes, asi que basta pedir una: 2.190 unidades nuevas son 2.190
    consultas, una noche, y despues no se vuelven a preguntar nunca.

    Se empieza por las que mas compran, que son las que ella va a buscar.
    """
    conocidas = unidades_conocidas()
    ya_estan = set(conocidas["codigo_unidad"])

    # Cuantas ordenes tiene cada unidad en toda la bodega: es la frecuencia real
    # de compra, medida sobre 594 dias y no sobre 8.
    frecuencia = mapa.groupby("unidad").size().sort_values(ascending=False)
    faltan = [u for u in frecuencia.index if u not in ya_estan]
    if not faltan:
        return 0

    print(f"NOMBRES: faltan {len(faltan)} unidades por identificar", flush=True)
    nuevas = []
    for unidad in faltan:
        if not contador.queda():
            break
        ordenes = mapa[mapa["unidad"] == unidad]["orden"]
        if ordenes.empty:
            continue
        datos = pedir(f"ordenesdecompra.json?codigo={ordenes.iloc[0]}", contador)
        listado = (datos or {}).get("Listado") or []
        if not listado:
            continue
        comprador = listado[0].get("Comprador") or {}
        nuevas.append({
            "codigo_unidad": unidad,
            "nombre_unidad": str(comprador.get("NombreUnidad") or "").strip(),
            "codigo_organismo": str(comprador.get("CodigoOrganismo") or "").strip(),
            "nombre_organismo": str(comprador.get("NombreOrganismo") or "").strip(),
            "region": str(comprador.get("RegionUnidad") or "").strip(),
            "comuna": str(comprador.get("ComunaUnidad") or "").strip(),
        })
        if len(nuevas) % 100 == 0:
            print(f"  {len(nuevas)} identificadas · {contador.resumen()}", flush=True)

    if nuevas:
        juntas = pd.concat([conocidas, pd.DataFrame(nuevas)], ignore_index=True)
        juntas = juntas.drop_duplicates("codigo_unidad", keep="last")
        juntas.to_parquet(BODEGA / "unidades.parquet", index=False, compression="zstd")
    return len(nuevas)


def dias_por_llenar(listos: list[str], hasta: date) -> list[date]:
    """Los dias que faltan, del mas reciente al mas antiguo.

    Lo reciente primero porque es lo que sirve para vender: el mes pasado
    importa mucho mas que enero de 2025.
    """
    hechos = set(listos)
    faltan = []
    dia = hasta
    while dia >= PRIMER_DIA:
        if dia.isoformat() not in hechos:
            faltan.append(dia)
        dia -= timedelta(days=1)
    return faltan


def main() -> None:
    try:
        llenar()
    except CuotaAgotada as fin:
        # No es un fallo: es el techo del ticket. Lo que alcanzo a bajar ya
        # quedo guardado, y manana sigue donde quedo.
        print(f"\nSE ACABÓ LA CUOTA DEL DÍA ({fin}). Lo descargado quedó guardado.")


def llenar() -> None:
    argumentos = argparse.ArgumentParser(description="Llena la bodega de Mercado Publico")
    argumentos.add_argument("--consultas", type=int, default=PRESUPUESTO,
                            help="tope de consultas de esta corrida")
    argumentos.add_argument("--horas", type=float, default=HORAS_MAXIMO)
    argumentos.add_argument("--refrescar", type=int, default=7,
                            help="dias recientes que se vuelven a bajar (llegan tarde)")
    opciones = argumentos.parse_args()

    contador = Contador(opciones.consultas, opciones.horas)
    estado = leer_estado()
    hoy = date.today()
    print(f"BODEGUERO · {datetime.now():%d-%m-%Y %H:%M} · "
          f"presupuesto {opciones.consultas} consultas")
    print(f"bodega al empezar: mapa {len(estado['mapa'])} días · "
          f"detalle {len(estado['detalle'])} días\n", flush=True)

    # Los ultimos dias se vuelven a bajar siempre: una orden puede aparecer en la
    # API varios dias despues de emitida (la API lista por dia de movimiento).
    recientes = {(hoy - timedelta(days=n)).isoformat() for n in range(opciones.refrescar)}

    # --- 1. El mapa: barato, se completa primero ---------------------------
    faltan_mapa = dias_por_llenar([d for d in estado["mapa"] if d not in recientes], hoy)
    print(f"MAPA: faltan {len(faltan_mapa)} días", flush=True)
    pendientes: dict[str, list[dict]] = {}
    for dia in faltan_mapa:
        if not contador.queda():
            break
        filas = bajar_mapa(dia, contador)
        if filas is None:
            continue
        pendientes.setdefault(f"{dia:%Y-%m}", []).extend(filas)
        if dia.isoformat() not in estado["mapa"]:
            estado["mapa"].append(dia.isoformat())
        if len(pendientes) > 2:            # se guarda de a poco, por si se corta
            for mes, filas_mes in pendientes.items():
                guardar_mes(filas_mes, "mapa", mes)
            pendientes = {}
            guardar_estado(estado)
    for mes, filas_mes in pendientes.items():
        guardar_mes(filas_mes, "mapa", mes)
    guardar_estado(estado)
    print(f"  mapa: {len(estado['mapa'])} días listos · {contador.resumen()}\n", flush=True)

    # --- 2. Los nombres de las unidades: una consulta por unidad, una vez --
    archivos_mapa = sorted((BODEGA / "mapa").glob("*.parquet"))
    if archivos_mapa and contador.queda():
        todo_el_mapa = pd.concat([pd.read_parquet(a) for a in archivos_mapa],
                                 ignore_index=True)
        identificadas = completar_nombres(todo_el_mapa, contador)
        if identificadas:
            print(f"  {identificadas} unidades identificadas · {contador.resumen()}\n",
                  flush=True)

    # --- 3. El detalle: caro, se llena de a poco ---------------------------
    faltan_detalle = dias_por_llenar([d for d in estado["detalle"] if d not in recientes], hoy)
    print(f"DETALLE: faltan {len(faltan_detalle)} días (se empieza por el más reciente)",
          flush=True)
    for dia in faltan_detalle:
        if not contador.queda():
            print("  se acabó el presupuesto de esta corrida", flush=True)
            break
        mes = f"{dia:%Y-%m}"
        archivo_mapa = BODEGA / "mapa" / f"{mes}.parquet"
        if not archivo_mapa.exists():
            continue
        mapa = pd.read_parquet(archivo_mapa)
        ordenes = sorted(mapa[mapa["dia"] == dia.isoformat()]["orden"].unique())
        if not ordenes:
            if dia.isoformat() not in estado["detalle"]:
                estado["detalle"].append(dia.isoformat())
            continue

        filas, completo = bajar_detalle(dia, ordenes, contador)
        guardar_mes(filas, "detalle", mes)
        if completo:
            if dia.isoformat() not in estado["detalle"]:
                estado["detalle"].append(dia.isoformat())
            print(f"  {dia:%d-%m-%Y}: {len(ordenes)} órdenes, {len(filas)} líneas · "
                  f"{contador.resumen()}", flush=True)
        guardar_estado(estado)
        if not completo:
            break

    print(f"\nFIN · {contador.resumen()}")
    print(f"bodega: mapa {len(estado['mapa'])} días · detalle {len(estado['detalle'])} días")


if __name__ == "__main__":
    main()
