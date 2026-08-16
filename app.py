"""
PANEL OPORTUNIDADES — Comercial Emergenza
==========================================

Lee el libro de Google Sheets con el analisis de compras de una institucion y
lo convierte en oportunidades de venta:

  1. Enlace de la hoja y del catalogo de ofertas, arriba en el encabezado.
  2. Filtro por MI ESTADO: CON STOCK / SIN STOCK / NO LO TENGO / TODOS.
  3. Columna MONTO (venta del periodo) y COMENTARIO con las señales de negocio
     (compra recurrente, frecuencia de OC, poca competencia, tu precio vs mercado).
  4. Dos informes independientes: año en curso y periodo anterior.
  5. Exporta a Excel, o marca productos uno a uno y genera un PDF tipo
     cotizacion con el precio de oferta de la semana, mas el correo listo
     para copiar y pegar en Gmail.

Ejecutar:  streamlit run app.py
"""

from __future__ import annotations

import base64
import io
import json
import re
import unicodedata
import urllib.error
import urllib.request
from datetime import datetime
from pathlib import Path

import pandas as pd
import streamlit as st
from fpdf import FPDF
from fpdf.fonts import FontFace

# ===========================================================================
# 1. CONFIGURACION
# ===========================================================================

TITULO_APP = "Panel Oportunidades"
SUBTITULO_APP = "Convenio Marco · Comercial Emergenza"

CARPETA = Path(__file__).parent
RUTA_LOGO = CARPETA / "LogoVec.png"

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

# Variantes aceptadas de cada encabezado. Se comparan normalizadas (sin tildes,
# sin espacios, sin puntos), asi que "p. min", "P.MIN" y " P Min " son lo mismo.
ALIAS_COLUMNAS: dict[str, list[str]] = {
    "ID":                 ["ID", "IDPRODUCTO", "CODIGO", "COD", "SKU", "IDCONVENIO"],
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
}

ASUNTO_CORREO = "ID disponibles en Convenio Marco | Comercial Emergenza"

# Ambitos minimos de lectura para el Modo 2 (cuenta de servicio, en construccion).
SCOPES_GOOGLE = [
    "https://www.googleapis.com/auth/spreadsheets.readonly",
    "https://www.googleapis.com/auth/drive.readonly",
]


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
                "(Lector)."
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

@st.cache_data(ttl=300, show_spinner="Leyendo el catálogo de ofertas...")
def cargar_ofertas(url: str) -> dict[str, float]:
    """Devuelve {ID de producto: precio oferta} leyendo el catalogo de la semana.

    Recorre TODAS las pestañas del catalogo (suelen venir separadas por rubro o
    region) y se queda con las que tengan una columna de ID y una de precio.
    """
    precios: dict[str, float] = {}
    for grilla in cargar_libro_por_enlace(url).values():
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
    return precios


# ===========================================================================
# 5. INTELIGENCIA: EL COMENTARIO DE CADA PRODUCTO
# ===========================================================================

def construir_comentario(
    id_producto: str,
    oc,
    proveedores,
    mi_publicado,
    p_prom,
    ids_periodo_anterior: set[str],
) -> str:
    """Arma la frase de oportunidad juntando las cuatro señales del negocio."""
    señales: list[str] = []

    # 1) Compra recurrente: el mismo ID aparece en el otro periodo del libro.
    if id_producto and id_producto in ids_periodo_anterior:
        señales.append("Compra recurrente (también el período anterior)")

    # 2) Frecuencia: la columna OC cuenta las ordenes de compra del periodo.
    n_oc = a_numero(oc)
    if n_oc:
        n_oc = int(n_oc)
        if n_oc >= 10:
            señales.append(f"{n_oc} OC en el período: compra casi mensual")
        elif n_oc >= 5:
            señales.append(f"{n_oc} OC en el período: compra frecuente")
        else:
            señales.append(f"{n_oc} OC en el período")

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
            publicados.iloc[i], promedios.iloc[i], ids_periodo_anterior,
        )
        for i in range(len(final))
    ]

    # --- Presentacion: montos y precios en formato peso -------------------
    for col in ["MONTO", "P.MIN", "P. PROM", "P.MAX", "MI PUBLICADO"]:
        if col in final.columns:
            final[col] = final[col].map(pesos)

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

