"""
MÓDULO VISITAS — el IPT, Itinerario Permanente de Visitas
==========================================================

LO QUE ESTE MODULO NO ES
------------------------
No es un calendario para ir a ver a todos. Ese calendario no existe, y el
numero lo dice solo: con 1.882 unidades objetivo y una jornada real, verlas
UNA vez toma entre 1,1 y 1,6 años. Prometer la ruta completa es prometer algo
que no se puede cumplir.

LO QUE SI ES
------------
La linea donde se deja de visitar y se empieza a llamar. Medido sobre datos
reales el 27-08-2026:

    las  20 mejores unidades = 30% de la plata por ganar
    las 100 mejores unidades = 51%   <- 3 a 5 semanas de visitas
    las 200 mejores unidades = 64%

O sea: la mitad del dinero esta al alcance de un mes de visitas, y la otra
mitad esta repartida en mil setecientas puertas que no se pueden tocar. A esas
se las llama.

EL MODELO DE TIEMPO, MEDIDO Y NO SUPUESTO
-----------------------------------------
    jornada 08:30-18:30 menos colacion = 9 h productivas al dia · 45 a la semana
    misma comuna    80 min por visita -> 6,8 al dia · 34 a la semana
    entre comunas  120 min por visita -> 4,5 al dia · 22 a la semana

La diferencia entre 80 y 120 minutos es el traslado, y por eso las visitas se
AGRUPAN por comuna: cuatro visitas en Iquique cuestan una sola llegada a
Iquique. Pero el itinerario se cuenta visita por visita, no comuna por comuna,
porque la linea tiene que poder caer en medio de una comuna grande: Santiago
sola son mas de setenta visitas, o sea dos semanas, y cortar por comuna entera
dejaba en cero cualquier agenda de una semana.

DE DONDE SALE «LO QUE HAY PARA GANAR»
-------------------------------------
Del panorama de `modulo_mercado`, que mira las SEIS vias de compra y no solo
Convenio Marco. Por ganar = lo que la unidad compra en el rubro menos lo que
este proveedor ya le vende. Donde ya vende no hay lo mismo que ganar.

POR QUE UNA TABLA Y NO UN MAPA
------------------------------
El mapa necesita las coordenadas de las 346 comunas, que la bodega no tiene.
Agrupada por comuna y ordenada por lo que hay para ganar, la tabla contesta la
misma pregunta —a donde voy primero— sin esa tabla de latitudes que todavia no
existe.
"""
import numpy as np
import pandas as pd
import streamlit as st

import modulo_cuentas

# --------------------------------------------------------------------------
#  El modelo de la jornada. Todo lo demas sale de estos cuatro numeros.
# --------------------------------------------------------------------------
HORAS_PRODUCTIVAS_SEMANA = 45.0     # 9 h al dia por 5 dias, sin colacion
MINUTOS_MISMA_COMUNA = 80           # visita + traslado corto
MINUTOS_ENTRE_COMUNAS = 120         # visita + llegar a otra comuna

# Debajo de esto no se justifica el viaje: es una visita que cuesta mas que lo
# que hay para ganar. Se puede mover en pantalla.
PISO_POR_GANAR = 5_000_000


