"""
VISTAS — el filtro guardado de cada vendedor
=============================================

EL PEDIDO, TEXTUAL: «configurar en el panel de inicio para este vendedor poder
crear filtro de vista» (Serling, 01-09-2026, punto 4).

Es el tercer filtro, y es de otra clase que los otros dos. Institución y unidad
acotan UNA consulta; la vista guarda TODO el conjunto —el RUT, la forma de
comparar, la situación, la región, las instituciones, las unidades y lo que se
sacó de la lista— con un nombre, para volver a eso mañana sin rearmarlo.

POR QUE ES DEL VENDEDOR Y NO DE LA EMPRESA
-------------------------------------------
Al revés que la cartera, que es de la empresa ([[cartera]]). Una vista es la
manera de trabajar de una persona: «mis hospitales de Valparaíso», «las
municipalidades que nunca me han comprado». Si fueran de la cuenta, dos
comerciales se pisarían los nombres y cada uno vería los recortes del otro.

TAMBIEN ARREGLA LA PANTALLA VACIA
----------------------------------
La vista marcada como la de entrada se aplica sola al abrir Oportunidades. Sin
eso la primera pantalla decía «Escribe un RUT para empezar» y nada más, que en
una demo obliga a escribir para que aparezca algo.

SIN SUPABASE FUNCIONA IGUAL
----------------------------
Mientras no se corra `vistas-para-copiar.txt`, las vistas viven en la sesión y
la pantalla lo dice. Mismo criterio que [[cartera]] y `mis_productos`: una
función nueva no puede dejar el panel esperando a que alguien corra un SQL.
"""
from __future__ import annotations

import datetime as dt

import streamlit as st

import modulo_cuentas

CLAVE_SESION = "vistas_local"

# Lo que compone una vista. En un solo lugar para que guardar y aplicar no se
# separen nunca: si se agrega un filtro nuevo a la pantalla, se agrega aquí y
# queda guardado solo.
CAMPOS = {
    "op_rut": "",
    "op_forma": "Según lo que ya has vendido",
    "op_situacion": [],
    "op_region": [],
    "op_organismo": [],
    "op_unidad": [],
    "op_sin_organismo": [],
    "op_sin_unidad": [],
}


def _quien(usuario: dict) -> str:
    return str((usuario or {}).get("email") or "").strip().lower()


# --------------------------------------------------------------------------
#  Leer y guardar
# --------------------------------------------------------------------------
def leer(usuario: dict) -> list[dict]:
    """Las vistas de esa persona, la de entrada primero."""
    correo = _quien(usuario)
    if correo:
        filas = modulo_cuentas._pedir(
            "vistas?select=*&email=eq." + correo + "&order=de_entrada.desc,nombre")
        if filas is not None:
            return filas
    return list(st.session_state.get(CLAVE_SESION) or [])


def guardar(usuario: dict, nombre: str, de_entrada: bool) -> tuple[bool, str]:
    """Guarda los filtros que están puestos ahora, con ese nombre."""
    nombre = " ".join(str(nombre or "").split())
    if not nombre:
        return False, "Ponle un nombre a la vista."

    vista = {"nombre": nombre, "de_entrada": bool(de_entrada),
             "email": _quien(usuario),
             "guardada_en": dt.datetime.now(dt.timezone.utc).isoformat()}
    for campo, defecto in CAMPOS.items():
        valor = st.session_state.get(campo, defecto)
        # Los multiselect devuelven listas; el radio y el texto, cadenas.
        vista[campo] = list(valor) if isinstance(valor, (list, tuple, set)) else valor

    locales = [v for v in (st.session_state.get(CLAVE_SESION) or [])
               if v.get("nombre") != nombre]
    if de_entrada:
        for v in locales:
            v["de_entrada"] = False
    locales.append(vista)
    st.session_state[CLAVE_SESION] = locales

    if not vista["email"]:
        return True, f"Vista «{nombre}» guardada para esta sesión."

    if de_entrada:
        modulo_cuentas._pedir("vistas?email=eq." + vista["email"], "PATCH",
                              {"de_entrada": False})
    respuesta = modulo_cuentas._pedir(
        "vistas?on_conflict=email,nombre", "POST", [vista],
        extra={"Prefer": "return=representation,resolution=merge-duplicates"})
    if respuesta is None:
        return True, (f"Vista «{nombre}» guardada **para esta sesión**. Para que "
                      "quede, hay que correr `vistas-para-copiar.txt` en Supabase.")
    return True, f"Vista «{nombre}» guardada."


