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
import cartera
import exportar
import mis_productos
import modulo_mercado
import vistas

CARPETA = Path(__file__).parent
RUTA_BODEGA = CARPETA / "bodega"

# Las columnas que se muestran, en orden, y como se llaman en el Excel. Van
# juntas y en un solo lugar para que la tabla de pantalla y el archivo que se
# baja nunca se separen: si se agrega una columna, aparece en las dos.
COLUMNAS_VISIBLES = ["nombre_unidad", "nombre_organismo", "region", "comuna",
                     "gasto", "vendido", "parte", "proveedores", "situacion"]
TITULOS_COLUMNAS = {
    "nombre_unidad": "UNIDAD COMPRADORA", "nombre_organismo": "ORGANISMO",
    "region": "REGIÓN", "comuna": "COMUNA", "gasto": "COMPRA",
    "vendido": "LE VENDIÓ", "parte": "SU PARTE %", "proveedores": "PROVEEDORES",
    "situacion": "SITUACIÓN",
}

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

    # Ponerle nombre y clasificar es lo mismo para las dos formas de comparar
    # —por convenio y por ID—, asi que vive en un solo lugar. Ver `mapa_por_ids`.
    tabla = _ponerle_nombre(tabla, unidades)
    tabla = _clasificar(tabla)

    resumen = {
        "sin_ventas": False,
        "por_ids": False,
        "convenios": convenios,
        "mercado": float(mercado["total"].sum()),
        "vendido": float(mercado.loc[mercado["mio"], "total"].sum()),
        "unidades": int(mercado["unidad"].nunique()),
        "nombre": _nombre_del_rut(compras, cuerpo),
    }
    resumen["parte"] = (resumen["vendido"] / resumen["mercado"] * 100
                        if resumen["mercado"] else 0)
    return tabla.sort_values("gasto", ascending=False), resumen


@st.cache_data(show_spinner="Cruzando tus productos con lo que compró el Estado…")
def compras_de_mis_ids(sello: str, ids: tuple[str, ...], cuerpo: str,
                       meses: int = 24) -> pd.DataFrame:
    """Por unidad compradora: cuánto compró de MIS productos, y cuánto fue mío.

    LA SEGUNDA FORMA DE COMPARAR, la que pidió Serling el 01-09-2026. La otra
    —`mapa_del_rut`— mira convenios marco completos; esta mira el ID exacto del
    producto, que es lo que de verdad se compra.

    SE LEE MES A MES Y SOLO CUATRO COLUMNAS. La bodega tiene 1,2 millones de
    líneas y la columna `producto` pesa 570 MB ella sola: pedirla acá dejaría
    la app al borde del techo de Streamlit, que es el error que la tumbó el
    27-08-2026. Con estas cuatro columnas, los 25 meses se leen en medio
    segundo y ocupan 2 MB por mes. Medido.

    `ids` va como tupla y no como set porque `st.cache_data` necesita poder
    calcular una llave, y un set no le sirve.
    """
    import alertador as _al

    if not ids:
        return pd.DataFrame()

    carpeta = _al.BODEGA_OC
    if not carpeta.exists():
        return pd.DataFrame()

    from datetime import date, timedelta
    corte = (date.today() - timedelta(days=meses * 31)).strftime("%Y-%m")
    mios = set(ids)
    trozos = []
    for archivo in sorted(carpeta.glob("*.parquet")):
        if archivo.stem < corte:
            continue
        try:
            mes = pd.read_parquet(archivo, columns=["unidad", "id_producto",
                                                    "total", "rut_proveedor"])
        except Exception:
            # Un mes con una columna de menos no puede dejar sin datos al resto.
            continue
        mes["id_producto"] = mes["id_producto"].astype(str).str.strip()
        mes = mes[mes["id_producto"].isin(mios)]
        if mes.empty:
            continue
        mes["mio"] = (mes["rut_proveedor"].astype(str)
                      .str.replace(".", "", regex=False)
                      .str.replace("-", "", regex=False)
                      .str.startswith(cuerpo, na=False))
        trozos.append(mes.groupby(["unidad", "rut_proveedor", "mio"],
                                  observed=True)["total"].sum().reset_index())
        del mes

    if not trozos:
        return pd.DataFrame()
    return pd.concat(trozos, ignore_index=True)