def plan_de_visitas(datos: dict, unidades: pd.DataFrame,
                    piso: float = PISO_POR_GANAR,
                    usuario: dict | None = None) -> pd.DataFrame:
    """El itinerario, visita por visita y en orden.

    `datos` es lo que devuelve `modulo_mercado.panorama_del_mercado`.
    `usuario` es lo que devuelve `modulo_cuentas.quien_soy()`: si esa persona
    tiene territorio, el itinerario es el suyo y no el de la empresa entera.

    EL TERRITORIO SE APLICA ANTES DE CONTAR LAS HORAS, y ese orden importa:
    si se filtrara despues, el comercial de Antofagasta veria que su primera
    visita cae en la semana 3 —porque delante suyo quedaron las de Santiago,
    que no son suyas— y su agenda no significaria nada.

    SE CUENTA VISITA POR VISITA, NO COMUNA POR COMUNA, y esto no es un detalle:
    la primera version cortaba por comuna entera y con una semana de agenda
    devolvia CERO, porque Santiago sola son 72 visitas —dos semanas— y no
    entraba completa. Nadie trabaja asi: se va a Santiago y se ve a los mejores
    que alcancen. La linea tiene que poder caer en medio de una comuna.

    El costo de cada visita: la primera de una comuna paga el traslado largo
    —hay que llegar hasta alla— y las siguientes el corto, porque ya se esta
    ahi. Es lo unico del calculo que no es una suma.
    """
    if not datos.get("unidades"):
        return pd.DataFrame()

    mio = datos.get("mio_por_unidad") or {}
    filas = []
    for codigo, compra in datos["unidades"].items():
        por_ganar = float(compra) - float(mio.get(codigo, 0.0))
        if por_ganar < piso:
            continue
        filas.append({"codigo_unidad": str(codigo), "compra": float(compra),
                      "ya_vendido": float(mio.get(codigo, 0.0)),
                      "por_ganar": por_ganar})
    if not filas:
        return pd.DataFrame()

    tabla = pd.DataFrame(filas)
    if not unidades.empty:
        tabla = tabla.merge(
            unidades[["codigo_unidad", "nombre_unidad", "region", "comuna"]],
            on="codigo_unidad", how="left")
    for columna, defecto in (("nombre_unidad", "(sin catalogar)"),
                             ("region", "Sin región"), ("comuna", "Sin comuna")):
        if columna not in tabla:
            tabla[columna] = defecto
        tabla[columna] = (tabla[columna].replace("", defecto).fillna(defecto))

    if usuario:
        tabla = modulo_cuentas.filtrar_por_territorio(tabla, usuario)
        if tabla.empty:
            return pd.DataFrame()

    # El orden de las comunas: por lo que hay para ganar en cada una. Las que
    # no tienen comuna van SIEMPRE al final, por mucha plata que muevan: no se
    # le arma ruta a una direccion que no se sabe, y si quedaran arriba se
    # comerian las primeras semanas con visitas que nadie puede planificar.
    peso = tabla.groupby("comuna", observed=True)["por_ganar"].sum()
    tabla["peso_comuna"] = tabla["comuna"].map(peso)
    tabla["sin_direccion"] = (tabla["comuna"] == "Sin comuna").astype(int)
    tabla = tabla.sort_values(
        ["sin_direccion", "peso_comuna", "comuna", "por_ganar"],
        ascending=[True, False, True, False]).reset_index(drop=True)

    # La primera visita de cada comuna paga el traslado largo; las siguientes,
    # el corto. `cumcount` da 0 en la primera de cada grupo.
    primera = tabla.groupby("comuna", observed=True).cumcount() == 0
    tabla["minutos"] = np.where(primera, MINUTOS_ENTRE_COMUNAS, MINUTOS_MISMA_COMUNA)
    tabla["horas_acumuladas"] = (tabla["minutos"].cumsum() / 60).round(1)
    tabla["semana"] = (tabla["horas_acumuladas"] / HORAS_PRODUCTIVAS_SEMANA).round(2)
    total = tabla["por_ganar"].sum()
    tabla["parte_acumulada"] = (
        (tabla["por_ganar"].cumsum() / total * 100).round(1) if total else 0.0)
    tabla["visita"] = range(1, len(tabla) + 1)
    return tabla.drop(columns=["peso_comuna", "sin_direccion"])


