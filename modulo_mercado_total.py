"""
Comportamiento Mercado Público — vista «Producto o marca» (Mercado total, 12-10-2026).

Elegir vías (Convenio Marco, Licitaciones, Compras ágiles, Trato directo) y
buscar un producto con 3 letras: sale cuánto se transó, dónde, quién compra y
quién vende. La MARCA solo existe en Convenio Marco (catálogo): aún no se
cruza aquí, el buscador es por producto.

MEMORIA: nunca se carga una bodega entera. El buscador sale de
`bodega/indice_productos.parquet` (chico) y el detalle de un producto se lee
mes a mes filtrando por ONU AL LEER (pyarrow) y resumiendo antes de seguir.
"""
from pathlib import Path
import pandas as pd
import streamlit as st

AQUI = Path(__file__).parent
BODEGA = AQUI / "bodega"
VIAS = {"cm": "Convenio Marco", "li": "Licitaciones", "ag": "Compras ágiles", "td": "Trato directo"}
MECA = {"CM": "cm", "SE": "li", "LP": "li", "LQ": "li", "LE": "li", "AG": "ag", "TD": "td", "CD": "td", "C1": "td"}
COLOR = {"cm": "🟢", "li": "🟠", "ag": "🔵", "td": "🟣"}


def _mm(x: float) -> str:
    return "$" + f"{x / 1e6:,.0f}".replace(",", ".") + " MM"


@st.cache_data(show_spinner=False, max_entries=2)
def _indice(sello: float) -> pd.DataFrame:
    return pd.read_parquet(BODEGA / "indice_productos.parquet")


@st.cache_data(show_spinner="Leyendo las compras…", max_entries=20)
def _detalle(onus: tuple[str, ...], sello: float) -> pd.DataFrame:
    """Líneas de esos productos, ya resumidas por comprador-vía-proveedor."""
    partes = []
    for archivo in sorted((BODEGA / "detalle").glob("20*.parquet")):
        try:
            t = pd.read_parquet(archivo, columns=["unidad", "mecanismo", "proveedor", "total", "orden", "onu"],
                                filters=[("onu", "in", list(onus))])
        except Exception:
            continue  # mes sin la columna ONU (anterior al 12-10-2026)
        if t.empty:
            continue
        t["via"] = t["mecanismo"].astype(str).map(MECA)
        t["total"] = pd.to_numeric(t["total"], errors="coerce").fillna(0)
        partes.append(t.dropna(subset=["via"]).groupby(["unidad", "via", "proveedor"], observed=True)
                       .agg(total=("total", "sum"), ordenes=("orden", "nunique")).reset_index())
    if not partes:
        return pd.DataFrame(columns=["unidad", "via", "proveedor", "total", "ordenes"])
    return (pd.concat(partes).groupby(["unidad", "via", "proveedor"], observed=True)
              .agg(total=("total", "sum"), ordenes=("ordenes", "sum")).reset_index())


def seccion_mercado_total() -> None:
    ruta = BODEGA / "indice_productos.parquet"
    if not ruta.exists():
        st.info("El índice de productos todavía no está listo: se arma cuando la bodega se rehace con el producto de cada compra.")
        return
    indice = _indice(ruta.stat().st_mtime)

    st.markdown("**1 · ¿Dónde quieres mirar?** (puedes elegir varias vías)")
    vias = st.multiselect("Vías", list(VIAS), default=["cm", "li", "ag"], format_func=VIAS.get,
                          key="mt_vias", label_visibility="collapsed")
    st.markdown("**2 · Busca tu producto** (escribe 3 letras)")
    q = st.text_input("Producto", key="mt_q", placeholder="Ej: ace, arr, pap…", label_visibility="collapsed")
    if len(q.strip()) < 3:
        st.caption("Escribe al menos 3 letras. La marca solo se mide en Convenio Marco y se suma en la siguiente versión.")
        return
    hay = indice[indice["generico"].str.contains(q.strip(), case=False, na=False, regex=False)]
    hay = hay.head(30)
    if hay.empty:
        st.warning("Sin coincidencias. Prueba con otra palabra.")
        return
    nombre = {r.onu: f"{r.generico} · {r.rubro1}" for r in hay.itertuples()}
    elegidos = st.multiselect("Elige uno o más", list(nombre), default=list(nombre)[:1], format_func=nombre.get, key="mt_sel")
    if not vias or not elegidos:
        st.info("Elige al menos una vía y un producto.")
        return

    d = _detalle(tuple(elegidos), ruta.stat().st_mtime)
    d = d[d["via"].isin(vias)]
    if d.empty:
        st.info("Sin compras de ese producto en las vías elegidas.")
        return
    c1, c2, c3 = st.columns(3)
    c1.metric("Transó el Estado", _mm(d["total"].sum()))
    c2.metric("Instituciones compradoras", f"{d['unidad'].nunique():,}".replace(",", "."))
    c3.metric("Proveedores que lo venden", f"{d['proveedor'].nunique():,}".replace(",", "."))

    por_via = d.groupby("via")["total"].sum().reindex(vias).fillna(0)
    st.markdown("**Por qué vía se compra**")
    st.bar_chart(pd.DataFrame({"Monto (MM)": (por_via / 1e6).round(0).values}, index=[VIAS[v] for v in por_via.index]))

    u = pd.read_parquet(BODEGA / "unidades.parquet", columns=["codigo_unidad", "nombre_unidad", "nombre_organismo", "region"])
    u["codigo_unidad"] = u["codigo_unidad"].astype(str)
    comp = d.groupby("unidad")["total"].sum().reset_index()
    comp["unidad"] = comp["unidad"].astype(str)
    comp = comp.merge(u, left_on="unidad", right_on="codigo_unidad", how="left")
    comp["Institución"] = comp["nombre_organismo"].fillna(comp["unidad"])
    comp["Unidad"] = comp["nombre_unidad"].fillna("")
    comp["Región"] = comp["region"].fillna("")
    a, b = st.columns(2)
    with a:
        st.markdown("**Dónde más se compra**")
        t = comp.sort_values("total", ascending=False).head(10)
        st.dataframe(t.assign(Monto=t["total"].round(0).astype("Int64"))[["Institución", "Unidad", "Región", "Monto"]],
                     hide_index=True, width="stretch", column_config={"Monto": st.column_config.NumberColumn(format="localized")})
    with b:
        st.markdown("**Por región**")
        r = comp.groupby("Región")["total"].sum().sort_values(ascending=False).head(10)
        st.bar_chart((r / 1e6).round(0))
    st.markdown("**Quién lo vende hoy** (posibles distribuidores o socios de canal)")
    p = d.groupby("proveedor")["total"].sum().sort_values(ascending=False).head(10).reset_index()
    p["Monto"] = p["total"].round(0).astype("Int64")
    st.dataframe(p[["proveedor", "Monto"]].rename(columns={"proveedor": "Proveedor"}), hide_index=True, width="stretch",
                 column_config={"Monto": st.column_config.NumberColumn(format="localized")})
