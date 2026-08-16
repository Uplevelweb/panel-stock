"""
CONTROL DE STOCK — Google Sheets
=================================

Aplicacion Streamlit que:
  1. Lee un Google Sheet, por enlace publico (Modo 1) o por API con cuenta
     de servicio (Modo 2).
  2. Deja elegir la pestaña del libro (año actual / periodo anterior).
  3. Filtra los registros por la columna "MI ESTADO": CON STOCK / SIN STOCK.
  4. Muestra y exporta UNICAMENTE 7 columnas:
     ID | PRODUCTO | P.MIN | P. PROM | P.MAX | MI PUBLICADO | OC
  5. Permite descargar lo filtrado en Excel (.xlsx) o CSV.

Ejecutar:  streamlit run app.py
"""

from __future__ import annotations

import io
import json
import re
import unicodedata
import urllib.error
import urllib.request
from datetime import datetime

import pandas as pd
import streamlit as st

# ===========================================================================
# 1. CONFIGURACION
# ===========================================================================

TITULO_APP = "Control de Stock — Google Sheets"

# Las 7 columnas que deben quedar en la tabla final, en este orden exacto.
# Cualquier otra columna de la hoja se descarta por completo.
COLUMNAS_FINALES = ["ID", "PRODUCTO", "P.MIN", "P. PROM", "P.MAX", "MI PUBLICADO", "OC"]

# Columna usada solo para filtrar (no se muestra ni se exporta).
COLUMNA_ESTADO = "MI ESTADO"

# Estados disponibles en el filtro de la pantalla principal.
ESTADOS = ["CON STOCK", "SIN STOCK"]

# Variantes aceptadas de cada encabezado. La comparacion se hace "normalizada"
# (sin tildes, sin espacios, sin puntos y en mayusculas), de modo que
# "p. min", "P.MIN" y "  P Min " son la misma columna.
ALIAS_COLUMNAS: dict[str, list[str]] = {
    "ID":           ["ID", "IDPRODUCTO", "CODIGO"],
    "PRODUCTO":     ["PRODUCTO", "PRODUCTOS", "NOMBREPRODUCTO", "DESCRIPCION"],
    "P.MIN":        ["PMIN", "PRECIOMIN", "PMINIMO", "PRECIOMINIMO"],
    "P. PROM":      ["PPROM", "PPROMEDIO", "PRECIOPROM", "PRECIOPROMEDIO"],
    "P.MAX":        ["PMAX", "PRECIOMAX", "PMAXIMO", "PRECIOMAXIMO"],
    "MI PUBLICADO": ["MIPUBLICADO", "PUBLICADO", "MIPRECIOPUBLICADO", "MIPRECIO"],
    "OC":           ["OC", "OCS", "ORDENCOMPRA", "ORDENDECOMPRA", "OCOS"],
    COLUMNA_ESTADO: ["MIESTADO", "ESTADO", "ESTADOSTOCK"],
}

# Palabras que delatan una pestaña de un periodo pasado cuando el nombre no
# alcanza a mostrar el año (ver sugerir_pestana).
PALABRAS_PERIODO_ANTERIOR = ["ULTIMOSEMESTRE", "ULTIMOTRIMESTRE", "SEMESTRE", "TRIMESTRE", "ANTERIOR", "ULTIMO"]

# Ambitos minimos de lectura para el Modo 2 (cuenta de servicio).
SCOPES_GOOGLE = [
    "https://www.googleapis.com/auth/spreadsheets.readonly",
    "https://www.googleapis.com/auth/drive.readonly",
]


# ===========================================================================
# 2. UTILIDADES DE TEXTO Y DE COLUMNAS
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


# Indice inverso: variante normalizada -> nombre canonico de la columna.
INDICE_ALIAS: dict[str, str] = {}
for _canonico, _variantes in ALIAS_COLUMNAS.items():
    INDICE_ALIAS[normalizar(_canonico)] = _canonico
    for _v in _variantes:
        INDICE_ALIAS[normalizar(_v)] = _canonico


