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
VIAS = {"cm": "Convenio Marco", "li": "Licitaciones", "ag": "Compras ágiles", "td": "Trato directo", "cc": "Compra coordinada"}
MECA = {"CM": "cm", "SE": "li", "LP": "li", "LQ": "li", "LE": "li", "AG": "ag", "TD": "td", "CD": "td", "C1": "td", "CC": "cc"}
COLOR = {"cm": "🟢", "li": "🟠", "ag": "🔵", "td": "🟣", "cc": "🟡"}


def _mm(x: float) -> str:
    return "$" + f"{x / 1e6:,.0f}".replace(",", ".") + " MM"


# 12-10-2026, pedido de Serling (vista móvil): el desplegable con buscador
# ocupaba media pantalla y el teclado tapaba el resto, y st.bar_chart no
# rotula las barras. Ahora: vías como botones tocables, productos en una
# lista que se desliza DENTRO de su propio recuadro (sin teclado, sin
# ventana encima) y barras horizontales con nombre, monto y % a la vista.
ESTILO = """<style>
[data-testid="stButtonGroup"] button{font-weight:700!important;min-height:44px;background:#fff!important;color:#5b6b82!important;border:2px solid #cfd8e6!important}
[data-testid="stButtonGroup"] button[aria-pressed="true"]{background:#0c2c57!important;color:#fff!important;border-color:#0c2c57!important}
.mt-b{margin:0 0 14px}
.mt-cat{font-size:.74rem;font-weight:800;letter-spacing:.04em;text-transform:uppercase;color:#f18c3f;margin:10px 0 2px}
.mt-b-top{display:flex;justify-content:space-between;align-items:baseline;gap:10px;margin-bottom:5px;line-height:1.25}
.mt-b-et{font-weight:700;color:#0c2c57;overflow-wrap:anywhere}
.mt-b-sub{display:block;font-weight:500;font-size:.78em;color:#5b6b82}
.mt-b-v{font-weight:800;color:#0c2c57;white-space:nowrap}
.mt-b-v small{font-size:.78em;font-weight:700;color:#5b6b82;margin-left:6px}
.mt-b-pista{height:14px;border-radius:99px;background:#e3eaf3;overflow:hidden}
.mt-b-barra{height:100%;border-radius:99px;background:#0c2c57}
.mt-b.top .mt-b-barra{background:#f18c3f}
.st-key-mt_rueda [data-testid="stCheckbox"]{min-height:52px;display:flex;align-items:center;padding:4px 6px;
  border-bottom:1px solid #e3eaf3;scroll-snap-align:center}
.st-key-mt_rueda [data-testid="stCheckbox"]:has(input:checked){background:#fff3e8;border-radius:10px}
.st-key-mt_rueda label{width:100%;cursor:pointer}
.st-key-mt_rueda [data-testid="stVerticalBlock"]{scroll-snap-type:y proximity}
.st-key-mt_rueda{scroll-snap-type:y proximity}
@media(max-width:640px){.block-container{padding-left:.9rem!important;padding-right:.9rem!important}}
</style>"""


def _barras(valores: pd.Series, detalle: list[str] | None = None, total: float | None = None) -> None:
    """Barras horizontales legibles: nombre, monto en MM y % del total.
    `valores` en pesos, ya ordenado de mayor a menor."""
    import html
    tot = float(total if total else valores.sum()) or 1.0
    mx = float(valores.max()) or 1.0
    filas = []
    for i, (nom, v) in enumerate(valores.items()):
        ancho = max(2.0, float(v) / mx * 100)
        filas.append(
            f'<div class="mt-b{" top" if i == 0 else ""}"><div class="mt-b-top">'
            f'<span class="mt-b-et">{html.escape(str(nom))}'
            + (f'<small class="mt-b-sub">{html.escape(detalle[i])}</small>' if detalle and detalle[i] else '') + '</span>'
            f'<span class="mt-b-v">{_mm(float(v))}<small>{float(v) / tot:.0%}</small></span></div>'
            f'<div class="mt-b-pista"><div class="mt-b-barra" style="width:{ancho:.0f}%"></div></div></div>')
    st.markdown("".join(filas), unsafe_allow_html=True)


@st.cache_data(show_spinner=False, max_entries=2)
def _indice(sello: float) -> pd.DataFrame:
    return pd.read_parquet(BODEGA / "indice_productos.parquet")


@st.cache_data(show_spinner=False, max_entries=2)
def _mapa(sello: float) -> dict[str, str]:
    from indice_productos import mapa_conceptos
    return mapa_conceptos()


