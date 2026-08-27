"""
ALERTADOR — el correo diario de oportunidades
==============================================

Junta lo que se publico hoy (licitaciones y compras agiles), se queda con lo
que le sirve a cada suscriptor, le pega encima lo que la bodega sabe del
comprador, y lo manda por correo.

LO QUE LO HACE DISTINTO DE PIAM
-------------------------------
Ellos avisan de que salio una licitacion que suena a lo tuyo. Aca, ademas, va
lo que ningun buscador de palabras puede saber: cuanto gasta ESE comprador en
lo que tu vendes, quien se lo esta llevando hoy y con que porcentaje. Eso sale
de cruzar la licitacion contra el millon y medio de lineas de orden de compra
que el bodeguero ya bajo.

LAS TRES MANERAS DE DECIR «ESTO ME SIRVE»
-----------------------------------------
1. Por RUT       el cliente escribe su RUT y las palabras salen solas de lo
                 que el mismo ha vendido en Convenio Marco. Cero configuracion.
2. Por rubro     se eligen rubros del catalogo (los que trae la propia
                 licitacion en `codigo_onu` y `rubro1`).
3. Por palabras  se escriben a mano. Es la salida para quien no quiere dar su
                 RUT, o para quien no tiene Convenio Marco registrado y por
                 lo tanto el RUT no diria nada.

Las tres terminan en la misma bolsa de terminos. El RUT no es otro sistema:
es un atajo que rellena la bolsa sin preguntar nada.

DOS FUENTES, DOS APIS DISTINTAS
-------------------------------
  v1  licitaciones.json?estado=activas    ticket en la URL, 2 s entre consultas
  v2  api2.mercadopublico.cl/v2/compra-agil  ticket en una CABECERA

`lic-da` (los datos abiertos) NO sirve para avisar: solo publica licitaciones
cuyo plazo ya cerro. Sirve de historial, y de eso vive el modo de prueba.

COMO SE PRUEBA SIN GASTAR EL TICKET
-----------------------------------
    python alertador.py --prueba --guardar correo.html

Toma las licitaciones mas nuevas de la bodega y las trata como si se hubieran
publicado hoy. Sirve para ver el correo de verdad, con datos de verdad, sin
tocar la API ni enviar nada.

PARA ENVIAR DE VERDAD
---------------------
    python alertador.py --enviar

Necesita en el entorno: TICKET_MP, RESEND_API_KEY y, si la configuracion vive
en Supabase, SUPABASE_URL y SUPABASE_SECRET_KEY.
"""
import argparse
import json
import os
import re
import sys
import time
import unicodedata
import urllib.error
import urllib.parse
import urllib.request
from datetime import date, datetime, timedelta
from pathlib import Path

import pandas as pd

import ficha_licitacion

# Este archivo tambien se importa desde la app (la pestana «Alertas»), y ahi
# la salida no siempre es una consola que admita reconfigurarse. Si reventara,
# se caeria la app entera por un detalle de impresion.
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

AQUI = Path(__file__).parent
BODEGA_OC = AQUI / "bodega" / "detalle"
BODEGA_LIC = AQUI / "bodega" / "licitaciones"
CONFIG_LOCAL = AQUI / "alertas_config.json"

V1 = "https://api.mercadopublico.cl/servicios/v1/publico/licitaciones.json"
V2 = "https://api2.mercadopublico.cl/v2/compra-agil"
ESPERA_V1 = 2.0

# Resend en plan gratis: 100 correos al dia. Al 101 se cae el envio, asi que
# el tope se respeta desde aca y no se descubre a mitad de la tanda.
TOPE_DIARIO = 100
MAXIMO_POR_CORREO = 15
# La paleta es la de uplevelweb.art, no la del documento de cierre: ahi quedo
# anotada una que el sitio no usa.
MARINO = "#0c2c57"
MARINO_OSCURO = "#081f3e"
NARANJO = "#f18c3f"
TEXTO = "#2c3e50"
TEXTO_SUAVE = "#6b7c8f"
BORDE = "#e1e8ed"
FONDO = "#f5f7fa"
LOGO = "https://uplevelweb.art/img/logo.png"

# Palabras que aparecen en todas las licitaciones y no distinguen nada.
VACIAS = {
    "de", "del", "la", "las", "el", "los", "y", "o", "para", "por", "con", "sin",
    "un", "una", "unos", "unas", "al", "en", "a", "su", "sus", "se", "que",
    "servicio", "servicios", "suministro", "adquisicion", "compra", "contratacion",
    "licitacion", "publica", "publico", "bienes", "varios", "otros", "general",
    "ano", "anos", "mes", "meses", "region", "regional", "comunal", "municipal",
    "hospital", "establecimiento", "unidad", "departamento", "direccion",
    "unidad", "caja", "unidades", "kit", "set", "tipo", "marca", "modelo",
}


# ======================================================================
#  UTILIDADES
# ======================================================================

def sin_tildes(texto: str) -> str:
    """«Alimentación» -> «alimentacion». Comparar con tildes falla siempre."""
    limpio = unicodedata.normalize("NFD", str(texto or ""))
    return "".join(c for c in limpio if unicodedata.category(c) != "Mn").lower()


def palabras(texto: str) -> set[str]:
    """Las palabras utiles de un texto, sin tildes y sin las de relleno."""
    trozos = re.findall(r"[a-z0-9]+", sin_tildes(texto))
    return {t for t in trozos if len(t) >= 4 and t not in VACIAS}


def solo_digitos_rut(rut: str) -> str:
    """«77.082.051-0» y «770820510» terminan igual: «770820510»."""
    return re.sub(r"[^0-9kK]", "", str(rut or "")).upper()


def plata(monto) -> str:
    """1234567 -> «$1.234.567». Los millones se acortan para que quepan."""
    try:
        n = float(monto)
    except (TypeError, ValueError):
        return "sin dato"
    if n <= 0:
        return "sin dato"
    if n >= 1_000_000_000:
        return f"${n/1_000_000_000:,.1f}".replace(",", ".") + " mil M"
    if n >= 1_000_000:
        return f"${n/1_000_000:,.0f}".replace(",", ".") + " M"
    return "$" + f"{n:,.0f}".replace(",", ".")


def minimo_coincidencias(bolsa: set[str]) -> int:
    """
    Cuantas palabras tienen que coincidir para que valga la pena avisar.

    NO ES UN NUMERO FIJO, y el 27-08-2026 se aprendio por que. Estaba en 3
    para todos, calibrado con el RUT: de ahi salen ~87 terminos sacados
    automaticamente de lo que ese proveedor vendio, muchos de relleno, y
    exigir 3 filtra bien el ruido.

    Pero con palabras escritas a mano el mismo 3 mata todo: dos suscriptoras
    con 5 y 6 palabras se quedaron en 3 y 5 terminos utiles, y para pasar el
    corte habrian necesitado que casi TODAS sus palabras aparecieran en la
    misma licitacion. Cero correos, dos dias seguidos, sin ningun error.

    La diferencia de fondo: una palabra que alguien se tomo el trabajo de
    escribir vale mucho mas que una sacada a la fuerza de un catalogo.
    """
    if len(bolsa) <= 10:
        return 1
    if len(bolsa) <= 30:
        return 2
    return 3


# ======================================================================
#  CONFIGURACION
# ======================================================================

def configuracion() -> list[dict]:
    """
    De donde salen los suscriptores y sus filtros.

    Primero Supabase, si estan las credenciales en el entorno; si no, el
    archivo local. El archivo local NO va al repositorio: el repositorio es
    publico y ahi no puede haber ni un correo de cliente.
    """
    url = os.environ.get("SUPABASE_URL", "").strip()
    clave = os.environ.get("SUPABASE_SECRET_KEY", "").strip()

    if url and clave:
        return _configuracion_supabase(url, clave)

    if CONFIG_LOCAL.exists():
        datos = json.loads(CONFIG_LOCAL.read_text(encoding="utf-8"))
        return datos.get("suscriptores", [])

    print(f"No hay configuracion. Falta {CONFIG_LOCAL.name} o las claves de Supabase.")
    return []


