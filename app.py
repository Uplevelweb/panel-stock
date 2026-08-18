"""
PANEL OPORTUNIDADES — Comercial Emergenza
==========================================

Dos pestañas:

ANALISIS DE COMPRAS — lee el libro de Google Sheets con el analisis de compras
de una institucion y lo convierte en oportunidades de venta:

  1. Enlace de la hoja y del catalogo de ofertas, arriba en el encabezado.
  2. Filtro por MI ESTADO: CON STOCK / SIN STOCK / NO LO TENGO / TODOS.
  3. Columna MONTO (venta del periodo) y COMENTARIO con las señales de negocio
     (compra recurrente, frecuencia de OC, poca competencia, tu precio vs mercado).
  4. Dos informes independientes: año en curso y periodo anterior.
  5. Exporta a Excel, o marca productos uno a uno y genera un PDF tipo
     cotizacion con el precio de oferta de la semana, mas el correo listo
     para copiar y pegar en Gmail.

MERCADO PUBLICO — que compro de verdad una institucion, consultado en vivo:

  6. Selector con filtros (region, organismo, buscador) sobre las 2.103 unidades
     que compran por Convenio Marco.
  7. Consulta a la API de Mercado Publico del periodo elegido, sin base de datos
     y sin nada corriendo de fondo, y una fila por producto comprado: fecha, ID,
     producto, cantidad, precio pagado y quien gano la venta.

Ejecutar:  streamlit run app.py
"""

from __future__ import annotations

import base64
import io
import json
import re
import time
import unicodedata
import urllib.error
import urllib.request
from datetime import date, datetime, timedelta
from pathlib import Path
from urllib.parse import quote

import pandas as pd
import streamlit as st
from fpdf import FPDF
from fpdf.fonts import FontFace

# ===========================================================================
# 1. CONFIGURACION
# ===========================================================================

TITULO_APP = "Panel Oportunidades"
SUBTITULO_APP = "Convenio Marco · Comercial Emergenza"

# Enlaces que trae la app cargados de fabrica. Los dos campos son editables:
# se pueden reemplazar por los de otra institucion o de otra carpeta.
URL_HOJA_POR_DEFECTO = (
    "https://docs.google.com/spreadsheets/d/"
    "1p21tCkxOOgdW9LU-5p6lD8FhY7SdSMc5Ee1zYoofH4A/edit"
)
URL_OFERTAS_POR_DEFECTO = (
    "https://drive.google.com/drive/folders/1jpbagaEvCcHyrssATVe-CwdXXQOTLwN3"
)

# En esa carpeta de Drive siempre hay un archivo cuyo nombre contiene esta
# palabra: es el catalogo de ofertas de la semana (misma regla que usa el
# Panel Armada en Code.gs con CONFIG.OFERTAS_PATRON).
PATRON_OFERTAS = "OFERTAS"

# Datos de la empresa que van en la cabecera del PDF.
EMPRESA = {
    "razon": "Comercial Emergenza SpA",
    "rut": "77.082.051-0",
    "direccion": "Bodega: Av. Calera de Tango, Paradero 9 Parcela 11A, Bodega 1C",
}

# Azules del formato de cotizacion (los del documento que ya usa Serling).
AZUL_BARRA = (11, 99, 176)
AZUL_TABLA = (47, 134, 203)

CARPETA = Path(__file__).parent
RUTA_LOGO = CARPETA / "LogoVec.png"
# Version cuadrada del logo: el original es horizontal (400x225) y como
# favicon o icono de celular sale aplastado.
RUTA_ICONO = CARPETA / "icono.png"

# Paleta tomada del Panel Armada (emergenza-mailer/Index.html) para que los
# dos paneles se vean como un mismo sistema.
COLOR = {
    "fondo": "#24333F",
    "tarjeta": "#33475B",
    "borde": "#46596C",
    "texto": "#EEF3F7",
    "texto_suave": "#A9BDCE",
    "rojo": "#C1303F",
    "blanco": "#FFFFFF",
}
TIPOGRAFIA = 'Tahoma, Geneva, Verdana, "DejaVu Sans", sans-serif'

# Columnas de la tabla final, en este orden. Todo lo demas se descarta.
COLUMNAS_FINALES = [
    "ID", "PRODUCTO", "MONTO", "P.MIN", "P. PROM", "P.MAX",
    "MI PUBLICADO", "OC", "COMENTARIO",
]

# Columnas que solo se usan por dentro (filtrar o calcular), nunca se muestran.
COLUMNA_ESTADO = "MI ESTADO"
COLUMNA_PROVEEDORES = "PROVEEDORES"

ESTADOS = ["CON STOCK", "SIN STOCK", "NO LO TENGO", "TODOS"]

# Columnas que se guardan como numero (no como texto) para que la tabla se
# pueda ordenar de verdad: como texto, "11" quedaba entre "1" y "2".
COLUMNAS_NUMERICAS = ["MONTO", "P.MIN", "P. PROM", "P.MAX", "MI PUBLICADO", "OC"]

# Señales del comentario que se pintan en amarillo. Se destaca solo la compra
# recurrente porque es la que sirve para priorizar: "sin competencia" la tiene
# el 72% del catalogo y "bajo el promedio" la mitad de lo que ella vende, asi
# que pintarlas dejaria casi todo amarillo y no destacaria nada.
SEÑALES_DESTACADAS = ("compra recurrente",)
COLOR_DESTACADO = "#F2C14E"

# Variantes aceptadas de cada encabezado. Se comparan normalizadas (sin tildes,
# sin espacios, sin puntos), asi que "p. min", "P.MIN" y " P Min " son lo mismo.
ALIAS_COLUMNAS: dict[str, list[str]] = {
    # "ID REGIÓN CM" e "ID CONVENIO REGIÓN" son los nombres que usa el catalogo
    # de ofertas semanales; el resto vienen de la hoja de compras.
    "ID":                 ["ID", "IDPRODUCTO", "CODIGO", "COD", "SKU", "IDCONVENIO",
                           "IDREGIONCM", "IDCONVENIOREGION", "IDREGION", "IDCM"],
    "PRODUCTO":           ["PRODUCTO", "PRODUCTOS", "NOMBREPRODUCTO", "DESCRIPCION", "DETALLE", "ARTICULO"],
    "MONTO":              ["MONTO", "MONTOTOTAL", "MONTOVENDIDO", "VENTA", "TOTAL"],
    "P.MIN":              ["PMIN", "PRECIOMIN", "PMINIMO", "PRECIOMINIMO"],
    "P. PROM":            ["PPROM", "PPROMEDIO", "PRECIOPROM", "PRECIOPROMEDIO"],
    "P.MAX":              ["PMAX", "PRECIOMAX", "PMAXIMO", "PRECIOMAXIMO"],
    "MI PUBLICADO":       ["MIPUBLICADO", "PUBLICADO", "MIPRECIOPUBLICADO", "MIPRECIO"],
    "OC":                 ["OC", "OCS", "ORDENCOMPRA", "ORDENDECOMPRA", "OCOS"],
    COLUMNA_ESTADO:       ["MIESTADO", "ESTADO", "ESTADOSTOCK"],
    COLUMNA_PROVEEDORES:  ["PROVEEDORES", "NPROVEEDORES", "CANTIDADPROVEEDORES", "COMPETIDORES"],
    # Solo aparece en el catalogo de ofertas semanales (mismos alias que usa
    # el Panel Armada en Code.gs).
    "PRECIO OFERTA":      ["PRECIOOFERTA", "PRECIODEOFERTA", "OFERTA", "PRECIO", "VALOROFERTA", "VALOR"],
}

# Palabras que delatan una pestaña de un periodo pasado cuando el nombre no
# alcanza a mostrar el año (ver sugerir_pestana).
PALABRAS_PERIODO_ANTERIOR = ["ULTIMOSEMESTRE", "ULTIMOTRIMESTRE", "SEMESTRE", "TRIMESTRE", "ANTERIOR", "ULTIMO"]

# Firma que va en el PDF y en el correo.
FIRMA = {
    "nombre": "Serling Vera",
    "cargo": "KAM Comercial",
    "empresa": "Comercial Emergenza",
    "fono": "+56 9 8126 5224",
    "correo": "svera@emergenza.cl",
    "correo_alt": "serlingvera@gmail.com",
}

# Cuentas desde las que Serling puede enviar el correo.
CORREOS_ENVIO = ["svera@emergenza.cl", "serlingvera@gmail.com"]

def asunto_correo(institucion: str) -> str:
    """«ID disponibles en Convenio Marco - Escuela Naval | Comercial Emergenza»."""
    nombre = institucion.strip()
    medio = f" - {nombre}" if nombre else ""
    return f"ID disponibles en Convenio Marco{medio} | Comercial Emergenza"

# Ambitos minimos de lectura para el Modo 2 (cuenta de servicio, en construccion).
SCOPES_GOOGLE = [
    "https://www.googleapis.com/auth/spreadsheets.readonly",
    "https://www.googleapis.com/auth/drive.readonly",
]

# --- Mercado Publico --------------------------------------------------------
API_MP = "https://api.mercadopublico.cl/servicios/v1/publico/"

# Las unidades compradoras. NO es una base de datos: es una tabla de nombres que
# casi no cambia y que viaja con el codigo, para poder ofrecer los filtros por
# region, organismo y unidad sin consultar nada.
RUTA_CATALOGO_UNIDADES = CARPETA / "catalogo_unidades.csv"

# El ticket vive en los secrets de Streamlit ([mercadopublico] ticket = "...").
# En el computador se lee de este archivo, que esta FUERA del proyecto a
# proposito para que no pueda subirse por error a GitHub.
RUTA_TICKET_LOCAL = Path.home() / "ticket-mp.txt"

# El periodo se elige con un calendario, sin topes: cada dia es una consulta por
# organismo, asi que el largo del rango ES el costo. Se comprobo que la API
# responde al menos hasta enero de 2023 (salio «2950-28-CM23»).
DIAS_INICIALES_MP = 15
PRIMERA_FECHA_MP = date(2023, 1, 1)

# A partir de aqui la consulta deja de ser instantanea y conviene avisarlo.
CONSULTAS_QUE_DEMORAN = 120

# Columnas del resultado, en este orden. Una fila por producto comprado.
# La orden se llama "ORDEN" y no "OC" a proposito: en el panel de arriba "OC" es
# CUANTAS ordenes hubo (un contador), no el numero de una orden.
COLUMNAS_MP = [
    "FECHA", "ORDEN", "ESTADO", "UNIDAD", "ID", "PRODUCTO",
    "CANTIDAD", "PRECIO", "TOTAL", "PROVEEDOR", "RUT PROVEEDOR",
]
COLUMNAS_NUMERICAS_MP = ["CANTIDAD", "PRECIO", "TOTAL"]

# Etiqueta de las unidades a las que la API no le informa la region (ver
# cargar_catalogo_unidades).
SIN_REGION = "(sin región informada)"

# La misma tabla, pero agrupada por producto: una fila por ID, que es como ella
# trabaja en el panel de arriba. Los precios son los que PAGO la institucion en
# el rango consultado, no precios de mercado.
COLUMNAS_PANEL_MP = [
    "ID", "PRODUCTO", "MONTO", "P.MIN", "P. PROM", "P.MAX",
    "MI OFERTA", "OC", "PROVEEDORES", "COMENTARIO",
]
COLUMNAS_NUMERICAS_PANEL_MP = [
    "MONTO", "P.MIN", "P. PROM", "P.MAX", "MI OFERTA", "OC", "PROVEEDORES",
]

# Aqui solo hay dos estados posibles, porque el catalogo de ofertas dice si el
# producto esta o no esta, y nada mas. Si esta, se entiende que lo comercializa
# (CON STOCK); SIN STOCK no se puede saber desde aqui y por eso no aparece.
ESTADOS_MP = ["CON STOCK", "NO LO TENGO", "TODOS"]

# En este modulo tambien se destaca el precio, no solo la recurrencia: estar bajo
# lo que la institucion ya pago es poco frecuente (4 de 54 productos en la prueba
# con la Escuela Naval) y es el mejor argumento de venta que da la consulta.
SEÑALES_DESTACADAS_MP = ("bajo lo que pagó", "compra recurrente")


# ===========================================================================
# 2. UTILIDADES DE TEXTO, NUMEROS Y COLUMNAS
# ===========================================================================

def normalizar(texto) -> str:
    """Deja un texto comparable: sin tildes, sin espacios, sin puntos, en MAYUSCULAS.

    Ejemplos:  " P. Prom " -> "PPROM"    "Institución 2026" -> "INSTITUCION2026"
    """
    if texto is None:
        return ""
    s = unicodedata.normalize("NFKD", str(texto))
    s = "".join(ch for ch in s if not unicodedata.combining(ch))  # quita tildes
    return re.sub(r"[^A-Z0-9]", "", s.upper())                    # deja solo A-Z0-9


def a_numero(valor) -> float | None:
    """Convierte a numero lo que venga de la hoja ('60331750', '1.877', '') -> float."""
    if valor is None:
        return None
    texto = str(valor).strip()
    if not texto:
        return None
    # Deja digitos, coma, punto y signo; luego decide que separador es decimal.
    texto = re.sub(r"[^\d,.\-]", "", texto)
    if not texto or texto in {"-", ".", ","}:
        return None
    if "," in texto and "." in texto:
        texto = texto.replace(".", "").replace(",", ".")   # 1.234,56 -> 1234.56
    elif re.fullmatch(r"-?\d{1,3}(\.\d{3})+", texto) and not texto.startswith("0."):
        texto = texto.replace(".", "")                     # 60.331.750 -> 60331750
    elif texto.count(",") == 1 and len(texto.split(",")[-1]) <= 2:
        texto = texto.replace(",", ".")                    # 1234,56 -> 1234.56
    else:
        texto = texto.replace(",", "")
    try:
        return float(texto)
    except ValueError:
        return None


def pesos(valor) -> str:
    """Formatea un numero como peso chileno: 60331750 -> $60.331.750"""
    n = a_numero(valor)
    if n is None:
        return ""
    return "$" + f"{int(round(n)):,}".replace(",", ".")


# Indice inverso: variante normalizada -> nombre canonico de la columna.
INDICE_ALIAS: dict[str, str] = {}
for _canonico, _variantes in ALIAS_COLUMNAS.items():
    INDICE_ALIAS[normalizar(_canonico)] = _canonico
    for _v in _variantes:
        INDICE_ALIAS.setdefault(normalizar(_v), _canonico)


def mapear_columnas(df: pd.DataFrame) -> dict[str, int]:
    """Devuelve {nombre canonico: posicion de la columna en el DataFrame}.

    Se trabaja con posiciones (no con nombres) para soportar hojas con
    encabezados repetidos o vacios.
    """
    encontradas: dict[str, int] = {}
    for posicion, nombre in enumerate(df.columns):
        canonico = INDICE_ALIAS.get(normalizar(nombre))
        if canonico and canonico not in encontradas:   # gana la primera aparicion
            encontradas[canonico] = posicion

    # Respaldo para el ID: cualquier encabezado que empiece con "ID" sirve
    # ("ID REGIÓN CM", "ID CONVENIO REGIÓN", "ID producto"...).
    if "ID" not in encontradas:
        for posicion, nombre in enumerate(df.columns):
            if normalizar(nombre).startswith("ID"):
                encontradas["ID"] = posicion
                break

    return encontradas


