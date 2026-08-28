"""
MÓDULO OPORTUNIDADES — a quién le puedo vender y todavía no le vendo
=====================================================================

Se escribe un RUT y sale el mapa comercial de ese proveedor: cuánto compra el
Estado en sus rubros, cuánto se lleva él, y sobre todo las unidades que compran
lo que él vende y nunca le han comprado.

POR QUE ESTO NO ES UNA PAGINA SUELTA
------------------------------------
Hace falta leer los parquet de la bodega y calcular al momento. Una pagina
estatica solo puede llevar numeros ya calculados para UN rut. Aca sirve para
cualquiera de los ~30.000 proveedores que aparecen en la bodega.

Y no gasta ni una consulta del ticket de Mercado Publico: la bodega ya esta en
disco, la bajo el bodeguero de madrugada. Por eso un cliente puede consultar su
rut las veces que quiera sin costo.

LOS RUBROS SALEN DEL PROPIO RUT
-------------------------------
No hay lista escrita a mano de «sus rubros»: se miran los convenios marco por
los que ese rut ya vendio y se compara contra ese mismo mercado. Con Emergenza
aparecieron siete convenios, dos de los cuales no estaban en la especificacion.
Si el rut no registra ventas, se dejan elegir los convenios a mano.
"""
from pathlib import Path

import pandas as pd
import streamlit as st

import alertador
import modulo_mercado

CARPETA = Path(__file__).parent
RUTA_BODEGA = CARPETA / "bodega"

# Debajo de esto una unidad no vale la pena mirarla: son compras sueltas.
PISO_GASTO = 10_000_000
# Sobre este porcentaje ya se considera cliente firme, no oportunidad.
TECHO_CLIENTE = 15.0


# --------------------------------------------------------------------------
#  RUT
# --------------------------------------------------------------------------
def normalizar(rut: str) -> str:
    """«77.082.051-0» y «770820510» y «77082051» -> «77082051»/«770820510»."""
    return (str(rut).replace(".", "").replace("-", "").replace(" ", "").upper())


def cuerpo_y_dv(rut: str) -> tuple[str, str]:
    """Separa el numero del digito verificador. Sin dv, devuelve dv vacio."""
    limpio = normalizar(rut)
    if len(limpio) < 2:
        return limpio, ""
    return limpio[:-1], limpio[-1]


def dv_correcto(cuerpo: str) -> str:
    """El digito verificador que le corresponde a ese numero (modulo 11)."""
    suma, factor = 0, 2
    for digito in reversed(cuerpo):
        suma += int(digito) * factor
        factor = 2 if factor == 7 else factor + 1
    resto = 11 - (suma % 11)
    return {11: "0", 10: "K"}.get(resto, str(resto))


# --------------------------------------------------------------------------
#  Bodega
# --------------------------------------------------------------------------
def _sello() -> str:
    """Cambia cuando el bodeguero deja datos nuevos, para soltar la cache."""
    archivo = RUTA_BODEGA / "estado.json"
    if not archivo.exists():
        return "vacia"
    try:
        import json
        return str(json.loads(archivo.read_text(encoding="utf-8")).get("actualizado") or "vacia")
    except Exception:
        return "vacia"


@st.cache_data(show_spinner="Abriendo la bodega…")
def cargar_compras(sello: str) -> pd.DataFrame:
    """LA UNICA CACHE DE LA BODEGA EN TODO EL PANEL. No hacer otra.

    Habia dos —esta y la de `modulo_alertas`— cargando las mismas filas por
    separado, y como `st.tabs` dibuja TODAS las pestañas en cada corrida, las
    dos se llenaban aunque nadie abriera esa pestaña. Con la bodega de las seis
    vias eso se paso del techo de memoria de Streamlit y la app publicada quedo
    en «Oh no. Error running app» sin un solo traceback en el registro.

    El trabajo de verdad —leer mes a mes y resumir— vive en
    `alertador.resumen_de_ordenes`, que es la misma que usa el correo diario.
    Una sola manera de leer la bodega, un solo lugar donde arreglarla.
    """
    return alertador.resumen_de_ordenes()


