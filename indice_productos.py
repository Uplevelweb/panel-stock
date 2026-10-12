"""
Indice del buscador de Mercado total (12-10-2026).

Lee la bodega de ordenes (`bodega/detalle/*.parquet`) y deja
`bodega/indice_productos.parquet`: una fila por producto (codigo ONU) con su
nombre generico, su rubro, y cuanto se transo por cada via. Es lo que consulta
el autocompletar de 3 letras: no se vuelve a leer la bodega entera.

La MARCA no esta aqui: solo existe en el catalogo de Convenio Marco y se cruza
aparte por ID de producto.

    python indice_productos.py
"""
import re
import unicodedata
from pathlib import Path
import pandas as pd

AQUI = Path(__file__).parent
DETALLE = AQUI / "bodega" / "detalle"
SALIDA = AQUI / "bodega" / "indice_productos.parquet"
MARCAS = AQUI / "bodega" / "marcas_cm.parquet"
SALIDA_MARCAS = AQUI / "bodega" / "indice_marcas.parquet"
VIAS = {"CM": "cm", "SE": "li", "LP": "li", "LQ": "li", "LE": "li", "AG": "ag", "TD": "td", "CD": "td", "C1": "td"}
COLS = ["orden", "mecanismo", "onu", "generico", "rubro1", "total", "id_producto"]


VACIAS = {"DE", "DEL", "LA", "EL", "LOS", "LAS", "PARA", "CON", "SIN", "POR", "EN", "AL", "UN", "UNA", "TIPO"}


def concepto_cm(nombre: str) -> str:
    """El «producto» de Convenio Marco: en CM el codigo ONU viene en 0 (99,8% de las
    lineas) y cada ID es un SKU con marca, tamaño y region en el nombre. Se agrupa
    por las dos primeras palabras («PAPEL HIGIENICO», «GAS LICUADO»)."""
    t = unicodedata.normalize("NFKD", str(nombre or "")).encode("ascii", "ignore").decode().upper()
    t = re.sub(r"^\(\d+\)\s*", "", t)
    palabras = [w for w in re.findall(r"[A-Z]{2,}", t) if w not in VACIAS]
    return " ".join(palabras[:2])


def mapa_conceptos() -> dict[str, str]:
    """id_producto -> concepto, desde el catalogo (marcas_cm.parquet)."""
    if not MARCAS.exists():
        return {}
    m = pd.read_parquet(MARCAS)
    if "producto" not in m.columns:
        return {}
    return {str(i): concepto_cm(n) for i, n in zip(m["id_producto"], m["producto"])}


def aplicar_concepto(t: pd.DataFrame, mapa: dict[str, str]) -> pd.DataFrame:
    """En las lineas CM reemplaza el ONU (0) por «cm:CONCEPTO»."""
    es_cm = t["mecanismo"].astype(str) == "CM"
    if not es_cm.any():
        return t
    t = t.copy()
    t["onu"] = t["onu"].astype(str)
    ids = t.loc[es_cm, "id_producto"].astype(str)
    conc = ids.map(mapa)
    # Sin catalogo para ese ID: se usa el nombre de la propia linea.
    falta = conc.isna() | (conc == "")
    conc[falta] = t.loc[es_cm, "generico"].astype(str)[falta].map(concepto_cm)
    t.loc[es_cm, "onu"] = "cm:" + conc
    t.loc[es_cm, "generico"] = conc.str.title()
    t.loc[es_cm, "rubro1"] = "Convenio Marco"
    return t


def construir() -> pd.DataFrame:
    partes = []
    mapa = mapa_conceptos()
    for archivo in sorted(DETALLE.glob("20*.parquet")):
        t = pd.read_parquet(archivo)
        if "onu" not in t.columns:
            continue  # mes anterior al 12-10-2026: aun sin producto ONU
        t = aplicar_concepto(t[COLS].copy(), mapa)
        t = t[~t["onu"].astype(str).isin(["0", ""]) & ~t["onu"].astype(str).str.endswith(":")]
        t["total"] = pd.to_numeric(t["total"], errors="coerce").fillna(0)
        t["via"] = t["mecanismo"].astype(str).map(VIAS)
        t = t[t["via"].notna() & (t["onu"].astype(str) != "")]
        g = (t.assign(onu=t["onu"].astype(str), generico=t["generico"].astype(str), rubro1=t["rubro1"].astype(str))
               .groupby(["onu", "generico", "rubro1", "via"], observed=True)
               .agg(monto=("total", "sum"), ordenes=("orden", "nunique")).reset_index())
        partes.append(g)
    if not partes:
        return pd.DataFrame(columns=["onu", "generico", "rubro1", "monto_cm", "monto_li", "monto_ag", "monto_td", "monto"])
    t = pd.concat(partes, ignore_index=True)
    t = t.groupby(["onu", "generico", "rubro1", "via"], observed=True).agg(monto=("monto", "sum")).reset_index()
    a = t.pivot_table(index=["onu", "generico", "rubro1"], columns="via", values="monto", fill_value=0).reset_index()
    for v in ("cm", "li", "ag", "td"):
        a["monto_" + v] = a.get(v, 0)
    a["monto"] = a[["monto_cm", "monto_li", "monto_ag", "monto_td"]].sum(axis=1)
    return a[["onu", "generico", "rubro1", "monto_cm", "monto_li", "monto_ag", "monto_td", "monto"]].sort_values("monto", ascending=False)


def construir_marcas() -> pd.DataFrame:
    """Por producto (ONU) y marca: cuanto se transo en Convenio Marco.
    La marca sale del catalogo (`marcas_catalogo.py`) cruzado por ID de producto."""
    cols = ["id_producto", "mecanismo", "onu", "total", "orden"]
    if not MARCAS.exists():
        return pd.DataFrame(columns=["onu", "marca", "monto", "ordenes"])
    mapa = mapa_conceptos()
    m = pd.read_parquet(MARCAS, columns=["id_producto", "marca"])
    m = m[m["marca"].astype(str) != ""]
    partes = []
    for archivo in sorted(DETALLE.glob("20*.parquet")):
        try:
            t = pd.read_parquet(archivo, columns=cols, filters=[("mecanismo", "==", "CM")])
        except Exception:
            continue
        t = t[t["id_producto"].astype(str) != ""].copy()
        t["total"] = pd.to_numeric(t["total"], errors="coerce").fillna(0)
        t["id_producto"] = t["id_producto"].astype(str)
        t["onu"] = "cm:" + t["id_producto"].map(mapa).fillna("")
        t = t[t["onu"] != "cm:"]
        j = t.merge(m, on="id_producto", how="inner")
        partes.append(j.groupby(["onu", "marca"], observed=True).agg(monto=("total", "sum"), ordenes=("orden", "nunique")).reset_index())
    if not partes:
        return pd.DataFrame(columns=["onu", "marca", "monto", "ordenes"])
    return (pd.concat(partes).groupby(["onu", "marca"], observed=True)
              .agg(monto=("monto", "sum"), ordenes=("ordenes", "sum")).reset_index()
              .sort_values("monto", ascending=False))


if __name__ == "__main__":
    r = construir()
    r.to_parquet(SALIDA, index=False, compression="zstd")
    print(f"{len(r):,} productos -> {SALIDA}")
    rm = construir_marcas()
    if len(rm):
        rm.to_parquet(SALIDA_MARCAS, index=False, compression="zstd")
        print(f"{len(rm):,} pares producto-marca -> {SALIDA_MARCAS}")