@st.cache_data(show_spinner="Leyendo las compras…", max_entries=20)
def _detalle(onus: tuple[str, ...], sello: float, ids: tuple[str, ...] = ()) -> pd.DataFrame:
    """Líneas de esos productos, ya resumidas por comprador-vía-proveedor.
    `onus` mezcla códigos ONU y conceptos de Convenio Marco («cm:PAPEL HIGIENICO»):
    en CM el ONU viene en 0, así que se filtra por los IDs del catálogo."""
    normales = [o for o in onus if not o.startswith("cm:")]
    conceptos = {o[3:] for o in onus if o.startswith("cm:")}
    ids_cm = set(ids)
    if conceptos:
        ids_cm |= {i for i, c in _mapa(sello).items() if c in conceptos}
    ids_cm = tuple(ids_cm)
    partes = []
    for archivo in sorted((BODEGA / "detalle").glob("20*.parquet")):
        try:
            t = pd.read_parquet(archivo, columns=["unidad", "mecanismo", "proveedor", "total", "orden", "onu", "id_producto", "generico"])
        except Exception:
            continue  # mes sin la columna ONU (anterior al 12-10-2026)
        es_cm = t["mecanismo"].astype(str) == "CM"
        pedido = pd.Series(False, index=t.index)
        if normales:
            pedido |= (~es_cm) & t["onu"].astype(str).isin(normales)
        if ids_cm:
            pedido |= es_cm & t["id_producto"].astype(str).isin(ids_cm)
        if conceptos:
            # Productos vendidos que ya no estan en el catalogo vigente: se les
            # asigna concepto por el nombre de la linea (igual que el indice).
            from indice_productos import concepto_cm
            nombres = t.loc[es_cm & ~pedido, "generico"].astype(str).unique()
            buenos = {n for n in nombres if concepto_cm(n) in conceptos}
            if buenos:
                pedido |= es_cm & t["generico"].astype(str).isin(buenos)
        t = t[pedido]
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


@st.cache_data(show_spinner=False, max_entries=2)
def _marcas(sello: float) -> pd.DataFrame:
    return pd.read_parquet(BODEGA / "indice_marcas.parquet")


@st.cache_data(show_spinner=False, max_entries=8)
def _ids_de_marca(marca: str, sello: float) -> tuple[str, ...]:
    m = pd.read_parquet(BODEGA / "marcas_cm.parquet", columns=["id_producto", "marca"])
    return tuple(m.loc[m["marca"] == marca, "id_producto"].astype(str))


# 16-10-2026, pedido de Serling: la busqueda debe ir arrojando sugerencias a
# medida que se escribe, sin apretar Enter. Streamlit solo envia el texto al
# apretar Enter, asi que este script (una sola vez por pagina, delegado en el
# documento) manda ese Enter solo, 300 ms despues de la ultima letra. El Enter
# a mano sigue funcionando igual.
BUSQUEDA_EN_VIVO = """<script>
(function(){
  if (window.__mtEnVivo) return; window.__mtEnVivo = true;
  var t = null;
  document.addEventListener('input', function(e){
    var el = e.target;
    if (!el || el.tagName !== 'INPUT' || el.getAttribute('aria-label') !== 'Producto') return;
    clearTimeout(t);
    t = setTimeout(function(){
      var ev = {key:'Enter', code:'Enter', keyCode:13, which:13, bubbles:true, cancelable:true};
      el.dispatchEvent(new KeyboardEvent('keydown', ev));
      el.dispatchEvent(new KeyboardEvent('keyup', ev));
    }, 300);
  }, true);
})();
</script>"""