def a_excel(tabla: pd.DataFrame) -> bytes:
    """Convierte la tabla en un .xlsx, con los montos como numeros (no texto)."""
    numerica = tabla.copy()
    for col in ["MONTO", "P.MIN", "P. PROM", "P.MAX", "MI PUBLICADO", "OC"]:
        if col in numerica.columns:
            numerica[col] = numerica[col].map(a_numero)

    memoria = io.BytesIO()
    with pd.ExcelWriter(memoria, engine="openpyxl") as escritor:
        numerica.to_excel(escritor, index=False, sheet_name="Oportunidades")
        hoja = escritor.sheets["Oportunidades"]
        anchos = {"ID": 12, "PRODUCTO": 60, "MONTO": 16, "P.MIN": 12, "P. PROM": 12,
                  "P.MAX": 12, "MI PUBLICADO": 14, "OC": 8, "COMENTARIO": 70}
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


class _Cotizacion(FPDF):
    """PDF con la cabecera y el pie de Comercial Emergenza."""

    def header(self) -> None:
        if RUTA_LOGO.exists():
            self.image(str(RUTA_LOGO), x=14, y=9, w=38)
        self.set_xy(60, 12)
        self.set_font("Helvetica", "B", 15)
        self.set_text_color(36, 51, 63)                       # azul pizarra
        self.cell(0, 8, _limpiar_pdf("ID DISPONIBLES EN CONVENIO MARCO"), align="R")
        self.set_xy(60, 20)
        self.set_font("Helvetica", "", 9)
        self.set_text_color(120, 130, 140)
        self.cell(0, 5, _limpiar_pdf(f"Emitido el {datetime.now():%d-%m-%Y}"), align="R")
        self.set_draw_color(193, 48, 63)                      # rojo Emergenza
        self.set_line_width(0.8)
        self.line(14, 30, 196, 30)
        self.set_y(36)

    def footer(self) -> None:
        self.set_y(-20)
        self.set_draw_color(210, 216, 222)
        self.set_line_width(0.2)
        self.line(14, self.get_y(), 196, self.get_y())
        self.set_y(-16)
        self.set_font("Helvetica", "", 8)
        self.set_text_color(120, 130, 140)
        pie = (f"{FIRMA['nombre']} · {FIRMA['cargo']} · {FIRMA['empresa']} · "
               f"{FIRMA['fono']} · {FIRMA['correo']}")
        self.cell(0, 4, _limpiar_pdf(pie), align="C")
        self.ln(4)
        self.cell(0, 4, _limpiar_pdf(f"Página {self.page_no()}"), align="C")


