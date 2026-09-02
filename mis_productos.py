"""
MIS PRODUCTOS — el catálogo de ID publicados de cada cliente
=============================================================

Serling lo pidió el 01-09-2026: «debe haber dos formas de comparar, contra
nuestros ID y según lo vendido; nuestros ID preferiblemente se carguen en un
panel dentro de la sesión de cada cliente».

LAS DOS FORMAS NO SON LA MISMA PREGUNTA, Y POR ESO CONVIVEN
------------------------------------------------------------
SEGÚN LO VENDIDO   los rubros salen solos del RUT: se miran los convenios por
                   los que ya vendió y se compara contra ese mercado. Cero
                   configuración, sirve desde el primer minuto. Es lo que ve
                   alguien que acaba de escanear el QR en la feria.

CONTRA MIS ID      el cliente carga su catálogo de Convenio Marco y se cruza
                   línea por línea: de lo que esa unidad compró, cuánto es de
                   productos que él TIENE PUBLICADOS. Es mucho más fino —el
                   convenio es un saco grande, el ID es el producto exacto—
                   pero necesita que alguien suba el archivo.

Lo primero contesta «¿a quién le podría vender?». Lo segundo, «¿qué de lo que
compran lo tengo yo publicado hoy?». Un vendedor necesita las dos.

DÓNDE SE GUARDAN
----------------
En la cuenta de la empresa, no en la sesión del navegador: si se guardaran en
la sesión, cada persona del equipo tendría que volver a subir el mismo archivo
y se perderían al recargar. Van en la columna `ids_publicados` de `cuentas`,
que la crea `mis-productos-para-copiar.txt`.

MIENTRAS ESA COLUMNA NO EXISTA, ESTO SIGUE FUNCIONANDO. Se guarda en la sesión
y se avisa en pantalla que dura hasta que se cierre. Un módulo nuevo no puede
dejar el panel esperando a que alguien corra un SQL.
"""
from __future__ import annotations

import io
import re

import pandas as pd
import streamlit as st

import modulo_cuentas

# UN ID DE CONVENIO MARCO TIENE EXACTAMENTE 7 DIGITOS. No es una suposición:
# medido el 02-09-2026 sobre la bodega entera —1.216.263 líneas, 125.874 ID
# distintos— y **el 100% tiene 7**. No hay ninguno de 6 ni de 8.
#
# Empezó siendo «5 o más» y eso metía basura: en el catálogo de verdad colaba
# 1.835 números de 5 dígitos y 272 de 6 —cantidades, códigos internos— que
# ninguno calzaba con la bodega. No producían falsos «sí lo tengo», pero sí
# inflaban la cuenta en pantalla: decía 24.763 productos cuando eran 22.656.
#
# Si algún día ChileCompra emite ID más largos, esta es la línea que se toca.
LARGO_ID = 7
CLAVE_SESION = "mis_ids"

# EL CATALOGO VIVE EN EL DRIVE DE ELLA Y SIEMPRE VA A VIVIR AHI. Lo dijo
# Serling el 02-09-2026: «ubícalo en el Drive, un archivo llamado CATALOGO
# CONVENIO MARCO, siempre reposará allí».
#
# Se baja sin credenciales por la vía de exportación de Google, la misma que ya
# usa `app.py` para la hoja de compras. El archivo está compartido por enlace;
# si algún día se deja de compartir, esto avisa y queda la carga a mano.
#
# La dirección va en el código y no en los secretos porque el repositorio ya
# lleva la carpeta de ofertas de la misma forma (`URL_OFERTAS_POR_DEFECTO`), y
# porque es el catálogo publicado en Mercado Público: es información que ella
# ya hace pública al publicarla. Si algún día quiere que no se vea, se muda a
# los secretos de Streamlit y se lee de ahí.
CATALOGO_DRIVE = "1_Z5tXDII93ovkNk-eBNFu6XIiRcbMOtb"
CATALOGO_NOMBRE = "CATALOGO CONVENIO MARCO"