@st.fragment
def seccion_mercado_total() -> None:
    ruta = BODEGA / "indice_productos.parquet"
    if not ruta.exists():
        st.info("El índice de productos todavía no está listo: se arma cuando la bodega se rehace con el producto de cada compra.")
        return
    indice = _indice(ruta.stat().st_mtime)

    st.markdown("**1 · ¿Dónde quieres mirar?** (puedes elegir varias vías)")
    st.markdown(ESTILO, unsafe_allow_html=True)
    vias = st.pills("Vías", list(VIAS), selection_mode="multi", default=["cm", "li", "ag"],
                    format_func=VIAS.get, key="mt_vias", label_visibility="collapsed") or []
    st.markdown("**2 · Busca tu producto** (las sugerencias aparecen mientras escribes)")
    q = st.text_input("Producto", key="mt_q", placeholder="Ej: ace, arr, pap…", label_visibility="collapsed")
    try:
        st.html(BUSQUEDA_EN_VIVO, unsafe_allow_javascript=True)
    except TypeError:  # Streamlit antiguo sin ese parametro: queda con Enter
        pass
    if len(q.strip()) < 3:
        st.caption("Escribe al menos 3 letras y aparecen las sugerencias. La marca solo se mide en Convenio Marco.")
        return
    hay = indice[indice["generico"].str.contains(q.strip(), case=False, na=False, regex=False)]
    # Primero los que tienen una PALABRA que empieza con lo escrito («ace» ->
    # «Aceite…» antes que «Acetato…» en medio de otro nombre); dentro de cada
    # grupo, mantiene el orden por monto del indice.
    ql = q.strip().lower()
    empieza = hay["generico"].str.lower().apply(lambda g: any(p.startswith(ql) for p in g.replace(",", " ").split()))
    inicia = hay["generico"].str.lower().str.startswith(ql)
    hay = pd.concat([hay[inicia], hay[empieza & ~inicia], hay[~empieza]]).head(30)
    nombre = {r.onu: f"{r.generico} · {r.rubro1}" for r in hay.itertuples()}
    # La MARCA solo existe en Convenio Marco (catalogo). Se busca igual: elegir
    # una marca deja la consulta solo en esa via.
    rm = ruta.with_name("indice_marcas.parquet")
    marcas_ok = rm.exists() and ruta.with_name("marcas_cm.parquet").exists()
    if marcas_ok:
        im = _marcas(rm.stat().st_mtime)
        ms = (im[im["marca"].str.contains(q.strip(), case=False, na=False, regex=False)]
              .groupby("marca")["monto"].sum().sort_values(ascending=False).head(8))
        for mc in ms.index:
            nombre["m:" + mc] = f"Marca {mc} · solo Convenio Marco"
    if not nombre:
        st.warning("Sin coincidencias. Prueba con otra palabra.")
        return
    # Sugerencias agrupadas por CATEGORIA (rubro): la lista se va armando sola
    # a medida que se escribe y cada producto cuelga de su categoria.
    st.caption("Toca el producto que quieres analizar (puedes marcar varios). Desliza la lista para ver más.")
    grupos: dict[str, list[tuple[str, str]]] = {}
    vistos: set = set()
    for r in hay.itertuples():
        if r.onu in vistos:
            continue
        vistos.add(r.onu)
        grupos.setdefault(r.rubro1, []).append((r.onu, r.generico))
    elegidos = []
    with st.container(height=300, border=True, key="mt_rueda"):
        for k in nombre:
            if k.startswith("m:"):
                grupos.setdefault("Marcas (solo Convenio Marco)", []).append((k, nombre[k].replace("Marca ", "").replace(" · solo Convenio Marco", "")))
        for rubro, items in grupos.items():
            st.markdown(f'<div class="mt-cat">{rubro}</div>', unsafe_allow_html=True)
            for k, t in items:
                if st.checkbox(t, value=False, key=f"mt_sel_{k}"):
                    elegidos.append(k)
    if not vias:
        st.info("Elige al menos una vía.")
        return
    if not elegidos:
        st.info("Marca arriba el producto que quieres analizar.")
        return
    # El resultado vive en un hueco propio que se VACIA apenas cambia la
    # seleccion: antes, mientras «Leyendo las compras…», seguian a la vista (en
    # gris) las cifras de la busqueda anterior y parecian las de esta.
    zona = st.empty()
    with zona.container():
        _resultado(vias, elegidos, ruta, rm, marcas_ok, im if marcas_ok else None)


def _resultado(vias, elegidos, ruta, rm, marcas_ok, im) -> None:
    onus = [e for e in elegidos if not e.startswith("m:")]
    marcas_sel = [e[2:] for e in elegidos if e.startswith("m:")]
    if marcas_sel:
        ids = tuple(i for mc in marcas_sel for i in _ids_de_marca(mc, rm.stat().st_mtime))
        if "cm" not in vias:
            st.warning("La marca solo se mide en Convenio Marco: se activó esa vía.")
            vias = vias + ["cm"]
        d = _detalle(tuple(onus), ruta.stat().st_mtime, ()) if onus else _detalle((), ruta.stat().st_mtime, ids)
        d = d[d["via"] == "cm"] if not onus else d
        st.caption("Con una marca elegida solo se cuenta Convenio Marco: es la única vía donde la marca existe.")
    else:
        d = _detalle(tuple(onus), ruta.stat().st_mtime)
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
    _barras(por_via.rename(index=VIAS).sort_values(ascending=False))

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
        _barras(pd.Series(t["total"].values, index=t["Institución"].values),
                [" · ".join(x for x in (u_, r_) if x) for u_, r_ in zip(t["Unidad"], t["Región"])], total=comp["total"].sum())
    with b:
        st.markdown("**Por región**")
        r = comp.groupby("Región")["total"].sum().sort_values(ascending=False).head(10)
        _barras(r.head(8), total=comp["total"].sum())
    st.markdown("**Quién lo vende hoy** (posibles distribuidores o socios de canal)")
    p = d.groupby("proveedor")["total"].sum().sort_values(ascending=False).head(10)
    _barras(p, total=d["total"].sum())

    if marcas_ok and onus:
        sub = im[im["onu"].isin(onus)].groupby("marca")["monto"].sum().sort_values(ascending=False).head(8)
        st.markdown("**Marcas (solo Convenio Marco)**")
        if sub.empty:
            st.caption("El catálogo no identifica marca para estos productos.")
        else:
            tot = sub.sum()
            _barras(sub)
            st.caption(f"Participación dentro de Convenio Marco; la marca líder concentra el {sub.iloc[0] / tot:.0%} de lo que tiene marca.")