def detectar_fila_encabezado(bruto: pd.DataFrame, max_filas: int = 12) -> int:
    """Ubica la fila que contiene los titulos de columna.

    Muchas hojas traen titulos, logos o filas en blanco arriba. Se elige la fila
    de las primeras `max_filas` que mas encabezados conocidos contenga.
    """
    mejor_fila, mejor_puntaje = 0, 0
    for i in range(min(max_filas, len(bruto))):
        puntaje = sum(1 for celda in bruto.iloc[i] if normalizar(celda) in INDICE_ALIAS)
        if puntaje > mejor_puntaje:
            mejor_fila, mejor_puntaje = i, puntaje
    return mejor_fila


def aplicar_encabezado(bruto: pd.DataFrame) -> pd.DataFrame:
    """Convierte una grilla sin procesar en un DataFrame con encabezados."""
    if bruto.empty:
        return bruto

    fila = detectar_fila_encabezado(bruto)
    datos = bruto.iloc[fila + 1:].copy()
    datos.columns = [str(c).strip() for c in bruto.iloc[fila]]

    # Descarta columnas sin titulo (celdas vacias o "nan" de la lectura).
    utiles = [j for j, c in enumerate(datos.columns) if c and c.lower() != "nan"]
    datos = datos.iloc[:, utiles]

    return datos.reset_index(drop=True)


# ===========================================================================
# 3. LECTURA POR ENLACE PUBLICO
# ===========================================================================

def extraer_id_hoja(url: str) -> str:
    """Saca el ID del libro desde cualquier URL de Google Sheets pegada."""
    url = (url or "").strip()
    coincidencia = re.search(r"/spreadsheets/d/([a-zA-Z0-9_-]+)", url)
    if coincidencia:
        return coincidencia.group(1)
    # Tambien se acepta que peguen solo el ID (los reales tienen ~44 caracteres).
    if re.fullmatch(r"[a-zA-Z0-9_-]{30,}", url):
        return url
    raise ValueError(
        "El enlace no parece de Google Sheets. Debe verse como:\n"
        "https://docs.google.com/spreadsheets/d/ID_DE_LA_HOJA/edit"
    )


def extraer_gid(url: str) -> str | None:
    """Saca el gid (pestaña puntual) del enlace, si viene incluido."""
    coincidencia = re.search(r"[#&?]gid=(\d+)", url or "")
    return coincidencia.group(1) if coincidencia else None


def _descargar(url: str, permitir_html: bool = False) -> bytes:
    """Descarga bytes desde una URL y traduce los errores a mensajes claros.

    `permitir_html=True` para las paginas que SI son HTML (el listado de una
    carpeta de Drive); en el resto, recibir HTML significa que Google devolvio
    la pantalla de inicio de sesion.
    """
    peticion = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    try:
        with urllib.request.urlopen(peticion, timeout=60) as respuesta:
            contenido = respuesta.read()
    except urllib.error.HTTPError as error:
        if error.code in (401, 403):
            raise PermissionError(
                "Google respondió 'sin permiso'. Abre la hoja, entra en "
                "Compartir y deja el acceso en 'Cualquier persona con el enlace' "
                "(Lector)."
            ) from error
        if error.code == 404:
            raise FileNotFoundError("No se encontró esa hoja. Revisa el enlace.") from error
        raise
    except urllib.error.URLError as error:
        raise ConnectionError(f"No se pudo conectar con Google: {error.reason}") from error

    # Si la hoja es privada, Google devuelve la pagina HTML de inicio de sesion.
    if not permitir_html and contenido[:200].lstrip().lower().startswith((b"<html", b"<!doctype")):
        raise PermissionError(
            "La hoja no es pública: Google devolvió la pantalla de inicio de sesión. "
            "Compártela con 'Cualquier persona con el enlace'."
        )
    return contenido


@st.cache_data(ttl=300, show_spinner="Leyendo el Google Sheet...")
def cargar_libro_por_enlace(url: str) -> dict[str, pd.DataFrame]:
    """Descarga el libro completo y devuelve {nombre de pestaña: grilla sin procesar}.

    Estrategia:
      1. Exportacion XLSX  -> trae TODAS las pestañas de una vez.
      2. Si falla, exportacion CSV de la pestaña indicada en el gid del enlace.
    """
    id_hoja = extraer_id_hoja(url)

    # --- 1) Libro completo en Excel -------------------------------------
    try:
        excel = _descargar(f"https://docs.google.com/spreadsheets/d/{id_hoja}/export?format=xlsx")
        hojas = pd.read_excel(io.BytesIO(excel), sheet_name=None, header=None, dtype=str)
        return {nombre: hoja.fillna("") for nombre, hoja in hojas.items()}
    except PermissionError:
        raise                      # problema de permisos: no sirve reintentar
    except Exception as error_excel:
        error_guardado = error_excel

    # --- 2) Respaldo: una sola pestaña en CSV ---------------------------
    gid = extraer_gid(url) or "0"
    csv = _descargar(
        f"https://docs.google.com/spreadsheets/d/{id_hoja}/export?format=csv&gid={gid}"
    )
    try:
        grilla = pd.read_csv(io.BytesIO(csv), header=None, dtype=str).fillna("")
    except Exception:
        raise RuntimeError(f"No se pudo leer la hoja. Detalle: {error_guardado}")
    return {f"Pestaña gid={gid}": grilla}


@st.cache_data(ttl=300, show_spinner="Conectando con la API de Google...")
def cargar_libro_por_api(credenciales_json: str, url_o_id: str) -> dict[str, pd.DataFrame]:
    """Lee el libro con gspread + google-auth (Modo 2, en construccion).

    `credenciales_json` es el contenido del archivo JSON de la cuenta de
    servicio (se recibe como texto para que Streamlit pueda cachearlo).
    """
    try:
        import gspread
        from google.oauth2.service_account import Credentials
    except ImportError as error:
        raise RuntimeError(
            "Faltan librerías del Modo 2. Instala con: pip install gspread google-auth"
        ) from error

    try:
        info = json.loads(credenciales_json)
    except json.JSONDecodeError as error:
        raise ValueError("El archivo de credenciales no es un JSON válido.") from error

    credenciales = Credentials.from_service_account_info(info, scopes=SCOPES_GOOGLE)
    cliente = gspread.authorize(credenciales)

    try:
        libro = cliente.open_by_key(extraer_id_hoja(url_o_id))
    except Exception as error:
        correo = info.get("client_email", "(sin client_email en el JSON)")
        raise PermissionError(
            "No se pudo abrir la hoja con la cuenta de servicio. Comparte la hoja "
            f"con este correo como Lector:\n{correo}\n\nDetalle: {error}"
        ) from error

    return {
        pestana.title: pd.DataFrame(pestana.get_all_values(), dtype=str).fillna("")
        for pestana in libro.worksheets()
    }


# ===========================================================================
# 4. CATALOGO DE OFERTAS SEMANALES
# ===========================================================================

def extraer_id_carpeta(url: str) -> str | None:
    """Saca el ID de una carpeta de Drive, si el enlace es de una carpeta."""
    coincidencia = re.search(r"/folders/([a-zA-Z0-9_-]+)", url or "")
    return coincidencia.group(1) if coincidencia else None


def fecha_del_nombre(nombre: str) -> tuple[int, int, int]:
    """Ultima fecha dd-mm-aaaa escrita en el nombre del archivo, para ordenar.

    "OFERTAS 11-08 AL 14-08-2026 (...)" -> (2026, 8, 14)
    """
    fechas = re.findall(r"(\d{1,2})[-/](\d{1,2})[-/](\d{4})", nombre)
    if not fechas:
        return (0, 0, 0)
    dia, mes, año = max(fechas, key=lambda f: (int(f[2]), int(f[1]), int(f[0])))
    return (int(año), int(mes), int(dia))


@st.cache_data(ttl=300, show_spinner="Buscando el catálogo de ofertas más reciente...")
def descargar_ofertas_de_carpeta(id_carpeta: str) -> tuple[str, bytes]:
    """Busca en la carpeta de Drive el archivo de ofertas mas nuevo y lo baja.

    La carpeta debe estar compartida como "cualquiera con el enlace". Se listan
    sus archivos con la vista publica de Drive (no hace falta cuenta ni API).
    """
    html = _descargar(
        f"https://drive.google.com/embeddedfolderview?id={id_carpeta}#list",
        permitir_html=True,
    ).decode("utf-8", "replace")

    entradas = re.findall(
        r'<div class="flip-entry" id="entry-([^"]+)".*?flip-entry-title">([^<]+)</div>',
        html, re.S,
    )
    if not entradas:
        raise FileNotFoundError(
            "No se pudo ver el contenido de la carpeta. Compártela con "
            "'Cualquier persona con el enlace' (Lector)."
        )

    candidatos = [(fid, nombre) for fid, nombre in entradas
                  if PATRON_OFERTAS in normalizar(nombre)]
    if not candidatos:
        disponibles = ", ".join(nombre for _, nombre in entradas[:6])
        raise FileNotFoundError(
            f"En la carpeta no hay ningún archivo con la palabra «{PATRON_OFERTAS}» "
            f"en el nombre. Encontré: {disponibles}"
        )

    candidatos.sort(key=lambda par: fecha_del_nombre(par[1]), reverse=True)
    id_archivo, nombre_archivo_ofertas = candidatos[0]
    contenido = _descargar(
        f"https://drive.google.com/uc?export=download&id={id_archivo}", permitir_html=True
    )

    # Si Drive devolvio HTML es porque el archivo es una hoja de calculo de
    # Google (no un .xlsx subido): esas se bajan por el enlace de exportacion.
    if contenido[:4] != b"PK\x03\x04":
        contenido = _descargar(
            f"https://docs.google.com/spreadsheets/d/{id_archivo}/export?format=xlsx"
        )
    return nombre_archivo_ofertas, contenido


@st.cache_data(ttl=300, show_spinner="Leyendo el catálogo de ofertas...")
def cargar_ofertas(url: str) -> tuple[dict[str, float], str]:
    """Devuelve ({ID de producto: precio oferta}, nombre de la fuente).

    Acepta las dos formas: el enlace de la CARPETA de Drive (busca sola el
    archivo de ofertas mas reciente) o el enlace directo de una hoja.
    Recorre TODAS las pestañas (ALIMENTOS, ASEO, EMERGENCIAS...) y se queda con
    las que tengan una columna de ID y una de precio.
    """
    id_carpeta = extraer_id_carpeta(url)
    if id_carpeta:
        fuente, contenido = descargar_ofertas_de_carpeta(id_carpeta)
        hojas = pd.read_excel(io.BytesIO(contenido), sheet_name=None, header=None, dtype=str)
        hojas = {nombre: hoja.fillna("") for nombre, hoja in hojas.items()}
    else:
        hojas = cargar_libro_por_enlace(url)
        fuente = "catálogo compartido por enlace"

    precios: dict[str, float] = {}
    for grilla in hojas.values():
        datos = aplicar_encabezado(grilla)
        if datos.empty:
            continue
        posiciones = mapear_columnas(datos)
        if "ID" not in posiciones or "PRECIO OFERTA" not in posiciones:
            continue
        columna_id = datos.iloc[:, posiciones["ID"]]
        columna_precio = datos.iloc[:, posiciones["PRECIO OFERTA"]]
        for id_producto, precio in zip(columna_id, columna_precio):
            clave = str(id_producto).strip()
            valor = a_numero(precio)
            if clave and valor:
                precios.setdefault(clave, valor)
    return precios, fuente


# ===========================================================================
# 5. INTELIGENCIA: EL COMENTARIO DE CADA PRODUCTO
# ===========================================================================

def meses_del_periodo(pestana: str) -> int:
    """Cuántos meses abarca la pestaña, para medir la frecuencia de compra.

    Del año en curso solo han pasado los meses corridos (en agosto, 8). Una
    pestaña de semestre son 6 y una de un año cerrado, 12.
    """
    nombre = normalizar(pestana)
    if str(datetime.now().year) in nombre:
        return max(1, datetime.now().month)
    if "TRIMESTRE" in nombre:
        return 3
    if "SEMESTRE" in nombre:
        return 6
    return 12


def construir_comentario(
    id_producto: str,
    oc,
    proveedores,
    mi_publicado,
    p_prom,
    ids_periodo_anterior: set[str],
    meses: int = 12,
) -> str:
    """Arma la frase de oportunidad juntando las señales del negocio.

    La frecuencia se mide contra los meses transcurridos del periodo: es
    recurrente cuando hay al menos una OC cada dos meses (la mitad de los meses
    corridos). Con 8 meses corridos, 4 OC o mas es recurrente.
    """
    señales: list[str] = []

    # 1) Frecuencia de compra: la columna OC cuenta las ordenes del periodo.
    n_oc = int(a_numero(oc) or 0)
    if n_oc > 0:
        cada = meses / n_oc                       # meses promedio entre compras
        if cada <= 1.3:
            ritmo = "mensual"
        elif cada <= 2.3:
            ritmo = "bimensual"
        elif cada <= 3.6:
            ritmo = "trimestral"
        elif cada <= 5.0:
            ritmo = "cuatrimestral"
        else:
            ritmo = "ocasional"

        if n_oc >= meses / 2:                     # el umbral que define recurrente
            señales.append(f"Compra recurrente: {n_oc} OC en {meses} meses ({ritmo})")
        else:
            señales.append(f"{n_oc} OC en {meses} meses: compra {ritmo}")

    # 2) El mismo ID también fue comprado en el otro período del libro.
    if id_producto and id_producto in ids_periodo_anterior:
        señales.append("También compró el período anterior")

    # 3) Competencia: cuantos proveedores se pelean ese producto.
    n_prov = a_numero(proveedores)
    if n_prov is not None:
        n_prov = int(n_prov)
        if n_prov <= 1:
            señales.append("1 solo proveedor: sin competencia")
        elif n_prov == 2:
            señales.append("2 proveedores: poca competencia")

    # 4) Tu precio contra el promedio del mercado.
    publicado, promedio = a_numero(mi_publicado), a_numero(p_prom)
    if publicado and promedio:
        diferencia = (publicado - promedio) / promedio * 100
        if diferencia <= -1:
            señales.append(f"Tu precio {abs(diferencia):.0f}% bajo el promedio")
        elif diferencia >= 1:
            señales.append(f"Tu precio {diferencia:.0f}% sobre el promedio")

    return " · ".join(señales)


# ===========================================================================
# 6. PREPARACION DE LA TABLA
# ===========================================================================