def resumen_por_comuna(plan: pd.DataFrame, semanas: float) -> pd.DataFrame:
    """El plan visto por comuna: cuántas visitas de cada una entran en el plazo.

    Una comuna puede quedar partida —entran seis de sus veinte unidades— y eso
    es lo correcto: se viaja igual, se ve a los mejores que alcancen.
    """
    if plan.empty:
        return pd.DataFrame()
    marcado = plan.assign(alcanza=(plan["semana"] <= semanas).astype(int))
    marcado["ganado"] = marcado["por_ganar"].where(marcado["alcanza"] == 1, 0.0)
    resumen = (marcado.groupby(["comuna", "region"], observed=True)
               .agg(unidades=("codigo_unidad", "count"),
                    alcanzan=("alcanza", "sum"),
                    por_ganar=("por_ganar", "sum"),
                    por_ganar_alcanzado=("ganado", "sum"),
                    minutos=("minutos", "sum"),
                    termina_semana=("semana", "max"))
               .reset_index())
    resumen["horas"] = (resumen["minutos"] / 60).round(1)
    return (resumen.drop(columns="minutos")
            .sort_values(["alcanzan", "por_ganar"], ascending=[False, False]))


def _plata(monto: float) -> str:
    if abs(monto) >= 1e9:
        return f"${monto/1e6:,.0f} M".replace(",", ".")
    return f"${monto:,.0f}".replace(",", ".")