def mapa_por_ids(lineas: pd.DataFrame, unidades: pd.DataFrame,
                 total_ids: int) -> tuple[pd.DataFrame, dict]:
    """La misma tabla de `mapa_del_rut`, pero contada por ID de producto.

    Devuelve exactamente las mismas columnas para que la pantalla de abajo
    —filtros, tabla, Excel— no tenga que saber de dónde vino el número.
    """
    if lineas.empty:
        return pd.DataFrame(), {"sin_ventas": True, "convenios": [], "por_ids": True}

    tabla = lineas.groupby("unidad", observed=True).agg(
        gasto=("total", "sum"),
        proveedores=("rut_proveedor", "nunique"),
    ).reset_index()
    vendido = (lineas[lineas["mio"]].groupby("unidad", observed=True)["total"]
               .sum().rename("vendido"))
    tabla = tabla.join(vendido, on="unidad").fillna({"vendido": 0})
    tabla["parte"] = (tabla["vendido"] / tabla["gasto"] * 100).round(1)
    tabla = tabla[tabla["gasto"] >= PISO_GASTO]

    tabla = _ponerle_nombre(tabla, unidades)
    tabla = _clasificar(tabla)

    resumen = {
        "sin_ventas": False,
        "por_ids": True,
        "convenios": [],
        "mercado": float(lineas["total"].sum()),
        "vendido": float(lineas.loc[lineas["mio"], "total"].sum()),
        "unidades": int(lineas["unidad"].nunique()),
        "nombre": "",
        "total_ids": total_ids,
    }
    resumen["parte"] = (resumen["vendido"] / resumen["mercado"] * 100
                        if resumen["mercado"] else 0)
    return tabla.sort_values("gasto", ascending=False), resumen


@st.cache_data(show_spinner="Leyendo qué compran esas instituciones…")
def productos_de_las_unidades(sello: str, codigos: tuple[str, ...], cuerpo: str,
                              meses: int = 24) -> pd.DataFrame:
    """Qué productos compran esas unidades, y cuánto de eso se lo llevó él.

    ES EL PASO SIGUIENTE DE OPORTUNIDADES, pedido por Serling el 01-09-2026:
    «luego de este paso, deben mostrar los ID que compran esas instituciones
    según el filtro seleccionado: ID que no tengo / ID que sí tengo».

    La tabla de arriba contesta A QUIEN venderle. Esta contesta QUE venderle,
    que es la pregunta con la que uno llega a la reunión.

    SE LEE MES A MES Y SE FILTRA AL LEER. Aquí sí hace falta la columna
    `producto`, que es la cara: 570 MB sobre la bodega entera. Pero se filtra
    por unidad apenas se lee cada mes y se suelta, así que el peor momento son
    los ~9,5 MB de un mes. Medido con las 12 unidades de Gendarmería de
    Valparaíso: 0,4 segundos y 23.536 líneas.
    """
    import alertador as _al

    if not codigos or not _al.BODEGA_OC.exists():
        return pd.DataFrame()

    from datetime import date, timedelta
    corte = (date.today() - timedelta(days=meses * 31)).strftime("%Y-%m")
    buscadas = set(codigos)
    trozos = []
    for archivo in sorted(_al.BODEGA_OC.glob("*.parquet")):
        if archivo.stem < corte:
            continue
        try:
            mes = pd.read_parquet(archivo, columns=["unidad", "id_producto",
                                                    "producto", "total",
                                                    "rut_proveedor"])
        except Exception:
            continue
        mes = mes[mes["unidad"].astype(str).str.strip().isin(buscadas)]
        if mes.empty:
            del mes
            continue
        mes["id_producto"] = mes["id_producto"].astype(str).str.strip()
        mes["mio"] = (mes["rut_proveedor"].astype(str)
                      .str.replace(".", "", regex=False)
                      .str.replace("-", "", regex=False)
                      .str.startswith(cuerpo, na=False))
        mes["tuyo"] = mes["total"].where(mes["mio"], 0.0)
        trozos.append(mes.groupby(["id_producto", "producto"], observed=True)
                      .agg(compran=("total", "sum"),
                           te_compraron=("tuyo", "sum"),
                           unidades=("unidad", "nunique"),
                           proveedores=("rut_proveedor", "nunique"))
                      .reset_index())
        del mes

    if not trozos:
        return pd.DataFrame()

    # Un mismo producto aparece en varios meses: se vuelve a juntar. `unidades`
    # y `proveedores` se suman por mes y por eso quedan altos; se usa el maximo,
    # que es el numero honesto («hasta N unidades lo compraron»).
    junto = pd.concat(trozos, ignore_index=True)
    return (junto.groupby(["id_producto", "producto"], observed=True)
            .agg(compran=("compran", "sum"),
                 te_compraron=("te_compraron", "sum"),
                 unidades=("unidades", "max"),
                 proveedores=("proveedores", "max"))
            .reset_index()
            .sort_values("compran", ascending=False))