def preparar_tabla(
    bruto: pd.DataFrame,
    estado: str,
    ids_periodo_anterior: set[str],
    meses: int = 12,
) -> tuple[pd.DataFrame, list[str]]:
    """Filtra por MI ESTADO y deja las columnas finales, con MONTO y COMENTARIO.

    Devuelve (tabla, lista de avisos para mostrar en pantalla).
    """
    avisos: list[str] = []
    datos = aplicar_encabezado(bruto)
    if datos.empty:
        return pd.DataFrame(columns=COLUMNAS_FINALES), ["La pestaña seleccionada está vacía."]

    posiciones = mapear_columnas(datos)

    # --- Filtro por MI ESTADO -------------------------------------------
    if estado != "TODOS":
        if COLUMNA_ESTADO in posiciones:
            valores = datos.iloc[:, posiciones[COLUMNA_ESTADO]].map(normalizar)
            objetivo = normalizar(estado)          # CONSTOCK / SINSTOCK / NOLOTENGO
            seleccion = valores == objetivo
            if not seleccion.any():
                distintos = sorted({v for v in datos.iloc[:, posiciones[COLUMNA_ESTADO]] if str(v).strip()})
                avisos.append(
                    f"Ningún registro coincide con «{estado}». Valores encontrados en "
                    f"{COLUMNA_ESTADO}: {', '.join(distintos[:10]) or '(columna vacía)'}"
                )
            datos = datos[seleccion]
        else:
            avisos.append(
                f"No se encontró la columna «{COLUMNA_ESTADO}» en esta pestaña: "
                "se muestran todos los registros sin filtrar."
            )

    # --- Columnas de la tabla final --------------------------------------
    presentes = [c for c in COLUMNAS_FINALES if c in posiciones]
    faltantes = [c for c in COLUMNAS_FINALES if c not in posiciones and c != "COMENTARIO"]
    if faltantes:
        avisos.append("Columnas no encontradas en la hoja: " + ", ".join(faltantes))

    # Elimina las filas totalmente vacias que arrastran las hojas de calculo.
    # Se hace sobre `datos` para que siga alineado con las columnas auxiliares.
    if presentes:
        celdas = datos.iloc[:, [posiciones[c] for c in presentes]].astype(str)
        datos = datos[~celdas.apply(lambda s: s.str.strip() == "").all(axis=1)]
    datos = datos.reset_index(drop=True)

    if datos.empty or not presentes:
        return pd.DataFrame(columns=COLUMNAS_FINALES), avisos

    final = pd.DataFrame({c: datos.iloc[:, posiciones[c]].astype(str).str.strip() for c in presentes})

    # --- Comentario de oportunidad ---------------------------------------
    def columna(nombre: str) -> pd.Series:
        """Serie de una columna auxiliar, vacia si la hoja no la trae."""
        if nombre in posiciones:
            return datos.iloc[:, posiciones[nombre]].astype(str).reset_index(drop=True)
        return pd.Series([""] * len(final))

    ids = final["ID"] if "ID" in final.columns else pd.Series([""] * len(final))
    ocs = final["OC"] if "OC" in final.columns else pd.Series([""] * len(final))
    publicados = final["MI PUBLICADO"] if "MI PUBLICADO" in final.columns else pd.Series([""] * len(final))
    promedios = final["P. PROM"] if "P. PROM" in final.columns else pd.Series([""] * len(final))
    proveedores = columna(COLUMNA_PROVEEDORES)

    final["COMENTARIO"] = [
        construir_comentario(
            str(ids.iloc[i]).strip(), ocs.iloc[i], proveedores.iloc[i],
            publicados.iloc[i], promedios.iloc[i], ids_periodo_anterior, meses,
        )
        for i in range(len(final))
    ]

    # --- Montos y cantidades como numeros, no como texto ------------------
    # Asi la tabla se ordena bien (como texto, "11" caia entre "1" y "2") y el
    # formato con puntos lo pone la propia tabla al mostrarlo.
    for col in COLUMNAS_NUMERICAS:
        if col in final.columns:
            final[col] = pd.array(
                [None if a_numero(v) is None else int(round(a_numero(v))) for v in final[col]],
                dtype="Int64",
            )

    return final.reindex(columns=[c for c in COLUMNAS_FINALES if c in final.columns]), avisos


def ids_de_pestana(bruto: pd.DataFrame) -> set[str]:
    """Conjunto de IDs de una pestaña, para detectar la compra recurrente."""
    datos = aplicar_encabezado(bruto)
    if datos.empty:
        return set()
    posiciones = mapear_columnas(datos)
    if "ID" not in posiciones:
        return set()
    return {str(v).strip() for v in datos.iloc[:, posiciones["ID"]] if str(v).strip()}


# ===========================================================================
# 7. EXPORTACION
# ===========================================================================

def a_excel(tabla: pd.DataFrame, nombre_hoja: str = "Oportunidades") -> bytes:
    """Convierte la tabla en un .xlsx, con los montos como numeros (no texto)."""
    numerica = tabla.copy()
    for col in ["MONTO", "P.MIN", "P. PROM", "P.MAX", "MI PUBLICADO", "OC"]:
        if col in numerica.columns:
            numerica[col] = numerica[col].map(a_numero)

    memoria = io.BytesIO()
    with pd.ExcelWriter(memoria, engine="openpyxl") as escritor:
        numerica.to_excel(escritor, index=False, sheet_name=nombre_hoja)
        hoja = escritor.sheets[nombre_hoja]
        anchos = {"ID": 12, "PRODUCTO": 60, "MONTO": 16, "P.MIN": 12, "P. PROM": 12,
                  "P.MAX": 12, "MI PUBLICADO": 14, "OC": 8, "COMENTARIO": 70,
                  # Columnas del modulo de Mercado Publico.
                  "FECHA": 12, "ORDEN": 20, "ESTADO": 20, "UNIDAD": 34,
                  "CANTIDAD": 11, "PRECIO": 14, "TOTAL": 16,
                  "PROVEEDOR": 34, "RUT PROVEEDOR": 15}
        for i, col in enumerate(numerica.columns, start=1):
            hoja.column_dimensions[hoja.cell(row=1, column=i).column_letter].width = anchos.get(col, 18)
    return memoria.getvalue()


def _limpiar_pdf(texto) -> str:
    """fpdf con fuentes base escribe en latin-1: cambia los signos que no existen."""
    reemplazos = {"—": "-", "–": "-", "•": "-", "“": '"', "”": '"', "’": "'", "…": "..."}
    salida = str(texto)
    for viejo, nuevo in reemplazos.items():
        salida = salida.replace(viejo, nuevo)
    return salida.encode("latin-1", "replace").decode("latin-1")


TITULO_PDF = "ID DISPONIBLE SEGÚN HISTÓRICO"


def numero_cotizacion_sugerido() -> str:
    """Correlativo con el mismo formato que usa Serling: 3007-001 (dia+mes)."""
    return f"{datetime.now():%d%m}-001"


def _barra(pdf: FPDF, texto: str, alto: float = 9, tamaño: float = 11,
           alineacion: str = "C") -> None:
    """Franja azul de ancho completo con el texto en blanco."""
    pdf.set_fill_color(*AZUL_BARRA)
    pdf.set_text_color(255, 255, 255)
    pdf.set_font("Helvetica", "B", tamaño)
    pdf.cell(0, alto, _limpiar_pdf(texto), align=alineacion, fill=True,
             new_x="LMARGIN", new_y="NEXT")


def a_pdf(tabla: pd.DataFrame, institucion: str, contacto: str, linea_producto: str,
          numero: str, precios_oferta: dict[str, float]) -> bytes:
    """Genera el documento 'ID disponible según histórico'.

    Respeta el formato de cotizacion que Comercial Emergenza ya usa (franja
    azul con el titulo, datos de la empresa, bloque ENVIAR A y franja de
    despacho), pero SIN cantidades, precios totales ni totalizacion: es un
    listado de ID disponibles, no una cotizacion cerrada.
    """
    pdf = FPDF(orientation="P", unit="mm", format="A4")
    pdf.set_margins(12, 10, 12)
    pdf.set_auto_page_break(auto=True, margin=15)
    pdf.add_page()

    # --- 1) Franja del titulo ---------------------------------------------
    _barra(pdf, TITULO_PDF, alto=10, tamaño=13)
    pdf.ln(3)

    # --- 2) Datos de la empresa (izquierda) y del documento (derecha) ------
    y_bloque = pdf.get_y()
    if RUTA_LOGO.exists():
        pdf.image(str(RUTA_LOGO), x=12, y=y_bloque, w=34)

    # El logo mide ~19 mm de alto con w=34: el texto arranca despues de eso.
    pdf.set_xy(12, y_bloque + 21)
    pdf.set_font("Helvetica", "", 7.5)
    pdf.set_text_color(60, 60, 60)
    for linea in (EMPRESA["razon"], EMPRESA["rut"], EMPRESA["direccion"],
                  f"Contacto: {FIRMA['fono']}",
                  f"{FIRMA['correo']} / {FIRMA['correo_alt']}"):
        pdf.set_x(12)
        pdf.cell(120, 3.8, _limpiar_pdf(linea), new_x="LMARGIN", new_y="NEXT")

    validez = datetime.now() + pd.Timedelta(days=60)
    datos_documento = [
        ("N° Cotización", numero.strip() or numero_cotizacion_sugerido()),
        ("Fecha", f"{datetime.now():%d-%m-%Y}"),
        ("Validez", f"{validez:%d-%m-%Y}"),
    ]
    pdf.set_font("Helvetica", "", 8)
    for i, (etiqueta, valor) in enumerate(datos_documento):
        pdf.set_xy(135, y_bloque + 21 + i * 4.5)
        pdf.set_text_color(60, 60, 60)
        pdf.cell(32, 4, _limpiar_pdf(etiqueta))
        pdf.set_text_color(20, 20, 20)
        pdf.cell(31, 4, _limpiar_pdf(valor), align="R")

    # Linea de sangria entre los correos y la franja ENVIAR A.
    pdf.set_y(max(pdf.get_y() + 5, y_bloque + 45))

    # --- 3) A quien va dirigido -------------------------------------------
    _barra(pdf, "  ENVIAR A:", alto=6, tamaño=8.5, alineacion="L")
    pdf.ln(3)
    pdf.set_font("Helvetica", "B", 8.5)
    pdf.set_text_color(60, 60, 60)
    for etiqueta, valor in (("CLIENTE:", institucion), ("PRODUCTO", linea_producto)):
        if not str(valor).strip():
            continue
        pdf.set_x(20)
        pdf.set_font("Helvetica", "B", 8.5)
        pdf.set_text_color(90, 90, 90)
        pdf.cell(40, 5, _limpiar_pdf(etiqueta))
        pdf.set_font("Helvetica", "", 9)
        pdf.set_text_color(20, 20, 20)
        pdf.cell(0, 5, _limpiar_pdf(str(valor).strip().upper()),
                 new_x="LMARGIN", new_y="NEXT")
    pdf.ln(3)

    # --- 4) Tabla de productos --------------------------------------------
    # Solo ID, articulo y el precio cuando el producto esta en la oferta de la
    # semana: este documento muestra disponibilidad, no cotiza cantidades.
    pdf.set_fill_color(255, 255, 255)      # si no, las filas heredan el azul de las franjas
    pdf.set_text_color(30, 30, 30)
    pdf.set_font("Helvetica", "", 8)
    with pdf.table(
        col_widths=(24, 132, 30),
        text_align=("CENTER", "LEFT", "CENTER"),
        headings_style=FontFace(emphasis="BOLD", color=(255, 255, 255), fill_color=AZUL_TABLA),
        cell_fill_color=(238, 243, 248),
        cell_fill_mode="ROWS",
        line_height=4.5,
        padding=1.2,
        borders_layout="MINIMAL",
    ) as tabla_pdf:
        fila = tabla_pdf.row()
        for titulo in ("ID", "ARTÍCULO", "PRECIO OFERTA"):
            fila.cell(_limpiar_pdf(titulo))

        for _, registro in tabla.iterrows():
            id_producto = str(registro.get("ID", "")).strip()
            precio = precios_oferta.get(id_producto)
            fila = tabla_pdf.row()
            fila.cell(_limpiar_pdf(id_producto))
            fila.cell(_limpiar_pdf(registro.get("PRODUCTO", "")))
            fila.cell(_limpiar_pdf(pesos(precio) if precio else "-"))

    # --- 5) Pie ------------------------------------------------------------
    pdf.ln(4)
    _barra(pdf, "DESPACHO INCLUIDO", alto=7, tamaño=9.5)
    pdf.ln(3)
    pdf.set_font("Helvetica", "I", 7.5)
    pdf.set_text_color(120, 130, 140)
    pdf.multi_cell(0, 3.6, _limpiar_pdf(
        "ID disponibles en Convenio Marco seleccionados según el histórico de compras "
        f"de {institucion.strip() or 'la institución'}. Precios de la oferta semanal "
        "vigente, sujetos a disponibilidad de stock; los productos sin precio se "
        f"cotizan a solicitud. Contacto: {FIRMA['nombre']}, {FIRMA['cargo']}, "
        f"{FIRMA['fono']}."
    ))

    return bytes(pdf.output())


def nombre_pdf(institucion: str, numero: str) -> str:
    """Nombre del PDF: «Id Convenio Marco, Institución, Correlativo.pdf»."""
    partes = [
        "Id Convenio Marco",
        institucion.strip() or "Institución",
        numero.strip() or numero_cotizacion_sugerido(),
    ]
    limpias = [re.sub(r'[\\/:*?"<>|]', "", parte).strip() for parte in partes]
    return ", ".join(limpias) + ".pdf"


def nombre_archivo(informe: str, pestana: str, estado: str, extension: str) -> str:
    """Arma un nombre de archivo limpio para las descargas."""
    partes = [informe, pestana, estado]
    base = "_".join(re.sub(r"[^\w\s-]", "", p).strip().replace(" ", "-") for p in partes)
    return f"{base}.{extension}"


# ===========================================================================
# 8. CORREO LISTO PARA COPIAR
# ===========================================================================

def urls_enviador() -> dict[str, str]:
    """{cuenta: dirección del script enviador} desde los secrets de Streamlit.

    Cada cuenta tiene su propio Apps Script (ver enviador-para-copiar.txt), que
    envía el correo desde esa misma cuenta de Google. No hay contraseñas de
    correo de por medio. En Streamlit ▸ Manage app ▸ Settings ▸ Secrets:

        [correo]
        clave_envio = "la misma clave que pusiste en los dos scripts"

        [correo.scripts]
        "svera@emergenza.cl" = "https://script.google.com/macros/s/XXXX/exec"
        "serlingvera@gmail.com" = "https://script.google.com/macros/s/YYYY/exec"
    """
    try:
        return {str(cuenta): str(url).strip()
                for cuenta, url in dict(st.secrets["correo"]["scripts"]).items()
                if str(url).strip()}
    except Exception:
        return {}


def clave_envio() -> str:
    """Clave que hay que escribir en la app para poder enviar (app publica)."""
    try:
        return str(st.secrets["correo"]["clave_envio"])
    except Exception:
        return ""


def cuerpo_html(cuerpo: str, remitente: str, con_logo: bool) -> str:
    """Versión con formato del correo, con la firma al pie como la de Gmail."""
    parrafos = [p.strip() for p in cuerpo.split("Saludos cordiales,")[0].split("\n\n") if p.strip()]
    texto = "".join(f"<p style='margin:0 0 12px'>{p}</p>" for p in parrafos)
    logo = ("<img src='cid:logoemergenza' alt='Comercial Emergenza' "
            "style='width:104px;display:block;margin-bottom:6px'>") if con_logo else ""
    return f"""
    <div style="font-family:Tahoma,Geneva,Verdana,sans-serif;font-size:14px;color:#222">
      {texto}
      <p style="margin:0 0 12px">Saludos cordiales,</p>
      <table cellpadding="0" cellspacing="0" style="border-top:2px solid #C1303F;padding-top:10px">
        <tr>
          <td style="padding-right:14px;vertical-align:middle">{logo}</td>
          <td style="vertical-align:middle;font-size:13px;line-height:1.45;color:#444">
            <b style="color:#24333F;font-size:14px">{FIRMA['nombre']}</b><br>
            {FIRMA['cargo']}<br>{FIRMA['empresa']}<br>{FIRMA['fono']}<br>
            <a href="mailto:{remitente}" style="color:#C1303F">{remitente}</a>
          </td>
        </tr>
      </table>
    </div>
    """


