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
# El mismo texto que usa app.TODOS_CONVENIOS. Se repite aqui a proposito:
# importar app.py desde este modulo seria un ciclo.
TODOS_CONVENIOS_POR_DEFECTO = "Todos los convenios"

# Lo que compone una vista. En un solo lugar para que guardar y aplicar no se
# separen nunca: si se agrega un filtro nuevo a la pantalla, se agrega aquí y
# queda guardado solo.
CAMPOS = {
    "op_rut": "",
    "op_forma": "Según lo que ya has vendido",
    "op_convenios": [],
    "op_situacion": [],
    "op_region": [],
    "op_organismo": [],
    "op_unidad": [],
    "op_sin_organismo": [],
    "op_sin_unidad": [],
}

# Lo mismo para Mercado Publico (03-09-2026). Es la CARTERA del comercial:
# «mis instituciones de Valparaiso y Metropolitana», para volver mañana sin
# rearmarla.
#
# ⚠️ EL PERIODO NO SE GUARDA, a proposito. Una cartera dice A QUIEN le vendes,
# no en que fechas: guardar el rango haria que una vista de septiembre se
# abriera en enero mirando meses viejos. El periodo ya se propone solo, un año
# hacia atras.
CAMPOS_MP = {
    "mp_convenio_uno": TODOS_CONVENIOS_POR_DEFECTO,
    "mp_region": [],
    "mp_organismo": [],
    "mp_busqueda": "",
    "mp_unidades": [],
}

# Los dos ambitos, con la columna de Supabase donde vive cada uno. Los `op_*`
# tienen una columna cada uno por historia; los de Mercado van TODOS dentro de
# un solo `jsonb`, que es como habria que haber hecho el primero: agregar un
# filtro nuevo no obliga a tocar la tabla.
AMBITOS = {
    "oportunidades": {"campos": CAMPOS, "columna": None, "prefijo": "vi"},
    "mercado": {"campos": CAMPOS_MP, "columna": "mp", "prefijo": "vimp"},
}


def _quien(usuario: dict) -> str:
    return str((usuario or {}).get("email") or "").strip().lower()


# --------------------------------------------------------------------------
#  Leer y guardar
# --------------------------------------------------------------------------
def leer(usuario: dict, ambito: str = "oportunidades") -> list[dict]:
    """Las vistas de esa persona en ese ambito, la de entrada primero.

    Se filtra por ambito EN PYTHON y no en la consulta: las filas viejas —las
    guardadas antes de que Mercado Publico tuviera vistas— no traen la columna,
    y se cuentan como de Oportunidades, que es lo que eran.
    """
    correo = _quien(usuario)
    filas = None
    if correo:
        filas = modulo_cuentas._pedir(
            "vistas?select=*&email=eq." + correo + "&order=de_entrada.desc,nombre")
    if filas is None:
        filas = list(st.session_state.get(CLAVE_SESION) or [])
    return [f for f in filas if (f.get("ambito") or "oportunidades") == ambito]


def guardar(usuario: dict, nombre: str, de_entrada: bool,
            ambito: str = "oportunidades") -> tuple[bool, str]:
    """Guarda los filtros que están puestos ahora, con ese nombre."""
    nombre = " ".join(str(nombre or "").split())
    if not nombre:
        return False, "Ponle un nombre a la vista."

    receta = AMBITOS[ambito]
    vista = {"nombre": nombre, "de_entrada": bool(de_entrada),
             "email": _quien(usuario), "ambito": ambito,
             "guardada_en": dt.datetime.now(dt.timezone.utc).isoformat()}
    valores = {}
    for campo, defecto in receta["campos"].items():
        valor = st.session_state.get(campo, defecto)
        # Los multiselect devuelven listas; el radio y el texto, cadenas.
        valores[campo] = list(valor) if isinstance(valor, (list, tuple, set)) else valor
    if receta["columna"]:
        vista[receta["columna"]] = valores      # todo junto en un jsonb
    else:
        vista.update(valores)                   # una columna por campo

    # La copia de sesión guarda SIEMPRE los campos sueltos además del jsonb: es
    # la que se usa cuando no hay Supabase, y `aplicar` los busca por su nombre.
    en_sesion = dict(vista)
    en_sesion.update(valores)
    locales = [v for v in (st.session_state.get(CLAVE_SESION) or [])
               if not (v.get("nombre") == nombre
                       and (v.get("ambito") or "oportunidades") == ambito)]
    if de_entrada:
        for v in locales:
            if (v.get("ambito") or "oportunidades") == ambito:
                v["de_entrada"] = False
    locales.append(en_sesion)
    st.session_state[CLAVE_SESION] = locales

    if not vista["email"]:
        return True, f"Vista «{nombre}» guardada para esta sesión."

    if de_entrada:
        modulo_cuentas._pedir(
            "vistas?email=eq." + vista["email"] + "&ambito=eq." + ambito,
            "PATCH", {"de_entrada": False})
    respuesta = modulo_cuentas._pedir(
        "vistas?on_conflict=email,nombre", "POST", [vista],
        extra={"Prefer": "return=representation,resolution=merge-duplicates"})
    if respuesta is None:
        return True, (f"Vista «{nombre}» guardada **para esta sesión**: se pierde al "
                      "cerrar el panel. Para que quede, hay que correr "
                      "`vistas-para-copiar.txt` en Supabase.")
    return True, f"Vista «{nombre}» guardada."


