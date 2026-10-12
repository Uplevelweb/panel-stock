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
from pathlib import Path
import pandas as pd

AQUI = Path(__file__).parent
DETALLE = AQUI / "bodega" / "detalle"
SALIDA = AQUI / "bodega" / "indice_productos.parquet"
VIAS = {"CM": "cm", "SE": "li", "LP": "li", "LQ": "li", "LE": "li", "AG": "ag", "TD": "td", "CD": "td", "C1": "td"}
COLS = ["orden", "mecanismo", "onu", "generico", "rubro1", "total"]


def construir() -> pd.DataFrame:
    partes = []
    for archivo in sorted(DETALLE.glob("20*.parquet")):
        t = pd.read_parquet(archivo)
        if "onu" not in t.columns:
            continue  # mes anterior al 12-10-2026: aun sin producto ONU
        t = t[COLS].copy()
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


if __name__ == "__main__":
    r = construir()
    r.to_parquet(SALIDA, index=False, compression="zstd")
    print(f"{len(r):,} productos -> {SALIDA}")