@st.cache_data(show_spinner=False)
def cargar_unidades(sello: str) -> pd.DataFrame:
    """Nombre, organismo, region y comuna de cada unidad compradora."""
    archivo = RUTA_BODEGA / "unidades.parquet"
    if not archivo.exists():
        return pd.DataFrame()
    unidades = pd.read_parquet(archivo).fillna("")
    unidades["codigo_unidad"] = unidades["codigo_unidad"].astype(str).str.strip()
    return unidades


# --------------------------------------------------------------------------
#  Calculo
# --------------------------------------------------------------------------
# El «NA» de los convenios se filtra en un solo lugar, `alertador.convenios_de`:
# es la misma pregunta que se hace el correo diario y no puede contestarse
# distinto en cada pantalla.
convenios_de = alertador.convenios_de


def mapa_del_rut(compras: pd.DataFrame, unidades: pd.DataFrame,
                 cuerpo: str, convenios: list[str] | None) -> tuple[pd.DataFrame, dict]:
    """La tabla de unidades y el resumen, para un rut dado."""
    mias = compras["rut"].str.startswith(cuerpo, na=False)

    # Sus rubros son los convenios por los que ya vendio, salvo que se elijan
    # a mano (rut sin ventas, o alguien que quiere mirar otro mercado).
    if not convenios:
        convenios = convenios_de(compras.loc[mias, "convenio_marco"])
    if not convenios:
        return pd.DataFrame(), {"sin_ventas": True, "convenios": []}

    mercado = compras[compras["convenio_marco"].isin(convenios)].copy()
    mercado["mio"] = mercado["rut"].str.startswith(cuerpo, na=False)

    tabla = mercado.groupby("unidad", observed=True).agg(
        gasto=("total", "sum"),
        proveedores=("rut", "nunique"),
    ).reset_index()
    vendido = (mercado[mercado["mio"]].groupby("unidad", observed=True)["total"].sum()
               .rename("vendido"))
    tabla = tabla.join(vendido, on="unidad").fillna({"vendido": 0})
    tabla["parte"] = (tabla["vendido"] / tabla["gasto"] * 100).round(1)
    tabla = tabla[tabla["gasto"] >= PISO_GASTO]

    if not unidades.empty:
        tabla = tabla.merge(unidades, left_on="unidad", right_on="codigo_unidad", how="left")
    for columna, defecto in (("nombre_unidad", "(sin catalogar)"),
                             ("nombre_organismo", ""), ("region", "Sin región"),
                             ("comuna", "")):
        if columna not in tabla:
            tabla[columna] = defecto
        tabla[columna] = tabla[columna].replace("", defecto).fillna(defecto)

    # Se clasifica por lo VENDIDO, no por el porcentaje. Con el porcentaje,
    # una venta chica contra una compra enorme redondea a 0,0% y la unidad
    # salia como «nunca le has vendido» siendo que si le vendio. Mandar a
    # alguien a llamar en frio a un cliente suyo es peor que no decirle nada.
    def clasificar(fila):
        if fila["vendido"] <= 0:
            return "Nunca le has vendido"
        return "Estás adentro con poco" if fila["parte"] < TECHO_CLIENTE else "Cliente firme"

    tabla["situacion"] = tabla.apply(clasificar, axis=1)
    tabla["por_ganar"] = tabla["gasto"] - tabla["vendido"]

    resumen = {
        "sin_ventas": False,
        "convenios": convenios,
        "mercado": float(mercado["total"].sum()),
        "vendido": float(mercado.loc[mercado["mio"], "total"].sum()),
        "unidades": int(mercado["unidad"].nunique()),
        "nombre": _nombre_del_rut(compras, cuerpo),
    }
    resumen["parte"] = (resumen["vendido"] / resumen["mercado"] * 100
                        if resumen["mercado"] else 0)
    return tabla.sort_values("gasto", ascending=False), resumen