def mapear_columnas(df: pd.DataFrame) -> dict[str, int]:
    """Devuelve {nombre canonico: posicion de la columna en el DataFrame}.

    Se trabaja con posiciones (no con nombres) para soportar hojas que traen
    encabezados repetidos o vacios.
    """
    encontradas: dict[str, int] = {}
    for posicion, nombre in enumerate(df.columns):
        canonico = INDICE_ALIAS.get(normalizar(nombre))
        if canonico and canonico not in encontradas:   # gana la primera aparicion
            encontradas[canonico] = posicion
    return encontradas


def detectar_fila_encabezado(bruto: pd.DataFrame, max_filas: int = 12) -> int:
    """Ubica la fila que contiene los titulos de columna.

    Muchas hojas reales traen titulos, logos o filas en blanco arriba. Se elige
    la fila de las primeras `max_filas` que mas encabezados conocidos contenga.
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
# 3. MODO 1 — LECTURA POR ENLACE PUBLICO
# ===========================================================================

def extraer_id_hoja(url: str) -> str:
    """Saca el ID del libro desde cualquier URL de Google Sheets pegada."""
    url = (url or "").strip()
    coincidencia = re.search(r"/spreadsheets/d/([a-zA-Z0-9_-]+)", url)
    if coincidencia:
        return coincidencia.group(1)
    # Tambien se acepta que peguen solo el ID (los IDs reales tienen ~44 caracteres).
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


def _descargar(url: str) -> bytes:
    """Descarga bytes desde una URL y traduce los errores a mensajes claros."""
    peticion = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    try:
        with urllib.request.urlopen(peticion, timeout=60) as respuesta:
            contenido = respuesta.read()
    except urllib.error.HTTPError as error:
        if error.code in (401, 403):
            raise PermissionError(
                "Google respondió 'sin permiso'. Abre la hoja, entra en "
                "Compartir y deja el acceso en 'Cualquier persona con el enlace' "
                "(Lector). O usa el Modo 2 (Conexión API)."
            ) from error
        if error.code == 404:
            raise FileNotFoundError("No se encontró esa hoja. Revisa el enlace.") from error
        raise
    except urllib.error.URLError as error:
        raise ConnectionError(f"No se pudo conectar con Google: {error.reason}") from error

    # Si la hoja es privada, Google devuelve la pagina HTML de inicio de sesion.
    if contenido[:200].lstrip().lower().startswith((b"<html", b"<!doctype")):
        raise PermissionError(
            "La hoja no es pública: Google devolvió la pantalla de inicio de sesión. "
            "Comparte la hoja con 'Cualquier persona con el enlace' o usa el Modo 2."
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


# ===========================================================================
# 4. MODO 2 — LECTURA POR API (CUENTA DE SERVICIO)
# ===========================================================================

@st.cache_data(ttl=300, show_spinner="Conectando con la API de Google...")
def cargar_libro_por_api(credenciales_json: str, url_o_id: str) -> dict[str, pd.DataFrame]:
    """Lee el libro con gspread + google-auth.

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
# 5. FILTRADO Y RECORTE A LAS 7 COLUMNAS
# ===========================================================================

def preparar_tabla(bruto: pd.DataFrame, estado: str) -> tuple[pd.DataFrame, list[str]]:
    """Filtra por MI ESTADO y deja solo las 7 columnas pedidas.

    Devuelve (tabla final, lista de avisos para mostrar en pantalla).
    """
    avisos: list[str] = []
    datos = aplicar_encabezado(bruto)
    if datos.empty:
        return pd.DataFrame(columns=COLUMNAS_FINALES), ["La pestaña seleccionada está vacía."]

    posiciones = mapear_columnas(datos)

    # --- Filtro por MI ESTADO -------------------------------------------
    if COLUMNA_ESTADO in posiciones:
        valores = datos.iloc[:, posiciones[COLUMNA_ESTADO]].map(normalizar)
        objetivo = normalizar(estado)                      # CONSTOCK / SINSTOCK
        seleccion = valores == objetivo
        if not seleccion.any():
            # Tolerancia: "SIN", "Sin stock disponible", "CON STOCK OC", etc.
            seleccion = valores.str.startswith(objetivo[:3])
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

    # --- Recorte: solo las 7 columnas, en el orden pedido ----------------
    presentes = [c for c in COLUMNAS_FINALES if c in posiciones]
    faltantes = [c for c in COLUMNAS_FINALES if c not in posiciones]
    if faltantes:
        avisos.append("Columnas no encontradas en la hoja: " + ", ".join(faltantes))

    final = pd.DataFrame({c: datos.iloc[:, posiciones[c]].astype(str).str.strip() for c in presentes})

    # Elimina filas totalmente vacias que arrastran las hojas de calculo.
    if not final.empty:
        final = final[~(final == "").all(axis=1)].reset_index(drop=True)

    return final, avisos