def _ponerle_nombre(tabla: pd.DataFrame, unidades: pd.DataFrame) -> pd.DataFrame:
    """Le pega nombre, organismo, región y comuna a cada código de unidad."""
    if not unidades.empty:
        tabla = tabla.merge(unidades, left_on="unidad",
                            right_on="codigo_unidad", how="left")
    for columna, defecto in (("nombre_unidad", "(sin catalogar)"),
                             ("nombre_organismo", ""), ("region", "Sin región"),
                             ("comuna", "")):
        if columna not in tabla:
            tabla[columna] = defecto
        tabla[columna] = tabla[columna].replace("", defecto).fillna(defecto)
    return tabla


def _clasificar(tabla: pd.DataFrame) -> pd.DataFrame:
    """Nunca / adentro con poco / cliente firme, y lo que queda por ganar.

    Se clasifica por lo VENDIDO, no por el porcentaje. Con el porcentaje, una
    venta chica contra una compra enorme redondea a 0,0% y la unidad salía como
    «nunca le has vendido» siendo que sí le vendió. Mandar a alguien a llamar
    en frío a un cliente suyo es peor que no decirle nada.
    """
    def clasificar(fila):
        if fila["vendido"] <= 0:
            return "Nunca le has vendido"
        return "Estás adentro con poco" if fila["parte"] < TECHO_CLIENTE else "Cliente firme"

    tabla = tabla.copy()
    tabla["situacion"] = tabla.apply(clasificar, axis=1)
    tabla["por_ganar"] = tabla["gasto"] - tabla["vendido"]
    return tabla


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

    # LA VISTA DE ENTRADA SE APLICA ANTES QUE NADA, y tiene que ser aquí: para
    # que Streamlit dibuje un widget ya puesto, su valor tiene que estar en
    # `session_state` ANTES de crearlo. Un botón «aplicar» que corriera después
    # no alcanzaría a mover los filtros de esta misma corrida.
    usuario_actual = st.session_state.get("yo", {})
    de_entrada = vistas.aplicar_la_de_entrada(usuario_actual)
    if de_entrada:
        st.caption(f"Abriste con tu vista **«{de_entrada}»**.")

    columna_rut, columna_boton = st.columns([3, 1])
    with columna_rut:
        escrito = st.text_input(
            "RUT del proveedor", key="op_rut", placeholder="77.082.051-0",
            help="Con o sin puntos y guion. También sirve sin dígito verificador.")
    with columna_boton:
        st.write("")
        buscar = st.button("Ver oportunidades", key="op_buscar",
                           type="primary", width="stretch")

    # EL CATALOGO PROPIO VA ARRIBA, ANTES DE CONSULTAR, y por dos razones.
    #
    # Es configuracion de la empresa, no resultado de una busqueda: se carga una
    # vez y sirve para todas las consultas. Si estuviera despues de la tabla,
    # habria que consultar algo primero para poder cargarlo, que es al reves.
    #
    # Y ademas la primera pantalla dejaba de estar vacia. Antes decia solo
    # «Escribe un RUT para empezar» y nada mas: en una demo hay que escribir
    # para que aparezca algo. Serling lo reporto el 01-09-2026.
    mis_ids = mis_productos.seccion_mis_productos(usuario_actual)

    # El tercer filtro: la vista guardada. Va junto al catálogo porque los dos
    # son configuración del vendedor, no resultado de una consulta.
    vistas.barra_de_vistas(usuario_actual)

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

    # ----------------------------------------------------------------------
    #  Las dos formas de comparar
    # ----------------------------------------------------------------------
    # Serling lo pidio el 01-09-2026. No compiten: contestan preguntas
    # distintas y un vendedor necesita las dos. Ver `mis_productos.py`.
    # EL SELECTOR SE DIBUJA SIEMPRE, haya catalogo o no.
    #
    # Antes solo aparecia si ya habia ID cargados, y eso lo dejaba escondido
    # justo para quien todavia no sabe que existe: para llegar a el habia que
    # adivinar que primero hay que subir un archivo. Serling pidio que la
    # eleccion fuera «con un click», y un selector que aparece a veces no lo es.
    #
    # Sin catalogo la segunda opcion se puede elegir igual, y lo que sale es la
    # explicacion de que le falta, no un error ni una pantalla vacia.
    forma = st.radio(
        "Con qué comparar", horizontal=True, key="op_forma",
        options=["Según lo que ya has vendido", "Contra mis ID publicados"],
        captions=["Los rubros salen solos del RUT. No hay que cargar nada.",
                  (f"Producto por producto, contra los {len(mis_ids):,}".replace(",", ".") +
                   " que subiste.") if mis_ids
                  else "Producto por producto. Necesita tu catálogo, arriba."])

    if forma == "Contra mis ID publicados" and not mis_ids:
        st.info(
            "Para comparar contra tus ID falta cargar el catálogo: ábrelo arriba "
            "en **«Mis productos publicados»** y sube el mismo `.xlsx` que usas "
            "para cotizar. Mientras tanto se muestra lo de siempre.")
        forma = "Según lo que ya has vendido"

    if forma == "Contra mis ID publicados":
        lineas = compras_de_mis_ids(sello, tuple(sorted(mis_ids)), cuerpo)
        tabla, resumen = mapa_por_ids(lineas, unidades, len(mis_ids))
        if resumen["sin_ventas"]:
            st.warning(
                "Ninguno de tus ID aparece comprado en los últimos 24 meses. "
                "Puede ser que el archivo traiga los ID de otro convenio, o que "
                "de verdad no se hayan comprado. Cambia arriba a «Según lo que "
                "ya has vendido» para ver el mercado igual.")
            return
        st.success(
            f"Cruzando **{resumen['total_ids']:,}".replace(",", ".") +
            "** productos tuyos contra lo que el Estado compró de ellos.")
    else:
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

    # ----------------------------------------------------------------------
    #  La navegación
    # ----------------------------------------------------------------------
    # ESTA PANTALLA ERA UN SOLO ROLLO DE SEIS MIL PIXELES: métricas, filtros,
    # tabla, cuatro gráficos, itinerario y el puente a las alertas, todo uno
    # debajo del otro. Para ver a quién visitar había que pasar por los cuatro
    # gráficos sí o sí. Son cuatro trabajos distintos y ahora se eligen.
    #
    # SE USA `segmented_control` Y NO `st.tabs`, y esto no es estético.
    # `st.tabs` DIBUJA TODAS LAS PESTAÑAS EN CADA CORRIDA aunque nadie las
    # abra: es exactamente lo que reventó la memoria del panel el 27-08-2026
    # —dos módulos cargando la bodega a la vez— y dejó la app publicada en «Oh
    # no. Error running app» sin traceback. Con el selector se dibuja UNA sola.
    #
    # Y la cápsula es la forma correcta según la regla de Uplevel: lo que se
    # elige va en cápsula, lo que contiene va en rectángulo suave.
    SECCIONES = {
        "A quién venderle": "Las unidades que compran lo tuyo, para filtrar y elegir",
        "Qué venderles": "Los ID que compran esas instituciones: los que tienes y los que no",
        "Mi cartera": "Las que ya elegiste trabajar — de acá sale el envío del catálogo",
        "Su mercado": "Quién compra, por qué vía y contra quién se compite",
        "A quién visitar": "El itinerario, ordenado por lo que hay para ganar",
        "Que llegue solo": "Que esto te llegue por correo cada mañana",
    }
    seccion = st.segmented_control(
        "Qué quieres ver", options=list(SECCIONES), key="op_seccion",
        default="A quién venderle", label_visibility="collapsed")
    # `segmented_control` devuelve None si se vuelve a apretar lo ya elegido.
    # Sin esto la pantalla queda en blanco y parece que se rompió.
    seccion = seccion or "A quién venderle"
    st.caption(SECCIONES[seccion])

    if seccion == "Qué venderles":
        _pantalla_que_venderles(_vista_filtrada(tabla), mis_ids, cuerpo, sello)
        return

    if seccion == "Mi cartera":
        cartera.seccion_cartera(usuario_actual)
        return

    if seccion == "Su mercado":
        modulo_mercado.seccion_mercado(f"{cuerpo}-{dv or dv_correcto(cuerpo)}",
                                       unidades, sello, con_visitas=False)
        return

    if seccion == "A quién visitar":
        modulo_mercado.seccion_visitas_sola(
            f"{cuerpo}-{dv or dv_correcto(cuerpo)}", unidades, sello)
        return

    if seccion == "Que llegue solo":
        _pantalla_alertas()
        return

    a, b, c, d = st.columns(4)
    a.metric("Mercado de tus productos" if resumen["por_ids"]
             else "Mercado de sus rubros", plata(resumen["mercado"]))
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

    # ----------------------------------------------------------------------
    #  Filtros
    # ----------------------------------------------------------------------
    # Los filtros se aplican EN CASCADA: las opciones de organismo salen de lo
    # que quedó después de situación y región, y las de unidad de lo que quedó
    # después de organismo. Sin eso, el selector de unidades ofrece las 2.700
    # del país aunque se haya filtrado una sola región, y no se puede usar.
    #
    # Serling lo pidió el 01-09-2026: hasta esa fecha solo se podía filtrar por
    # situación y región, y no se podía SACAR nada de la lista.
    filtro_situacion, filtro_region = st.columns([2, 2])
    with filtro_situacion:
        # El `default` se pasa SOLO si la vista guardada no puso ya un valor.
        # Streamlit avisa —«se creó con default y además se fijó por Session
        # State»— y descarta el default; funciona igual, pero deja un warning en
        # el registro en cada carga y es la clase de ruido que después tapa un
        # aviso de verdad.
        por_defecto = ({} if "op_situacion" in st.session_state
                       else {"default": ["Nunca le has vendido", "Estás adentro con poco"]})
        situaciones = st.multiselect(
            "Situación", key="op_situacion",
            options=["Nunca le has vendido", "Estás adentro con poco", "Cliente firme"],
            placeholder="Todas", **por_defecto)
    with filtro_region:
        # El `placeholder` va escrito aunque parezca de mas: sin el, Streamlit
        # pone «Choose options» en ingles y queda un cartel en otro idioma en
        # medio de una pantalla en castellano.
        regiones = st.multiselect(
            "Región", key="op_region",
            options=sorted(tabla["region"].unique()),
            placeholder="Todo Chile")

    vista = tabla
    if situaciones:
        vista = vista[vista["situacion"].isin(situaciones)]
    if regiones:
        vista = vista[vista["region"].isin(regiones)]

    filtro_organismo, filtro_unidad = st.columns([2, 2])
    with filtro_organismo:
        organismos = st.multiselect(
            "Institución", key="op_organismo",
            options=sorted(x for x in vista["nombre_organismo"].unique() if x),
            placeholder="Todas las de la región",
            help="Deja vacío para verlas todas.")
    if organismos:
        vista = vista[vista["nombre_organismo"].isin(organismos)]
    with filtro_unidad:
        unidades_elegidas = st.multiselect(
            "Unidad compradora", key="op_unidad",
            options=sorted(x for x in vista["nombre_unidad"].unique() if x),
            placeholder="Todas las de arriba")
    if unidades_elegidas:
        vista = vista[vista["nombre_unidad"].isin(unidades_elegidas)]

    # Sacar de la lista va en un desplegable, no a la vista: se usa mucho menos
    # que incluir, y cuatro selectores abiertos a la vez tapan la tabla.
    with st.expander("Sacar de la lista"):
        st.caption(
            "Para las que no interesan: la competencia, las que ya se atienden "
            "por otro canal, las que quedan fuera de ruta. Se descuentan de la "
            "tabla y del Excel.")
        sin_organismo, sin_unidad = st.columns([2, 2])
        with sin_organismo:
            fuera_organismos = st.multiselect(
                "Instituciones fuera", key="op_sin_organismo",
                options=sorted(x for x in vista["nombre_organismo"].unique() if x),
                placeholder="Ninguna")
        with sin_unidad:
            fuera_unidades = st.multiselect(
                "Unidades fuera", key="op_sin_unidad",
                options=sorted(x for x in vista["nombre_unidad"].unique() if x),
                placeholder="Ninguna")
    if fuera_organismos:
        vista = vista[~vista["nombre_organismo"].isin(fuera_organismos)]
    if fuera_unidades:
        vista = vista[~vista["nombre_unidad"].isin(fuera_unidades)]

    # ----------------------------------------------------------------------
    #  La tabla
    # ----------------------------------------------------------------------
    cuenta, bajar = st.columns([3, 1])
    with cuenta:
        st.caption(f"{len(vista):,}".replace(",", ".") +
                   " unidades · ordenadas por lo que gastan")
    with bajar:
        exportar.boton_excel(
            vista[COLUMNAS_VISIBLES].rename(columns=TITULOS_COLUMNAS),
            nombre=f"Oportunidades-{cuerpo}", clave="oportunidades",
            hoja="Oportunidades", ancho="stretch")

    if vista.empty:
        st.info("Con estos filtros no queda ninguna unidad. Saca alguno.")
        return

    # Anchos: el nombre de la unidad y el del organismo son los dos textos
    # largos («DIRECCION GENERAL DE GENDARMERIA DE CHILE») y son los que hay que
    # poder leer enteros; los números ocupan lo que ocupan. Serling reportó el
    # 01-09-2026 que salían cortados. Streamlit no mide el texto para ajustar
    # solo: lo más que se puede es repartir bien y dejar que la tabla ocupe todo
    # el ancho de la pantalla, que es lo que hace `width="stretch"`.
    seleccion = st.dataframe(
        vista[COLUMNAS_VISIBLES],
        width="stretch", hide_index=True, height=520,
        on_select="rerun", selection_mode="multi-row", key="op_tabla",
        column_config={
            "nombre_unidad": st.column_config.TextColumn("Unidad compradora", width="large"),
            "nombre_organismo": st.column_config.TextColumn("Organismo", width="large"),
            "region": st.column_config.TextColumn("Región", width="small"),
            "comuna": st.column_config.TextColumn("Comuna", width="small"),
            # Numeros como numeros, no como texto con $: si van como texto la
            # tabla ordena «11» entre «1» y «2».
            "gasto": st.column_config.NumberColumn("Compra", format="localized", width="small"),
            "vendido": st.column_config.NumberColumn("Le vendió", format="localized", width="small"),
            "parte": st.column_config.NumberColumn("Su parte", format="%.1f%%", width="small"),
            "proveedores": st.column_config.NumberColumn("Prov.", width="small"),
            "situacion": st.column_config.TextColumn("Situación", width="medium"),
        })

    # ----------------------------------------------------------------------
    #  De la tabla a la cartera
    # ----------------------------------------------------------------------
    # ESTE ES EL PUENTE QUE FALTABA. Hasta el 01-09-2026 la pantalla terminaba
    # en la tabla: decia a quien venderle y ahi moria. Quien queria hacer algo
    # con esas unidades las copiaba a mano a una planilla.
    #
    # Ahora se marcan y quedan en la cartera, que es lo unico que los dos lados
    # del sistema pueden leer: el panel de envio del catalogo saca de ahi a
    # quien le escribe. Ver `cartera.py`.
    from app import filas_seleccionadas
    marcadas = vista.iloc[filas_seleccionadas(seleccion, len(vista))]

    izq, der = st.columns([3, 2])
    with izq:
        if marcadas.empty:
            st.caption("Marca filas en la tabla para armar tu cartera.")
        else:
            st.caption(
                f"**{len(marcadas)}** marcadas · compran "
                f"{plata(marcadas['gasto'].sum())} · por ganar "
                f"{plata(marcadas['por_ganar'].sum())}")
    with der:
        if st.button(f"Agregar a mi cartera ({len(marcadas)})" if len(marcadas)
                     else "Agregar a mi cartera",
                     type="primary", width="stretch", key="op_a_cartera",
                     disabled=marcadas.empty):
            cuantas, aviso = cartera.agregar(st.session_state.get("yo", {}), marcadas)
            (st.success if cuantas else st.warning)(aviso)


