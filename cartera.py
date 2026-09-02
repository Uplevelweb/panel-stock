"""
CARTERA — las unidades que se decidió trabajar
===============================================

EL PUENTE QUE FALTABA ENTRE LAS DOS MITADES DEL SISTEMA
--------------------------------------------------------
Hasta el 01-09-2026 el negocio estaba cortado en dos y las dos mitades no se
hablaban:

  Oportunidades (Streamlit)  mostraba 235 unidades que compran lo que ella
                             vende y nunca le compraron. Y ahí terminaba.
  Panel de envío (Apps       mandaba el catálogo a una lista fija de 224
  Script)                    contactos de una planilla, escrita a mano.

Las dos listas nunca se cruzaron. El panel decía a quién venderle y el envío
le escribía a otra gente.

La cartera es lo que las une: se elige en Oportunidades y queda guardada en
Supabase, que es el único lugar que los dos lados pueden leer. Decidido con
Serling el 01-09-2026 —«datos unidos, envío en Gmail»— justamente para no
tener que mudar el envío fuera de Google.

POR QUE SE GUARDA UNA FOTO DE LOS NUMEROS
------------------------------------------
Se copian `gasto`, `por_ganar` y `situacion` tal como estaban el día que se
agregó la unidad. No es duplicar datos por descuido: sirve para dos cosas que
el cálculo en vivo no puede dar.

  1. El panel de envío no puede recalcular nada —Apps Script no tiene la
     bodega—, así que necesita los números ya escritos.
  2. Al cabo de unos meses se puede comparar: «cuando la metí a la cartera
     compraba $80 M y no me compraba nada; hoy le vendo $12 M». Esa frase es
     de la que depende que alguien renueve.

LA CARTERA ES DE LA EMPRESA, NO DE LA PERSONA
----------------------------------------------
La llave es `cuenta_id`, igual que en `modulo_seguimiento`. Si el comercial
del norte mete una unidad, su jefa la ve sin preguntar. Se guarda quién la
agregó, para saber de quién es.
"""
from __future__ import annotations

import datetime as dt

import pandas as pd
import streamlit as st

import exportar
import modulo_cuentas

CLAVE_SESION = "cartera_local"

# Lo que se guarda de cada unidad. En un solo lugar para que la tabla de
# Supabase, lo que se escribe y lo que se lee no se separen nunca.
CAMPOS = ["codigo_unidad", "nombre_unidad", "nombre_organismo", "region",
          "comuna", "gasto", "por_ganar", "situacion"]

TITULOS = {
    "nombre_unidad": "UNIDAD COMPRADORA", "nombre_organismo": "ORGANISMO",
    "region": "REGIÓN", "comuna": "COMUNA", "gasto": "COMPRA",
    "por_ganar": "POR GANAR", "situacion": "SITUACIÓN",
    "agregada_por": "LA AGREGÓ", "agregada_en": "CUÁNDO", "nota": "NOTA",
}


def _cuenta(usuario: dict) -> str:
    return str((usuario or {}).get("cuenta_id") or "")


# --------------------------------------------------------------------------
#  Leer, agregar, quitar
# --------------------------------------------------------------------------
def leer(usuario: dict) -> pd.DataFrame:
    """La cartera de esa empresa. Vacía si no hay nada o no se pudo preguntar."""
    cuenta = _cuenta(usuario)
    if cuenta:
        filas = modulo_cuentas._pedir(
            f"cartera?select=*&cuenta_id=eq.{cuenta}&order=por_ganar.desc")
        if filas is not None:
            return pd.DataFrame(filas)
    guardadas = st.session_state.get(CLAVE_SESION) or []
    return pd.DataFrame(guardadas)


def agregar(usuario: dict, unidades: pd.DataFrame) -> tuple[int, str]:
    """Mete esas unidades en la cartera. Devuelve (cuántas, aviso)."""
    if unidades is None or unidades.empty:
        return 0, "No había ninguna marcada."

    ahora = dt.datetime.now(dt.timezone.utc).isoformat()
    quien = str((usuario or {}).get("email") or "")
    cuenta = _cuenta(usuario)

    nuevas = []
    for _, fila in unidades.iterrows():
        registro = {campo: fila.get(campo) for campo in CAMPOS}
        registro["codigo_unidad"] = str(registro.get("codigo_unidad") or
                                        fila.get("unidad") or "").strip()
        if not registro["codigo_unidad"]:
            continue
        # Los numeros de pandas (numpy.int64) no son JSON: se pasan a float.
        for numero in ("gasto", "por_ganar"):
            try:
                registro[numero] = float(registro[numero])
            except (TypeError, ValueError):
                registro[numero] = None
        registro["agregada_por"] = quien
        registro["agregada_en"] = ahora
        nuevas.append(registro)

    if not nuevas:
        return 0, "Esas filas no traen código de unidad."

    # Siempre en la sesion, para que funcione en el momento aunque la base no
    # conteste. Mismo criterio que `mis_productos`.
    locales = {r["codigo_unidad"]: r for r in (st.session_state.get(CLAVE_SESION) or [])}
    locales.update({r["codigo_unidad"]: r for r in nuevas})
    st.session_state[CLAVE_SESION] = list(locales.values())

    if not cuenta:
        return len(nuevas), f"{len(nuevas)} en tu cartera, para esta sesión."

    respuesta = modulo_cuentas._pedir(
        "cartera?on_conflict=cuenta_id,codigo_unidad", "POST",
        [dict(r, cuenta_id=cuenta) for r in nuevas],
        extra={"Prefer": "return=representation,resolution=merge-duplicates"})
    if respuesta is None:
        return len(nuevas), (
            f"{len(nuevas)} agregadas **para esta sesión**. Para que queden "
            "guardadas hay que correr `cartera-para-copiar.txt` en Supabase.")
    return len(nuevas), f"{len(nuevas)} unidades quedaron en tu cartera."


