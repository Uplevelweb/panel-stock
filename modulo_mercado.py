"""
MÓDULO MERCADO — entender el mercado, no encontrar la licitación
=================================================================

Lo pidió Mikel, usuario de LicitaPyme: encontrar la licitación ya lo hace otra
herramienta. Lo que no tiene nadie es **entender el mercado**: cuánto se mueve,
quién compra, por qué vía, y contra quién se compite. Cuatro preguntas, cuatro
gráficos de barras.

POR QUE BARRAS Y NO UNA TABLA MAS
---------------------------------
«Clientes que capaz son personas adultas que no son muy duchos con la
computadora». Una tabla de veinte filas con montos hay que leerla; una barra
que mide el doble que la de abajo se entiende sin leer. Los números van igual
al lado, para quien sí quiera el dato exacto.

POR QUE HAY QUE APRETAR UN BOTON
--------------------------------
Esto cuesta ~5 segundos por mes de bodega, porque hay que mirar el texto de
cada producto —ocho millones de líneas— y ver si habla del rubro de este
proveedor. Doce meses son casi un minuto. Nadie deberia esperar ese minuto sin
haberlo pedido, asi que la pantalla no calcula nada hasta que se aprieta el
boton, y despues queda guardado: la segunda vez es instantaneo.

DE DONDE SALE «SU RUBRO»
------------------------
De `alertador.terminos_del_rut`: las palabras que se repiten en lo que ese RUT
ya vendio. Y se exige el mismo minimo de coincidencias que para avisar por
correo (`minimo_coincidencias`), no una palabra suelta. Con una sola, la bolsa
de Emergenza —que trae «agua», «blanca», «chile»— hacia entrar factor
antihemofilico y 90 camionetas: once veces mas plata de la que existe.

ESTO MIRA LAS SEIS VIAS DE COMPRA
---------------------------------
No solo Convenio Marco. La tabla de arriba en la pestaña Oportunidades todavia
se calcula sobre convenios marco, que son el 4,2% del dinero; estos graficos
miran todo lo que la bodega tiene: licitaciones, trato directo, compras agiles,
convenio marco, convenios y contratos.
"""
from pathlib import Path

import pandas as pd
import streamlit as st

import alertador
import modulo_visitas

CARPETA = Path(__file__).parent
RUTA_DETALLE = CARPETA / "bodega" / "detalle"

# Cuantas barras tiene cada grafico. Mas de doce y las de abajo son una linea
# que no se distingue de la siguiente.
BARRAS = 12


def _corte(meses: int) -> str:
    """El primer mes que entra, como «AAAA-MM»."""
    hoy = pd.Timestamp.today()
    return (hoy - pd.DateOffset(months=meses)).strftime("%Y-%m")