COLUMNAS_PRODUCTOS = ["id_producto", "producto", "compran", "te_compraron",
                      "unidades", "proveedores"]
TITULOS_PRODUCTOS = {
    "id_producto": "ID CONVENIO MARCO", "producto": "PRODUCTO",
    "compran": "COMPRAN", "te_compraron": "TE COMPRARON",
    "unidades": "UNIDADES", "proveedores": "PROVEEDORES",
}

# Sobre esto la tabla de productos deja de ser util y solo pesa. Con el filtro
# puesto en una institucion nunca se llega; sin filtro, si.
TECHO_UNIDADES = 400


def _vista_filtrada(tabla: pd.DataFrame) -> pd.DataFrame:
    """La tabla con los filtros que están puestos, SIN volver a dibujarlos.

    Los selectores se dibujan una sola vez, en «A quién venderle». Esta sección
    usa lo mismo leyéndolo de `session_state`: si dibujara su propio juego de
    filtros habría dos sitios donde filtrar lo mismo, que es la forma más
    segura de que digan cosas distintas.
    """
    vista = tabla
    for clave, columna, fuera in (
            ("op_situacion", "situacion", False),
            ("op_region", "region", False),
            ("op_organismo", "nombre_organismo", False),
            ("op_unidad", "nombre_unidad", False),
            ("op_sin_organismo", "nombre_organismo", True),
            ("op_sin_unidad", "nombre_unidad", True)):
        elegidos = st.session_state.get(clave) or []
        if not elegidos or columna not in vista.columns:
            continue
        dentro = vista[columna].isin(elegidos)
        vista = vista[~dentro] if fuera else vista[dentro]
    return vista