def borrar(usuario: dict, nombre: str) -> None:
    st.session_state[CLAVE_SESION] = [
        v for v in (st.session_state.get(CLAVE_SESION) or [])
        if v.get("nombre") != nombre]
    correo = _quien(usuario)
    if correo:
        import urllib.parse
        modulo_cuentas._pedir(
            "vistas?email=eq." + correo + "&nombre=eq." +
            urllib.parse.quote(nombre), "DELETE")


def aplicar(vista: dict) -> None:
    """Deja los filtros de esa vista puestos en la pantalla.

    Se escribe en `session_state` ANTES de que se dibujen los widgets, que es
    la única forma de que Streamlit los muestre ya puestos. Por eso esto se
    llama al principio de `seccion_oportunidades` y no al apretar un botón.
    """
    for campo, defecto in CAMPOS.items():
        if campo in vista and vista[campo] is not None:
            st.session_state[campo] = vista[campo]
    # La copia que sobrevive al cambio de sección también se pone al día, o la
    # vista recién aplicada duraría hasta que se mirara otra sección.
    # Ver `modulo_oportunidades._recordar_filtros`.
    from modulo_oportunidades import COPIA_FILTROS, FILTROS
    st.session_state[COPIA_FILTROS] = {
        clave: list(vista.get(clave) or []) for clave, _, _ in FILTROS}
    # Para que la consulta se lance sola, sin tener que apretar el botón.
    if vista.get("op_rut"):
        st.session_state["op_visto"] = vista["op_rut"]


def aplicar_la_de_entrada(usuario: dict) -> str:
    """Al abrir la pestaña, deja puesta la vista de entrada. Una sola vez."""
    if st.session_state.get("vista_aplicada"):
        return ""
    st.session_state["vista_aplicada"] = True
    for vista in leer(usuario):
        if vista.get("de_entrada"):
            aplicar(vista)
            return str(vista.get("nombre") or "")
    return ""


# --------------------------------------------------------------------------
#  La pantalla
# --------------------------------------------------------------------------
def barra_de_vistas(usuario: dict) -> None:
    """El selector de vistas y el botón de guardar la que está puesta."""
    guardadas = leer(usuario)
    nombres = [str(v.get("nombre") or "") for v in guardadas]

    with st.expander("Mis vistas guardadas" +
                     (f" — {len(nombres)}" if nombres else " — ninguna todavía")):
        st.caption(
            "Una vista guarda **todo el conjunto**: el RUT, con qué comparas y "
            "los cinco filtros. Sirve para volver mañana a lo mismo sin "
            "rearmarlo. La que marques como de entrada se aplica sola al abrir.")

        if nombres:
            elegir, aplicar_col, borrar_col = st.columns([3, 1, 1])
            with elegir:
                elegida = st.selectbox("Vista", nombres, key="vi_elegida",
                                       label_visibility="collapsed")
            with aplicar_col:
                if st.button("Aplicar", key="vi_aplicar", width="stretch"):
                    for v in guardadas:
                        if v.get("nombre") == elegida:
                            aplicar(v)
                            st.rerun()
            with borrar_col:
                if st.button("Borrar", key="vi_borrar", width="stretch"):
                    borrar(usuario, elegida)
                    st.rerun()
            st.divider()

        st.caption("Guardar los filtros que tienes puestos ahora:")
        nombre_col, entrada_col, boton_col = st.columns([3, 1, 1])
        with nombre_col:
            nombre = st.text_input("Nombre", key="vi_nombre",
                                   placeholder="Hospitales de Valparaíso",
                                   label_visibility="collapsed")
        with entrada_col:
            de_entrada = st.checkbox("De entrada", key="vi_entrada",
                                     help="Se aplica sola al abrir Oportunidades.")
        with boton_col:
            if st.button("Guardar", key="vi_guardar", type="primary",
                         width="stretch"):
                bien, aviso = guardar(usuario, nombre, de_entrada)
                (st.success if bien else st.error)(aviso)