@st.cache_data(show_spinner=False)
def panorama_del_mercado(rut: str, meses: int, sello: str) -> dict:
    """Las cuatro cuentas del mercado de ese RUT, en una sola pasada.

    `sello` no se usa adentro: esta para que el cache se bote solo cuando la
    bodega cambia, igual que en el resto del panel.

    Se lee mes por mes y se suelta: el peor momento es un archivo, no los
    veinte. `producto` es la columna cara —casi ningun valor se repite, no se
    puede comprimir— y es justamente la que hay que mirar, asi que se lee aca
    y no se guarda nada de ella.
    """
    vacio = {"bolsa": 0, "minimo": 0, "meses": meses, "total": 0.0, "lineas": 0,
             "unidades": {}, "vias": {}, "proveedores": {}, "productos": {},
             "mio_por_unidad": {}}
    if not RUTA_DETALLE.exists():
        return vacio

    bolsa, _ = alertador.terminos_del_rut(rut, pd.DataFrame({"hay": [1]}))
    if not bolsa:
        return vacio
    minimo = alertador.minimo_coincidencias(bolsa)
    suyo = alertador.solo_digitos_rut(rut)

    desde = _corte(meses)
    unidades: dict[str, float] = {}
    vias: dict[str, float] = {}
    proveedores: dict[str, float] = {}
    productos: dict[str, float] = {}
    # Lo que ESTE proveedor ya le vendio a cada unidad. Sirve para la agenda de
    # visitas: donde ya vende no hay lo mismo que ganar que donde no vende.
    mio: dict[str, float] = {}
    lineas = 0

    for archivo in sorted(RUTA_DETALLE.glob("*.parquet")):
        if archivo.stem < desde:
            continue
        try:
            # Solo las columnas que ESE archivo tiene: pedir una que no esta
            # hace fallar la lectura entera, y los parquet viejos no traen
            # `mecanismo`. Ya paso dos veces.
            import pyarrow.parquet as pq
            hay = set(pq.read_schema(archivo).names)
            pedidas = [c for c in ("unidad", "mecanismo", "proveedor", "producto",
                                   "total", "rut_proveedor")
                       if c in hay]
            if "producto" not in pedidas or "total" not in pedidas:
                continue
            mes = pd.read_parquet(archivo, columns=pedidas)
            if "mecanismo" not in mes.columns:
                mes["mecanismo"] = "CM"      # los archivos viejos son solo Convenio Marco
        except Exception:
            continue

        cuantas = mes["producto"].astype(str).map(lambda x: len(alertador.palabras(x) & bolsa))
        mes = mes[cuantas >= minimo]
        if mes.empty:
            del mes, cuantas
            continue
        mes["total"] = pd.to_numeric(mes["total"], errors="coerce").fillna(0.0)
        lineas += len(mes)

        # `observed=True` obligatorio: las columnas vienen como categoria y sin
        # esto arrastran las 4.212 unidades del catalogo entero, casi todas en
        # cero, y el grafico sale con barras invisibles.
        for destino, columna in ((unidades, "unidad"), (vias, "mecanismo"),
                                 (proveedores, "proveedor")):
            if columna not in mes.columns:
                continue
            for clave, monto in mes.groupby(columna, observed=True)["total"].sum().items():
                destino[str(clave)] = destino.get(str(clave), 0.0) + float(monto)
        for clave, monto in mes.groupby("producto", observed=True)["total"].sum().items():
            texto = str(clave).strip()
            if texto:
                productos[texto] = productos.get(texto, 0.0) + float(monto)
        if "rut_proveedor" in mes.columns and suyo:
            suyas = mes[mes["rut_proveedor"].astype(str).map(alertador.solo_digitos_rut) == suyo]
            for clave, monto in suyas.groupby("unidad", observed=True)["total"].sum().items():
                mio[str(clave)] = mio.get(str(clave), 0.0) + float(monto)
            del suyas
        del mes, cuantas

    ordenar = lambda d: dict(sorted(d.items(), key=lambda x: -x[1]))
    mayores = lambda d: dict(sorted(d.items(), key=lambda x: -x[1])[:BARRAS])
    return {
        "bolsa": len(bolsa), "minimo": minimo, "meses": meses,
        "total": float(sum(vias.values())), "lineas": lineas,
        # Las unidades van ENTERAS, no cortadas a doce: el grafico se queda con
        # las de arriba, pero la agenda de visitas las necesita todas para
        # saber donde esta la linea entre ir y llamar.
        "unidades": ordenar(unidades), "mio_por_unidad": mio, "vias": vias,
        "proveedores": mayores(proveedores), "productos": mayores(productos),
    }