def _configuracion_supabase(url: str, clave: str) -> list[dict]:
    """Los suscriptores activos con sus filtros, en una sola consulta."""
    consulta = (
        f"{url}/rest/v1/suscriptores"
        "?select=id,email,nombre,empresa,rut_empresa,token_baja,fecha_consentimiento,"
        "filtros(rubros,regiones,monto_minimo,frecuencia,rut_proveedor,palabras_clave,"
        "correos_envio,hora_envio,incluye_licitaciones,incluye_compras_agiles)"
        "&activo=eq.true"
    )
    peticion = urllib.request.Request(consulta, headers={
        "apikey": clave,
        "Authorization": f"Bearer {clave}",
        "Accept": "application/json",
    })
    with urllib.request.urlopen(peticion, timeout=60) as respuesta:
        filas = json.loads(respuesta.read().decode("utf-8"))

    salida = []
    for fila in filas:
        f = (fila.get("filtros") or [{}])
        f = f[0] if isinstance(f, list) and f else (f if isinstance(f, dict) else {})
        salida.append({
            "id": fila.get("id"),
            "email": fila.get("email"),
            "nombre": fila.get("nombre"),
            "rut_empresa": fila.get("rut_empresa"),
            "token_baja": fila.get("token_baja"),
            "fecha_consentimiento": (fila.get("fecha_consentimiento") or "")[:10],
            "rut_proveedor": f.get("rut_proveedor") or "",
            "correos_envio": f.get("correos_envio") or [],
            "hora_envio": int(f.get("hora_envio") or 8),
            "rubros": f.get("rubros") or [],
            "palabras_clave": f.get("palabras_clave") or [],
            "regiones": f.get("regiones") or [],
            "monto_minimo": int(f.get("monto_minimo") or 0),
            "incluye_licitaciones": f.get("incluye_licitaciones", True),
            "incluye_compras_agiles": f.get("incluye_compras_agiles", True),
        })
    return salida


# ======================================================================
#  MEMORIA DE LO YA AVISADO
# ======================================================================
#
# Una licitacion abierta sigue abierta una o dos semanas. Sin memoria, el
# correo de manana repetiria las mismas de hoy, y el de pasado tambien: en
# tres dias el suscriptor se da de baja. Por eso se anota lo enviado y no se
# vuelve a mandar.

ENVIADOS_LOCAL = AQUI / "envios_enviados.json"


def ya_avisado(suscriptor: dict) -> set[str]:
    """Los codigos que esa persona ya recibio alguna vez."""
    url = os.environ.get("SUPABASE_URL", "").strip()
    clave = os.environ.get("SUPABASE_SECRET_KEY", "").strip()

    if url and clave and suscriptor.get("id"):
        consulta = (f"{url}/rest/v1/envios?select=codigo_licitacion"
                    f"&suscriptor_id=eq.{suscriptor['id']}")
        peticion = urllib.request.Request(consulta, headers={
            "apikey": clave, "Authorization": f"Bearer {clave}", "Accept": "application/json"})
        try:
            with urllib.request.urlopen(peticion, timeout=60) as respuesta:
                filas = json.loads(respuesta.read().decode("utf-8"))
            return {str(f.get("codigo_licitacion")) for f in filas}
        except Exception as error:
            # Si no se puede leer, es mejor no enviar que enviar repetido.
            print(f"   no se pudo leer lo ya enviado: {type(error).__name__}")
            return set()

    if ENVIADOS_LOCAL.exists():
        datos = json.loads(ENVIADOS_LOCAL.read_text(encoding="utf-8"))
        return set(datos.get(suscriptor.get("email", ""), []))
    return set()


def anotar_avisado(suscriptor: dict, codigos: list[str], tipos: list[str]) -> None:
    """Deja constancia de lo que SI salio. Solo se llama tras enviar."""
    url = os.environ.get("SUPABASE_URL", "").strip()
    clave = os.environ.get("SUPABASE_SECRET_KEY", "").strip()

    if url and clave and suscriptor.get("id"):
        cuerpo = json.dumps([
            {"suscriptor_id": suscriptor["id"], "codigo_licitacion": c, "tipo": t}
            for c, t in zip(codigos, tipos)
        ]).encode("utf-8")
        peticion = urllib.request.Request(
            f"{url}/rest/v1/envios", data=cuerpo, method="POST",
            headers={"apikey": clave, "Authorization": f"Bearer {clave}",
                     "Content-Type": "application/json",
                     # Si alguno ya estaba, que no reviente la tanda entera.
                     "Prefer": "resolution=ignore-duplicates"})
        try:
            urllib.request.urlopen(peticion, timeout=60).read()
        except Exception as error:
            print(f"   no se pudo anotar el envio: {type(error).__name__}")
        return

    datos = {}
    if ENVIADOS_LOCAL.exists():
        datos = json.loads(ENVIADOS_LOCAL.read_text(encoding="utf-8"))
    correo = suscriptor.get("email", "")
    datos[correo] = sorted(set(datos.get(correo, [])) | set(codigos))
    ENVIADOS_LOCAL.write_text(json.dumps(datos, ensure_ascii=False, indent=1), encoding="utf-8")


# ======================================================================
#  LA BOLSA DE TERMINOS DE CADA SUSCRIPTOR
# ======================================================================

def productos_del_rut(objetivo: str, meses: int = 24) -> pd.DataFrame:
    """
    Lo que ese RUT ha vendido, leido del disco archivo por archivo.

    POR QUE NO SALE DE LA TABLA YA CARGADA: `producto` pesa 570 MB sobre la
    bodega completa —1.095.495 textos distintos, casi ninguno repetido— y de
    todos ellos se usan los de UN proveedor, unos pocos miles. Tener los ocho
    millones en memoria para leer nueve mil es lo que dejaba la app al borde
    del limite de Streamlit.

    Asi se lee un mes a la vez, se filtra y se suelta: el peor momento son los
    ~28 MB de un solo archivo, no los 570 de todos.
    """
    if not objetivo or not BODEGA_OC.exists():
        return pd.DataFrame(columns=["producto", "total", "convenio_marco"])

    corte = (date.today() - timedelta(days=meses * 31)).strftime("%Y-%m")
    trozos = []
    for archivo in sorted(BODEGA_OC.glob("*.parquet")):
        if archivo.stem < corte:
            continue
        try:
            mes = pd.read_parquet(archivo, columns=["rut_proveedor", "producto",
                                                    "total", "convenio_marco"])
        except Exception:
            continue
        mias = mes[mes["rut_proveedor"].astype(str).map(solo_digitos_rut) == objetivo]
        if not mias.empty:
            trozos.append(mias[["producto", "total", "convenio_marco"]])
        del mes
    if not trozos:
        return pd.DataFrame(columns=["producto", "total", "convenio_marco"])
    juntas = pd.concat(trozos, ignore_index=True)
    juntas["total"] = pd.to_numeric(juntas["total"], errors="coerce").fillna(0.0)
    return juntas


def terminos_del_rut(rut: str, oc: pd.DataFrame) -> tuple[set[str], list[str]]:
    """
    Las palabras que describen lo que ese RUT vende, sacadas de sus propias
    ordenes de compra. Devuelve tambien sus convenios marco.

    Si el RUT no aparece en la bodega —porque no tiene Convenio Marco
    registrado— vuelve vacio, y entonces manda lo que el cliente haya escrito
    a mano. Es el caso que hay que tener previsto: el RUT solo no basta.
    """
    objetivo = solo_digitos_rut(rut)
    if not objetivo or oc.empty:
        return set(), []

    mias = productos_del_rut(objetivo)
    if mias.empty:
        return set(), []

    convenios = sorted(c for c in mias["convenio_marco"].dropna().unique() if c)

    # Se miran los productos mas vendidos, no todos: la cola larga mete ruido.
    top = (mias.groupby("producto", observed=True)["total"].sum()
           .sort_values(ascending=False).head(200).index)

    # Y de esos, solo las palabras que se repiten en VARIOS productos. Una
    # palabra que sale en un solo producto describe ese producto, no el
    # negocio: asi entraba «cctv» por una compra suelta y despues hacia
    # coincidir licitaciones de camaras del Metro.
    veces: dict[str, int] = {}
    for producto in top:
        for termino in palabras(producto):
            veces[termino] = veces.get(termino, 0) + 1

    bolsa = {t for t, n in veces.items() if n >= 3}
    return bolsa, list(convenios)


def quitar_palabras_de_todos(bolsa: set[str], universo: list[dict], techo: float = 0.12) -> set[str]:
    """
    Saca de la bolsa las palabras que aparecen en casi todo.

    Sin esto pasa lo que se vio en la primera prueba: «produccion», «apoyo» o
    «comunal» estan en el catalogo de cualquier proveedor Y en media plaza de
    licitaciones, asi que hacen coincidir cosas que no tienen nada que ver.
    Una palabra que sale en mas del 12% de lo publicado no distingue nada.
    """
    # Con una bolsa chica hay que dejarla entera: si alguien escribio cinco
    # palabras, esas cinco son las que le importan. Sacarle las «comunes»
    # —que es lo correcto con una bolsa de 87 sacada del RUT— aca la deja en
    # nada. A una suscriptora le quitaba la mitad.
    if not universo or len(bolsa) <= 15:
        return bolsa
    veces: dict[str, int] = {}
    for op in universo:
        for termino in palabras(f"{op['nombre']} {op['descripcion']}") & bolsa:
            veces[termino] = veces.get(termino, 0) + 1
    limite = max(2, int(len(universo) * techo))
    return {t for t in bolsa if veces.get(t, 0) <= limite}