def seccion_visitas(datos: dict, unidades: pd.DataFrame) -> None:
    """La agenda de visitas, debajo de los gráficos del mercado."""
    st.divider()
    st.markdown("#### A quién ir a ver, y a quién llamar")
    st.caption(
        "Visitar a todos no se puede: la jornada da lo que da. Esto ordena las "
        "visitas por lo que hay para ganar, agrupadas por comuna para no pagar "
        "dos veces el mismo viaje, y muestra **dónde está la línea**: hasta ahí "
        "se va en persona, de ahí para abajo se llama.")

    if not datos.get("unidades"):
        st.info("Primero hay que calcular el mercado, con el botón de arriba.")
        return

    izquierda, derecha = st.columns(2)
    with izquierda:
        semanas = st.slider("Semanas de visitas que tienes", 1, 26, 4,
                            key="vi_semanas",
                            help="Una semana son 45 horas productivas: de 08:30 "
                                 "a 18:30 menos colación, cinco días.")
    with derecha:
        piso = st.select_slider(
            "Mínimo por ganar para que valga el viaje",
            options=[1_000_000, 5_000_000, 10_000_000, 25_000_000, 50_000_000],
            value=PISO_POR_GANAR, key="vi_piso", format_func=_plata)

    usuario = modulo_cuentas.quien_soy()
    plan = plan_de_visitas(datos, unidades, piso, usuario)
    if plan.empty:
        if modulo_cuentas.tiene_territorio(usuario):
            st.warning(
                f"No hay unidades sobre ese mínimo **en tu territorio** "
                f"({modulo_cuentas.resumen_de_territorio(usuario)}). Baja el "
                "piso, o pídele a tu administrador que revise las regiones "
                "que tienes asignadas.")
        else:
            st.warning("No hay unidades con ese mínimo por ganar. Baja el piso.")
        return

    if modulo_cuentas.tiene_territorio(usuario):
        st.caption(f"Este itinerario es **el tuyo**: "
                   f"{modulo_cuentas.resumen_de_territorio(usuario)}.")

    dentro = plan[plan["semana"] <= semanas]
    fuera = plan[plan["semana"] > semanas]
    total = plan["por_ganar"].sum()

    a, b, c, d = st.columns(4)
    a.metric("Visitas que caben", f"{len(dentro):,}".replace(",", "."))
    b.metric("Comunas que alcanzas",
             f"{dentro['comuna'].nunique():,}".replace(",", "."))
    c.metric("Plata al alcance", _plata(dentro["por_ganar"].sum()),
             help="Lo que compran en tu rubro las unidades que sí alcanzas a ver")
    d.metric("Del total por ganar",
             f"{dentro['por_ganar'].sum() / total * 100:.0f}%" if total else "0%")

    if len(fuera):
        st.info(
            f"**La línea cae en la visita {len(dentro) + 1}.** Con {semanas} "
            f"semanas alcanzas {len(dentro)} visitas en "
            f"{dentro['comuna'].nunique()} comunas, y eso es "
            f"{dentro['por_ganar'].sum() / total * 100:.0f}% de todo lo que hay "
            f"por ganar. Las otras {len(fuera)} unidades "
            f"—{_plata(fuera['por_ganar'].sum())}— no se alcanzan a visitar en "
            "ese plazo: **a ésas se las llama.**")
    else:
        st.success(
            f"Con {semanas} semanas alcanzas las {len(plan)} visitas. No hace "
            "falta dejar a nadie para el teléfono.")

    # ----------------------------------------------------------------------
    #  El itinerario, visita por visita
    # ----------------------------------------------------------------------
    st.markdown("**El itinerario, en orden**")
    st.caption("En este orden: primero las comunas donde hay más para ganar, y "
               "dentro de cada una las unidades más grandes.")
    vista = plan.copy()
    vista["plan"] = ["Ir" if s <= semanas else "Llamar" for s in vista["semana"]]
    st.dataframe(
        vista[["visita", "plan", "comuna", "nombre_unidad", "region",
               "por_ganar", "semana", "parte_acumulada"]],
        width="stretch", hide_index=True, height=440,
        column_config={
            "visita": st.column_config.NumberColumn("#", width="small"),
            "plan": st.column_config.TextColumn("Plan", width="small"),
            "comuna": st.column_config.TextColumn("Comuna", width="medium"),
            "nombre_unidad": st.column_config.TextColumn(
                "Unidad compradora", width="large"),
            "region": st.column_config.TextColumn("Región", width="medium"),
            "por_ganar": st.column_config.NumberColumn(
                "Por ganar", format="localized"),
            "semana": st.column_config.NumberColumn(
                "Semana", format="%.1f",
                help="En qué semana caería esa visita si se va en este orden"),
            "parte_acumulada": st.column_config.NumberColumn(
                "% acumulado", format="%.1f%%",
                help="Qué parte de toda la plata por ganar llevas hasta ahí"),
        })

    # ----------------------------------------------------------------------
    #  El mismo plan, visto por comuna
    # ----------------------------------------------------------------------
    with st.expander("Verlo por comuna — cuántas visitas entran en cada una"):
        st.caption(
            "Una comuna puede quedar partida y está bien: se viaja igual y se "
            "ve a las mejores que alcancen. La columna «Alcanzan» dice cuántas.")
        resumen = resumen_por_comuna(plan, semanas)
        st.dataframe(
            resumen[["comuna", "region", "unidades", "alcanzan", "por_ganar",
                     "por_ganar_alcanzado", "horas"]],
            width="stretch", hide_index=True, height=380,
            column_config={
                "comuna": st.column_config.TextColumn("Comuna", width="medium"),
                "region": st.column_config.TextColumn("Región", width="medium"),
                "unidades": st.column_config.NumberColumn("Unidades"),
                "alcanzan": st.column_config.NumberColumn(
                    "Alcanzan", help="Cuántas de esas visitas entran en el plazo"),
                "por_ganar": st.column_config.NumberColumn(
                    "Por ganar", format="localized"),
                "por_ganar_alcanzado": st.column_config.NumberColumn(
                    "Del que alcanzas", format="localized"),
                "horas": st.column_config.NumberColumn(
                    "Horas", format="%.1f",
                    help="Lo que cuesta verlas todas, viaje incluido"),
            })

    sin_comuna = plan[plan["comuna"] == "Sin comuna"]
    if len(sin_comuna):
        st.caption(
            f"⚠️ {len(sin_comuna)} unidades sin comuna registrada "
            f"({_plata(sin_comuna['por_ganar'].sum())} por ganar) van al final "
            "de la lista: no se les puede armar ruta hasta saber dónde están.")