def a_pdf(tabla: pd.DataFrame, institucion: str, contacto: str,
          precios_oferta: dict[str, float]) -> bytes:
    """Genera la cotizacion: ID, producto y precio de oferta de la semana."""
    pdf = _Cotizacion()
    pdf.set_auto_page_break(auto=True, margin=25)
    pdf.add_page()

    # --- Datos del destinatario ------------------------------------------
    pdf.set_font("Helvetica", "", 10)
    pdf.set_text_color(40, 40, 40)
    encabezado = []
    if institucion.strip():
        encabezado.append(f"Institución: {institucion.strip()}")
    if contacto.strip():
        encabezado.append(f"Contacto: {contacto.strip()}")
    for linea in encabezado:
        pdf.cell(0, 5, _limpiar_pdf(linea), new_x="LMARGIN", new_y="NEXT")
    if encabezado:
        pdf.ln(2)

    pdf.set_font("Helvetica", "", 9.5)
    pdf.multi_cell(0, 5, _limpiar_pdf(
        "Detalle de los ID que Comercial Emergenza tiene disponibles para su compra "
        "en Convenio Marco, seleccionados según sus últimas compras."
    ))
    pdf.ln(3)

    # --- Tabla -------------------------------------------------------------
    with pdf.table(
        col_widths=(20, 62, 18),
        text_align=("CENTER", "LEFT", "RIGHT"),
        headings_style=FontFace(emphasis="BOLD", color=(255, 255, 255), fill_color=(36, 51, 63)),
        line_height=5,
        padding=1.5,
    ) as tabla_pdf:
        fila = tabla_pdf.row()
        for titulo in ("ID", "PRODUCTO", "PRECIO OFERTA"):
            fila.cell(titulo)
        for _, registro in tabla.iterrows():
            id_producto = str(registro.get("ID", "")).strip()
            precio = precios_oferta.get(id_producto)
            fila = tabla_pdf.row()
            fila.cell(_limpiar_pdf(id_producto))
            fila.cell(_limpiar_pdf(registro.get("PRODUCTO", "")))
            fila.cell(_limpiar_pdf(pesos(precio) if precio else "-"))

    # --- Nota al pie -------------------------------------------------------
    pdf.ln(4)
    pdf.set_font("Helvetica", "I", 8)
    pdf.set_text_color(120, 130, 140)
    pdf.multi_cell(0, 4, _limpiar_pdf(
        "Precios de la oferta semanal vigente, sujetos a disponibilidad de stock. "
        "Los productos sin precio se cotizan a solicitud."
    ))

    return bytes(pdf.output())


def nombre_archivo(informe: str, pestana: str, estado: str, extension: str) -> str:
    """Arma un nombre de archivo limpio para las descargas."""
    partes = [informe, pestana, estado]
    base = "_".join(re.sub(r"[^\w\s-]", "", p).strip().replace(" ", "-") for p in partes)
    return f"{base}.{extension}"


# ===========================================================================
# 8. CORREO LISTO PARA COPIAR
# ===========================================================================

def texto_correo(contacto: str, institucion: str, cantidad: int) -> str:
    """Redacta el correo con el mismo tono de los envios semanales."""
    saludo = f"Estimado/a {contacto.strip()}, buen día." if contacto.strip() else "Estimados, buen día."
    de_quien = f" de {institucion.strip()}" if institucion.strip() else ""
    return "\n".join([
        saludo,
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
        FIRMA["correo"],
    ])


# ===========================================================================
# 9. INTERFAZ
# ===========================================================================

def aplicar_estilos() -> None:
    """Tipografia y tarjetas iguales a las del Panel Armada."""
    st.markdown(
        f"""
        <style>
        html, body, .stApp, button, input, textarea, select,
        [class*="st-"], [data-testid="stMarkdownContainer"] {{
            font-family: {TIPOGRAFIA} !important;
        }}
        /* Tarjetas: mismo azul pizarra que el panel de Apps Script */
        [data-testid="stVerticalBlockBorderWrapper"]:has(> div > div > [data-testid="stVerticalBlock"]) {{
            background: {COLOR['tarjeta']};
            border: 1px solid {COLOR['borde']};
            border-radius: 12px;
        }}
        .cabecera {{
            background: {COLOR['blanco']};
            border-radius: 14px;
            padding: 16px 20px 10px;
            text-align: center;
            margin-bottom: 14px;
        }}
        .cabecera img {{ width: 186px; }}
        .titulo-panel {{
            color: {COLOR['texto']}; text-align: center;
            font-size: 34px; font-weight: bold; margin: 6px 0 0;
        }}
        .subtitulo-panel {{
            color: {COLOR['texto_suave']}; text-align: center;
            font-size: 14px; margin: 2px 0 18px;
        }}
        .stTabs [data-baseweb="tab"] {{ font-size: 15px; font-weight: 600; }}
        </style>
        """,
        unsafe_allow_html=True,
    )