def bolsa_de_terminos(suscriptor: dict, oc: pd.DataFrame) -> tuple[set[str], list[str], str]:
    """
    Junta las tres maneras en una sola bolsa.
    Devuelve (terminos, convenios, de donde salieron) para poder explicarlo.
    """
    bolsa: set[str] = set()
    convenios: list[str] = []
    origen = []

    if suscriptor.get("rut_proveedor"):
        del_rut, convenios = terminos_del_rut(suscriptor["rut_proveedor"], oc)
        if del_rut:
            bolsa |= del_rut
            origen.append(f"RUT ({len(convenios)} convenios)")

    for rubro in suscriptor.get("rubros") or []:
        bolsa |= palabras(rubro)
    if suscriptor.get("rubros"):
        origen.append(f"{len(suscriptor['rubros'])} rubros")

    for clave in suscriptor.get("palabras_clave") or []:
        bolsa |= palabras(clave)
    if suscriptor.get("palabras_clave"):
        origen.append(f"{len(suscriptor['palabras_clave'])} palabras")

    return bolsa, convenios, " + ".join(origen) if origen else "sin filtro"


# ======================================================================
#  LA BODEGA DE ORDENES DE COMPRA (para enriquecer)
# ======================================================================

# Las columnas de texto se guardan como «categoria»: el nombre de cada
# proveedor aparece una sola vez y las filas apuntan a el.
#
# Medido el 27-08-2026 sobre la bodega real: 1.216.263 filas pero solo 1.291
# proveedores distintos y 4.212 unidades. Guardando el texto completo en cada
# fila la tabla ocupa 198 MB; guardandolo una vez, 32 MB. Seis veces menos,
# y sin perder un dato.
#
# Esto es lo que hace posible ampliar la bodega mas alla de Convenio Marco:
# con 5,6 veces mas filas seguiria por debajo de lo que ocupa hoy.
# «producto» NO va en esta lista, y es a proposito: tiene 1.095.495 valores
# distintos entre 1,5 millones de filas, o sea que casi ninguno se repite.
# Comprimirlo no ahorra nada y encima cuesta. Se lee aparte, solo para el RUT
# que se esta mirando (ver `productos_del_rut`).
COLUMNAS_REPETIDAS = ["unidad", "organismo", "mecanismo", "convenio", "convenio_marco",
                      "estado", "dia", "fecha", "rut_proveedor", "proveedor",
                      "id_producto", "rut_limpio"]


def comprimir_textos(tabla):
    """Deja las columnas de texto repetido como categoria. Ver arriba el porque."""
    for columna in COLUMNAS_REPETIDAS:
        if columna in tabla.columns:
            tabla[columna] = tabla[columna].astype("category")
    return tabla


def cargar_ordenes(meses: int = 24) -> pd.DataFrame:
    """
    Solo las columnas que hacen falta. Cargar las 16 de los 25 archivos se
    demora y no aporta: para enriquecer basta con quien compro, a quien y
    cuanto.
    """
    if not BODEGA_OC.exists():
        return pd.DataFrame()

    corte = (date.today() - timedelta(days=meses * 31)).strftime("%Y-%m")
    # «producto» NO se carga: son 8 millones de textos casi todos distintos,
    # y se usan solo para UN rut a la vez. Ver `productos_del_rut`.
    columnas = ["fecha", "unidad", "organismo", "mecanismo", "convenio_marco",
                "proveedor", "rut_proveedor", "total"]

    partes = []
    for archivo in sorted(BODEGA_OC.glob("*.parquet")):
        if archivo.stem < corte:
            continue
        try:
            # Se piden solo las columnas que ese archivo TIENE. Pedir una que
            # no esta hace reventar la lectura entera, y la bodega cambia de
            # forma cada vez que se le agrega algo: el 27-08-2026 se le sumo
            # `mecanismo` y los archivos viejos no lo traen. Un archivo con
            # una columna de menos no puede dejar la app sin datos.
            hay = set(pd.read_parquet(archivo, columns=[]).columns) or None
            if hay is None:
                import pyarrow.parquet as pq
                hay = set(pq.read_schema(archivo).names)
            partes.append(pd.read_parquet(archivo, columns=[c for c in columnas if c in hay]))
        except Exception as error:
            print(f"  no se pudo leer {archivo.name}: {type(error).__name__}")

    if not partes:
        return pd.DataFrame()

    oc = pd.concat(partes, ignore_index=True)
    oc["unidad"] = oc["unidad"].astype(str)
    # El rut limpio se calcula ANTES de comprimir, sobre texto normal, y
    # despues se comprime igual que los demas: son 1.291 valores distintos
    # repetidos 1,2 millones de veces, como el resto.
    oc["rut_limpio"] = oc["rut_proveedor"].astype(str).map(solo_digitos_rut)
    oc["total"] = pd.to_numeric(oc["total"], errors="coerce").fillna(0.0)
    return comprimir_textos(oc)


VIAS = {
    "SE": "Licitaciones",
    "TD": "Trato directo",
    "AG": "Compras ágiles",
    "CM": "Convenio Marco",
    "CC": "Convenios",
    "CT": "Contratos",
}


def radiografia_de_unidades(unidades: set[str], bolsa: set[str],
                            meses: int = 12) -> dict:
    """
    Todo lo que la bodega sabe de esos compradores, EN LOS RUBROS del
    suscriptor: cuanto compran, por que via, y quienes se lo estan llevando.

    Una sola pasada por los archivos para las ~15 oportunidades del correo.
    Leer `producto` es lo caro —570 MB sobre la bodega entera— asi que se
    hace una vez y se saca todo de ahi.

    POR QUE «EN SUS RUBROS» Y NO EL TOTAL DEL COMPRADOR: una municipalidad
    mueve $900 M al año, pero ahi adentro va combustible, asfalto y
    ambulancias. Mostrarle ese numero a un proveedor de alimentos es venderle
    humo: cuando descubra que en alimentos son $50 M se siente engañado.

    Devuelve, por unidad:
      via         {mecanismo: monto}   como compra
      proveedores [(nombre, monto)]    quienes se lo llevan hoy, de mayor a menor
      rubro       {palabra: monto}     en que se le va la plata dentro del rubro
      total       float
    """
    if not unidades or not bolsa or not BODEGA_OC.exists():
        return {}

    corte = (date.today() - timedelta(days=meses * 31)).strftime("%Y-%m")
    via: dict[str, dict[str, float]] = {}
    prov: dict[str, dict[str, float]] = {}
    rubro: dict[str, dict[str, float]] = {}

    for archivo in sorted(BODEGA_OC.glob("*.parquet")):
        if archivo.stem < corte:
            continue
        try:
            # Igual que en `cargar_ordenes`: se piden solo las columnas que ese
            # archivo tiene. Un parquet viejo sin `mecanismo` hacia fallar la
            # lectura entera y el correo salia sin el desglose, en silencio.
            import pyarrow.parquet as pq
            hay = set(pq.read_schema(archivo).names)
            pedidas = [c for c in ("unidad", "mecanismo", "proveedor", "producto", "total")
                       if c in hay]
            if "producto" not in pedidas or "total" not in pedidas:
                continue
            mes = pd.read_parquet(archivo, columns=pedidas)
            if "mecanismo" not in mes.columns:
                # Los archivos viejos guardaban solo Convenio Marco.
                mes["mecanismo"] = "CM"
        except Exception:
            continue
        mes = mes[mes["unidad"].astype(str).isin(unidades)]
        if mes.empty:
            del mes
            continue

        # Que palabras de la bolsa toca cada linea. Se calcula una vez y sirve
        # tanto para filtrar como para saber en que rubro cae el gasto.
        #
        # 27-08-2026: se exige el MISMO minimo que para avisar, no una palabra
        # suelta. Con una sola, la bolsa de 100 terminos que sale del RUT de
        # Emergenza —donde hay «agua», «blanca», «chile», «barra»— hacia entrar
        # factor antihemofilico, 90 camionetas y la normalizacion de un
        # hospital. Medido sobre mayo-agosto 2026: $572.293 M con una palabra
        # contra $51.081 M con tres. Once veces inflado, y era el numero de
        # «CUANTO COMPRA en tus rubros» del correo: exactamente el humo que la
        # tarjeta se diseño para no vender.
        minimo = minimo_coincidencias(bolsa)
        tocadas = mes["producto"].astype(str).map(lambda x: palabras(x) & bolsa)
        suficientes = tocadas.map(len) >= minimo
        mes = mes[suficientes]
        if mes.empty:
            del mes, tocadas, suficientes
            continue
        tocadas = tocadas[suficientes]
        mes["total"] = pd.to_numeric(mes["total"], errors="coerce").fillna(0.0)

        for (u, m), monto in mes.groupby(["unidad", "mecanismo"], observed=True)["total"].sum().items():
            via.setdefault(str(u), {})[str(m)] = via.get(str(u), {}).get(str(m), 0.0) + float(monto)
        for (u, pr), monto in mes.groupby(["unidad", "proveedor"], observed=True)["total"].sum().items():
            prov.setdefault(str(u), {})
            prov[str(u)][str(pr)] = prov[str(u)].get(str(pr), 0.0) + float(monto)
        for unidad, terminos, monto in zip(mes["unidad"].astype(str), tocadas, mes["total"]):
            reparto = float(monto) / max(len(terminos), 1)
            rubro.setdefault(unidad, {})
            for palabra in terminos:
                rubro[unidad][palabra] = rubro[unidad].get(palabra, 0.0) + reparto
        del mes, tocadas, suficientes

    salida = {}
    for u in unidades:
        u = str(u)
        proveedores = sorted(prov.get(u, {}).items(), key=lambda x: -x[1])
        salida[u] = {
            "via": via.get(u, {}),
            "proveedores": proveedores[:10],
            "rubro": dict(sorted(rubro.get(u, {}).items(), key=lambda x: -x[1])[:6]),
            "total": sum(via.get(u, {}).values()),
        }
    return salida


