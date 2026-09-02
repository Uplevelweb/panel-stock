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

# Un ID de Convenio Marco es un número de varios dígitos («4194137»). El piso
# de 5 descarta cantidades, años y números de fila, que es lo que ensucia
# cuando se lee una planilla entera sin saber qué columna mirar.
LARGO_MINIMO_ID = 5
CLAVE_SESION = "mis_ids"


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
            buenos = valores[valores.str.fullmatch(r"\d{%d,}" % LARGO_MINIMO_ID)]
            encontrados.update(buenos.tolist())

    if not encontrados:
        return set(), ("No encontré ningún ID en ese archivo. Tienen que ser "
                       "números de al menos 5 dígitos, en cualquier columna.")
    return encontrados, (f"{len(encontrados):,}".replace(",", ".") +
                         f" productos leídos de «{nombre}»" +
                         (f", {len(hojas)} pestañas" if len(hojas) > 1 else ""))


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
    """El panel donde el cliente carga su catálogo. Devuelve los ID vigentes."""
    ids = leer(usuario)

    titulo = ("Mis productos publicados — " +
              (f"{len(ids):,}".replace(",", ".") + " cargados" if ids
               else "todavía sin cargar"))
    with st.expander(titulo, expanded=not ids):
        st.caption(
            "Sube tu catálogo de Convenio Marco —el mismo archivo que usas para "
            "cotizar— y el panel cruza cada compra contra tus ID. No hace falta "
            "que digas qué columna es: se buscan los números de 5 dígitos o más "
            "en todas las pestañas.")

        archivo = st.file_uploader(
            "Tu catálogo", type=["xlsx", "xls", "csv"], key="mp_archivo",
            help="Vale el catálogo completo, con una pestaña por rubro.")

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

        if ids:
            st.caption(f"Hoy hay **{len(ids):,}".replace(",", ".") +
                       "** productos cargados.")
            if st.button("Quitarlos todos", key="mp_borrar"):
                borrar(usuario)
                st.rerun()

    return ids