def _nombre_del_rut(compras: pd.DataFrame, cuerpo: str) -> str:
    """Con que nombre figura ese rut.

    Va la columna `proveedor`, no `rut_proveedor`: la segunda trae el numero.
    Y se toma el que mas se repite porque un mismo rut aparece escrito de
    varias formas («SOLUCIONES INTEGRALES EMERGENZA SPA» en ordenes de compra,
    «Emergenza SpA» en licitaciones).

    Se cuenta por `lineas`, no por filas: la tabla viene resumida y cada fila
    puede ser una orden o quinientas. Contando filas ganaria el nombre que
    aparece en mas convenios, no el que aparece en mas ordenes.
    """
    filas = compras.loc[compras["rut"].str.startswith(cuerpo, na=False),
                        ["proveedor", "lineas"]].dropna(subset=["proveedor"])
    filas = filas[filas["proveedor"].astype(str).str.strip() != ""]
    if filas.empty:
        return ""
    veces = filas.groupby("proveedor", observed=True)["lineas"].sum()
    return str(veces.sort_values(ascending=False).index[0])


# --------------------------------------------------------------------------
#  Pantalla
# --------------------------------------------------------------------------
def plata(monto: float) -> str:
    """$1.234 millones. En pesos exactos no se lee, y acá lo que importa es el orden."""
    if abs(monto) >= 1e9:
        return f"${monto/1e6:,.0f} M".replace(",", ".")
    return f"${monto:,.0f}".replace(",", ".")