def cabecera() -> None:
    """Franja blanca con el logo, mas el titulo del panel."""
    if RUTA_LOGO.exists():
        logo = base64.b64encode(RUTA_LOGO.read_bytes()).decode()
        marca = f'<img src="data:image/png;base64,{logo}" alt="Comercial Emergenza">'
    else:
        marca = (f'<div style="color:{COLOR["rojo"]};font-size:26px;font-weight:bold;'
                 f'line-height:1.1">COMERCIAL<br>EMERGENZA</div>')
    st.markdown(f'<div class="cabecera">{marca}</div>', unsafe_allow_html=True)
    st.markdown(f'<div class="titulo-panel">{TITULO_APP}</div>', unsafe_allow_html=True)
    st.markdown(f'<div class="subtitulo-panel">{SUBTITULO_APP}</div>', unsafe_allow_html=True)


def panel_lateral_en_construccion() -> None:
    """Modo 2 (cuenta de servicio): reservado mientras se gestiona la API."""
    st.sidebar.title("Modo 2 · Conexión API")
    st.sidebar.info(
        "🔧 **En construcción.**\n\n"
        "Cuando esté lista la cuenta de servicio de Google, la app leerá las hojas "
        "privadas y la carpeta de ofertas semanales de Drive sin necesidad de "
        "compartir enlaces."
    )
    st.sidebar.caption("Mientras tanto, usa los enlaces del encabezado.")