def armar_envio(remitente: str, para: str, copia: str, asunto: str, cuerpo: str,
                pdf: bytes, nombre_adjunto: str, clave: str) -> dict:
    """Paquete de datos que recibe el Apps Script (el PDF viaja como texto)."""
    hay_logo = RUTA_LOGO.exists()
    envio = {
        "clave": clave,
        "para": para.strip(),
        "cc": copia.strip(),
        "asunto": asunto,
        "cuerpo": cuerpo,
        "cuerpoHtml": cuerpo_html(cuerpo, remitente, hay_logo),
        "nombrePdf": nombre_adjunto,
        "pdfBase64": base64.b64encode(pdf).decode(),
        "nombreRemitente": FIRMA["nombre"],
    }
    if hay_logo:
        envio["logoBase64"] = base64.b64encode(RUTA_LOGO.read_bytes()).decode()
    return envio


def enviar_por_script(url: str, envio: dict) -> dict:
    """Manda el correo a través del Apps Script de esa cuenta.

    El script responde en JSON: {"ok": true, "cuenta": ..., "para": ...} o
    {"ok": false, "error": ...}.
    """
    peticion = urllib.request.Request(
        url,
        data=json.dumps(envio).encode("utf-8"),
        headers={"Content-Type": "application/json", "User-Agent": "Mozilla/5.0"},
    )
    try:
        with urllib.request.urlopen(peticion, timeout=90) as respuesta:
            contenido = respuesta.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as error:
        raise RuntimeError(
            f"El enviador respondió con un error {error.code}. Revisa que la "
            "implementación esté como «Ejecutar como: Yo» y «Quién tiene acceso: "
            "Cualquier persona»."
        ) from error
    except urllib.error.URLError as error:
        raise ConnectionError(f"No se pudo contactar al enviador: {error.reason}") from error

    try:
        return json.loads(contenido)
    except json.JSONDecodeError:
        raise RuntimeError(
            "El enviador no respondió como se esperaba. Suele pasar cuando la "
            "dirección no termina en /exec o cuando falta implementar una versión "
            "nueva del script."
        )


def enlace_gmail(remitente: str, para: str, copia: str, asunto: str, cuerpo: str) -> str:
    """Enlace que abre Gmail con el correo ya redactado en la cuenta elegida.

    `authuser` es lo que hace que Gmail lo abra desde svera@emergenza.cl o
    desde serlingvera@gmail.com. El PDF se adjunta a mano: ninguna pagina web
    puede adjuntar archivos a Gmail por seguridad del navegador.
    """
    partes = [
        f"authuser={quote(remitente)}",
        "view=cm", "fs=1",
        f"to={quote(para.strip())}",
        f"su={quote(asunto)}",
        f"body={quote(cuerpo)}",
    ]
    if copia.strip():
        partes.append(f"cc={quote(copia.strip())}")
    return "https://mail.google.com/mail/u/?" + "&".join(partes)


# --- Para decidir si el saludo va en masculino o femenino -------------------
# Tratamientos que ya traen el genero puesto.
TRATAMIENTOS = {
    "SR": "M", "SENOR": "M", "DON": "M", "DR": "M", "DOCTOR": "M", "JEFE": "M",
    "DIRECTOR": "M", "ENCARGADO": "M", "ADMINISTRADOR": "M",
    "SRA": "F", "SENORA": "F", "SRTA": "F", "SENORITA": "F", "DONA": "F",
    "DRA": "F", "DOCTORA": "F", "JEFA": "F", "DIRECTORA": "F", "ENCARGADA": "F",
    "ADMINISTRADORA": "F", "CAPITANA": "F", "SARGENTA": "F",
}

# Grados y cargos sin genero: se saltan para buscar el nombre que viene despues.
# Importa tenerlos completos: "Guardiamarina" termina en A y "Subteniente" en E,
# asi que sin esta lista el saludo se equivocaria de genero.
PALABRAS_NEUTRAS = {
    # Armada
    "GRUMETE", "MARINERO", "CONTRAMAESTRE", "GUARDIAMARINA", "SUBTENIENTE",
    "CORBETA", "FRAGATA", "NAVIO", "CONTRAALMIRANTE", "VICEALMIRANTE",
    "ALMIRANTE",
    # Ejercito y comunes a las dos ramas
    "SOLDADO", "CABO", "SARGENTO", "SUBOFICIAL", "ALFEREZ", "TENIENTE",
    "CAPITAN", "MAYOR", "COMANDANTE", "CORONEL", "GENERAL", "BRIGADIER",
    "OFICIAL", "PRIMERO", "SEGUNDO", "TERCERO", "PRIMER",
    # Civiles
    "ING", "INGENIERO", "INGENIERA", "CONTADOR", "CONTADORA", "ABOGADO",
    "ABOGADA", "DE", "DEL", "LA", "LOS", "LAS",
}

# Nombres que la regla de la ultima letra no acierta.
NOMBRES_M = {
    "JOSE", "NICOLAS", "ANDRES", "MATIAS", "ELIAS", "TOMAS", "LUCAS", "JESUS",
    "ISAIAS", "MACIAS", "LUIS", "JUAN", "CRISTIAN", "CHRISTIAN", "SEBASTIAN",
    "BASTIAN", "IVAN", "NELSON", "WILSON", "VICTOR", "HECTOR", "NESTOR",
    "OSCAR", "OMAR", "CESAR", "JAVIER", "MANUEL", "MIGUEL", "DANIEL",
    "GABRIEL", "RAFAEL", "ARIEL", "ISRAEL", "ISMAEL", "JOEL", "ABEL", "ANGEL",
    "EZEQUIEL", "EMANUEL", "JORGE", "FELIPE", "ENRIQUE", "VICENTE", "CLEMENTE",
    "RENE", "CARLOS", "MARCOS", "RUBEN", "EFRAIN", "JOAQUIN", "AGUSTIN",
    "MARTIN", "RAMON", "SIMON", "GERMAN", "FABIAN", "DAMIAN", "JULIAN",
    "ADRIAN", "KEVIN", "BRAYAN", "JONATHAN", "ALEXIS", "YERKO", "ARTURO",
    "HERNAN", "ESTEBAN", "GASTON", "MAURICIO", "PATRICIO", "IGNACIO",
}
NOMBRES_F = {
    "CARMEN", "ISABEL", "RAQUEL", "INES", "BEATRIZ", "RUTH", "ESTER", "ESTHER",
    "JUDITH", "MERCEDES", "DOLORES", "PILAR", "SOLEDAD", "MARISOL", "MARIBEL",
    "ROCIO", "BELEN", "JAZMIN", "YASMIN", "KAREN", "INGRID", "ASTRID",
    "MIRIAM", "MYRIAM", "JACQUELINE", "KATHERINE", "NICOLE", "MICHELLE",
    "DENISSE", "ELIZABETH", "YANET", "JANET", "MILLARAY", "AYELEN", "YASNA",
    "LISSETTE", "DAMARIS", "ABIGAIL", "NOEMI", "SARAI", "MARLEN", "MARLENE",
    "MARIA", "MARIELA", "FABIOLA", "JAVIERA", "PAULINA", "VERONICA",
    # Terminan en "o" pero son de mujer:
    "LORETO", "CONSUELO", "ROSARIO", "AMPARO", "SOCORRO",
}

# Cuando el contacto es un área y no una persona, no se arriesga el género.
PALABRAS_NO_NOMBRE = {
    "DEPARTAMENTO", "DEPTO", "CENTRAL", "UNIDAD", "OFICINA", "SECCION",
    "ABASTECIMIENTO", "ADQUISICIONES", "COMPRAS", "FINANZAS", "LOGISTICA",
    "ALMACEN", "BODEGA", "CASINO", "RANCHO", "INTENDENCIA", "TESORERIA",
    "CONTABILIDAD", "EQUIPO", "AREA", "SUBDIRECCION", "DIRECCION",
}


def genero_nombre(contacto: str) -> str:
    """Devuelve "M", "F" o "" (cuando no se puede determinar).

    Manda el PRIMER nombre, no el segundo: "María José" es de mujer y "José
    María" de hombre. Un tratamiento explícito (Sra., Don, Directora...) gana
    por sobre todo lo demás.
    """
    palabras = [normalizar(p) for p in str(contacto).split() if normalizar(p)]

    # 1) Tratamientos: si aparece uno, ya está resuelto.
    for palabra in palabras:
        if palabra in TRATAMIENTOS:
            return TRATAMIENTOS[palabra]

    # 2) El primer nombre de verdad decide (los grados militares se saltan).
    for palabra in palabras:
        if palabra in PALABRAS_NEUTRAS or len(palabra) < 3:
            continue
        if palabra in PALABRAS_NO_NOMBRE:
            return ""                      # es un área, no una persona
        if palabra in NOMBRES_M:
            return "M"
        if palabra in NOMBRES_F:
            return "F"
        if palabra.endswith("A"):
            return "F"
        if palabra.endswith("O"):
            return "M"
        return ""                          # otras terminaciones: no arriesgar
    return ""


def saludo_correo(contacto: str) -> str:
    """Saludo del correo. Sin nombre o con genero dudoso: «Estimados,»."""
    nombre = str(contacto).strip()
    genero = genero_nombre(nombre) if nombre else ""
    if genero == "M":
        return f"Estimado {nombre}, buen día."
    if genero == "F":
        return f"Estimada {nombre}, buen día."
    return "Estimados, buen día."


def nombre_institucion(pestana: str) -> str:
    """Nombre de cliente a partir del nombre de la pestaña, sin el periodo.

    "Escuela Naval 2026" y "Escuela Naval Ultimo Semestre 2" -> "Escuela Naval".
    (El año y el semestre son la forma de Serling de nombrar las pestañas, no
    parte del nombre de la institución.)
    """
    texto = str(pestana).strip()
    texto = re.sub(r"(?i)\b(ultimo|último|primer|segundo|1er|2do)?\s*"
                   r"(semestre|trimestre|periodo|período)\b", " ", texto)
    texto = re.sub(r"\b(19|20)\d{2}\b", " ", texto)     # años completos
    texto = re.sub(r"\s+\d{1,3}\s*$", " ", texto)       # restos del nombre recortado
    return re.sub(r"\s{2,}", " ", texto).strip(" -–—,") or str(pestana).strip()


def texto_correo(contacto: str, institucion: str, cantidad: int, remitente: str) -> str:
    """Redacta el correo con el mismo tono de los envios semanales.

    La firma lleva el correo desde el que se va a enviar, para que el comprador
    responda a esa misma casilla.
    """
    de_quien = f" de {institucion.strip()}" if institucion.strip() else ""
    return "\n".join([
        saludo_correo(contacto),
        "",
        f"Le saluda {FIRMA['nombre']} de {FIRMA['empresa']}.",
        "",
        f"Le comparto los ID disponibles en Convenio Marco según sus últimas compras{de_quien}. "
        f"Son {cantidad} productos que podemos entregarle, con el detalle y los precios "
        "de la oferta vigente en el archivo adjunto.",
        "",
        "Contamos con stock permanente y flexibilidad para entregas parceladas.",
        "",
        "Si requiere ajustar cantidades o agregar productos, respóndame este correo "
        "con el detalle y le respondo al instante.",
        "",
        "Saludos cordiales,",
        "",
        FIRMA["nombre"],
        FIRMA["cargo"],
        FIRMA["empresa"],
        FIRMA["fono"],
        remitente.strip() or FIRMA["correo"],
    ])


# ===========================================================================
# 9. MERCADO PUBLICO: CONSULTA EN VIVO
# ===========================================================================
#
# Sin base de datos y sin nada corriendo de fondo: se consulta al momento.
#
#   1. `catalogo_unidades.csv` da los filtros (region, organismo, unidad).
#   2. Se barre dia por dia el listado de ordenes, SIEMPRE filtrado por
#      organismo: el listado del dia completo son ~16.000 ordenes y 2 MB, y
#      filtrado por organismo son decenas y 10 KB. Se comprobo que devuelve
#      exactamente las mismas ordenes de la unidad que filtrar el dia entero.
#   3. Se pide el detalle solo de las ordenes que calzan (decenas, no miles).
#
# OJO CON LAS FECHAS (comprobado el 17-08-2026, y no es lo que uno supone):
# `fecha=DDMMAAAA` NO es la fecha de creacion de la orden, es el dia en que la
# orden tuvo movimiento. Barriendo 6 dias de 4 unidades de la Armada salieron 43
# ordenes, pero solo 6 estaban creadas en esos dias: habia 15 de septiembre y
# octubre de 2025. Por eso el resultado trae la fecha REAL de cada orden y se
# puede filtrar por ella; y por eso el barrido no garantiza traer todas las
# ordenes creadas ayer (si su movimiento cae manana, aparece manana).

def ticket_mp() -> str:
    """El ticket de la API. En la nube sale de los secrets; en el PC, del archivo."""
    try:
        anotado = st.secrets["mercadopublico"]["ticket"]
        if str(anotado).strip():
            return str(anotado).strip()
    except Exception:
        pass
    if RUTA_TICKET_LOCAL.exists():
        return RUTA_TICKET_LOCAL.read_text(encoding="utf-8-sig").strip()
    return ""


def consultar_mp(recurso: str) -> dict:
    """Una consulta a la API, con reintentos.

    El ticket viaja pegado en la URL, asi que la URL NO puede aparecer en ningun
    mensaje de error: la app es publica y se veria en pantalla. Por eso todos los
    errores se vuelven a levantar con un texto propio.

    El 429 ("peticiones simultaneas") es esporadico porque la API atiende una
    consulta a la vez; se resuelve reintentando con una espera corta.
    """
    ticket = ticket_mp()
    if not ticket:
        raise RuntimeError(
            "Falta el ticket de la API de Mercado Público. Se anota en "
            "Streamlit ▸ Manage app ▸ Settings ▸ Secrets así:\n\n"
            '[mercadopublico]\nticket = "TU-TICKET"'
        )

    separador = "&" if "?" in recurso else "?"
    url = f"{API_MP}{recurso}{separador}ticket={ticket}"
    espera = 1.5
    for intento in range(4):
        try:
            peticion = urllib.request.Request(url, headers={"User-Agent": TITULO_APP})
            with urllib.request.urlopen(peticion, timeout=90) as respuesta:
                return json.loads(respuesta.read().decode("utf-8"))
        except urllib.error.HTTPError as error:
            # El 429 («peticiones simultaneas») y los 500/502/503 (la API
            # saturada) son pasajeros: se reintentan igual que en el bodeguero.
            # Antes el 500 cortaba la consulta al primer intento.
            if error.code in (429, 500, 502, 503) and intento < 3:
                time.sleep(espera)
                espera *= 2
                continue
            if error.code == 429:
                raise RuntimeError(
                    "La API está recibiendo dos consultas a la vez con el mismo "
                    "ticket. Espera un momento y vuelve a consultar."
                ) from None
            if error.code in (500, 502, 503):
                raise RuntimeError(
                    "La API de Mercado Público no está respondiendo bien en este "
                    "momento. Puede ser que se hayan agotado las 10.000 consultas "
                    "del día: prueba de nuevo más tarde o con un período más corto."
                ) from None
            raise RuntimeError(
                f"La API de Mercado Público respondió con el error {error.code}. "
                "Si se repite, revisa que el ticket siga vigente."
            ) from None
        except (urllib.error.URLError, TimeoutError):
            if intento < 3:
                time.sleep(espera)
                espera *= 2
                continue
            raise RuntimeError(
                "No se pudo conectar con la API de Mercado Público. Revisa tu conexión."
            ) from None
        except json.JSONDecodeError:
            raise RuntimeError(
                "La API de Mercado Público devolvió una respuesta ilegible."
            ) from None
    raise RuntimeError("No se pudo consultar la API de Mercado Público.")