def _pantalla_que_venderles(vista: pd.DataFrame, mis_ids: set, cuerpo: str,
                            sello: str) -> None:
    """Qué productos compran las unidades filtradas, partidos en tengo / no tengo.

    LA PREGUNTA CON LA QUE SE LLEGA A LA REUNION. «A quién venderle» da la
    lista de compradores; esto dice qué ponerle sobre la mesa a cada uno, y
    sobre todo qué de lo que compran **no** está publicado todavía.
    """
    st.caption(
        "Los productos que compran las unidades que tienes filtradas arriba, "
        "partidos en los que **sí** tienes publicados y los que **no**.")

    codigos = []
    for columna in ("codigo_unidad", "unidad"):
        if columna in vista.columns:
            codigos = [str(x).strip() for x in vista[columna].dropna().unique()]
            break
    codigos = [c for c in codigos if c]

    if not codigos:
        st.info("Primero filtra unidades en **A quién venderle**.")
        return
    if len(codigos) > TECHO_UNIDADES:
        st.warning(
            f"Tienes **{len(codigos):,}".replace(",", ".") + "** unidades "
            "filtradas: eso es casi el mercado entero y la lista de productos "
            "saldría inmanejable. Filtra por institución o por región arriba "
            f"—hasta {TECHO_UNIDADES}— y vuelve.")
        return

    st.caption(f"Sobre las **{len(codigos)}** unidades que tienes filtradas.")
    productos = productos_de_las_unidades(sello, tuple(sorted(codigos)), cuerpo)
    if productos.empty:
        st.info("Esas unidades no registran compras en los últimos 24 meses.")
        return

    productos["lo_tengo"] = productos["id_producto"].isin(mis_ids)
    tengo = productos[productos["lo_tengo"]]
    no_tengo = productos[~productos["lo_tengo"]]

    if not mis_ids:
        st.warning(
            "Todavía no cargaste tu catálogo, así que no se puede separar lo "
            "que tienes de lo que no: abajo va **todo lo que compran**. Sube "
            "tu catálogo en **«Mis productos publicados»**, arriba, y esta "
            "misma pantalla se parte en dos.")
    else:
        total = float(productos["compran"].sum()) or 1.0
        a, b, c = st.columns(3)
        a.metric("Compran en total", plata(total),
                 help="Todo lo que compraron esas unidades en 24 meses")
        b.metric("De eso, lo tienes publicado", plata(tengo["compran"].sum()),
                 delta=f"{tengo['compran'].sum() / total * 100:.0f}% del total"
                       .replace(".", ","), delta_color="off")
        c.metric("No lo tienes", plata(no_tengo["compran"].sum()),
                 help="Lo que compran y hoy no puedes ni cotizar")

    st.divider()

    def tabla_de(datos: pd.DataFrame, clave: str, nombre: str) -> None:
        if datos.empty:
            st.caption("No hay ninguno en este grupo.")
            return
        cuenta, bajar = st.columns([3, 1])
        with cuenta:
            st.caption(f"{len(datos):,}".replace(",", ".") +
                       " productos · " + plata(datos["compran"].sum()))
        with bajar:
            exportar.boton_excel(
                datos[COLUMNAS_PRODUCTOS].rename(columns=TITULOS_PRODUCTOS),
                nombre=nombre, clave=clave, hoja="Productos", ancho="stretch")
        st.dataframe(
            datos[COLUMNAS_PRODUCTOS], width="stretch", hide_index=True, height=420,
            column_config={
                "id_producto": st.column_config.TextColumn("ID", width="small"),
                "producto": st.column_config.TextColumn("Producto", width="large"),
                "compran": st.column_config.NumberColumn("Compran", format="localized",
                                                         width="small"),
                "te_compraron": st.column_config.NumberColumn(
                    "Te compraron", format="localized", width="small",
                    help="De eso, cuánto te lo llevaste tú"),
                "unidades": st.column_config.NumberColumn("Unidades", width="small",
                                                          help="Cuántas lo compran"),
                "proveedores": st.column_config.NumberColumn("Prov.", width="small",
                                                             help="Contra cuántos compites"),
            })

    if not mis_ids:
        tabla_de(productos, "prod_todo", f"Productos-{cuerpo}")
        return

    sin, con = st.tabs([f"ID que NO tengo ({len(no_tengo)})",
                        f"ID que SÍ tengo ({len(tengo)})"])
    # Los que NO tiene van PRIMERO y por defecto: son los que no puede cotizar
    # hoy, o sea la plata que se le está yendo sin que lo sepa. Lo que ya tiene
    # publicado se lo sabe; lo que le falta, no.
    with sin:
        st.caption("Lo que compran y **no tienes publicado**. Cada uno es una "
                   "venta que hoy no puedes ni cotizar.")
        tabla_de(no_tengo, "prod_sin", f"ID-que-no-tengo-{cuerpo}")
    with con:
        st.caption("Lo que compran y **sí tienes publicado**. Esto se cotiza "
                   "mañana; lleva estos ID a la reunión.")
        tabla_de(tengo, "prod_con", f"ID-que-si-tengo-{cuerpo}")


def _pantalla_alertas() -> None:
    """El puente a las alertas, ahora como su propia sección.

    Quien llego hasta aca ya vio su propio mapa: sabe cuanto se mueve en sus
    rubros y a quien no le ha vendido nunca. Es el momento en que la alerta
    diaria tiene sentido, no antes. Si hay que salir a buscar la pestaña de
    Alertas y volver a escribir el RUT, se pierde a la mitad por el camino.
    """
    st.markdown("#### Que esto te llegue solo, cada mañana")
    st.caption(
        "Lo que viste es el histórico: quién compra lo que vendes. La alerta "
        "diaria es lo otro: lo que se **publicó hoy** en esos mismos rubros, "
        "con el gasto de cada comprador al lado.")
    izq, der = st.columns([3, 2])
    with der:
        if st.button("Recibir estas oportunidades por correo",
                     type="primary", width="stretch", key="op_a_alertas"):
            # El RUT ya escrito se deja listo para la pestaña de Alertas, para
            # que no haya que volver a escribirlo.
            st.session_state["al_rut"] = st.session_state.get("op_rut", "")
            st.info("Anda a la pestaña **🔔 Alertas** — tu RUT ya quedó puesto ahí.")