def borrar(usuario: dict, nombre: str, ambito: str = "oportunidades") -> None:
    st.session_state[CLAVE_SESION] = [
        v for v in (st.session_state.get(CLAVE_SESION) or [])
        if not (v.get("nombre") == nombre
                and (v.get("ambito") or "oportunidades") == ambito)]
    correo = _quien(usuario)
    if correo:
        import urllib.parse
        modulo_cuentas._pedir(
            "vistas?email=eq." + correo + "&nombre=eq." +
            urllib.parse.quote(nombre) + "&ambito=eq." + ambito, "DELETE")


def aplicar(vista: dict, ambito: str = "oportunidades") -> None:
    """Deja los filtros de esa vista puestos en la pantalla.

    Se escribe en `session_state` ANTES de que se dibujen los widgets, que es
    la única forma de que Streamlit los muestre ya puestos. Por eso esto se
    llama al principio de la sección y no al apretar un botón.
    """
    receta = AMBITOS[ambito]
    # Los de Mercado vienen dentro del jsonb cuando la fila salió de Supabase, y
    # sueltos cuando salió de la sesión. Se miran los dos lados.
    guardados = dict(vista.get(receta["columna"]) or {}) if receta["columna"] else {}
    for campo in receta["campos"]:
        valor = guardados.get(campo, vista.get(campo))
        if valor is not None:
            st.session_state[campo] = valor

    if ambito != "oportunidades":
        return
    # La copia que sobrevive al cambio de sección también se pone al día, o la
    # vista recién aplicada duraría hasta que se mirara otra sección.
    # Ver `modulo_oportunidades._recordar_filtros`.
    from modulo_oportunidades import COPIA_FILTROS, PERSISTEN
    st.session_state[COPIA_FILTROS] = {
        clave: list(vista.get(clave) or []) for clave in PERSISTEN}
    # Para que la consulta se lance sola, sin tener que apretar el botón.
    if vista.get("op_rut"):
        st.session_state["op_visto"] = vista["op_rut"]


def aplicar_la_de_entrada(usuario: dict, ambito: str = "oportunidades") -> str:
    """Al abrir la pestaña, deja puesta la vista de entrada. Una sola vez."""
    marca = f"vista_aplicada_{ambito}"
    if st.session_state.get(marca):
        return ""
    st.session_state[marca] = True
    for vista in leer(usuario, ambito):
        if vista.get("de_entrada"):
            aplicar(vista, ambito)
            return str(vista.get("nombre") or "")
    return ""


# --------------------------------------------------------------------------
#  La pantalla
# --------------------------------------------------------------------------
TEXTOS = {
    "oportunidades": {
        "titulo": "Mis vistas guardadas",
        "que_guarda": ("Una vista guarda **todo el conjunto**: el RUT, con qué comparas y "
                       "los cinco filtros. Sirve para volver mañana a lo mismo sin "
                       "rearmarlo. La que marques como de entrada se aplica sola al abrir."),
        "ejemplo": "Hospitales de Valparaíso",
        "donde": "Oportunidades",
    },
    "mercado": {
        "titulo": "Mi cartera guardada",
        "que_guarda": ("Guarda **a quién le vendes**: el convenio, las regiones, los "
                       "organismos, la búsqueda y las unidades marcadas. Es tu cartera: "
                       "vuelves mañana sin rearmarla. **El período no se guarda** —una "
                       "cartera dice a quién, no en qué fechas— y se propone solo, un año "
                       "hacia atrás. La que marques como de entrada se aplica sola al abrir."),
        "ejemplo": "Mi cartera Armada",
        "donde": "Mercado Público",
    },
}


def barra_de_vistas(usuario: dict, ambito: str = "oportunidades") -> None:
    """El selector de vistas y el botón de guardar la que está puesta."""
    receta = AMBITOS[ambito]
    textos = TEXTOS[ambito]
    p = receta["prefijo"]                      # las llaves no se pueden repetir
    guardadas = leer(usuario, ambito)
    nombres = [str(v.get("nombre") or "") for v in guardadas]

    with st.expander(textos["titulo"] +
                     (f" — {len(nombres)}" if nombres else " — ninguna todavía")):
        st.caption(textos["que_guarda"])
        if not _quien(usuario):
            st.info(
                "Todavía no hay con quién asociarlas, así que **viven solo en esta "
                "sesión**: al cerrar el panel se pierden. Quedan de verdad cuando se "
                "corra `vistas-para-copiar.txt` en Supabase.")

        if nombres:
            elegir, aplicar_col, borrar_col = st.columns([3, 1, 1])
            with elegir:
                elegida = st.selectbox("Vista", nombres, key=f"{p}_elegida",
                                       label_visibility="collapsed")
            with aplicar_col:
                if st.button("Aplicar", key=f"{p}_aplicar", width="stretch"):
                    for v in guardadas:
                        if v.get("nombre") == elegida:
                            aplicar(v, ambito)
                            st.rerun()
            with borrar_col:
                if st.button("Borrar", key=f"{p}_borrar", width="stretch"):
                    borrar(usuario, elegida, ambito)
                    st.rerun()
            st.divider()

        st.caption("Guardar los filtros que tienes puestos ahora:")
        nombre_col, entrada_col, boton_col = st.columns([3, 1, 1])
        with nombre_col:
            nombre = st.text_input("Nombre", key=f"{p}_nombre",
                                   placeholder=textos["ejemplo"],
                                   label_visibility="collapsed")
        with entrada_col:
            de_entrada = st.checkbox("De entrada", key=f"{p}_entrada",
                                     help=f"Se aplica sola al abrir {textos['donde']}.")
        with boton_col:
            if st.button("Guardar", key=f"{p}_guardar", type="primary",
                         width="stretch"):
                bien, aviso = guardar(usuario, nombre, de_entrada, ambito)
                (st.success if bien else st.error)(aviso)