def retrato_del_comprador(unidad: str, oc: pd.DataFrame, convenios: list[str]) -> dict:
    """
    Lo que la bodega sabe de esa unidad compradora. Esto es lo que ningun
    competidor puede poner en el correo.
    """
    vacio = {"gasto": 0.0, "lider": "", "share": 0.0, "n_proveedores": 0, "ordenes": 0}
    if oc.empty or not unidad:
        return vacio

    suyas = oc[oc["unidad"] == str(unidad)]
    # Si el suscriptor tiene convenios propios, se mira solo ese mercado:
    # comparar contra todo lo que compra un hospital no dice nada util.
    if convenios:
        acotadas = suyas[suyas["convenio_marco"].isin(convenios)]
        if not acotadas.empty:
            suyas = acotadas
    if suyas.empty:
        return vacio

    gasto = float(suyas["total"].sum())
    por_proveedor = (suyas.groupby("proveedor", observed=True)["total"].sum()
                     .sort_values(ascending=False))
    lider = str(por_proveedor.index[0]) if len(por_proveedor) else ""
    share = float(por_proveedor.iloc[0] / gasto * 100) if gasto > 0 else 0.0

    return {
        "gasto": gasto,
        "lider": lider,
        "share": share,
        "n_proveedores": int(por_proveedor.shape[0]),
        "ordenes": int(suyas.shape[0]),
    }


def nota(retrato: dict) -> tuple[int, str]:
    """
    POTENCIAL x ATACABILIDAD / 100, como quedo definido en la especificacion.

    POTENCIAL     = tamano del premio (el monto, en logaritmo: si no, un solo
                    comprador enorme aplasta a todos los demas).
    ATACABILIDAD  = lo repartido que esta hoy. Si el lider tiene el 90%, entrar
                    cuesta; si tiene el 15%, el mercado esta abierto.
    """
    gasto = retrato["gasto"]
    if gasto <= 0:
        return 0, "D"

    import math
    # $1.000 M se toma como techo: de ahi para arriba ya es «muy grande».
    potencial = min(100.0, math.log10(max(gasto, 1)) / math.log10(1_000_000_000) * 100)

    fragmentacion = max(0.0, 100.0 - retrato["share"])
    diversidad = min(100.0, retrato["n_proveedores"] / 20 * 100)
    atacabilidad = fragmentacion * 0.65 + diversidad * 0.35

    valor = int(round(potencial * atacabilidad / 100))
    clase = "A" if valor >= 70 else "B" if valor >= 45 else "C" if valor >= 25 else "D"
    return valor, clase


# ======================================================================
#  LAS FUENTES DE LO QUE SE PUBLICO HOY
# ======================================================================

def _pedir(url: str, cabeceras: dict | None = None):
    peticion = urllib.request.Request(url, headers={
        "User-Agent": "Uplevel-Inteligencia/1.0",
        "Accept": "application/json",
        **(cabeceras or {}),
    })
    try:
        with urllib.request.urlopen(peticion, timeout=120) as respuesta:
            return json.loads(respuesta.read().decode("utf-8", errors="replace"))
    except urllib.error.HTTPError as error:
        cuerpo = error.read().decode("utf-8", errors="replace")[:200]
        print(f"  HTTP {error.code}: {cuerpo}")
        return None
    except Exception as error:
        print(f"  {type(error).__name__}: {error}")
        return None


def _primera_lista(datos) -> list:
    """
    El listado viene en una clave distinta en cada API, y en la v2 viene ademas
    ENTERRADO: la respuesta es {success, trace, payload, errors} y las filas
    estan en `payload.items`. Por eso se busca hacia adentro y no solo en el
    primer nivel.
    """
    if isinstance(datos, list):
        return datos
    if isinstance(datos, dict):
        for valor in datos.values():
            if isinstance(valor, list) and valor:
                return valor
        for valor in datos.values():
            if isinstance(valor, dict):
                dentro = _primera_lista(valor)
                if dentro:
                    return dentro
    return []


def _campo(fila: dict, *nombres, defecto=""):
    """Lee el primero que exista. Las dos APIs no escriben igual los campos."""
    for nombre in nombres:
        if "." in nombre:
            actual = fila
            for tramo in nombre.split("."):
                actual = actual.get(tramo) if isinstance(actual, dict) else None
                if actual is None:
                    break
            if actual not in (None, ""):
                return actual
        elif fila.get(nombre) not in (None, ""):
            return fila[nombre]
    return defecto


# Se busca en el texto porque el campo de la ficha viene vacio. Medido el
# 27-08-2026 sobre 70 licitaciones abiertas: `FechaVisitaTerreno` lleno en
# CERO. El dato real vive en las bases adjuntas, y a esas no se llega por la
# API —no hay endpoint de adjuntos, da 404—.
#
# Buscarlo en el nombre y la descripcion atrapa solo el 0,2% (6 de 2.800),
# pero esas 6 son de verdad: reparacion de techumbre, habilitacion de
# oficinas. Cuesta cero y avisa de algo que descalifica.
#
# NO es deteccion completa, y por eso el aviso dice «lo menciona» y no
# «tiene»: si no aparece, puede igual haber visita escondida en las bases.
SEÑAS_DE_VISITA = re.compile(
    r"visita\s+a\s+terreno|visita\s+en\s+terreno|visita\s+obligatoria|"
    r"obligatoria\s+la\s+visita|charla\s+informativa|reuni[oó]n\s+informativa",
    re.IGNORECASE)


def menciona_visita(*textos) -> str:
    """Devuelve el trozo donde lo dice, o vacio. Ver SEÑAS_DE_VISITA."""
    for texto in textos:
        encontrado = SEÑAS_DE_VISITA.search(str(texto or ""))
        if encontrado:
            entorno = str(texto)[max(0, encontrado.start() - 40):encontrado.end() + 60]
            return " ".join(entorno.split())
    return ""


def unidad_del_codigo(codigo: str) -> str:
    """
    «1058101-1-LR26» -> «1058101». El prefijo del codigo ES la unidad
    compradora, y es la unica manera de enriquecer lo que viene en vivo: el
    listado de activas trae cuatro campos y ninguno es la unidad. Sin esto,
    el correo no podria decir cuanto gasta el comprador, que es justo lo que
    ningun competidor pone.
    """
    tramo = str(codigo or "").split("-")[0].strip()
    return tramo if tramo.isdigit() else ""