@st.cache_data(ttl=1800, show_spinner=False)
def ordenes_del_dia(fecha_api: str, organismo: str) -> list[dict]:
    """Ordenes con movimiento un dia en un organismo. Solo trae codigo y nombre."""
    datos = consultar_mp(f"ordenesdecompra.json?fecha={fecha_api}&CodigoOrganismo={organismo}")
    return datos.get("Listado") or []


@st.cache_data(ttl=3600, show_spinner=False)
def detalle_orden(codigo: str) -> dict:
    """Detalle de una orden: comprador, proveedor, productos, cantidades y precios.

    OJO: el detalle se pide al MISMO `ordenesdecompra.json` con `codigo`. El
    `OrdenCompra.json` que aparece en la documentacion oficial da 404.
    """
    datos = consultar_mp(f"ordenesdecompra.json?codigo={codigo}")
    listado = datos.get("Listado") or []
    return listado[0] if listado else {}


COLUMNAS_CATALOGO = ["codigo_unidad", "nombre_unidad", "codigo_organismo",
                     "nombre_organismo", "region", "comuna", "oc_convenio_marco"]


# ---------------------------------------------------------------------------
# LA BODEGA: lo que el bodeguero dejo descargado
# ---------------------------------------------------------------------------
# `bodeguero.py` corre de madrugada en GitHub y deja aqui las ordenes ya
# bajadas. Leer de la bodega es instantaneo y no gasta ni una consulta del
# ticket; consultar en vivo tomaba minutos.
#
# La app funciona con bodega y sin ella: mientras se va llenando, lo que no
# alcanza a cubrir se sigue consultando en vivo como antes.

RUTA_BODEGA = CARPETA / "bodega"


def estado_bodega() -> dict:
    """Que dias tiene la bodega y cuando se actualizo por ultima vez."""
    archivo = RUTA_BODEGA / "estado.json"
    if not archivo.exists():
        return {"mapa": [], "detalle": [], "actualizado": None}
    try:
        return json.loads(archivo.read_text(encoding="utf-8"))
    except Exception:
        return {"mapa": [], "detalle": [], "actualizado": None}


def _meses_del_rango(desde: date, hasta: date) -> list[str]:
    """«2026-06», «2026-07», «2026-08»: los archivos que hay que abrir."""
    meses, cursor = [], date(desde.year, desde.month, 1)
    while cursor <= hasta:
        meses.append(f"{cursor:%Y-%m}")
        cursor = date(cursor.year + (cursor.month == 12),
                      cursor.month % 12 + 1, 1)
    return meses


@st.cache_data(show_spinner=False)
def leer_bodega(capa: str, meses: tuple[str, ...], sello: str) -> pd.DataFrame:
    """Lee los archivos mensuales de una capa. `sello` invalida la cache."""
    partes = []
    for mes in meses:
        archivo = RUTA_BODEGA / capa / f"{mes}.parquet"
        if archivo.exists():
            partes.append(pd.read_parquet(archivo))
    if not partes:
        return pd.DataFrame()
    return pd.concat(partes, ignore_index=True)


def sello_bodega() -> str:
    """Cambia cuando el bodeguero deja datos nuevos, para soltar la cache."""
    return str(estado_bodega().get("actualizado") or "vacia")


def dias_cubiertos(desde: date, hasta: date) -> tuple[int, int]:
    """(dias del rango que la bodega tiene con detalle, dias del rango)."""
    listos = set(estado_bodega().get("detalle") or [])
    dias = dias_del_barrido(desde, hasta)
    return sum(1 for d in dias if d.isoformat() in listos), len(dias)


def compras_desde_bodega(unidades: pd.DataFrame, desde: date,
                         hasta: date) -> pd.DataFrame:
    """Las compras guardadas, en el mismo formato que devuelve la consulta viva."""
    detalle = leer_bodega("detalle", tuple(_meses_del_rango(desde, hasta)),
                          sello_bodega())
    if detalle.empty:
        return pd.DataFrame(columns=COLUMNAS_MP)

    codigos = set(unidades["codigo_unidad"])
    nombres = dict(zip(unidades["codigo_unidad"], unidades["nombre_unidad"]))
    # Se filtra por el DIA DEL BARRIDO, no por la fecha de creacion: es lo mismo
    # que hace la consulta en vivo, que barre dias y despues deja filtrar por la
    # fecha real. Filtrando por creacion no salia nada, porque las ordenes que
    # la API lista un dia casi siempre se crearon antes.
    dias_barridos = pd.to_datetime(detalle["dia"], errors="coerce").dt.date
    dentro = dias_barridos.between(desde, hasta)
    suyas = detalle["unidad"].isin(codigos)
    elegidas = detalle[dentro.values & suyas.values].copy()
    if elegidas.empty:
        return pd.DataFrame(columns=COLUMNAS_MP)

    tabla = pd.DataFrame({
        "FECHA": pd.to_datetime(elegidas["fecha"], errors="coerce").dt.date,
        "ORDEN": elegidas["orden"].astype(str),
        "ESTADO": elegidas["estado"].astype(str),
        "UNIDAD": [nombres.get(u, u) for u in elegidas["unidad"]],
        "ID": elegidas["id_producto"].astype(str),
        "PRODUCTO": elegidas["producto"].astype(str),
        "CANTIDAD": elegidas["cantidad"],
        "PRECIO": elegidas["precio"],
        "TOTAL": elegidas["total"],
        "PROVEEDOR": elegidas["proveedor"].astype(str),
        "RUT PROVEEDOR": elegidas["rut_proveedor"].astype(str),
    })
    for columna in COLUMNAS_NUMERICAS_MP:
        tabla[columna] = _numeros_de_columna(tabla[columna])
    return (tabla.sort_values(["ORDEN"], ascending=False)
            .sort_values("FECHA", ascending=False, na_position="last", kind="stable")
            .reset_index(drop=True))


def resumen_bodega(tabla: pd.DataFrame, desde: date, hasta: date,
                   detalle: pd.DataFrame | None = None) -> dict:
    """El mismo resumen que arma la consulta viva, pero sin gastar consultas."""
    fechas = [f for f in tabla["FECHA"] if f] if len(tabla) else []
    en_periodo = [bool(f and desde <= f <= hasta) for f in tabla["FECHA"]] if len(tabla) else []
    contacto = ""
    if detalle is not None and not detalle.empty and "contacto" in detalle:
        posibles = detalle["contacto"][detalle["contacto"].astype(str).str.strip() != ""]
        if not posibles.empty:
            contacto = posibles.mode().iloc[0]
    return {
        "consultas": 0,
        "dias": (hasta - desde).days + 1,
        "organismos": 0,
        "ordenes": int(tabla["ORDEN"].nunique()) if len(tabla) else 0,
        "ordenes_en_periodo": int(tabla.loc[en_periodo, "ORDEN"].nunique()) if len(tabla) else 0,
        "desde_real": min(fechas, default=None),
        "hasta_real": max(fechas, default=None),
        "contacto": contacto,
        "de_bodega": True,
    }


def cargar_catalogo_unidades() -> pd.DataFrame:
    """Las unidades que compran por Convenio Marco (codigo, nombre, region...).

    OJO: la comprobacion de que el archivo existe va AFUERA de la cache, y la
    lectura se guarda con la fecha del archivo como llave. Si no, pasa lo que
    paso al publicar: la app arranco antes de que el CSV estuviera subido,
    guardo "no existe" en una cache sin vencimiento y siguio diciendo que
    faltaba el archivo aunque ya estaba. Con la fecha como llave, ademas, basta
    con reemplazar el CSV para que la app lea el nuevo.
    """
    if RUTA_CATALOGO_UNIDADES.exists():
        catalogo = leer_catalogo_unidades(RUTA_CATALOGO_UNIDADES.stat().st_mtime)
    else:
        catalogo = pd.DataFrame(columns=COLUMNAS_CATALOGO)
    return con_unidades_de_bodega(catalogo, sello_bodega())


@st.cache_data(show_spinner=False)
def con_unidades_de_bodega(catalogo: pd.DataFrame, sello: str) -> pd.DataFrame:
    """Suma al catalogo las unidades que descubrio el bodeguero.

    El CSV se armo con 8 dias habiles y trae 2.103 unidades; la bodega, con 594
    dias, encontro 4.293. Se combinan en vez de reemplazar porque el bodeguero
    va averiguando los nombres de a poco: mientras no sepa uno, manda el CSV.

    La frecuencia de compra tambien se recalcula: el CSV la medio sobre 8 dias y
    la bodega la mide sobre todo lo descargado, que es muchisimo mas fiel.
    """
    unidades = RUTA_BODEGA / "unidades.parquet"
    if not unidades.exists():
        return catalogo

    try:
        nuevas = pd.read_parquet(unidades).fillna("")
    except Exception:
        return catalogo

    juntas = pd.concat([catalogo, nuevas], ignore_index=True)
    for columna in COLUMNAS_CATALOGO:
        if columna not in juntas.columns:
            juntas[columna] = ""
    juntas = juntas.fillna("")
    # Gana la fila con nombre: la del bodeguero si lo trae, si no la del CSV.
    juntas["_tiene_nombre"] = juntas["nombre_unidad"].astype(str).str.strip() != ""
    juntas = (juntas.sort_values("_tiene_nombre")
              .drop_duplicates("codigo_unidad", keep="last")
              .drop(columns="_tiene_nombre"))

    sin_region = juntas["region"].astype(str).str.strip() == ""
    juntas.loc[sin_region, "region"] = SIN_REGION

    frecuencia = ordenes_por_unidad(sello)
    if frecuencia:
        juntas["oc_convenio_marco"] = [
            frecuencia.get(u, 0) or v
            for u, v in zip(juntas["codigo_unidad"],
                            pd.to_numeric(juntas["oc_convenio_marco"],
                                          errors="coerce").fillna(0).astype(int))
        ]
    juntas["oc_convenio_marco"] = (
        pd.to_numeric(juntas["oc_convenio_marco"], errors="coerce").fillna(0).astype(int))
    juntas = juntas[juntas["codigo_unidad"].astype(str).str.strip() != ""]
    return (juntas[COLUMNAS_CATALOGO]
            .sort_values(["oc_convenio_marco", "nombre_unidad"], ascending=[False, True])
            .reset_index(drop=True))


@st.cache_data(show_spinner=False)
def ordenes_por_unidad(sello: str) -> dict[str, int]:
    """Cuantas ordenes de Convenio Marco lleva cada unidad en toda la bodega."""
    archivos = sorted((RUTA_BODEGA / "mapa").glob("*.parquet"))
    if not archivos:
        return {}
    try:
        mapa = pd.concat([pd.read_parquet(a, columns=["unidad"]) for a in archivos],
                         ignore_index=True)
    except Exception:
        return {}
    return mapa.groupby("unidad").size().to_dict()


@st.cache_data(show_spinner=False)
def leer_catalogo_unidades(fecha_del_archivo: float) -> pd.DataFrame:
    """Lee el CSV. El argumento solo sirve de llave de la cache.

    El nombre NO puede empezar con guion bajo: Streamlit excluye de la llave de
    la cache los argumentos que empiezan asi, y entonces cambiar el archivo no
    serviria de nada.
    """
    columnas = COLUMNAS_CATALOGO
    catalogo = pd.read_csv(RUTA_CATALOGO_UNIDADES, sep=";", dtype=str,
                           encoding="utf-8-sig").fillna("")
    for columna in columnas:
        if columna not in catalogo.columns:
            catalogo[columna] = ""

    # 176 unidades vienen sin region ni comuna porque la API no las informa, y
    # son casi todas hospitales y servicios de salud: 1.530 ordenes de Convenio
    # Marco, el 11% del total. Se les pone una etiqueta propia para que el filtro
    # por region no las esconda. No se les adivina la region a partir de otra
    # unidad del mismo organismo: un organismo puede tener unidades en varias.
    sin_region = catalogo["region"].str.strip() == ""
    catalogo.loc[sin_region, "region"] = SIN_REGION

    # Las que mas compran primero: son las que valen la pena mirar.
    catalogo["oc_convenio_marco"] = (
        pd.to_numeric(catalogo["oc_convenio_marco"], errors="coerce").fillna(0).astype(int)
    )
    catalogo = catalogo[catalogo["codigo_unidad"].str.strip() != ""]
    return (catalogo.sort_values(["oc_convenio_marco", "nombre_unidad"],
                                 ascending=[False, True])
            .reset_index(drop=True))


def es_convenio_marco(codigo: str) -> bool:
    """«2945-381-CM26» sí; «1002584-259-AG26» no.

    El mecanismo esta en el ultimo tramo del codigo. Se mira ahi y no se busca
    "-CM" suelto, que podria coincidir con otra cosa.
    """
    tramos = str(codigo).split("-")
    return len(tramos) >= 3 and tramos[-1].strip().upper().startswith("CM")


def convenio_del_codigo(codigo: str) -> str:
    """El convenio y su año: «2950-1975-CM25» -> «CM25».

    Es el mismo ultimo tramo que dice que la orden es de Convenio Marco. El
    numero es el año del convenio, no el de la compra: en un barrido de agosto
    de 2026 aparecen ordenes CM25 y CM24 todavia vivas.
    """
    tramos = str(codigo).split("-")
    return tramos[-1].strip().upper() if len(tramos) >= 3 else ""


def unidad_del_codigo(codigo: str) -> str:
    """El primer tramo del codigo ES la unidad compradora: «2945-381-CM26» -> «2945».

    Por esto no hace falta pedir el detalle para saber de quien es cada orden.
    """
    return str(codigo).split("-")[0].strip()


def id_convenio_marco(especificacion) -> str:
    """El ID de Convenio Marco viene entre parentesis en la especificacion.

    «(4427537) GOMA DE BORRAR RHEIN...» -> «4427537». Es el mismo numero de la
    columna ID de su hoja de compras, asi que sirve para cruzar lo que compro la
    institucion con lo que ella tiene publicado.
    """
    coincidencia = re.match(r"\s*\((\d+)\)", str(especificacion or ""))
    return coincidencia.group(1) if coincidencia else ""


def dias_del_barrido(desde: date, hasta: date) -> list[date]:
    """Todos los dias del periodo, uno por consulta."""
    if hasta < desde:
        desde, hasta = hasta, desde
    return [desde + timedelta(days=n) for n in range((hasta - desde).days + 1)]


def filas_de_orden(orden: dict, nombres_unidad: dict[str, str]) -> list[dict]:
    """Una fila por producto de la orden. Si no detalla productos, una sola fila."""
    codigo = str(orden.get("Codigo") or "")
    comprador = orden.get("Comprador") or {}
    proveedor = orden.get("Proveedor") or {}
    fechas = orden.get("Fechas") or {}

    comun = {
        "FECHA": (fechas.get("FechaCreacion") or "")[:10],
        "ORDEN": codigo,
        "ESTADO": str(orden.get("Estado") or "").strip(),
        "UNIDAD": (str(comprador.get("NombreUnidad") or "").strip()
                   or nombres_unidad.get(unidad_del_codigo(codigo), "")),
        "PROVEEDOR": str(proveedor.get("Nombre") or "").strip(),
        "RUT PROVEEDOR": str(proveedor.get("RutSucursal") or "").strip(),
    }

    productos = (orden.get("Items") or {}).get("Listado") or []
    if not productos:
        # Pasa poco, pero si la orden no trae items no se puede perder: se
        # muestra igual con su monto total.
        return [comun | {"ID": "", "PRODUCTO": "(la orden no detalla productos)",
                         "CANTIDAD": None, "PRECIO": None,
                         "TOTAL": a_numero(orden.get("Total"))}]

    filas = []
    for producto in productos:
        filas.append(comun | {
            "ID": id_convenio_marco(producto.get("EspecificacionComprador")),
            "PRODUCTO": str(producto.get("Producto") or "").strip(),
            "CANTIDAD": a_numero(producto.get("Cantidad")),
            "PRECIO": a_numero(producto.get("PrecioNeto")),
            "TOTAL": a_numero(producto.get("Total")),
        })
    return filas