def seccion_oportunidades() -> None:
    st.subheader("¿A quién le puedo vender y todavía no le vendo?")
    st.caption(
        "Escribe un RUT de proveedor. Sale lo que el Estado compró por Convenio "
        "Marco en sus rubros y qué parte se llevó él. Todo de datos públicos: "
        "no consume consultas del ticket.")

    columna_rut, columna_boton = st.columns([3, 1])
    with columna_rut:
        escrito = st.text_input(
            "RUT del proveedor", key="op_rut", placeholder="77.082.051-0",
            help="Con o sin puntos y guion. También sirve sin dígito verificador.")
    with columna_boton:
        st.write("")
        buscar = st.button("Ver oportunidades", key="op_buscar",
                           type="primary", width="stretch")

    if not escrito:
        st.info("Escribe un RUT para empezar.")
        return
    if not (buscar or st.session_state.get("op_visto") == escrito):
        return
    st.session_state["op_visto"] = escrito

    cuerpo, dv = cuerpo_y_dv(escrito)
    if not cuerpo.isdigit():
        st.error("Ese RUT no se entiende. Escríbelo como 77.082.051-0.")
        return
    if dv and dv != dv_correcto(cuerpo):
        # Se avisa pero no se detiene: puede estar bien escrito el número y mal
        # el dígito, y el cruce se hace igual por el número.
        st.warning(f"El dígito verificador no calza: para {cuerpo} debería ser "
                   f"{dv_correcto(cuerpo)}, no {dv}. Se busca igual.")

    sello = _sello()
    compras = cargar_compras(sello)
    if compras.empty:
        st.error("La bodega está vacía. Todavía no hay datos que consultar.")
        return
    unidades = cargar_unidades(sello)

    elegidos = st.session_state.get("op_convenios") or None
    tabla, resumen = mapa_del_rut(compras, unidades, cuerpo, elegidos)

    if resumen["sin_ventas"]:
        st.warning("Ese RUT no registra ventas por Convenio Marco. "
                   "Elige abajo los convenios de tu rubro para ver el mercado igual.")
        st.multiselect(
            "Convenios marco de tu rubro", key="op_convenios",
            options=convenios_de(compras["convenio_marco"]))
        return

    if resumen["nombre"]:
        st.success(f"**{resumen['nombre']}** · {len(resumen['convenios'])} convenios marco")

    a, b, c, d = st.columns(4)
    a.metric("Mercado de sus rubros", plata(resumen["mercado"]))
    b.metric("Lo que él vendió", plata(resumen["vendido"]))
    c.metric("Su parte", f"{resumen['parte']:.1f}%".replace(".", ","))
    d.metric("Unidades que compran", f"{resumen['unidades']:,}".replace(",", "."))

    nunca = tabla[tabla["situacion"] == "Nunca le has vendido"]
    poco = tabla[tabla["situacion"] == "Estás adentro con poco"]
    e, f, g = st.columns(3)
    e.metric("Nunca le has vendido", f"{len(nunca):,}".replace(",", "."),
             help=f"{plata(nunca['gasto'].sum())} que hoy se lleva otro")
    f.metric("Estás adentro con poco", f"{len(poco):,}".replace(",", "."),
            help=f"Compran {plata(poco['gasto'].sum())}, tiene {plata(poco['vendido'].sum())}")
    g.metric("Por ganar", plata(tabla["por_ganar"].sum()),
             help="Todo lo que compran estas unidades y no le compran a él")

    st.divider()
    filtro_situacion, filtro_region = st.columns([2, 2])
    with filtro_situacion:
        situaciones = st.multiselect(
            "Situación", key="op_situacion",
            options=["Nunca le has vendido", "Estás adentro con poco", "Cliente firme"],
            default=["Nunca le has vendido", "Estás adentro con poco"])
    with filtro_region:
        regiones = st.multiselect(
            "Región", key="op_region",
            options=sorted(tabla["region"].unique()))

    vista = tabla
    if situaciones:
        vista = vista[vista["situacion"].isin(situaciones)]
    if regiones:
        vista = vista[vista["region"].isin(regiones)]

    st.caption(f"{len(vista):,}".replace(",", ".") + " unidades · ordenadas por lo que gastan")
    st.dataframe(
        vista[["nombre_unidad", "nombre_organismo", "region", "comuna",
               "gasto", "vendido", "parte", "proveedores", "situacion"]],
        width="stretch", hide_index=True, height=520,
        column_config={
            "nombre_unidad": st.column_config.TextColumn("Unidad compradora", width="medium"),
            "nombre_organismo": st.column_config.TextColumn("Organismo", width="medium"),
            "region": st.column_config.TextColumn("Región"),
            "comuna": st.column_config.TextColumn("Comuna"),
            # Numeros como numeros, no como texto con $: si van como texto la
            # tabla ordena «11» entre «1» y «2».
            "gasto": st.column_config.NumberColumn("Compra", format="localized"),
            "vendido": st.column_config.NumberColumn("Le vendió", format="localized"),
            "parte": st.column_config.NumberColumn("Su parte", format="%.1f%%"),
            "proveedores": st.column_config.NumberColumn("Prov."),
            "situacion": st.column_config.TextColumn("Situación", width="small"),
        })

    # ----------------------------------------------------------------------
    #  El mercado en gráficos
    # ----------------------------------------------------------------------
    # La tabla de arriba se calcula sobre convenios marco. Estos gráficos miran
    # las seis vías, que es donde está el 95,8% del dinero, y por eso van en un
    # bloque aparte y no como otra columna de la misma tabla: son otra cuenta.
    #
    # El RUT va COMPLETO, con dígito verificador: en la bodega está escrito
    # «77.082.051-0» y con el cuerpo solo no encuentra ninguna venta.
    modulo_mercado.seccion_mercado(f"{cuerpo}-{dv or dv_correcto(cuerpo)}",
                                   unidades, sello)

    # ----------------------------------------------------------------------
    #  El puente a las alertas
    # ----------------------------------------------------------------------
    # Quien llego hasta aca ya vio su propio mapa: sabe cuanto se mueve en sus
    # rubros y a quien no le ha vendido nunca. Es el momento en que la alerta
    # diaria tiene sentido, no antes. Si hay que salir a buscar la pestana de
    # Alertas y volver a escribir el RUT, se pierde a la mitad por el camino.
    st.divider()
    izq, der = st.columns([3, 2])
    with izq:
        st.markdown("#### Que esto te llegue solo, cada mañana")
        st.caption(
            "Lo de arriba es el histórico: quién compra lo que vendes. La alerta "
            "diaria es lo otro: lo que se **publicó hoy** en esos mismos rubros, "
            "con el gasto de cada comprador al lado."
        )
    with der:
        st.write("")
        if st.button("Recibir estas oportunidades por correo",
                     type="primary", width="stretch", key="op_a_alertas"):
            # El RUT ya escrito se deja listo para la pestana de Alertas, para
            # que no haya que volver a escribirlo.
            st.session_state["al_rut"] = st.session_state.get("op_rut", "")
            st.info("Anda a la pestaña **🔔 Alertas** — tu RUT ya quedó puesto ahí.")