def licitaciones_abiertas(ticket: str, bolsa_comun: set[str], techo: int = 400) -> list[dict]:
    """
    Las activas de la v1, en dos pasadas.

    Hace falta que sean dos porque el listado de activas trae CUATRO campos
    —codigo, nombre, estado y fecha de cierre— y nada mas. Ni descripcion, ni
    region, ni unidad compradora. Con solo el nombre no se puede ni filtrar
    bien ni enriquecer.

    Y no se puede pedir el detalle de las 4.580: eso da 429 casi de inmediato,
    y con los 2 segundos de espera obligatorios serian mas de dos horas.

    Asi que: primero se descartan por el nombre las que no le sirven a NADIE,
    que son la enorme mayoria; y solo a las que sobreviven se les pide el
    detalle, de a una, con la espera. Quedan decenas, no miles.
    """
    print("Pidiendo licitaciones activas...")
    datos = _pedir(f"{V1}?estado=activas&ticket={urllib.parse.quote(ticket)}")
    filas = [f for f in _primera_lista(datos) if isinstance(f, dict)]
    print(f"  {len(filas)} licitaciones abiertas")

    # --- primera pasada: por el nombre, contra la bolsa de TODOS ---
    candidatas = []
    for fila in filas:
        nombre = str(_campo(fila, "Nombre", "nombre"))
        if palabras(nombre) & bolsa_comun:
            candidatas.append((str(_campo(fila, "CodigoExterno", "Codigo", "codigo")), fila))
    print(f"  {len(candidatas)} sobreviven al nombre")
    if len(candidatas) > techo:
        print(f"  se piden solo las primeras {techo} para no agotar el ticket")
        candidatas = candidatas[:techo]

    # --- segunda pasada: el detalle, que es donde esta lo que sirve ---
    salida = []
    for i, (codigo, fila) in enumerate(candidatas, 1):
        if i > 1:
            time.sleep(ESPERA_V1)  # menos de 2 s y la API responde 429
        detalle = _primera_lista(_pedir(
            f"{V1}?codigo={urllib.parse.quote(codigo)}&ticket={urllib.parse.quote(ticket)}"))
        d = detalle[0] if detalle and isinstance(detalle[0], dict) else {}
        comprador = d.get("Comprador") if isinstance(d.get("Comprador"), dict) else {}

        # LA VISITA A TERRENO ES DESCALIFICANTE.
        # Muchas licitaciones exigen ir al lugar, o asistir a una charla, antes
        # de poder ofertar: quien no va queda fuera, por buena que sea su
        # oferta. Viene en la propia ficha y es de lo primero que hay que saber,
        # porque si la visita es pasado mañana en Punta Arenas y el proveedor
        # esta en Santiago, la decision es hoy.
        fechas = d.get("Fechas") if isinstance(d.get("Fechas"), dict) else {}
        visita = str(fechas.get("FechaVisitaTerreno") or "")
        nombre_lic = str(_campo(fila, "Nombre", "nombre"))
        mencion = menciona_visita(nombre_lic, d.get("Descripcion"))
        salida.append({
            "tipo": "licitacion",
            "codigo": codigo,
            "nombre": str(_campo(fila, "Nombre", "nombre")),
            "descripcion": str(d.get("Descripcion") or ""),
            "visita": visita[:16].replace("T", " ") if visita else "",
            "direccion_visita": str(d.get("DireccionVisita") or "").strip(),
            "mencion_visita": mencion,
            "cierre": str(_campo(fila, "FechaCierre", "fechaCierre") or
                          _campo(d, "Fechas.FechaCierre"))[:10],
            "monto": 0.0,
            # CodigoUnidad y el prefijo del codigo son lo mismo; se prefiere el
            # que viene declarado y se cae al prefijo si no vino.
            "unidad": str(comprador.get("CodigoUnidad") or unidad_del_codigo(codigo)),
            "nombre_unidad": str(comprador.get("NombreUnidad") or ""),
            "organismo": str(comprador.get("NombreOrganismo") or ""),
            "region": str(comprador.get("RegionUnidad") or ""),
            "comuna": str(comprador.get("ComunaUnidad") or ""),
        })
        if i % 25 == 0:
            print(f"    {i}/{len(candidatas)} detalles pedidos")

    return salida


def compras_agiles_abiertas(ticket: str, dias: int = 1, techo_paginas: int = 40) -> list[dict]:
    """
    Las publicadas de la v2. Cierran en 24-72 horas, asi que son las que mas
    se agradecen en un correo de la manana.

    Hay casi NUEVE MIL publicadas en cualquier momento (890 paginas de 10 el
    26-08-2026), asi que no se piden todas: el correo diario avisa de lo que
    se publico hoy, y para eso esta `publicado_desde`.

    Ojo con dos cosas de esta API:
    - `tamano_pagina` tiene que estar entre 10 y 50. Con 5 responde 400.
    - El 429 significa cuota diaria agotada, no «vas muy rapido». No sirve
      reintentar en un rato: se restablece al cambiar el dia.
    """
    print("Pidiendo compras agiles publicadas...")
    desde = (date.today() - timedelta(days=dias)).isoformat()
    salida = []
    for pagina in range(1, techo_paginas + 1):
        url = (f"{V2}?estado=publicada&tamano_pagina=50&numero_pagina={pagina}"
               f"&publicado_desde={desde}")
        # Esta API se cae sola de vez en cuando con un 504 «Endpoint request
        # timed out». Paso el 26-08-2026 en la pagina 6 de golpe. Sin
        # reintentar, el correo sale con la mitad de las compras agiles y
        # nadie se entera: no hay error, simplemente vienen menos.
        filas = []
        for intento in range(3):
            filas = _primera_lista(_pedir(url, {"ticket": ticket}))
            if filas:
                break
            if intento < 2:
                print(f"    pagina {pagina} vino vacia, reintento {intento + 1} de 2")
                time.sleep(5)
        if not filas:
            break
        for fila in filas:
            if not isinstance(fila, dict):
                continue
            codigo = str(_campo(fila, "codigo", "Codigo"))
            # Esta API no manda descripcion, pero los nombres de los archivos
            # adjuntos dicen bastante («taco carta 30 hojas», «CARPETA_AZUL»),
            # asi que se suman al texto que se compara.
            adjuntos = " ".join(
                str(doc.get("nombre") or "")
                for doc in (fila.get("documentos") or [])
                if isinstance(doc, dict)
            )
            salida.append({
                "tipo": "compra_agil",
                "codigo": codigo,
                # Las compras agiles no exigen visita: se cotiza en linea.
                "visita": "", "direccion_visita": "",
                "nombre": str(_campo(fila, "nombre", "Nombre")),
                "descripcion": adjuntos,
                "cierre": str(_campo(fila, "fechas.fecha_cierre", "fecha_cierre"))[:10],
                "monto": float(_campo(fila, "montos.monto_disponible_clp", "monto_disponible_clp", defecto=0) or 0),
                # Para cruzar con la bodega sirve el codigo de la unidad, que
                # es el prefijo; el nombre solo se usa para mostrarlo.
                "unidad": unidad_del_codigo(codigo),
                "nombre_unidad": str(_campo(fila, "institucion.unidad_compra", "unidad_compra")),
                "organismo": str(_campo(fila, "institucion.organismo_comprador", "organismo_comprador")),
                # `region` viene como numero (13); el nombre esta al lado.
                "region": str(_campo(fila, "institucion.nombre_region", "nombre_region")),
                "comuna": "",
            })
        if len(filas) < 50:
            break
    print(f"  {len(salida)} compras agiles abiertas")
    return salida


def fuente_de_prueba(dias: int = 3) -> list[dict]:
    """
    El modo de prueba: las licitaciones mas nuevas de la bodega, tratadas como
    si se hubieran publicado hoy. No toca la API ni gasta ticket.
    """
    archivos = sorted(BODEGA_LIC.glob("*.parquet"))
    if not archivos:
        print("No hay bodega de licitaciones. Correr licitador.py primero.")
        return []

    d = pd.read_parquet(archivos[-1])
    d = d.drop_duplicates("codigo")

    # Una fila de cada 2.800 sale con las columnas corridas (el CSV de origen
    # trae separadores dentro de un campo). Se descarta sin drama.
    d = d[d["estado"].astype(str).str[0].str.isalpha().fillna(False)]

    d["fecha_publicacion"] = pd.to_datetime(d["fecha_publicacion"], errors="coerce")
    ultimo = d["fecha_publicacion"].max()
    if pd.isna(ultimo):
        return []
    recientes = d[d["fecha_publicacion"] >= ultimo - pd.Timedelta(days=dias)]
    print(f"Modo prueba: {len(recientes)} licitaciones publicadas "
          f"hasta el {ultimo:%d-%m-%Y}")

    salida = []
    for _, fila in recientes.iterrows():
        salida.append({
            "tipo": "licitacion",
            "codigo": str(fila["codigo"]),
            "visita": "", "direccion_visita": "",
            "nombre": str(fila["nombre"]),
            # `codigo_onu` es el numero del rubro, no su nombre: no aporta al
            # comparar palabras. Los nombres estan en rubro1/2/3.
            "descripcion": " ".join(str(fila.get(c) or "") for c in
                                    ("descripcion", "rubro1", "rubro2", "rubro3")),
            "cierre": str(fila.get("fecha_cierre") or "")[:10],
            "monto": float(pd.to_numeric(fila.get("monto_estimado"), errors="coerce") or 0),
            "unidad": str(fila.get("unidad") or ""),
            "nombre_unidad": str(fila.get("nombre_unidad") or ""),
            "organismo": str(fila.get("nombre_organismo") or ""),
            "region": str(fila.get("region") or ""),
            "comuna": str(fila.get("comuna") or ""),
        })
    return salida