# --------------------------------------------------------------------------
#  Leer el archivo que sube el cliente
# --------------------------------------------------------------------------
def ids_del_archivo(archivo) -> tuple[set[str], str]:
    """Saca los ID de un .xlsx o .csv. Devuelve (ids, explicación).

    NO SE LE PIDE AL CLIENTE QUE DIGA CUÁL ES LA COLUMNA DE ID, y es a
    propósito. El catálogo de Convenio Marco viene con una pestaña por rubro,
    con títulos y filas en blanco arriba, y la columna del ID se llama distinto
    en cada versión («ID», «ID REGIÓN CM», «ID CONVENIO REGIÓN», «ID producto»).
    Preguntar por la columna es garantizar que alguien la elija mal.

    Se leen TODAS las celdas y se toma lo que parece un ID: solo dígitos y al
    menos cinco. Con eso da igual dónde esté la columna y cómo se llame.
    """
    nombre = getattr(archivo, "name", "") or "archivo"
    try:
        contenido = archivo.read()
    except Exception:
        return set(), "No se pudo leer el archivo."

    hojas: dict[str, pd.DataFrame] = {}
    if nombre.lower().endswith(".csv"):
        for separador in (";", ","):
            try:
                hojas = {"csv": pd.read_csv(io.BytesIO(contenido), sep=separador,
                                            header=None, dtype=str,
                                            on_bad_lines="skip")}
                break
            except Exception:
                continue
    else:
        try:
            hojas = pd.read_excel(io.BytesIO(contenido), sheet_name=None,
                                  header=None, dtype=str)
        except Exception as error:
            return set(), f"No se pudo abrir el archivo: {error}"

    if not hojas:
        return set(), "El archivo no se pudo leer. ¿Es un .xlsx o un .csv?"

    encontrados: set[str] = set()
    for grilla in hojas.values():
        if grilla is None or grilla.empty:
            continue
        for columna in grilla.columns:
            valores = grilla[columna].dropna().astype(str).str.strip()
            # `.str.replace` saca los puntos de miles que Excel a veces deja.
            valores = valores.str.replace(".", "", regex=False)
            buenos = valores[valores.str.fullmatch(r"\d{%d}" % LARGO_ID)]
            encontrados.update(buenos.tolist())

    if not encontrados:
        return set(), ("No encontré ningún ID en ese archivo. Tienen que ser "
                       f"números de {LARGO_ID} dígitos, en cualquier columna.")
    return encontrados, (f"{len(encontrados):,}".replace(",", ".") +
                         f" productos leídos de «{nombre}»" +
                         (f", {len(hojas)} pestañas" if len(hojas) > 1 else ""))


# --------------------------------------------------------------------------
#  El catálogo del Drive
# --------------------------------------------------------------------------
@st.cache_data(ttl=600, show_spinner="Leyendo tu catálogo del Drive…")
def ids_del_drive() -> tuple[set, str]:
    """Baja «CATALOGO CONVENIO MARCO» del Drive y saca sus ID.

    Diez minutos de cache: es el mismo plazo que usa `app.cargar_catalogo_propio`
    para el otro catálogo. Suficiente para que ella actualice el archivo y lo
    vea reflejado en la siguiente vuelta, sin bajarlo en cada clic.
    """
    import urllib.error
    import urllib.request

    url = (f"https://docs.google.com/spreadsheets/d/{CATALOGO_DRIVE}"
           "/export?format=xlsx")
    try:
        peticion = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(peticion, timeout=90) as respuesta:
            datos = respuesta.read()
    except urllib.error.HTTPError as error:
        return set(), (f"El Drive respondió {error.code}. Puede que el archivo "
                       "haya dejado de estar compartido por enlace.")
    except Exception as error:
        return set(), f"No se pudo bajar del Drive: {type(error).__name__}."

    # Si Google devuelve una página en vez del archivo, no es un xlsx: pasa
    # cuando el enlace dejó de ser público y contesta con el formulario de
    # acceso. Sin esta comprobación, el lector de más abajo diría «no encontré
    # ningún ID», que manda a buscar el problema al lado equivocado.
    if datos[:4] != b"PK\x03\x04":
        return set(), ("El Drive devolvió una página en vez del archivo: "
                       "seguramente dejó de estar compartido por enlace.")

    envoltorio = io.BytesIO(datos)
    envoltorio.name = f"{CATALOGO_NOMBRE}.xlsx"
    return ids_del_archivo(envoltorio)


# --------------------------------------------------------------------------
#  Guardar y recuperar
# --------------------------------------------------------------------------
def _cuenta_de(usuario: dict) -> str:
    return str((usuario or {}).get("cuenta_id") or "")


def leer(usuario: dict) -> set[str]:
    """Los ID de esa empresa. Primero la cuenta; si no, lo de la sesión."""
    cuenta = _cuenta_de(usuario)
    if cuenta:
        filas = modulo_cuentas._pedir(
            f"cuentas?select=ids_publicados&id=eq.{cuenta}&limit=1")
        if filas:
            guardados = (filas[0] or {}).get("ids_publicados")
            if guardados:
                return {str(x) for x in guardados}
    return set(st.session_state.get(CLAVE_SESION) or [])