def quitar(usuario: dict, codigos: list[str]) -> int:
    """Saca esas unidades de la cartera."""
    codigos = [str(c).strip() for c in codigos if str(c).strip()]
    if not codigos:
        return 0

    locales = [r for r in (st.session_state.get(CLAVE_SESION) or [])
               if r.get("codigo_unidad") not in codigos]
    st.session_state[CLAVE_SESION] = locales

    cuenta = _cuenta(usuario)
    if cuenta:
        lista = ",".join(f'"{c}"' for c in codigos)
        modulo_cuentas._pedir(
            f"cartera?cuenta_id=eq.{cuenta}&codigo_unidad=in.({lista})", "DELETE")
    return len(codigos)


# --------------------------------------------------------------------------
#  La pantalla
# --------------------------------------------------------------------------
def seccion_cartera(usuario: dict) -> None:
    """Las unidades elegidas, para trabajarlas y para que las lea el envío."""
    st.caption(
        "Las unidades que decidiste trabajar. Se eligen en «A quién venderle» "
        "marcando filas. Esta lista es la que va a leer el panel de envío del "
        "catálogo: lo que elijas acá es a quién le vas a escribir.")

    mia = leer(usuario)
    if mia.empty:
        st.info(
            "Tu cartera está vacía. Anda a **A quién venderle**, marca las "
            "unidades que te interesan y aprieta **Agregar a mi cartera**.")
        return

    for columna in ("gasto", "por_ganar"):
        if columna in mia:
            mia[columna] = pd.to_numeric(mia[columna], errors="coerce")

    a, b, c = st.columns(3)
    a.metric("Unidades en cartera", f"{len(mia):,}".replace(",", "."))
    b.metric("Compran al año", _plata(mia.get("gasto", pd.Series(dtype=float)).sum()))
    c.metric("Por ganar", _plata(mia.get("por_ganar", pd.Series(dtype=float)).sum()),
             help="Lo que compran estas unidades y hoy no te compran a ti")

    st.write("")
    visibles = [c for c in ["nombre_unidad", "nombre_organismo", "region", "comuna",
                            "gasto", "por_ganar", "situacion", "agregada_por"]
                if c in mia.columns]
    seleccion = st.dataframe(
        mia[visibles], width="stretch", hide_index=True, height=420,
        on_select="rerun", selection_mode="multi-row", key="ca_tabla",
        column_config={
            "nombre_unidad": st.column_config.TextColumn("Unidad compradora", width="large"),
            "nombre_organismo": st.column_config.TextColumn("Organismo", width="large"),
            "region": st.column_config.TextColumn("Región", width="small"),
            "comuna": st.column_config.TextColumn("Comuna", width="small"),
            "gasto": st.column_config.NumberColumn("Compra", format="localized", width="small"),
            "por_ganar": st.column_config.NumberColumn("Por ganar", format="localized", width="small"),
            "situacion": st.column_config.TextColumn("Situación", width="medium"),
            "agregada_por": st.column_config.TextColumn("La agregó", width="medium"),
        })

    from app import filas_seleccionadas
    marcadas = mia.iloc[filas_seleccionadas(seleccion, len(mia))]

    izquierda, derecha = st.columns([1, 1])
    with izquierda:
        exportar.boton_excel(
            mia[visibles].rename(columns=TITULOS),
            nombre="Cartera", clave="cartera", hoja="Cartera",
            etiqueta="Bajar la cartera", ancho="stretch")
    with derecha:
        if st.button(f"Sacar las {len(marcadas)} marcadas" if len(marcadas)
                     else "Sacar de la cartera", key="ca_quitar",
                     width="stretch", disabled=marcadas.empty):
            quitar(usuario, marcadas["codigo_unidad"].tolist())
            st.rerun()


def _plata(monto: float) -> str:
    monto = float(monto or 0)
    if abs(monto) >= 1e9:
        return f"${monto/1e6:,.0f} M".replace(",", ".")
    return f"${monto:,.0f}".replace(",", ".")