# ======================================================================
#  EL FILTRO
# ======================================================================

def le_sirve(oportunidad: dict, bolsa: set[str], suscriptor: dict) -> int:
    """
    Cuantos terminos del suscriptor aparecen en la oportunidad.
    Cero significa que no le sirve. Mas alto, mas encaja.
    """
    if not bolsa:
        return 0

    if oportunidad["tipo"] == "licitacion" and not suscriptor.get("incluye_licitaciones", True):
        return 0
    if oportunidad["tipo"] == "compra_agil" and not suscriptor.get("incluye_compras_agiles", True):
        return 0

    regiones = suscriptor.get("regiones") or []
    if regiones:
        suya = sin_tildes(oportunidad.get("region") or "")
        if suya and not any(sin_tildes(r) in suya or suya in sin_tildes(r) for r in regiones):
            return 0

    minimo = suscriptor.get("monto_minimo") or 0
    if minimo and oportunidad.get("monto") and oportunidad["monto"] < minimo:
        return 0

    texto = palabras(f"{oportunidad['nombre']} {oportunidad['descripcion']}")
    return len(texto & bolsa)


# ======================================================================
#  EL CORREO
# ======================================================================

def encabezado_grupo(titulo: str, bajada: str) -> str:
    """El titulo que separa un tipo de oportunidad del otro."""
    return f"""
  <tr>
    <td style="padding:22px 30px 4px;">
      <div style="color:{MARINO};font-size:15px;font-weight:700;
                  letter-spacing:.04em;text-transform:uppercase;">
        {titulo}
      </div>
      <div style="color:{TEXTO_SUAVE};font-size:12.5px;margin-top:2px;">
        {bajada}
      </div>
      <div style="height:2px;background:{NARANJO};width:44px;margin-top:8px;"></div>
    </td>
  </tr>"""


def tarjeta(op: dict) -> str:
    """Una oportunidad. Todo con tablas y estilos en linea, por Outlook."""
    # El tipo ya lo dice el titulo del grupo, asi que la etiqueta de la tarjeta
    # se queda solo con la prioridad y no repite la palabra en cada una.
    retrato, valor, clase = op["retrato"], op["nota"], op["clase"]

    donde = " · ".join(x for x in (op.get("nombre_unidad") or op.get("organismo"),
                                   op.get("comuna") or op.get("region")) if x)

    # ------------------------------------------------------------------
    #  LO QUE LA BODEGA SABE DE ESTE COMPRADOR
    # ------------------------------------------------------------------
    # Tres bloques separados por lineas, no un parrafo corrido: el ojo salta
    # de uno a otro y cada uno responde una pregunta distinta.
    #
    #   cuanto    ¿vale la pena?          el monto en SUS rubros
    #   como      ¿como le vendo?         el reparto por via de compra
    #   quien     ¿contra quien compito?  los proveedores de hoy
    radio = op.get("radiografia") or {}
    via, total_vias = radio.get("via") or {}, radio.get("total") or 0.0
    proveedores = radio.get("proveedores") or []
    detalle_rubro = radio.get("rubro") or {}

    def barra(monto, tope):
        """Una barra de fondo, con tablas: los <div> de ancho % fallan en Outlook."""
        ancho = max(2, int(monto / tope * 100)) if tope else 2
        return (f'<table width="100%" cellpadding="0" cellspacing="0" border="0">'
                f'<tr><td width="{ancho}%" style="background:{NARANJO};height:4px;'
                f'font-size:0;line-height:0;border-radius:2px;">&nbsp;</td>'
                f'<td style="font-size:0;line-height:0;">&nbsp;</td></tr></table>')

    def seccion(titulo, cuerpo):
        return (f'<tr><td style="padding:11px 0 3px;border-top:1px solid {BORDE};">'
                f'<div style="color:{TEXTO_SUAVE};font-size:10.5px;font-weight:700;'
                f'letter-spacing:.09em;text-transform:uppercase;margin-bottom:6px;">'
                f'{titulo}</div>{cuerpo}</td></tr>')

    bloques = []

    if total_vias > 0:
        # CUANTO — y en que, dentro de sus rubros
        cuanto = (f'<div style="color:{MARINO};font-size:21px;font-weight:700;'
                  f'line-height:1.1;">{plata(total_vias)}</div>'
                  f'<div style="color:{TEXTO_SUAVE};font-size:12px;margin-top:2px;">'
                  f'en lo que tú vendes · últimos 12 meses</div>')
        if detalle_rubro:
            trozos = [f'{p} {plata(m)}' for p, m in list(detalle_rubro.items())[:4]]
            cuanto += (f'<div style="color:{TEXTO};font-size:12px;margin-top:7px;'
                       f'line-height:1.7;">' + ' · '.join(trozos) + '</div>')
        bloques.append(seccion("Cuánto compra", cuanto))

        # COMO — el reparto por via, con barra
        tope = max(via.values())
        filas = []
        for mecanismo, monto in sorted(via.items(), key=lambda x: -x[1]):
            if monto <= 0:
                continue
            filas.append(
                f'<tr>'
                f'<td width="42%" style="padding:3px 0;color:{TEXTO};font-size:12.5px;">'
                f'{VIAS.get(mecanismo, mecanismo)}</td>'
                f'<td width="34%" style="padding:3px 8px;">{barra(monto, tope)}</td>'
                f'<td align="right" style="padding:3px 0;color:{TEXTO};font-size:12.5px;'
                f'font-weight:600;white-space:nowrap;">{plata(monto)}'
                f'<span style="color:{NARANJO};"> {monto/total_vias*100:.0f}%</span></td>'
                f'</tr>')
        bloques.append(seccion(
            "Cómo compra",
            '<table width="100%" cellpadding="0" cellspacing="0" border="0">'
            + "".join(filas) + '</table>'))

    if proveedores:
        # QUIEN — contra quien compite, hasta 10
        suma = sum(m for _, m in proveedores) or 1
        filas = []
        for i, (nombre, monto) in enumerate(proveedores, 1):
            destacado = "700" if i == 1 else "400"
            filas.append(
                f'<tr>'
                f'<td width="16" valign="top" style="padding:3px 0;color:{TEXTO_SUAVE};'
                f'font-size:11.5px;">{i}.</td>'
                f'<td style="padding:3px 0;color:{TEXTO};font-size:12.5px;'
                f'font-weight:{destacado};">{nombre[:40]}</td>'
                f'<td align="right" style="padding:3px 0;color:{TEXTO_SUAVE};'
                f'font-size:12.5px;white-space:nowrap;">{plata(monto)} '
                f'<span style="color:{NARANJO};font-weight:600;">'
                f'{monto/suma*100:.0f}%</span></td>'
                f'</tr>')
        bloques.append(seccion(
            f"Quién se lo lleva hoy · {len(proveedores)} proveedores",
            '<table width="100%" cellpadding="0" cellspacing="0" border="0">'
            + "".join(filas) + '</table>'))

    criterios = op.get("criterios") or []
    if criterios:
        # Ordenados de mayor a menor peso: lo primero que hay que saber es
        # contra que se compite. Un 80% al precio y un 80% a lo tecnico son
        # dos licitaciones distintas y no se preparan igual.
        filas = []
        for c in sorted(criterios, key=lambda x: -x["ponderacion"]):
            filas.append(
                f'<tr>'
                f'<td width="52%" style="padding:3px 0;color:{TEXTO};font-size:12.5px;">'
                f'{c["item"][:46]}</td>'
                f'<td width="30%" style="padding:3px 8px;">'
                f'{barra(c["ponderacion"], 100)}</td>'
                f'<td align="right" style="padding:3px 0;color:{MARINO};'
                f'font-size:13px;font-weight:700;">{c["ponderacion"]}%</td>'
                f'</tr>')
        bloques.append(seccion(
            "Con qué te van a evaluar",
            '<table width="100%" cellpadding="0" cellspacing="0" border="0">'
            + "".join(filas) + '</table>'))

    if not bloques:
        bloques.append(seccion(
            "Este comprador",
            f'<div style="color:{TEXTO_SUAVE};font-size:12.5px;">No aparece '
            f'comprando lo que tú vendes en los últimos 12 meses. Es terreno nuevo.</div>'))

    detalle = ('<table width="100%" cellpadding="0" cellspacing="0" border="0">'
               + "".join(bloques) + '</table>')

    monto = f"<br>Monto disponible: <strong>{plata(op['monto'])}</strong>" if op.get("monto") else ""

    # La visita va ARRIBA del todo y en su propio recuadro, no como una linea
    # mas entre los datos: es lo unico de la tarjeta que, si se pasa por alto,
    # deja fuera al proveedor pase lo que pase con su oferta.
    aviso_visita = ""
    # Dos avisos distintos a proposito. Con fecha es un hecho: se sabe cuando y
    # donde. Por mencion es una advertencia: el texto la nombra pero el detalle
    # esta en las bases, y prometer una certeza que no se tiene es peor que
    # avisar de la duda.
    if not op.get("visita") and op.get("mencion_visita"):
        aviso_visita = f"""
          <table width="100%" cellpadding="0" cellspacing="0" border="0"
                 style="background:#fffaf2;border:1px dashed {NARANJO};
                        border-radius:5px;margin-bottom:12px;">
            <tr><td style="padding:10px 12px;color:#8a4b12;font-size:12.5px;line-height:1.5;">
              <strong>MENCIONA VISITA A TERRENO</strong><br>
              <span style="color:#a86a35;font-style:italic;">
                «{op['mencion_visita'][:150]}»</span><br>
              Revisa las bases antes de ofertar: si es obligatoria y no vas, quedas fuera.
            </td></tr>
          </table>"""
    if op.get("visita"):
        donde_visita = op.get("direccion_visita") or ""
        aviso_visita = f"""
          <table width="100%" cellpadding="0" cellspacing="0" border="0"
                 style="background:#fff4e8;border:1px solid {NARANJO};
                        border-radius:5px;margin-bottom:12px;">
            <tr><td style="padding:10px 12px;color:#8a4b12;font-size:13px;line-height:1.5;">
              <strong>VISITA A TERRENO OBLIGATORIA</strong><br>
              {op['visita']}{(' · ' + donde_visita[:70]) if donde_visita else ''}<br>
              <span style="color:#a86a35;">Si no asistes, quedas fuera.</span>
            </td></tr>
          </table>"""

    return f"""
  <tr>
    <td style="padding:10px 30px;">
      <table width="100%" cellpadding="0" cellspacing="0" border="0"
             style="border:1px solid {BORDE};border-left:4px solid {NARANJO};border-radius:6px;">
        <tr><td style="padding:16px 18px;">
          <div style="color:{NARANJO};font-size:11px;font-weight:700;letter-spacing:1px;margin-bottom:8px;">
            PRIORIDAD {clase} · {valor}
          </div>
          <div style="color:{MARINO};font-size:16px;font-weight:600;line-height:1.35;margin-bottom:6px;">
            {op['nombre'][:150]}
          </div>
          <div style="color:{TEXTO_SUAVE};font-size:13px;margin-bottom:12px;">
            {donde} · cierra {op['cierre'] or 'sin fecha'}
          </div>
{aviso_visita}
          {detalle}{monto}
          <a href="{op['enlace']}"
             style="display:inline-block;margin-top:14px;padding:9px 18px;background:{MARINO};
                    color:#ffffff;font-size:13px;font-weight:600;text-decoration:none;border-radius:5px;">
            Ver en Mercado Público
          </a>
        </td></tr>
      </table>
    </td>
  </tr>"""