def _barras(titulo: str, pregunta: str, datos: dict, etiqueta: str,
            completos: dict | None = None) -> None:
    """Un gráfico de barras horizontales, de mayor a menor.

    Horizontales a proposito: los nombres de las unidades compradoras y de los
    productos son largos, y en vertical quedan de costado o cortados.

    POR QUE ALTAIR Y NO `st.bar_chart`: probado el 27-08-2026 en pantalla, y
    `st.bar_chart` falla en las dos cosas que este grafico tiene que hacer.
    Ordena las barras ALFABETICAMENTE —«Compras agiles» antes que «Convenio
    Marco», que es cinco veces mas grande—, y un ranking en orden alfabetico no
    es un ranking. Y corta los nombres a un puñado de letras
    («Abastecimiento G…»), justo lo que hay que leer. Con `sort="-x"` y
    `labelLimit` se arreglan las dos. Altair no agrega una dependencia: viene
    dentro de Streamlit.
    """
    if not datos:
        st.caption(f"**{titulo}** — sin datos suficientes.")
        return
    import altair as alt

    st.markdown(f"**{titulo}**")
    st.caption(pregunta)
    completos = completos or {}
    tabla = pd.DataFrame({
        "etiqueta": list(datos.keys()),
        # Los nombres de producto son parrafos y en el eje hay que cortarlos.
        # El globo muestra el nombre entero, para que nadie se quede con la
        # duda de que era «(2223481) KIT DE ALIMENTOS 4 PERSONAS 4 D…».
        "completo": [completos.get(k, k) for k in datos],
        "monto": [round(v / 1e6) for v in datos.values()],
    })
    grafico = (
        alt.Chart(tabla)
        .mark_bar(color="#1f6feb", cornerRadiusEnd=3)
        .encode(
            # `sort="-x"` es lo que pone la barra mas larga arriba.
            y=alt.Y("etiqueta:N", sort="-x", title=etiqueta,
                    axis=alt.Axis(labelLimit=420, labelFontSize=13)),
            x=alt.X("monto:Q", title="Millones de pesos",
                    axis=alt.Axis(format=",.0f")),
            tooltip=[alt.Tooltip("completo:N", title=etiqueta),
                     alt.Tooltip("monto:Q", title="Millones de pesos", format=",.0f")],
        )
        .properties(height=max(28 * len(tabla), 120))
    )
    st.altair_chart(grafico, use_container_width=True)


def _acortar(texto: str, largo: int = 58) -> str:
    """Los nombres de producto traen párrafos enteros; en una barra no caben."""
    limpio = " ".join(str(texto).split())
    return limpio if len(limpio) <= largo else limpio[:largo - 1] + "…"