def _numeros_de_columna(serie: pd.Series) -> pd.Series:
    """Columna numerica de verdad: entera si todos los valores son enteros.

    Igual que en el panel de arriba: como texto, la tabla ordenaba "11" entre
    "1" y "2". Las cantidades pueden venir con decimales (kilos), asi que solo
    se pasan a entero cuando de verdad lo son.
    """
    numeros = pd.to_numeric(serie, errors="coerce")
    validos = numeros.dropna()
    if validos.empty or bool((validos % 1 == 0).all()):
        return numeros.round().astype("Int64")
    return numeros.astype("Float64")


def comentario_compra(ocs: int, proveedores: int, oferta, precio_pagado, dias: int) -> str:
    """Las señales de negocio de un producto, con los numeros a la vista.

    La mas valiosa es la ultima: si su oferta esta bajo lo que la institucion ya
    pago, eso es un argumento de venta con nombre, ID y monto.
    """
    señales = []

    periodo = f"{dias} día" + ("s" if dias != 1 else "")
    if ocs >= 2:
        señales.append(f"compra recurrente: {ocs} OC en {periodo}")
    else:
        señales.append(f"1 sola OC en {periodo}")

    if proveedores <= 1:
        señales.append("1 solo proveedor: poca competencia")
    else:
        señales.append(f"{proveedores} proveedores")

    if oferta is None:
        señales.append("no está en tu catálogo")
    elif precio_pagado:
        diferencia = (oferta - precio_pagado) / precio_pagado * 100
        if diferencia <= -1:
            señales.append(f"tu oferta está {abs(diferencia):.0f}% bajo lo que pagó")
        elif diferencia >= 1:
            señales.append(f"tu oferta está {diferencia:.0f}% sobre lo que pagó")
        else:
            señales.append("tu oferta iguala lo que pagó")

    return " · ".join(señales)


def agrupar_por_producto(compras: pd.DataFrame, precios_oferta: dict[str, float],
                         dias: int) -> pd.DataFrame:
    """De una fila por linea de orden a una fila por ID, como el panel de arriba.

    Los precios son los que PAGO la institucion en el rango consultado. El
    promedio es el de los precios unitarios de cada linea, no ponderado por
    cantidad: asi P.MIN, P. PROM y P.MAX se leen como una misma escala.
    """
    columnas = COLUMNAS_PANEL_MP + [COLUMNA_ESTADO]
    if compras.empty:
        return pd.DataFrame(columns=columnas)

    con_id = compras[compras["ID"].astype(str).str.strip() != ""]
    if con_id.empty:
        return pd.DataFrame(columns=columnas)

    filas = []
    for identificador, grupo in con_id.groupby("ID", sort=False):
        precios = [p for p in grupo["PRECIO"] if p is not None and not pd.isna(p)]
        montos = [m for m in grupo["TOTAL"] if m is not None and not pd.isna(m)]
        promedio = sum(precios) / len(precios) if precios else None
        oferta = precios_oferta.get(str(identificador).strip())
        ocs = int(grupo["ORDEN"].nunique())
        proveedores = int(grupo["PROVEEDOR"].nunique())

        filas.append({
            "ID": str(identificador),
            "PRODUCTO": str(grupo["PRODUCTO"].iloc[0]),
            "MONTO": sum(montos) if montos else None,
            "P.MIN": min(precios) if precios else None,
            "P. PROM": promedio,
            "P.MAX": max(precios) if precios else None,
            # Solo se llena si existe oferta: un precio normal no sirve para
            # cotizar y en el PDF sale con un guion.
            "MI OFERTA": oferta,
            "OC": ocs,
            "PROVEEDORES": proveedores,
            "COMENTARIO": comentario_compra(ocs, proveedores, oferta, promedio, dias),
            COLUMNA_ESTADO: "CON STOCK" if oferta is not None else "NO LO TENGO",
        })

    tabla = pd.DataFrame(filas, columns=columnas)
    for columna in COLUMNAS_NUMERICAS_PANEL_MP:
        tabla[columna] = _numeros_de_columna(tabla[columna])
    return tabla.sort_values("MONTO", ascending=False, na_position="last").reset_index(drop=True)


def buscar_compras_cm(unidades: pd.DataFrame, desde: date, hasta: date,
                      avisar=None) -> tuple[pd.DataFrame, dict]:
    """Barre el periodo y devuelve (tabla de productos comprados, resumen)."""
    codigos_unidad = set(unidades["codigo_unidad"])
    nombres_unidad = dict(zip(unidades["codigo_unidad"], unidades["nombre_unidad"]))
    organismos = sorted(set(unidades["codigo_organismo"]))
    dias = dias_del_barrido(desde, hasta)

    # --- Paso 1: que ordenes de Convenio Marco existen (consulta barata) ----
    total_dias = max(len(dias) * len(organismos), 1)
    ordenes: dict[str, str] = {}          # codigo de orden -> dia en que aparecio
    hechas = 0
    for organismo in organismos:
        for dia in dias:
            for orden in ordenes_del_dia(f"{dia:%d%m%Y}", organismo):
                codigo = str(orden.get("Codigo") or "")
                if unidad_del_codigo(codigo) in codigos_unidad and es_convenio_marco(codigo):
                    ordenes.setdefault(codigo, f"{dia:%d-%m-%Y}")
            hechas += 1
            if avisar:
                avisar(hechas / total_dias * 0.4,
                       f"Barriendo el período: {hechas} de {total_dias} días · "
                       f"{len(ordenes)} órdenes de Convenio Marco encontradas")

    # --- Paso 2: el detalle solo de esas ------------------------------------
    filas: list[dict] = []
    contactos: list[str] = []
    total_ordenes = max(len(ordenes), 1)
    for numero, codigo in enumerate(sorted(ordenes), start=1):
        orden = detalle_orden(codigo)
        if orden:
            filas.extend(filas_de_orden(orden, nombres_unidad))
            # El nombre del contacto viene siempre; el correo NO (llega vacio en
            # todas las ordenes revisadas). Sirve para proponer el destinatario.
            quien = str((orden.get("Comprador") or {}).get("NombreContacto") or "").strip()
            if quien:
                contactos.append(quien)
        if avisar:
            avisar(0.4 + numero / total_ordenes * 0.6,
                   f"Leyendo el detalle: {numero} de {len(ordenes)} órdenes")

    tabla = pd.DataFrame(filas, columns=COLUMNAS_MP)
    for columna in COLUMNAS_NUMERICAS_MP:
        tabla[columna] = _numeros_de_columna(tabla[columna])

    fechas = pd.to_datetime(tabla["FECHA"], errors="coerce")
    tabla["FECHA"] = [None if pd.isna(f) else f.date() for f in fechas]
    tabla = (tabla.sort_values(["ORDEN"], ascending=False)
             .sort_values("FECHA", ascending=False, na_position="last", kind="stable")
             .reset_index(drop=True))

    # OJO: esto se calcula DESPUES de ordenar y reindexar, sobre la columna ya
    # ordenada. Calculado antes, las posiciones apuntaban a otras filas y el
    # resumen contaba ordenes que no eran.
    primero, ultimo = min(desde, hasta), max(desde, hasta)
    en_periodo = [bool(f and primero <= f <= ultimo) for f in tabla["FECHA"]]
    resumen = {
        "consultas": len(dias) * len(organismos) + len(ordenes),
        "dias": len(dias),
        "organismos": len(organismos),
        "ordenes": len(ordenes),
        "ordenes_en_periodo": int(tabla.loc[en_periodo, "ORDEN"].nunique()) if len(tabla) else 0,
        "desde_real": min((f for f in tabla["FECHA"] if f), default=None),
        "hasta_real": max((f for f in tabla["FECHA"] if f), default=None),
        # El contacto que mas se repite: es quien compra habitualmente.
        "contacto": (pd.Series(contactos).mode().iloc[0] if contactos else ""),
    }
    return tabla, resumen


# ===========================================================================
# 10. INTERFAZ
# ===========================================================================

def aplicar_estilos() -> None:
    """Tipografia y tarjetas iguales a las del Panel Armada."""
    st.markdown(
        f"""
        <style>
        /* OJO: no incluir selectores amplios como [class*="st-"]: los iconos de
           Streamlit son ligaduras de la fuente Material Symbols y, si se les
           cambia la tipografia, se ven como texto ("keyboard_double_arrow_left")
           montado sobre la pantalla. */
        html, body, .stApp, button, input, textarea, select, label,
        p, h1, h2, h3, h4, h5, h6, li, td, th,
        [data-testid="stMarkdownContainer"] {{
            font-family: {TIPOGRAFIA} !important;
        }}
        /* Red de seguridad: los iconos siempre con su fuente propia. */
        [data-testid="stIconMaterial"], span[class*="material-symbols"],
        .material-symbols-rounded, [data-testid*="ToggleIcon"] {{
            font-family: "Material Symbols Rounded" !important;
        }}
        /* Tarjetas: mismo azul pizarra que el panel de Apps Script */
        [data-testid="stVerticalBlockBorderWrapper"]:has(> div > div > [data-testid="stVerticalBlock"]) {{
            background: {COLOR['tarjeta']};
            border: 1px solid {COLOR['borde']};
            border-radius: 12px;
        }}
        /* El tamaño general (20% mas chico) se define en .streamlit/config.toml
           con baseFontSize; aqui solo se ajusta el ancho y el aire de arriba.
           Sin barra lateral se aprovecha todo el ancho de la pantalla. */
        [data-testid="stMainBlockContainer"] {{
            padding-top: 1.6rem;
            padding-left: 2rem;
            padding-right: 2rem;
            max-width: 100%;
        }}
        /* En el celular, los margenes se comen la pantalla. */
        @media (max-width: 640px) {{
            [data-testid="stMainBlockContainer"] {{
                padding-left: 0.7rem; padding-right: 0.7rem; padding-top: 1rem;
            }}
        }}
        /* Cabecera compacta: logo y titulo centrados, con el filo rojo. */
        .cabecera {{
            display: flex; align-items: center; justify-content: center; gap: 22px;
            background: {COLOR['blanco']};
            border-radius: 12px;
            border-bottom: 4px solid {COLOR['rojo']};
            padding: 12px 24px;
            margin-bottom: 16px;
        }}
        .cabecera img {{ width: 132px; flex: none; }}
        .cabecera-texto {{ line-height: 1.15; text-align: center; }}
        .titulo-panel {{
            color: #24333F; font-size: 27px; font-weight: bold; letter-spacing: -0.4px;
        }}
        .subtitulo-panel {{
            color: #5A7089; font-size: 12.5px; margin-top: 2px;
        }}
        /* En el celular: logo arriba, titulo abajo y mas chico. Este bloque va
           AL FINAL a proposito: las reglas de arriba tienen la misma fuerza y,
           puesto antes, el tamaño del titulo lo pisaba la regla general. */
        @media (max-width: 640px) {{
            .cabecera {{ flex-direction: column; gap: 8px; padding: 12px 10px; }}
            .cabecera img {{ width: 108px; }}
            .titulo-panel {{ font-size: 21px; letter-spacing: -0.2px; }}
            .subtitulo-panel {{ font-size: 11px; }}
        }}
        </style>
        """,
        unsafe_allow_html=True,
    )


def cabecera() -> None:
    """Franja blanca con el logo a la izquierda y el titulo al lado."""
    if RUTA_LOGO.exists():
        logo = base64.b64encode(RUTA_LOGO.read_bytes()).decode()
        marca = f'<img src="data:image/png;base64,{logo}" alt="Comercial Emergenza">'
    else:
        marca = (f'<div style="color:{COLOR["rojo"]};font-size:20px;font-weight:bold;'
                 f'line-height:1.1">COMERCIAL<br>EMERGENZA</div>')
    st.markdown(
        f'<div class="cabecera">{marca}'
        f'<div class="cabecera-texto">'
        f'<div class="titulo-panel">{TITULO_APP}</div>'
        f'<div class="subtitulo-panel">{SUBTITULO_APP}</div>'
        f'</div></div>',
        unsafe_allow_html=True,
    )


def icono_del_movil() -> None:
    """El icono cuadrado para cuando se agrega la app a la pantalla del celular.

    `page_icon` de Streamlit deja el favicon de la pestaña, pero el celular usa
    otra etiqueta (`apple-touch-icon`) y sin ella pone una captura de la pagina.
    Las etiquetas van dentro del <body>, que es lo unico que Streamlit permite
    escribir; los navegadores igual las leen. No ocupan espacio en pantalla.
    """
    if not RUTA_ICONO.exists():
        return
    icono = f"data:image/png;base64,{base64.b64encode(RUTA_ICONO.read_bytes()).decode()}"
    st.markdown(
        f'<link rel="apple-touch-icon" href="{icono}">'
        f'<link rel="apple-touch-icon-precomposed" href="{icono}">'
        f'<link rel="icon" href="{icono}">'
        f'<meta name="apple-mobile-web-app-title" content="{TITULO_APP}">'
        f'<meta name="application-name" content="{TITULO_APP}">',
        unsafe_allow_html=True,
    )


def origen_de_datos() -> tuple[str, str]:
    """Los dos enlaces, arriba en el encabezado. Devuelve (hoja, catálogo)."""
    with st.container(border=True):
        st.markdown("##### 🔗 Origen de datos")
        izquierda, derecha = st.columns(2)
        hoja = izquierda.text_input(
            "URL del Google Sheet (análisis de compras)",
            value=URL_HOJA_POR_DEFECTO,
            key="url_hoja",
            help="Viene cargada la hoja de la Escuela Naval. Puedes reemplazarla por "
                 "la de otra institución cuando quieras.",
        )
        catalogo = derecha.text_input(
            "Carpeta (o enlace) del catálogo de ofertas",
            value=URL_OFERTAS_POR_DEFECTO,
            key="url_ofertas",
            help="Viene cargada tu carpeta de ofertas de Drive: la app busca sola el "
                 "archivo «OFERTAS» más reciente y cruza los ID para poner el precio "
                 "en la cotización. También acepta el enlace directo de una hoja.",
        )
    return hoja.strip(), catalogo.strip()


def sugerir_pestana(nombres: list[str], año: int, año_actual: int) -> int:
    """Elige que pestaña mostrar por defecto en cada informe.

    OJO: al exportar el libro, Google recorta los nombres de pestaña a 31
    caracteres (limite de Excel), asi que "Escuela Naval Ultimo Semestre 2025"
    llega como "Escuela Naval Ultimo Semestre 2" y pierde el año. Por eso, si
    no aparece el año, se busca por palabras de periodo.
    """
    for i, nombre in enumerate(nombres):
        if str(año) in normalizar(nombre):
            return i

    if año != año_actual:
        otras = [i for i, n in enumerate(nombres) if str(año_actual) not in normalizar(n)]
        for i in otras:
            if any(p in normalizar(nombres[i]) for p in PALABRAS_PERIODO_ANTERIOR):
                return i
        if otras:
            return otras[0]

    return 0


def comentario_destacado(comentario, señales=SEÑALES_DESTACADAS) -> bool:
    """¿El comentario trae una señal que conviene aprovechar para vender?"""
    texto = str(comentario).lower()
    return any(señal.lower() in texto for señal in señales)