def armar_correo(suscriptor: dict, oportunidades: list[dict]) -> str:
    hoy = datetime.now().strftime("%d-%m-%Y")
    n = len(oportunidades)
    saludo = f"Hola {suscriptor['nombre'].split()[0]}, " if suscriptor.get("nombre") else ""

    # Agrupadas por tipo, no mezcladas: son dos cosas distintas y se actua
    # distinto. Las compras agiles van PRIMERO porque cierran en 24-72 horas;
    # una licitacion da una o dos semanas para preparar la oferta.
    agiles = [o for o in oportunidades if o["tipo"] == "compra_agil"]
    licitaciones = [o for o in oportunidades if o["tipo"] != "compra_agil"]

    bloques = []
    if agiles:
        bloques.append(encabezado_grupo(
            f"Compras ágiles · {len(agiles)}",
            "Cierran en 24 a 72 horas. Si vas, es hoy."))
        bloques += [tarjeta(o) for o in agiles]
    if licitaciones:
        bloques.append(encabezado_grupo(
            f"Licitaciones · {len(licitaciones)}",
            "Con plazo para preparar la oferta."))
        bloques += [tarjeta(o) for o in licitaciones]
    tarjetas = "".join(bloques)

    token = suscriptor.get("token_baja") or ""
    rut = suscriptor.get("rut_empresa") or "77.082.051-0"
    desde = suscriptor.get("fecha_consentimiento") or ""

    return f"""<!DOCTYPE html>
<html lang="es"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"></head>
<body style="margin:0;padding:0;background:{FONDO};">
<table width="100%" cellpadding="0" cellspacing="0" border="0" style="background:{FONDO};padding:24px 12px;">
<tr><td align="center">
<table width="600" cellpadding="0" cellspacing="0" border="0"
       style="background:#ffffff;border-radius:8px;overflow:hidden;max-width:600px;
              font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,Arial,sans-serif;">

  <!-- La cabecera va BLANCA a proposito. El logo tiene fondo blanco: sobre el
       azul marino dejaria un recuadro y se veria pegoteado. Asi el logo se
       integra solo, y el color de marca lo pone la franja naranja de abajo. -->
  <tr>
    <td style="background:#ffffff;padding:20px 30px 14px;">
      <table cellpadding="0" cellspacing="0" border="0"><tr>
        <td><img src="{LOGO}" alt="Uplevel" width="46" height="46"
                 style="display:block;"></td>
        <td style="padding-left:12px;color:{MARINO};font-size:17px;font-weight:700;
                   letter-spacing:.01em;">Uplevel Inteligencia</td>
      </tr></table>
    </td>
  </tr>
  <tr><td style="height:3px;background:{NARANJO};font-size:0;line-height:0;">&nbsp;</td></tr>

  <tr>
    <td style="padding:26px 30px 6px;">
      <div style="color:{TEXTO};font-size:20px;font-weight:700;margin-bottom:4px;">
        Oportunidades de hoy
      </div>
      <div style="color:{TEXTO_SUAVE};font-size:14px;">
        {saludo}{n} {'oportunidad coincide' if n == 1 else 'oportunidades coinciden'} con lo que vendes · {hoy}
      </div>
    </td>
  </tr>
{tarjetas}
  <tr>
    <td style="padding:22px 30px 26px;border-top:1px solid {BORDE};">
      <div style="color:{TEXTO_SUAVE};font-size:11px;line-height:1.7;">
        Cifras calculadas sobre los <strong>datos públicos de ChileCompra</strong>,
        actualizados al {hoy}. Incluyen Convenio Marco, licitaciones, compras
        ágiles y trato directo.<br><br>
        Uplevel · {rut} · Santiago, Chile<br>
        Recibes este correo porque te suscribiste{' el ' + desde if desde else ''}.<br>
        <a href="https://uplevelweb.art/baja?t={token}" style="color:{MARINO};">Cancelar suscripción</a> ·
        <a href="https://uplevelweb.art/privacidad" style="color:{MARINO};">Política de privacidad</a>
      </div>
    </td>
  </tr>

</table>
</td></tr></table>
</body></html>"""


def destinatarios(suscriptor: dict) -> list[str]:
    """
    A quien llega este correo.

    La cuenta se identifica SIEMPRE por su correo registrado: esa es la llave
    unica de la tabla y el respaldo del consentimiento. Pero el aviso puede
    llegarle ademas al comercial o al gerente sin abrirles cuenta propia.

    Y va en UN solo mensaje a proposito: tres personas de la misma empresa
    gastan un envio de los 100 del dia, no tres. Con cuentas separadas serian
    33 empresas en vez de 100.
    """
    lista = [str(suscriptor.get("email") or "").strip()]
    for extra in suscriptor.get("correos_envio") or []:
        extra = str(extra).strip()
        if extra and extra.lower() not in {x.lower() for x in lista}:
            lista.append(extra)
    # Resend admite hasta 50 destinatarios en un mensaje.
    return [x for x in lista if "@" in x][:50]


def enviar(a_quienes: list[str], asunto: str, html: str) -> bool:
    """Un correo por Resend, a uno o varios. Devuelve si salio."""
    clave = os.environ.get("RESEND_API_KEY", "").strip()
    if not clave:
        print("  falta RESEND_API_KEY")
        return False
    if not a_quienes:
        print("  no hay a quien enviarlo")
        return False

    cuerpo = json.dumps({
        "from": "Uplevel Alertas <alertas@uplevelweb.art>",
        "to": a_quienes,
        "subject": asunto,
        "html": html,
    }).encode("utf-8")

    # EL User-Agent NO ES DECORATIVO: sin el, Cloudflare —que protege a
    # Resend— responde «403 · error code: 1010», que significa «tu navegador
    # esta vetado». urllib se identifica por defecto como «Python-urllib/3.x»
    # y esa firma esta en su lista negra. El correo se armaba perfecto y
    # moria en el ultimo paso, con un codigo que no es de Resend y que no
    # dice nada de correos.
    peticion = urllib.request.Request(
        "https://api.resend.com/emails", data=cuerpo, method="POST",
        headers={
            "Authorization": f"Bearer {clave}",
            "Content-Type": "application/json",
            "User-Agent": "Uplevel-Inteligencia/1.0",
            "Accept": "application/json",
        })
    try:
        with urllib.request.urlopen(peticion, timeout=60) as respuesta:
            print(f"  enviado: {json.loads(respuesta.read()).get('id')}")
            return True
    except urllib.error.HTTPError as error:
        print(f"  no salio ({error.code}): {error.read().decode('utf-8')[:200]}")
        return False