def seccion_mercado(rut: str, unidades: pd.DataFrame, sello: str) -> None:
    """El bloque de gráficos, para pegar debajo de la tabla de Oportunidades.

    `rut` tiene que venir COMPLETO, con dígito verificador: los productos del
    proveedor se buscan por el RUT tal como está escrito en la bodega
    («77.082.051-0»), y con el cuerpo solo no encuentra ni una línea.

    `sello` es el mismo que usa el resto de la pestaña, para que la cache se
    suelte cuando el bodeguero deja datos nuevos.
    """
    st.divider()
    st.markdown("#### El mercado en cuatro gráficos")
    st.caption(
        "Lo de arriba dice a quién venderle. Esto dice **cómo es el mercado**: "
        "quién compra, por qué vía y contra quién se compite. Mira las seis "
        "vías de compra, no solo Convenio Marco.")

    izquierda, derecha = st.columns([2, 3])
    with izquierda:
        meses = st.selectbox("Cuánto mirar hacia atrás", [6, 12, 24], index=1,
                             format_func=lambda m: f"{m} meses", key="me_meses")
    with derecha:
        st.write("")
        pedir = st.button("Ver el mercado en gráficos", key="me_ver",
                          type="secondary", width="stretch")

    if not (pedir or st.session_state.get("me_listo") == f"{rut}|{meses}"):
        # Medido: ~5,5 segundos por mes de bodega, casi todo en mirar el texto
        # de cada producto. Se dice el número para que la espera no sorprenda.
        st.caption(f"Con {meses} meses tarda cerca de "
                   f"{'medio minuto' if meses <= 6 else ('un minuto' if meses <= 12 else 'dos minutos')} "
                   "la primera vez, porque hay que leer el texto de cada producto "
                   "de la bodega. Después queda guardado y es instantáneo.")
        return
    st.session_state["me_listo"] = f"{rut}|{meses}"

    with st.spinner("Leyendo la bodega y separando lo de tu rubro…"):
        datos = panorama_del_mercado(rut, meses, sello)

    if not datos["bolsa"]:
        st.warning("Ese RUT no registra ventas en la bodega, así que no se puede "
                   "deducir su rubro. Los gráficos necesitan saber qué vende.")
        return
    if not datos["lineas"]:
        st.warning("No se encontraron compras del Estado en ese rubro en el "
                   "período elegido. Prueba con más meses.")
        return

    a, b, c = st.columns(3)
    a.metric("El mercado de su rubro", _plata(datos["total"]))
    b.metric("Compras que lo tocan", f"{datos['lineas']:,}".replace(",", "."))
    c.metric("Unidades que compran", f"{len(datos['unidades']):,}".replace(",", "."),
             help=f"Son todas las que compraron algo del rubro. El gráfico "
                  f"muestra las {BARRAS} mayores.")

    st.caption(
        f"Se buscó con {datos['bolsa']} palabras sacadas de lo que este RUT ya "
        f"vendió, exigiendo {datos['minimo']} coincidencias por compra para no "
        "arrastrar cosas de otro rubro.")

    # Los codigos de unidad no le dicen nada a nadie: se cambian por el nombre.
    #
    # OJO CON LOS NOMBRES REPETIDOS: hay decenas de unidades llamadas «Bienes y
    # Servicios» o «Adquisiciones», de organismos distintos. Si se usa el nombre
    # pelado como etiqueta, dos compradores distintos se funden en una sola
    # barra y el grafico miente. A los repetidos se les pone el organismo al
    # lado; a los demas no, para no alargarlos de gusto.
    nombres, organismos = {}, {}
    if not unidades.empty:
        codigos = unidades["codigo_unidad"].astype(str)
        nombres = dict(zip(codigos, unidades["nombre_unidad"].astype(str)))
        organismos = dict(zip(codigos, unidades["nombre_organismo"].astype(str)))

    # Al grafico van solo las de arriba; el diccionario completo queda para la
    # agenda de visitas.
    mayores = dict(list(datos["unidades"].items())[:BARRAS])
    crudos = [nombres.get(codigo) or f"Unidad {codigo}" for codigo in mayores]
    repetidos = {n for n in crudos if crudos.count(n) > 1}
    por_unidad = {}
    for codigo, monto in mayores.items():
        etiqueta = nombres.get(codigo) or f"Unidad {codigo}"
        if etiqueta in repetidos:
            etiqueta = f"{etiqueta} · {organismos.get(codigo, codigo)}"
        por_unidad[_acortar(etiqueta)] = monto

    # Uno debajo del otro y a todo el ancho, no en dos columnas: en media
    # pantalla los nombres de los compradores y de los productos no caben, y
    # esto se hizo justamente para que se lean sin esfuerzo.
    st.write("")
    _barras("Cómo compran", "Por qué vía sale la plata. Cada una se vende "
            "distinto: una compra ágil cierra en 24 o 48 horas, una licitación no.",
            {alertador.VIAS.get(k, k): v
             for k, v in sorted(datos["vias"].items(), key=lambda x: -x[1])},
            "Vía de compra")

    _barras("Quién compra más", "Las unidades del Estado que más gastan en "
            "este rubro.", por_unidad, "Comprador")

    _barras("Qué compran más", "Los productos que se llevan la plata dentro "
            "del rubro. Pasa el mouse por encima para ver el nombre completo.",
            {_acortar(p): v for p, v in datos["productos"].items()}, "Producto",
            completos={_acortar(p): " ".join(str(p).split())
                       for p in datos["productos"]})

    _barras("Quién se lo está llevando", "Los proveedores que hoy ganan este "
            "mercado. Es contra ellos que se compite.",
            {_acortar(p, 46): v for p, v in datos["proveedores"].items()},
            "Proveedor",
            completos={_acortar(p, 46): " ".join(str(p).split())
                       for p in datos["proveedores"]})

    # El itinerario de visitas se cuelga de estos mismos datos: ya estan en
    # memoria y no hay que volver a leer la bodega.
    modulo_visitas.seccion_visitas(datos, unidades)


def _plata(monto: float) -> str:
    """$1.234 M. En pesos exactos no se lee y acá importa el orden de magnitud."""
    if abs(monto) >= 1e9:
        return f"${monto/1e6:,.0f} M".replace(",", ".")
    return f"${monto:,.0f}".replace(",", ".")