def origen_de_datos() -> tuple[str, str]:
    """Los dos enlaces, arriba en el encabezado. Devuelve (hoja, catálogo)."""
    with st.container(border=True):
        st.markdown("##### 🔗 Origen de datos")
        izquierda, derecha = st.columns(2)
        hoja = izquierda.text_input(
            "URL del Google Sheet (análisis de compras)",
            key="url_hoja",
            placeholder="https://docs.google.com/spreadsheets/d/ID_HOJA/edit",
        )
        catalogo = derecha.text_input(
            "URL del catálogo de ofertas de la semana",
            key="url_ofertas",
            placeholder="Opcional: para el precio oferta del PDF",
            help="Comparte el archivo de ofertas con 'Cualquiera con el enlace' y pégalo aquí. "
                 "La app cruza los ID para poner el precio en la cotización.",
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

    tabla, avisos = preparar_tabla(libro[pestana], estado, ids_otros)
    for aviso in avisos:
        st.warning(aviso)

    # --- Resumen del filtro ------------------------------------------------
    total = sum(a_numero(v) or 0 for v in tabla.get("MONTO", []))
    recurrentes = int(tabla.get("COMENTARIO", pd.Series(dtype=str)).str.contains("recurrente").sum()) if len(tabla) else 0
    col1, col2, col3 = st.columns(3)
    col1.metric("Productos", len(tabla))
    col2.metric("Monto del período", pesos(total) or "$0")
    col3.metric("Compra recurrente", recurrentes)

    # --- Tabla con casilla de seleccion ------------------------------------
    st.caption(f"{pestana} — {estado}. Marca los productos que quieres incluir en el PDF.")
    editable = tabla.copy()
    editable.insert(0, "✓", False)
    editada = st.data_editor(
        editable,
        width="stretch",
        hide_index=True,
        disabled=[c for c in editable.columns if c != "✓"],
        column_config={
            "✓": st.column_config.CheckboxColumn("✓", help="Incluir en el PDF", width="small"),
            "PRODUCTO": st.column_config.TextColumn(width="large"),
            "COMENTARIO": st.column_config.TextColumn(width="large"),
        },
        key=f"tabla_{clave}",
    )
    seleccionados = editada[editada["✓"]].drop(columns=["✓"]) if len(editada) else editada

    # --- Excel de todo lo filtrado ------------------------------------------
    st.download_button(
        "⬇️ Descargar Excel de esta vista",
        data=a_excel(tabla),
        file_name=nombre_archivo(titulo, pestana, estado, "xlsx"),
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        disabled=tabla.empty,
        key=f"xlsx_{clave}",
    )

    # --- Cotizacion y correo -------------------------------------------------
    with st.container(border=True):
        st.markdown("##### 📄 Cotización y correo")
        if seleccionados.empty:
            st.info("Marca con ✓ los productos de la tabla para generar el PDF y el correo.")
            return

        c1, c2 = st.columns(2)
        institucion = c1.text_input("Institución", value=pestana, key=f"inst_{clave}")
        contacto = c2.text_input("Nombre del contacto", key=f"cont_{clave}",
                                 placeholder="Ej: Claudia Inzunza")
        c3, c4 = st.columns(2)
        para = c3.text_input("Para", key=f"para_{clave}", placeholder="correo@institucion.cl")
        copia = c4.text_input("Copia (CC)", key=f"cc_{clave}", placeholder="otro@correo.cl")

        con_precio = sum(1 for i in seleccionados.get("ID", []) if str(i).strip() in precios_oferta)
        if precios_oferta:
            st.caption(f"{con_precio} de {len(seleccionados)} productos marcados tienen precio "
                       "en el catálogo de ofertas. El resto sale con un guión.")
        else:
            st.caption("Sin catálogo de ofertas cargado: el PDF saldrá sin precios. "
                       "Pega el enlace del catálogo arriba para incluirlos.")

        st.download_button(
            f"⬇️ Descargar PDF con {len(seleccionados)} productos",
            data=a_pdf(seleccionados, institucion, contacto, precios_oferta),
            file_name=nombre_archivo("ID-disponibles", institucion, str(len(seleccionados)), "pdf"),
            mime="application/pdf",
            key=f"pdf_{clave}",
        )

        st.markdown("**Correo listo para copiar y pegar en Gmail:**")
        if para.strip():
            st.text("Para:")
            st.code(para.strip(), language=None)
        if copia.strip():
            st.text("Copia:")
            st.code(copia.strip(), language=None)
        st.text("Asunto:")
        st.code(ASUNTO_CORREO, language=None)
        st.text("Mensaje:")
        st.code(texto_correo(contacto, institucion, len(seleccionados)), language=None)


# ===========================================================================
# 10. PROGRAMA PRINCIPAL
# ===========================================================================

def main() -> None:
    st.set_page_config(
        page_title=TITULO_APP,
        page_icon=str(RUTA_LOGO) if RUTA_LOGO.exists() else "📊",
        layout="wide",
    )
    aplicar_estilos()
    cabecera()
    panel_lateral_en_construccion()

    url_hoja, url_ofertas = origen_de_datos()

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

    precios_oferta: dict[str, float] = {}
    if url_ofertas:
        try:
            precios_oferta = cargar_ofertas(url_ofertas)
            if precios_oferta:
                st.success(f"Catálogo de ofertas cargado: {len(precios_oferta)} precios encontrados.")
            else:
                st.warning("El catálogo de ofertas se leyó, pero no se encontraron columnas "
                           "de ID y precio. Revisa que el archivo tenga esos encabezados.")
        except Exception as error:
            st.warning(f"No se pudo leer el catálogo de ofertas: {error}")

    año_actual = datetime.now().year
    informe_actual, informe_anterior = st.tabs(
        [f"Informe 1 · Año actual ({año_actual})", f"Informe 2 · Período anterior ({año_actual - 1})"]
    )

    with informe_actual:
        render_informe(libro, precios_oferta, f"Oportunidades-{año_actual}", año_actual, clave="actual")

    with informe_anterior:
        render_informe(libro, precios_oferta, f"Oportunidades-{año_actual - 1}", año_actual - 1, clave="anterior")


if __name__ == "__main__":
    main()