def guardar(usuario: dict, ids: set[str]) -> tuple[bool, str]:
    """Deja los ID en la cuenta. Si la columna no existe, en la sesión."""
    # Siempre en la sesión: es lo que hace que funcione en el momento, aunque
    # la base conteste mal.
    st.session_state[CLAVE_SESION] = sorted(ids)

    cuenta = _cuenta_de(usuario)
    if not cuenta:
        return True, "Cargados para esta sesión."

    respuesta = modulo_cuentas._pedir(
        f"cuentas?id=eq.{cuenta}", "PATCH",
        {"ids_publicados": sorted(ids)},
        extra={"Prefer": "return=representation"})
    if respuesta is None:
        return True, ("Cargados **para esta sesión**. Para que queden guardados "
                      "hay que correr `mis-productos-para-copiar.txt` en Supabase.")
    return True, "Guardados en tu cuenta."


def borrar(usuario: dict) -> None:
    st.session_state.pop(CLAVE_SESION, None)
    cuenta = _cuenta_de(usuario)
    if cuenta:
        modulo_cuentas._pedir(f"cuentas?id=eq.{cuenta}", "PATCH",
                              {"ids_publicados": None})


# --------------------------------------------------------------------------
#  La pantalla
# --------------------------------------------------------------------------
def seccion_mis_productos(usuario: dict) -> set[str]:
    """El catálogo del cliente. Devuelve los ID vigentes.

    SE LEE SOLO DEL DRIVE. Antes había que subir el archivo a mano cada vez, y
    Serling lo corrigió el 02-09-2026: el catálogo vive en su Drive y siempre va
    a vivir ahí, así que el panel lo va a buscar. La carga a mano queda como
    salida de emergencia —para probar otro archivo, o si el Drive falla—, no
    como el camino normal.
    """
    del_drive, aviso_drive = ids_del_drive()
    ids = del_drive or leer(usuario)
    de_donde = "del Drive" if del_drive else "cargados a mano"

    titulo = ("Mis productos publicados — " +
              (f"{len(ids):,}".replace(",", ".") + f" {de_donde}" if ids
               else "no se pudo leer el catálogo"))
    with st.expander(titulo, expanded=not ids):
        if del_drive:
            st.success(
                f"Leídos **{len(del_drive):,}".replace(",", ".") + "** productos "
                f"de **{CATALOGO_NOMBRE}**, en tu Drive. No hay que subir nada: "
                "cuando actualices ese archivo, el panel lo toma solo.")
            if st.button("Volver a leerlo ahora", key="mp_releer",
                         help="Por si acabas de actualizar el archivo."):
                ids_del_drive.clear()
                st.rerun()
        else:
            st.error(f"No se pudo leer **{CATALOGO_NOMBRE}** del Drive. {aviso_drive}")
            st.caption(
                "Mientras tanto puedes subir el archivo a mano acá abajo, o "
                "seguir con «Según lo que ya has vendido», que no lo necesita.")

        st.caption(
            f"Se buscan los números de {LARGO_ID} dígitos en todas las pestañas: "
            "así da igual cómo se llame la columna del ID —«ID REGIÓN CM», «ID "
            "CONVENIO REGIÓN»— y dónde esté.")

        archivo = st.file_uploader(
            "Subir otro archivo (opcional)", type=["xlsx", "xls", "csv"],
            key="mp_archivo",
            help="Solo si quieres probar un catálogo distinto al del Drive.")

        if archivo is not None:
            leidos, explicacion = ids_del_archivo(archivo)
            if not leidos:
                st.error(explicacion)
            else:
                st.success(explicacion)
                izquierda, derecha = st.columns(2)
                with izquierda:
                    if st.button("Usar estos productos", type="primary",
                                 width="stretch", key="mp_usar"):
                        bien, aviso = guardar(usuario, leidos)
                        (st.success if bien else st.error)(aviso)
                        st.rerun()
                with derecha:
                    if ids and st.button("Sumarlos a los que ya tengo",
                                         width="stretch", key="mp_sumar"):
                        bien, aviso = guardar(usuario, ids | leidos)
                        (st.success if bien else st.error)(aviso)
                        st.rerun()

        # «Quitarlos todos» solo tiene sentido para lo cargado a mano: lo del
        # Drive se vuelve a leer solo en la corrida siguiente, así que el botón
        # no haría nada y quedaría como un botón roto.
        if ids and not del_drive:
            if st.button("Quitarlos todos", key="mp_borrar"):
                borrar(usuario)
                st.rerun()

    return ids