# ===========================================================================
# 6. EXPORTACION
# ===========================================================================

def a_excel(tabla: pd.DataFrame) -> bytes:
    """Convierte la tabla en un archivo .xlsx en memoria."""
    memoria = io.BytesIO()
    with pd.ExcelWriter(memoria, engine="openpyxl") as escritor:
        tabla.to_excel(escritor, index=False, sheet_name="Datos")
    return memoria.getvalue()


def a_csv(tabla: pd.DataFrame) -> bytes:
    """Convierte la tabla en CSV.

    Se usa ';' como separador y BOM (utf-8-sig) para que Excel en español lo
    abra en columnas y respete las tildes.
    """
    return tabla.to_csv(index=False, sep=";").encode("utf-8-sig")


def nombre_archivo(informe: str, pestana: str, estado: str, extension: str) -> str:
    """Arma un nombre de archivo limpio para las descargas."""
    partes = [informe, pestana, estado]
    base = "_".join(re.sub(r"[^\w\s-]", "", p).strip().replace(" ", "-") for p in partes)
    return f"{base}.{extension}"


# ===========================================================================
# 7. INTERFAZ — BARRA LATERAL (ORIGEN DE DATOS)
# ===========================================================================

def barra_lateral() -> dict[str, pd.DataFrame] | None:
    """Dibuja el panel lateral y devuelve el libro leido (o None si falta info)."""
    st.sidebar.title("Origen de datos")

    modo = st.sidebar.radio(
        "Modo de entrada",
        ["Modo 1 · Enlace manual", "Modo 2 · Conexión API"],
        help="El Modo 1 sólo necesita que la hoja esté compartida por enlace.",
    )

    # ---------------- Modo 1: enlace publico ----------------------------
    if modo.startswith("Modo 1"):
        url = st.sidebar.text_input(
            "URL del Google Sheet",
            placeholder="https://docs.google.com/spreadsheets/d/ID_HOJA/edit",
        )
        if not url.strip():
            return None
        try:
            return cargar_libro_por_enlace(url.strip())
        except Exception as error:
            st.sidebar.error(str(error))
            return None

    # ---------------- Modo 2: cuenta de servicio ------------------------
    url_o_id = st.sidebar.text_input(
        "URL o ID del Google Sheet",
        placeholder="https://docs.google.com/spreadsheets/d/ID_HOJA/edit",
    )
    archivo = st.sidebar.file_uploader("Credenciales de la cuenta de servicio (.json)", type="json")

    credenciales_json = None
    if archivo is not None:
        credenciales_json = archivo.getvalue().decode("utf-8")
    else:
        # Alternativa sin subir archivo: .streamlit/secrets.toml
        # (st.secrets lanza error si el archivo no existe, por eso el try).
        try:
            if "gcp_service_account" in st.secrets:
                credenciales_json = json.dumps(dict(st.secrets["gcp_service_account"]))
                st.sidebar.caption("Usando las credenciales guardadas en secrets.toml")
        except Exception:
            pass

    if not url_o_id.strip() or not credenciales_json:
        st.sidebar.caption(
            "Sube el JSON de la cuenta de servicio (o guárdalo en "
            "`.streamlit/secrets.toml` bajo `[gcp_service_account]`) y comparte "
            "la hoja con el correo de esa cuenta."
        )
        return None

    try:
        return cargar_libro_por_api(credenciales_json, url_o_id.strip())
    except Exception as error:
        st.sidebar.error(str(error))
        return None