def destacar_comentarios(tabla: pd.DataFrame, señales=SEÑALES_DESTACADAS):
    """Pinta en amarillo el comentario cuando trae una señal de oportunidad."""
    if "COMENTARIO" not in tabla.columns:
        return tabla

    def color(fila: pd.Series) -> list[str]:
        if comentario_destacado(fila["COMENTARIO"], señales):
            return [f"color: {COLOR_DESTACADO}; font-weight: 600"
                    if columna == "COMENTARIO" else "" for columna in tabla.columns]
        return [""] * len(tabla.columns)

    return tabla.style.apply(color, axis=1)


def filas_seleccionadas(seleccion, total_filas: int) -> list[int]:
    """Posiciones de las filas marcadas en la tabla, siempre limpias.

    No se confia en el formato que devuelve el componente: se descarta lo que
    no sea un numero y lo que quede fuera de rango. Eso ultimo pasa de verdad
    cuando se marcan filas y despues se cambia el filtro o la pestaña: la
    seleccion guardada apunta a posiciones que ya no existen.
    """
    crudas = getattr(getattr(seleccion, "selection", None), "rows", None) or []
    if isinstance(crudas, (str, int, float)):
        crudas = [crudas]

    posiciones: list[int] = []
    for valor in crudas:
        try:
            posicion = int(valor)
        except (TypeError, ValueError):
            continue
        if 0 <= posicion < total_filas and posicion not in posiciones:
            posiciones.append(posicion)
    return posiciones


def render_informe(libro: dict[str, pd.DataFrame], precios_oferta: dict[str, float],
                   titulo: str, año: int, clave: str) -> None:
    """Un informe completo: pestaña, filtro, tabla, exportacion y correo."""
    nombres = list(libro.keys())

    with st.container(border=True):
        arriba_izq, arriba_der = st.columns([2, 3])
        pestana = arriba_izq.selectbox(
            "Pestaña del libro",
            nombres,
            index=sugerir_pestana(nombres, año, datetime.now().year),
            key=f"pestana_{clave}",
            help=f"Se preselecciona la pestaña del período «{año}». Puedes cambiarla.",
        )
        estado = arriba_der.radio(
            "Estado", ESTADOS, horizontal=True, key=f"estado_{clave}",
        )

    # Los IDs de las OTRAS pestañas sirven para detectar la compra recurrente.
    ids_otros = set()
    for nombre, grilla in libro.items():
        if nombre != pestana:
            ids_otros |= ids_de_pestana(grilla)

    meses = meses_del_periodo(pestana)
    tabla, avisos = preparar_tabla(libro[pestana], estado, ids_otros, meses)
    for aviso in avisos:
        st.warning(aviso)

    # --- Resumen del filtro ------------------------------------------------
    total = sum(a_numero(v) or 0 for v in tabla.get("MONTO", []))
    recurrentes = int(tabla.get("COMENTARIO", pd.Series(dtype=str)).str.contains("recurrente").sum()) if len(tabla) else 0
    col1, col2, col3 = st.columns(3)
    col1.metric("Productos", len(tabla))
    col2.metric("Monto del período", pesos(total) or "$0")
    col3.metric("Compra recurrente", recurrentes)

    # --- Tabla con seleccion de varias filas -------------------------------
    st.caption(f"{pestana} — {estado} · frecuencia medida sobre {meses} meses. "
               "Selecciona los productos para el PDF: clic en una fila, y con **Shift** o "
               "arrastrando marcas varias de corrido. **Ctrl** para sumar sueltas. "
               "En amarillo, las oportunidades que conviene aprovechar.")
    # Columnas numericas con separador de miles (y ordenables de verdad).
    configuracion = {
        "PRODUCTO": st.column_config.TextColumn(width="large"),
        "COMENTARIO": st.column_config.TextColumn(width="large"),
    }
    for columna in COLUMNAS_NUMERICAS:
        if columna in tabla.columns:
            configuracion[columna] = st.column_config.NumberColumn(
                format="localized",
                help="Órdenes de compra del período" if columna == "OC" else "En pesos",
            )

    seleccion = st.dataframe(
        destacar_comentarios(tabla),
        width="stretch",
        hide_index=True,
        on_select="rerun",
        selection_mode="multi-row",
        column_config=configuracion,
        key=f"tabla_{clave}",
    )
    seleccionados = tabla.iloc[filas_seleccionadas(seleccion, len(tabla))]

    # --- Excel de todo lo filtrado ------------------------------------------
    st.download_button(
        "⬇️ Descargar Excel de esta vista",
        data=a_excel(tabla),
        file_name=nombre_archivo(titulo, pestana, estado, "xlsx"),
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        disabled=tabla.empty,
        key=f"xlsx_{clave}",
    )

    cotizacion_y_correo(seleccionados, precios_oferta, nombre_institucion(pestana), "", clave)


def cotizacion_y_correo(seleccionados: pd.DataFrame, precios_oferta: dict[str, float],
                        institucion_sugerida: str, contacto_sugerido: str,
                        clave: str) -> None:
    """El PDF de cotizacion y el correo, a partir de las filas marcadas.

    Lo usan los dos lados de la app: el panel de la hoja de compras y el modulo
    de Mercado Publico. Necesita que la tabla traiga una columna ID.
    """
    with st.container(border=True):
        st.markdown("##### 📄 Cotización y correo")
        if seleccionados.empty:
            st.info("Selecciona en la tabla los productos que van en el PDF y el correo.")
            return

        # autocomplete="off" en todos: si no, Chrome rellena solo el CC con la
        # misma direccion que se escribio en Para.
        c1, c2 = st.columns(2)
        institucion = c1.text_input("Cliente (institución)", value=institucion_sugerida,
                                    key=f"inst_{clave}", autocomplete="off")
        contacto = c2.text_input("Nombre del contacto", value=contacto_sugerido,
                                 key=f"cont_{clave}",
                                 placeholder="Ej: Claudia Inzunza", autocomplete="off")
        c3, c4 = st.columns([2, 1])
        linea_producto = c3.text_input("Producto (línea del documento)", key=f"prod_{clave}",
                                       placeholder="Ej: CAJAS DE ALIMENTOS", autocomplete="off")
        numero = c4.text_input("N° Cotización", value=numero_cotizacion_sugerido(),
                               key=f"num_{clave}", autocomplete="off")
        c5, c6, c7 = st.columns(3)
        remitente = c5.selectbox("Enviar desde", CORREOS_ENVIO, key=f"desde_{clave}")
        para = c6.text_input("Para", key=f"para_{clave}", placeholder="correo@institucion.cl",
                             autocomplete="off")
        copia = c7.text_input("Copia (CC)", key=f"cc_{clave}", placeholder="otro@correo.cl",
                              autocomplete="off")

        con_precio = sum(1 for i in seleccionados.get("ID", []) if str(i).strip() in precios_oferta)
        if precios_oferta:
            st.caption(f"{con_precio} de {len(seleccionados)} productos marcados tienen precio "
                       "en el catálogo de ofertas. El resto sale con un guión.")
        else:
            st.caption("Sin catálogo de ofertas cargado: el PDF saldrá sin precios. "
                       "Pega el enlace del catálogo arriba para incluirlos.")

        cuerpo = texto_correo(contacto, institucion, len(seleccionados), remitente)
        asunto = asunto_correo(institucion)

        pdf = a_pdf(seleccionados, institucion, contacto, linea_producto,
                    numero, precios_oferta)
        archivo_pdf = nombre_pdf(institucion, numero)
        enviadores = urls_enviador()
        automatico = remitente in enviadores and clave_envio()

        boton_pdf, boton_envio = st.columns(2)
        boton_pdf.download_button(
            f"⬇️ Descargar PDF ({len(seleccionados)} productos)",
            data=pdf,
            file_name=archivo_pdf,
            mime="application/pdf",
            width="stretch",
            key=f"pdf_{clave}",
        )

        if automatico:
            # --- Envio con un clic (necesita las claves en los secrets) -----
            with boton_envio:
                clave_escrita = st.text_input(
                    "Clave de envío", type="password", key=f"clave_{clave}",
                    placeholder="Requerida: la app es pública")
                enviar = st.button(f"📧 Enviar ahora desde {remitente}", width="stretch",
                                   type="primary", disabled=not para.strip(),
                                   key=f"enviar_{clave}")
            if enviar:
                if clave_escrita != clave_envio():
                    st.error("Clave de envío incorrecta. El correo no se envió.")
                else:
                    try:
                        with st.spinner("Enviando..."):
                            envio = armar_envio(remitente, para, copia, asunto, cuerpo,
                                                pdf, archivo_pdf, clave_escrita)
                            respuesta = enviar_por_script(enviadores[remitente], envio)
                        if respuesta.get("ok"):
                            destinos = ", ".join(x for x in [respuesta.get("para"),
                                                             respuesta.get("cc")] if x)
                            st.success(
                                f"✅ Enviado desde {respuesta.get('cuenta') or remitente} "
                                f"a {destinos} con «{archivo_pdf}» adjunto. "
                                "Queda copia en tus Enviados de Gmail.")
                        else:
                            st.error(f"El enviador no lo mandó: {respuesta.get('error')}")
                    except Exception as error:
                        st.error(f"No se pudo enviar: {error}")
        else:
            # --- Sin claves configuradas: se abre Gmail redactado ------------
            if para.strip():
                boton_envio.link_button(
                    f"📧 Abrir correo en {remitente}",
                    url=enlace_gmail(remitente, para, copia, asunto, cuerpo),
                    width="stretch",
                    help="Abre Gmail con el mensaje ya escrito. Adjunta el PDF y envía.",
                )
            else:
                boton_envio.button("📧 Abrir correo", disabled=True, width="stretch",
                                   help="Escribe primero la dirección en «Para».",
                                   key=f"sin_para_{clave}")
            st.caption("Envío con un clic desactivado para esta cuenta: falta instalar su "
                       "script enviador y anotarlo en Streamlit ▸ Manage app ▸ Settings ▸ "
                       "Secrets. Mientras tanto, el botón abre Gmail y adjuntas el PDF a mano.")

        with st.expander("Ver el texto del correo para copiarlo"):
            st.text("Asunto:")
            st.code(asunto, language=None)
            st.text("Mensaje:")
            st.code(cuerpo, language=None)