# ======================================================================
#  EL PROGRAMA
# ======================================================================

def enlace(op: dict) -> str:
    if op["tipo"] == "compra_agil":
        return f"https://www.mercadopublico.cl/CompraAgil/Cotizacion/{op['codigo']}"
    return f"http://www.mercadopublico.cl/fichaLicitacion.html?idLicitacion={op['codigo']}"


def main():
    parser = argparse.ArgumentParser(description="El correo diario de oportunidades")
    parser.add_argument("--prueba", action="store_true",
                        help="usa la bodega en vez de la API. No gasta ticket ni envia")
    parser.add_argument("--guardar", metavar="ARCHIVO",
                        help="escribe el correo a disco en vez de enviarlo")
    parser.add_argument("--enviar", action="store_true", help="envia de verdad")
    parser.add_argument("--hora", type=int, metavar="N",
                        help="solo a quienes pidieron recibirlo a esa hora de Chile "
                             "(8, 13 o 18). Sin esto, va a todos")
    args = parser.parse_args()

    suscriptores = configuracion()
    if not suscriptores:
        # Antes se salia callado y la corrida terminaba «bien» en 18 segundos,
        # sin una linea que dijera por que. Desde afuera parecia que habia
        # funcionado. Si no hay a quien mandarle, hay que decirlo.
        print("NO HAY SUSCRIPTORES ACTIVOS. No hay a quien mandarle nada.")
        print("Revisar: la pestaña «Alertas» del panel, boton «Guardar")
        print("configuracion», tiene que dejar un mensaje VERDE.")
        return

    # Cada suscriptor elige su turno (8, 13 o 18 de Chile) y el workflow corre
    # en los tres. Sin --hora van todos, que es lo que se quiere al dispararlo
    # a mano para probar.
    if args.hora is not None:
        antes = len(suscriptores)
        suscriptores = [s for s in suscriptores
                        if int(s.get("hora_envio") or 8) == args.hora]
        print(f"Turno de las {args.hora}:00 · {len(suscriptores)} de {antes}")
        if not suscriptores:
            print("Nadie pidio recibirlo a esta hora. Nada que hacer.")
            return

    print(f"{len(suscriptores)} suscriptor(es) activo(s)\n")

    print("Cargando la bodega de ordenes de compra...")
    oc = cargar_ordenes()
    print(f"  {len(oc):,} lineas\n".replace(",", "."))

    # --- la bolsa de cada uno, ANTES de pedir nada ---
    # La union de todas sirve para descartar de una sola pasada lo que no le
    # interesa a nadie, que es la enorme mayoria. Sin eso habria que pedir el
    # detalle de las 4.580 licitaciones activas: dos horas y medio ticket.
    bolsas: dict[str, tuple] = {}
    union: set[str] = set()
    for suscriptor in suscriptores:
        bolsa, convenios, origen = bolsa_de_terminos(suscriptor, oc)
        bolsas[suscriptor["email"]] = (bolsa, convenios, origen)
        union |= bolsa
    print(f"Bolsa comun de todos los suscriptores: {len(union)} terminos\n")

    # --- de donde salen las oportunidades de hoy ---
    if args.prueba:
        universo = fuente_de_prueba()
    else:
        ticket = os.environ.get("TICKET_MP", "").strip()
        if not ticket:
            print("Falta TICKET_MP en el entorno. Con --prueba no hace falta.")
            return
        universo = licitaciones_abiertas(ticket, union) + compras_agiles_abiertas(ticket)

    if not universo:
        print("No hay nada publicado. No se envia: el silencio construye confianza.")
        return
    print()

    enviados_hoy = 0
    for suscriptor in suscriptores:
        bolsa, convenios, origen = bolsas[suscriptor["email"]]
        print(f"— {suscriptor.get('email')} · filtro: {origen} · {len(bolsa)} terminos")

        if not bolsa:
            print("   sin terminos: no se puede filtrar. Revisar su configuracion.")
            continue

        # Las palabras que estan en todas partes no distinguen: fuera.
        bolsa = quitar_palabras_de_todos(bolsa, universo)
        minimo = minimo_coincidencias(bolsa)
        print(f"   quedan {len(bolsa)} terminos · hacen falta {minimo} coincidencia(s)")

        vistos = ya_avisado(suscriptor)
        if vistos:
            print(f"   ya recibio {len(vistos)} oportunidades antes: esas no se repiten")

        elegidas = []
        for op in universo:
            if op["codigo"] in vistos:
                continue
            encaje = le_sirve(op, bolsa, suscriptor)
            if encaje < minimo:
                continue
            retrato = retrato_del_comprador(op.get("unidad"), oc, convenios)
            valor, clase = nota(retrato)
            elegidas.append({**op, "encaje": encaje, "retrato": retrato,
                             "nota": valor, "clase": clase, "enlace": enlace(op)})

        # PRIMERO lo que mas se parece a lo que vende; la nota solo desempata.
        #
        # Ordenando por la nota pasaba esto: «ALIMENTOS Y BEBIDAS ANIVERSARIO
        # PATRIO», que es exactamente su rubro, quedaba ULTIMA con nota 1, y
        # arriba iba un servicio de teleasistencia que no tiene nada que ver.
        # La nota mide al COMPRADOR —cuanto gasta, que tan repartido esta—, no
        # si la oportunidad le sirve. Un comprador desconocido saca nota baja
        # aunque la licitacion le calce perfecto.
        elegidas.sort(key=lambda x: (x["encaje"], x["nota"]), reverse=True)
        elegidas = elegidas[:MAXIMO_POR_CORREO]

        # UNA sola pasada por los archivos para las ~15 elegidas, no una por
        # cada una: leer `producto` es lo caro y hay que hacerlo lo menos
        # posible.
        if elegidas:
            unidades = {str(o.get("unidad")) for o in elegidas if o.get("unidad")}
            radiografia = radiografia_de_unidades(unidades, bolsa)
            for o in elegidas:
                o["radiografia"] = radiografia.get(str(o.get("unidad")), {})

            # Los criterios de evaluacion y la visita a terreno NO estan en la
            # API —comprobado sobre 93 campos de 12 licitaciones— pero si en el
            # HTML de la ficha publica. Una peticion por oportunidad, solo para
            # las ~15 que ya pasaron el filtro.
            for o in elegidas:
                if o["tipo"] != "licitacion":
                    continue
                documento = ficha_licitacion.bajar_ficha(o["codigo"])
                if not documento:
                    continue
                o["criterios"] = ficha_licitacion.criterios_de_evaluacion(documento)
                if not o.get("visita") and not o.get("mencion_visita"):
                    o["mencion_visita"] = ficha_licitacion.menciona_visita_en_ficha(documento)

        if not elegidas:
            print("   nada que coincida hoy. No se envia.")
            continue
        print(f"   {len(elegidas)} oportunidades · mejor nota {elegidas[0]['nota']} ({elegidas[0]['clase']})")

        html = armar_correo(suscriptor, elegidas)
        asunto = f"{len(elegidas)} oportunidades de hoy · Uplevel"

        if args.guardar:
            Path(args.guardar).write_text(html, encoding="utf-8")
            print(f"   correo escrito en {args.guardar}")
        elif args.enviar:
            if enviados_hoy >= TOPE_DIARIO:
                print(f"   TOPE de {TOPE_DIARIO} correos alcanzado. Queda pendiente.")
                continue
            a_quienes = destinatarios(suscriptor)
            print(f"   va a: {', '.join(a_quienes)}")
            if enviar(a_quienes, asunto, html):
                enviados_hoy += 1
                # Se anota DESPUES de que salio, nunca antes: si el envio
                # falla, esas oportunidades tienen que poder salir manana.
                anotar_avisado(suscriptor,
                               [o["codigo"] for o in elegidas],
                               [o["tipo"] for o in elegidas])
        else:
            print("   (ni --guardar ni --enviar: no se hizo nada con el correo)")

    print(f"\nListo. Correos enviados: {enviados_hoy}")


if __name__ == "__main__":
    main()