# ===========================================================================
# 8. INTERFAZ — INFORMES
# ===========================================================================

def sugerir_pestana(nombres: list[str], año: int, año_actual: int) -> int:
    """Elige que pestaña mostrar por defecto en cada informe.

    OJO: al exportar el libro, Google recorta los nombres de pestaña a 31
    caracteres (limite de Excel), asi que "Escuela Naval Ultimo Semestre 2025"
    llega como "Escuela Naval Ultimo Semestre 2" y pierde el año. Por eso, si
    no aparece el año, se busca por palabras de periodo.
    """
    # 1) La pestaña que lleva el año en el nombre.
    for i, nombre in enumerate(nombres):
        if str(año) in normalizar(nombre):
            return i

    if año != año_actual:
        otras = [i for i, n in enumerate(nombres) if str(año_actual) not in normalizar(n)]
        # 2) Alguna que hable de un periodo pasado (semestre, trimestre, ultimo...).
        for i in otras:
            if any(p in normalizar(nombres[i]) for p in PALABRAS_PERIODO_ANTERIOR):
                return i
        # 3) Cualquiera que no sea la del año actual.
        if otras:
            return otras[0]

    return 0


def render_informe(libro: dict[str, pd.DataFrame], titulo: str, año: int, clave: str) -> None:
    """Dibuja un informe completo: selector de pestaña, filtro, tabla y descargas."""
    nombres = list(libro.keys())

    pestana = st.selectbox(
        "Pestaña del libro",
        nombres,
        index=sugerir_pestana(nombres, año, datetime.now().year),
        key=f"pestana_{clave}",
        help=f"Se preselecciona la pestaña del periodo «{año}». Puedes cambiarla.",
    )

    estado = st.radio(
        "Estado",
        ESTADOS,
        horizontal=True,
        key=f"estado_{clave}",
    )

    tabla, avisos = preparar_tabla(libro[pestana], estado)
    for aviso in avisos:
        st.warning(aviso)

    st.caption(f"{len(tabla)} registros — {pestana} — {estado}")
    st.dataframe(tabla, width="stretch", hide_index=True)

    # ---------------- Descargas -----------------------------------------
    izquierda, derecha = st.columns(2)
    izquierda.download_button(
        "Descargar Excel (.xlsx)",
        data=a_excel(tabla),
        file_name=nombre_archivo(titulo, pestana, estado, "xlsx"),
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        width="stretch",
        disabled=tabla.empty,
        key=f"xlsx_{clave}",
    )
    derecha.download_button(
        "Descargar CSV",
        data=a_csv(tabla),
        file_name=nombre_archivo(titulo, pestana, estado, "csv"),
        mime="text/csv",
        width="stretch",
        disabled=tabla.empty,
        key=f"csv_{clave}",
    )


# ===========================================================================
# 9. PROGRAMA PRINCIPAL
# ===========================================================================

def main() -> None:
    st.set_page_config(page_title=TITULO_APP, page_icon="📦", layout="wide")
    st.title(TITULO_APP)

    libro = barra_lateral()

    if libro is None:
        st.info(
            "Pega el enlace de tu Google Sheet en el panel de la izquierda "
            "(Modo 1) o conecta la cuenta de servicio (Modo 2) para comenzar."
        )
        return

    if not libro:
        st.error("El libro no tiene pestañas legibles.")
        return

    año_actual = datetime.now().year
    informe_actual, informe_anterior = st.tabs(
        [f"Informe 1 · Año actual ({año_actual})", f"Informe 2 · Período anterior ({año_actual - 1})"]
    )

    with informe_actual:
        render_informe(libro, f"Informe-{año_actual}", año_actual, clave="actual")

    with informe_anterior:
        render_informe(libro, f"Informe-{año_actual - 1}", año_actual - 1, clave="anterior")


if __name__ == "__main__":
    main()