def seccion_mercado_publico(precios_oferta: dict[str, float]) -> None:
    """Selector de instituciones con filtros y consulta en vivo a la API.

    Recibe el catalogo de ofertas ya cargado por la otra pestaña: de ahi salen
    MI OFERTA y el estado (si el ID esta en el catalogo, se entiende que lo
    comercializa).
    """
    catalogo = cargar_catalogo_unidades()
    if catalogo.empty:
        st.error(
            "Falta el archivo «catalogo_unidades.csv» en el proyecto. Es la tabla de "
            "unidades compradoras que da los filtros por región, organismo y unidad."
        )
        return

    hay_ticket = bool(ticket_mp())

    # --- Filtros -------------------------------------------------------------
    with st.container(border=True):
        st.markdown("##### 🏛️ Institución a consultar")

        f1, f2 = st.columns([1, 2])
        # Las sin region van al final de la lista, no primeras por el parentesis.
        nombradas = sorted(r for r in catalogo["region"].unique() if r and r != SIN_REGION)
        regiones = ["Todas las regiones"] + nombradas
        if (catalogo["region"] == SIN_REGION).any():
            regiones.append(SIN_REGION)
        region = f1.selectbox("Región", regiones, key="mp_region")
        por_region = catalogo if region == regiones[0] else catalogo[catalogo["region"] == region]

        organismos = ["Todos los organismos"] + sorted(
            o for o in por_region["nombre_organismo"].unique() if o)
        organismo = f2.selectbox("Organismo", organismos, key="mp_organismo")
        candidatas = (por_region if organismo == organismos[0]
                      else por_region[por_region["nombre_organismo"] == organismo])

        busqueda = st.text_input(
            "Buscar por institución o unidad", key="mp_busqueda",
            placeholder="Ej: escuela naval, municipalidad valparaíso, hospital",
            help="Se puede escribir sin tildes, en minúsculas y con palabras sueltas.")
        if busqueda.strip():
            # Dos cosas que parecen detalles y son la diferencia entre encontrar
            # y no encontrar:
            #  - Las palabras se buscan POR SEPARADO, no como frase pegada:
            #    «servicio oceano» encuentra «SERVICIO HIDROGRÁFICO Y OCEANOGRÁFICO».
            #  - Se busca tambien en el ORGANISMO: 16 de las 21 unidades de
            #    municipios se llaman «Dirección de Salud» o «EDUCACION», asi que
            #    «municipalidad valparaiso» no aparecia por ningun lado.
            palabras = [p for p in (normalizar(t) for t in busqueda.split()) if p]
            donde = candidatas["nombre_unidad"] + " " + candidatas["nombre_organismo"]
            candidatas = candidatas[donde.map(
                lambda texto: all(p in normalizar(texto) for p in palabras))]

        # El organismo se agrega cuando el nombre de la unidad no lo dice ya:
        # sin eso, veinte municipios distintos se ven todos como «Dirección de
        # Salud». La comuna se omite cuando viene vacia, para no dejar el punto
        # colgando.
        etiquetas = {}
        for fila in candidatas.itertuples():
            partes = [fila.nombre_unidad]
            if normalizar(fila.nombre_organismo) not in normalizar(fila.nombre_unidad):
                partes.append(fila.nombre_organismo)
            partes += [fila.comuna, f"{fila.oc_convenio_marco} OC"]
            etiquetas[fila.codigo_unidad] = " · ".join(p for p in partes if p)

        # Igual que la seleccion de filas de la tabla: si se cambia un filtro, las
        # unidades ya marcadas pueden dejar de estar entre las opciones. Se limpian
        # ANTES de dibujar el selector, o Streamlit reclama.
        marcadas = [c for c in st.session_state.get("mp_unidades", []) if c in etiquetas]
        if marcadas != list(st.session_state.get("mp_unidades", [])):
            st.session_state["mp_unidades"] = marcadas

        elegidas = st.multiselect(
            f"Unidades compradoras ({len(etiquetas)} para elegir)",
            options=list(etiquetas),
            format_func=lambda codigo: etiquetas.get(codigo, codigo),
            key="mp_unidades",
            help="Se pueden marcar varias: si son del mismo organismo (las unidades "
                 "de la Armada, por ejemplo) la consulta no demora más. El número "
                 "de cada una es cuántas órdenes de Convenio Marco tuvo en los 8 "
                 "días hábiles con que se armó el catálogo: sirve para saber quién "
                 "compra seguido.")

        # --- Periodo y costo de la consulta ---------------------------------
        hoy = date.today()
        p1, p2 = st.columns([1, 2])
        elegido = p1.date_input(
            "Período a consultar",
            value=(hoy - timedelta(days=DIAS_INICIALES_MP - 1), hoy),
            min_value=PRIMERA_FECHA_MP, max_value=hoy,
            format="DD/MM/YYYY", key="mp_periodo",
            help="Elige la fecha de inicio y la de término. Puedes ir hacia atrás "
                 "hasta 2023, pero mientras más largo el período, más demora: "
                 "cada día es una consulta.")

        # Mientras elige la segunda fecha, el calendario devuelve una sola: hay
        # que esperarla o la consulta saldria con un rango a medias.
        fechas = list(elegido) if isinstance(elegido, (list, tuple)) else [elegido]
        desde = fechas[0] if fechas else hoy
        rango_listo = len(fechas) > 1
        hasta = fechas[1] if rango_listo else desde

        elegidas_df = catalogo[catalogo["codigo_unidad"].isin(elegidas)]
        dias = len(dias_del_barrido(desde, hasta))
        organismos_distintos = elegidas_df["codigo_organismo"].nunique()
        consultas = dias * organismos_distintos
        # La bodega manda cuando tiene el periodo completo: es instantanea y no
        # gasta consultas. Si le falta aunque sea un dia, se consulta en vivo
        # para no mostrar datos a medias sin avisar.
        en_bodega, del_rango = dias_cubiertos(desde, hasta)
        usar_bodega = rango_listo and en_bodega == del_rango and en_bodega > 0
        with p2:
            if not rango_listo:
                st.caption("Elige también la fecha de término.")
            elif usar_bodega:
                cuando = estado_bodega().get("actualizado") or ""
                sello = f" · datos al {cuando[8:10]}-{cuando[5:7]} a las {cuando[11:16]}" if cuando else ""
                st.caption(
                    f"Del **{desde:%d-%m-%Y}** al **{hasta:%d-%m-%Y}** · "
                    f"**está todo en la bodega**{sello}. La consulta es inmediata y no "
                    "gasta ninguna consulta del ticket.")
            elif elegidas:
                falta = del_rango - en_bodega
                st.caption(
                    f"Del **{desde:%d-%m-%Y}** al **{hasta:%d-%m-%Y}**: son **{consultas} "
                    f"consultas** para barrer el período ({dias} días × "
                    f"{organismos_distintos} organismo/s), más una por cada orden que "
                    "calce. El ticket permite 10.000 al día.")
                if en_bodega:
                    st.caption(f"La bodega ya tiene {en_bodega} de estos {del_rango} días; "
                               f"faltan {falta} y por eso se consulta en vivo.")
                if consultas > CONSULTAS_QUE_DEMORAN:
                    st.warning(
                        f"Son {dias} días: la consulta puede demorar varios minutos y "
                        "no hay que cerrar la página mientras avanza.")
            else:
                st.caption(f"Del **{desde:%d-%m-%Y}** al **{hasta:%d-%m-%Y}**.")

        if not hay_ticket and not usar_bodega:
            st.warning(
                "Falta el ticket de la API. Se anota en Streamlit ▸ Manage app ▸ "
                'Settings ▸ Secrets así:\n\n[mercadopublico]\nticket = "TU-TICKET"')

        consultar = st.button(
            "🔎 Consultar Mercado Público", type="primary", width="stretch",
            disabled=not elegidas or not rango_listo or (not hay_ticket and not usar_bodega),
            key="mp_consultar",
            help=None if elegidas else "Marca primero al menos una unidad.")

    # --- La consulta ---------------------------------------------------------
    if consultar:
        # Si el bodeguero ya dejo el periodo descargado, se lee de la bodega:
        # es instantaneo y no gasta ni una consulta del ticket.
        if usar_bodega:
            with st.spinner("Leyendo la bodega..."):
                tabla = compras_desde_bodega(elegidas_df, desde, hasta)
                crudo = leer_bodega("detalle", tuple(_meses_del_rango(desde, hasta)),
                                    sello_bodega())
                if not crudo.empty:
                    crudo = crudo[crudo["unidad"].isin(set(elegidas_df["codigo_unidad"]))]
                resumen = resumen_bodega(tabla, desde, hasta, crudo)
        else:
            barra = st.progress(0.0, text="Consultando Mercado Público...")
            try:
                tabla, resumen = buscar_compras_cm(
                    elegidas_df, desde, hasta,
                    avisar=lambda avance, texto: barra.progress(min(max(avance, 0.0), 1.0),
                                                                text=texto))
            except Exception as error:
                barra.empty()
                st.error(str(error))
                return
            barra.empty()
        st.session_state["mp_tabla"] = tabla
        st.session_state["mp_resumen"] = resumen
        st.session_state["mp_consultado"] = (desde, hasta, list(elegidas_df["nombre_unidad"]))

    # --- El resultado (se guarda, para que no se pierda al tocar otra cosa) --
    tabla = st.session_state.get("mp_tabla")
    if tabla is None:
        st.info("Elige una o más unidades y toca **Consultar Mercado Público**.")
        return

    resumen = st.session_state.get("mp_resumen", {})
    desde_c, hasta_c, unidades_c = st.session_state.get("mp_consultado", (desde, hasta, []))

    if tabla.empty:
        st.warning(
            f"No se encontraron órdenes de Convenio Marco de "
            f"{', '.join(unidades_c) or 'esas unidades'} en el período consultado. "
            "Con un período más largo pueden aparecer.")
        return

    # La fecha con que se filtra es la de creacion de la orden, que es la real.
    # El barrido trae ordenes mas antiguas porque la API lista por dia de
    # movimiento; se avisa y se deja elegir.
    solo_periodo = st.checkbox(
        f"Mostrar solo las órdenes creadas entre el {desde_c:%d-%m-%Y} y el {hasta_c:%d-%m-%Y}",
        value=False, key="mp_solo_periodo")
    vista = tabla
    if solo_periodo:
        vista = tabla[[bool(f and desde_c <= f <= hasta_c) for f in tabla["FECHA"]]]

    # --- Filtro por convenio (el año del CM) --------------------------------
    convenios = sorted({convenio_del_codigo(c) for c in vista["ORDEN"] if c}, reverse=True)
    if len(convenios) > 1:
        # Igual que con las unidades: al reconsultar otra institucion los
        # convenios cambian, y hay que soltar los que ya no existen antes de
        # dibujar el selector.
        vigentes = [c for c in st.session_state.get("mp_convenio", convenios) if c in convenios]
        st.session_state["mp_convenio"] = vigentes or convenios

        elegidos = st.multiselect(
            "Convenio", convenios, key="mp_convenio",
            help="El año del Convenio Marco, sacado del código de cada orden. El "
                 "barrido trae órdenes de convenios anteriores que siguen vivos.")
        vista = vista[[convenio_del_codigo(c) in elegidos for c in vista["ORDEN"]]]
        if vista.empty:
            st.warning("No queda ninguna orden con esos convenios marcados.")
            return

    if resumen.get("de_bodega") and resumen.get("desde_real"):
        st.caption(
            f"{', '.join(unidades_c)} · **leído de la bodega**, sin gastar consultas. "
            f"{resumen.get('ordenes', 0)} órdenes creadas entre "
            f"**{resumen['desde_real']:%d-%m-%Y}** y **{resumen['hasta_real']:%d-%m-%Y}**.")
    elif resumen.get("desde_real") and resumen.get("hasta_real"):
        st.caption(
            f"{', '.join(unidades_c)} · {resumen.get('consultas', 0)} consultas a la API. "
            f"El barrido de {resumen.get('dias', 0)} días encontró "
            f"{resumen.get('ordenes', 0)} órdenes, creadas entre "
            f"**{resumen['desde_real']:%d-%m-%Y}** y **{resumen['hasta_real']:%d-%m-%Y}**: "
            f"{resumen.get('ordenes_en_periodo', 0)} son del período consultado y el resto "
            "son anteriores. La API lista las órdenes por día de movimiento, no por fecha "
            "de creación, así que esas compras más antiguas aparecen solas y son reales.")

    # --- La tabla de trabajo: una fila por producto --------------------------
    # Los dias que dice el comentario son los que de verdad cubren las ordenes
    # que se estan mirando, no los del rango pedido: el barrido trae ordenes
    # anteriores, y decir «3 OC en 15 días» cuando dos son de meses atras es
    # falso y exagera la recurrencia.
    fechas_vista = [f for f in vista["FECHA"] if f]
    dias_vista = (hasta_c - desde_c).days + 1
    if fechas_vista:
        dias_vista = max(dias_vista, (max(fechas_vista) - min(fechas_vista)).days + 1)
    productos = agrupar_por_producto(vista, precios_oferta, dias_vista)
    if productos.empty:
        st.warning("Las órdenes encontradas no traen el ID de Convenio Marco, "
                   "así que no se pueden agrupar por producto.")
        return

    # Arranca en TODOS, al reves que el panel de arriba: al abrir una institucion
    # nueva lo primero que interesa es TODO lo que compra. Empezando en CON STOCK
    # se veian 7 de 54 productos y parecia que la consulta habia fallado.
    estado = st.radio("Estado", ESTADOS_MP, horizontal=True, key="mp_estado",
                      index=ESTADOS_MP.index("TODOS"),
                      help="CON STOCK son los ID que están en tu catálogo de ofertas; "
                           "NO LO TENGO, los que no están en él.")
    if estado != "TODOS":
        productos = productos[productos[COLUMNA_ESTADO] == estado]
    productos = productos.reset_index(drop=True)

    monto = sum(v for v in productos["MONTO"].tolist() if v is not None and not pd.isna(v))
    en_catalogo = int((productos[COLUMNA_ESTADO] == "CON STOCK").sum())
    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Productos", len(productos))
    m2.metric("Monto del período", pesos(monto) or "$0")
    m3.metric("En tu catálogo", en_catalogo)
    m4.metric("Órdenes", int(vista["ORDEN"].nunique()))

    st.caption(
        "Los precios son los que **pagó esta institución** en el período consultado, no "
        "precios de mercado. **MI OFERTA** sale de tu catálogo y queda en blanco si ese ID "
        "no tiene oferta. Selecciona los productos para el PDF: clic en una fila, y con "
        "**Shift** o arrastrando marcas varias de corrido. **Ctrl** para sumar sueltas. "
        "En amarillo, las oportunidades que conviene aprovechar.")

    configuracion = {
        "PRODUCTO": st.column_config.TextColumn(width="large"),
        "COMENTARIO": st.column_config.TextColumn(width="large"),
        "ID": st.column_config.TextColumn(
            "ID", help="El ID de Convenio Marco, el mismo de tu hoja de compras"),
    }
    for columna in COLUMNAS_NUMERICAS_PANEL_MP:
        configuracion[columna] = st.column_config.NumberColumn(
            format="localized",
            help={"OC": "Órdenes de compra del período",
                  "PROVEEDORES": "Cuántos proveedores le vendieron este ID",
                  "MI OFERTA": "Tu precio de oferta de la semana, si ese ID la tiene",
                  }.get(columna, "En pesos"))

    seleccion = st.dataframe(
        destacar_comentarios(productos.drop(columns=[COLUMNA_ESTADO]), SEÑALES_DESTACADAS_MP),
        width="stretch",
        hide_index=True,
        on_select="rerun",
        selection_mode="multi-row",
        column_config=configuracion,
        key="mp_tabla_productos",
    )
    marcados = productos.iloc[filas_seleccionadas(seleccion, len(productos))]

    nombre_base = normalizar(unidades_c[0])[:20] if unidades_c else "consulta"
    st.download_button(
        "⬇️ Descargar Excel de esta vista",
        data=a_excel(productos.drop(columns=[COLUMNA_ESTADO]), nombre_hoja="Mercado Público"),
        file_name=f"MercadoPublico-{nombre_base}-{desde_c:%d%m%Y}-{hasta_c:%d%m%Y}.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        disabled=productos.empty,
        key="mp_xlsx",
    )

    # El PDF y el correo son los mismos del panel de arriba. El contacto lo
    # propone la API; el correo no, porque llega siempre vacio.
    cotizacion_y_correo(marcados, precios_oferta,
                        unidades_c[0] if unidades_c else "",
                        resumen.get("contacto", ""), "mp")

    # --- El detalle, por si quiere ver orden por orden -----------------------
    with st.expander(f"Ver el detalle de las {int(vista['ORDEN'].nunique())} órdenes "
                     f"({len(vista)} líneas)"):
        st.dataframe(
            vista,
            width="stretch",
            hide_index=True,
            column_config={
                "FECHA": st.column_config.DateColumn("FECHA", format="DD-MM-YYYY",
                                                     help="Fecha de creación de la orden"),
                "PRODUCTO": st.column_config.TextColumn(width="large"),
                "UNIDAD": st.column_config.TextColumn(width="medium"),
                "PROVEEDOR": st.column_config.TextColumn("PROVEEDOR", width="medium",
                                                         help="Quién ganó la venta"),
                "CANTIDAD": st.column_config.NumberColumn(format="localized"),
                "PRECIO": st.column_config.NumberColumn(format="localized",
                                                        help="Precio unitario neto pagado"),
                "TOTAL": st.column_config.NumberColumn(format="localized",
                                                       help="Total de la línea, en pesos"),
            },
            key="mp_tabla_ordenes",
        )
        st.download_button(
            "⬇️ Descargar Excel de las órdenes",
            data=a_excel(vista, nombre_hoja="Órdenes"),
            file_name=f"MercadoPublico-ordenes-{nombre_base}-{desde_c:%d%m%Y}.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            key="mp_xlsx_ordenes",
        )


# ===========================================================================
# 11. PROGRAMA PRINCIPAL
# ===========================================================================

def precios_del_catalogo(url_ofertas: str) -> tuple[dict[str, float], str, str]:
    """(precios, archivo, error). No dibuja nada: lo necesitan las dos pestañas.

    Se carga en `main`, antes de las pestañas, porque Mercado Público va primero
    y tambien lo usa (para MI OFERTA y el estado de cada producto).
    """
    if not url_ofertas:
        return {}, "", ""
    try:
        precios, fuente = cargar_ofertas(url_ofertas)
        return precios, fuente, ""
    except Exception as error:
        return {}, "", str(error)


def seccion_analisis_compras(precios_oferta: dict[str, float], fuente: str,
                             error_ofertas: str) -> None:
    """El panel de siempre: la hoja de compras convertida en oportunidades."""
    url_hoja, _ = origen_de_datos()

    if error_ofertas:
        st.warning(f"No se pudo leer el catálogo de ofertas: {error_ofertas}")
    elif precios_oferta:
        st.caption(f"✅ Catálogo de ofertas: **{fuente}** — "
                   f"{len(precios_oferta)} precios cargados.")
    elif fuente:
        st.warning("El catálogo de ofertas se leyó, pero no se encontraron columnas "
                   "de ID y precio. Revisa que el archivo tenga esos encabezados.")

    if not url_hoja:
        st.info("Pega arriba el enlace de tu Google Sheet para comenzar.")
        return

    try:
        libro = cargar_libro_por_enlace(url_hoja)
    except Exception as error:
        st.error(str(error))
        return

    if not libro:
        st.error("El libro no tiene pestañas legibles.")
        return

    año_actual = datetime.now().year
    render_informe(libro, precios_oferta, f"Oportunidades-{año_actual}", año_actual, clave="unico")


def main() -> None:
    st.set_page_config(
        page_title=TITULO_APP,
        # El icono cuadrado, no el logo horizontal: como favicon salia aplastado.
        page_icon=str(RUTA_ICONO) if RUTA_ICONO.exists() else "🏛️",
        layout="wide",
        initial_sidebar_state="collapsed",
    )
    aplicar_estilos()
    icono_del_movil()
    cabecera()

    # El catalogo de ofertas se lee una vez y lo usan las dos pestañas. La URL
    # sale del campo de «Análisis de compras», que se dibuja despues: en la
    # primera pasada todavia no esta en session_state y se usa la de fabrica.
    url_ofertas = st.session_state.get("url_ofertas", URL_OFERTAS_POR_DEFECTO)
    precios_oferta, fuente_ofertas, error_ofertas = precios_del_catalogo(url_ofertas)

    # Mercado Público va primero: es la pestaña con la que ella trabaja.
    mercado, analisis = st.tabs(["🏛️  Mercado Público", "📊  Análisis de compras"])
    with mercado:
        seccion_mercado_publico(precios_oferta)
    with analisis:
        seccion_analisis_compras(precios_oferta, fuente_ofertas, error_ofertas)


if __name__ == "__main__":
    main()
