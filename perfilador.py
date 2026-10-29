"""
PERFILADOR — la «Ficha de la institucion» de CupidoLicita
==========================================================

Para cada unidad compradora (el prefijo del codigo: «2735-134-LP26» -> 2735)
deja en la tabla `organismo_perfil` de Supabase un resumen sacado de la bodega:

- Que compra: ultimos 12 meses de ordenes de compra (`bodega/detalle`), monto
  por via (Convenio Marco, compra agil, licitacion, trato directo), los rubros
  y productos donde mas gasta y a que proveedores les compra.
- A quien le adjudica: ultimos 24 meses de licitaciones (`bodega/licitaciones`),
  cuantas publico, cuantas adjudico, cuantos oferentes llegan en promedio y
  quienes ganan mas.

Con eso la vista espejo muestra la ficha del comprador sin leer la bodega,
que vive en este repositorio y no en Supabase.

Corre dentro del workflow «Bodega de Licitaciones», despues del adjudicador.
Recalcula todo en cada corrida. Necesita SUPABASE_URL y SUPABASE_SECRET_KEY.

    python perfilador.py              # sube a Supabase
    python perfilador.py --prueba     # muestra tres perfiles y no sube nada

MEMORIA: el detalle son ~8 millones de lineas en 24 meses. Se lee mes a mes,
solo las columnas necesarias, y se suma al leer (igual que resumen_de_ordenes
en alertador.py, que tumbo la app el 27-08-2026 cuando cargaba todo de una).
"""
import argparse
import json
import os
import sys
import urllib.request
from datetime import date, timedelta
from pathlib import Path

import pandas as pd
import pyarrow.parquet as pq

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

AQUI = Path(__file__).parent
BODEGA_OC = AQUI / "bodega" / "detalle"
BODEGA_LIC = AQUI / "bodega" / "licitaciones"
VIAS = {"CM": "Convenio Marco", "AG": "Compra ágil", "SE": "Licitación", "TD": "Trato directo",
        "CC": "Convenios", "CT": "Contratos"}
TOPE = 6          # cuantos rubros, productos, proveedores y ganadores por unidad
TANDA = 300


def _texto(serie: pd.Series) -> pd.Series:
    return serie.astype(str).str.strip().str.replace(r"\s+", " ", regex=True)


def _top(tabla: pd.DataFrame, llave: str, n: int) -> pd.DataFrame:
    """Los n mas grandes por unidad (tabla ya sumada: unidad, llave, monto, ...)."""
    tabla = tabla[tabla[llave].ne("") & tabla[llave].ne("nan")]
    return (tabla.sort_values("monto", ascending=False)
                 .groupby("unidad", sort=False).head(n))


def leer_ordenes(meses: int = 12):
    corte = (date.today() - timedelta(days=meses * 31)).strftime("%Y-%m")
    vias, rubros, productos, proveedores, nombres = [], [], [], [], []
    for archivo in sorted(BODEGA_OC.glob("*.parquet")):
        if archivo.stem < corte:
            continue
        hay = set(pq.read_schema(archivo).names)
        pedidas = [c for c in ["unidad", "organismo", "orden", "mecanismo", "proveedor", "producto",
                               "generico", "rubro3", "rubro1", "total"] if c in hay]
        if "unidad" not in pedidas or "total" not in pedidas:
            continue
        m = pd.read_parquet(archivo, columns=pedidas)
        m["unidad"] = _texto(m["unidad"])
        m["monto"] = pd.to_numeric(m["total"], errors="coerce").fillna(0.0)
        if "mecanismo" not in m:
            m["mecanismo"] = "CM"
        if "orden" not in m:
            m["orden"] = ""
        vias.append(m.groupby(["unidad", "mecanismo"], sort=False)
                     .agg(monto=("monto", "sum"), ordenes=("orden", "nunique")).reset_index())
        if "organismo" in m:
            nombres.append(m.groupby("unidad", sort=False)["organismo"].last().reset_index())
        # El rubro existe desde el 12-10-2026; los meses viejos aportan solo productos.
        rubro = next((c for c in ("rubro3", "rubro1") if c in m), None)
        if rubro:
            m["rubro"] = _texto(m[rubro])
            rubros.append(m.groupby(["unidad", "rubro"], sort=False)["monto"].sum().reset_index())
        nombre = m["generico"] if "generico" in m else m.get("producto")
        if nombre is not None:
            m["prod"] = _texto(nombre).str.slice(0, 70).str.capitalize()
            if "producto" in m and "generico" in m:
                vacio = m["prod"].isin(["", "Nan", "None"])
                m.loc[vacio, "prod"] = _texto(m.loc[vacio, "producto"]).str.slice(0, 70).str.capitalize()
            p = m.groupby(["unidad", "prod"], sort=False).agg(monto=("monto", "sum"), veces=("monto", "size")).reset_index()
            productos.append(_top(p, "prod", 40))
        if "proveedor" in m:
            m["prov"] = _texto(m["proveedor"])
            pr = m.groupby(["unidad", "prov"], sort=False)["monto"].sum().reset_index()
            proveedores.append(_top(pr, "prov", 30))
        del m

    def sumar(partes, llaves, cols):
        if not partes:
            return pd.DataFrame(columns=llaves + list(cols))
        return pd.concat(partes, ignore_index=True).groupby(llaves, sort=False).agg(cols).reset_index()

    return (sumar(vias, ["unidad", "mecanismo"], {"monto": "sum", "ordenes": "sum"}),
            sumar(rubros, ["unidad", "rubro"], {"monto": "sum"}),
            sumar(productos, ["unidad", "prod"], {"monto": "sum", "veces": "sum"}),
            sumar(proveedores, ["unidad", "prov"], {"monto": "sum"}),
            pd.concat(nombres, ignore_index=True).groupby("unidad").last().reset_index() if nombres
            else pd.DataFrame(columns=["unidad", "organismo"]))


def leer_licitaciones(meses: int = 24):
    corte = (date.today() - timedelta(days=meses * 31)).strftime("%Y-%m")
    resumen, ganadores, nombres = [], [], []
    for archivo in sorted(BODEGA_LIC.glob("*.parquet")):
        if archivo.stem < corte:
            continue
        hay = set(pq.read_schema(archivo).names)
        pedidas = [c for c in ["unidad", "codigo", "estado", "n_oferentes", "proveedor", "rut_proveedor",
                               "seleccionada", "monto_adjudicado", "nombre_unidad", "nombre_organismo", "comuna", "region"] if c in hay]
        if "unidad" not in pedidas or "codigo" not in pedidas:
            continue
        d = pd.read_parquet(archivo, columns=pedidas)
        d["unidad"] = _texto(d["unidad"])
        estado = d["estado"].astype(str).str.lower() if "estado" in d else pd.Series("", index=d.index)
        d["adjudicada"] = estado.str.startswith("adjudicada")
        d["desierta"] = estado.str.startswith("desierta")
        por_lic = d.groupby(["unidad", "codigo"], sort=False).agg(
            adjudicada=("adjudicada", "max"), desierta=("desierta", "max"),
            oferentes=("n_oferentes", "max") if "n_oferentes" in d else ("adjudicada", "size")).reset_index()
        resumen.append(por_lic)
        if "nombre_organismo" in d:
            n = d[["unidad"]].copy()
            n["nombre"] = _texto(d["nombre_organismo"])
            if "nombre_unidad" in d:
                n["nombre"] = (n["nombre"] + " - " + _texto(d["nombre_unidad"])).str.strip(" -")
            # Comuna y region del organismo: con eso el Mapa de Calor ubica cada oportunidad.
            for col in ("comuna", "region"):
                n[col] = _texto(d[col]) if col in d else ""
            n = n.replace({"nan": ""})
            n["nombre"] = n["nombre"].str.replace(r"^nan\s*-\s*|\s*-\s*nan$", "", regex=True)
            nombres.append(n[n["nombre"] != ""].groupby("unidad", sort=False)[["nombre", "comuna", "region"]].last().reset_index())
        if "seleccionada" in d and "proveedor" in d:
            g = d[d["seleccionada"].astype(str).str.strip().str.lower() == "seleccionada"].copy()
            g["prov"] = _texto(g["proveedor"])
            g["monto"] = pd.to_numeric(g.get("monto_adjudicado"), errors="coerce").fillna(0.0)
            ganadores.append(g.groupby(["unidad", "prov", "codigo"], sort=False)["monto"].sum().reset_index())
        del d
    lic = (pd.concat(resumen, ignore_index=True).drop_duplicates(["unidad", "codigo"], keep="last")
           if resumen else pd.DataFrame(columns=["unidad", "codigo", "adjudicada", "desierta", "oferentes"]))
    gan = pd.concat(ganadores, ignore_index=True) if ganadores else pd.DataFrame(columns=["unidad", "prov", "codigo", "monto"])
    if not gan.empty:
        gan = (gan.groupby(["unidad", "prov"], sort=False)
                  .agg(ganadas=("codigo", "nunique"), monto=("monto", "sum")).reset_index())
    nom = (pd.concat(nombres, ignore_index=True).groupby("unidad").last().reset_index()
           if nombres else pd.DataFrame(columns=["unidad", "nombre", "comuna", "region"]))
    return lic, gan, nom


def armar_perfiles() -> list[dict]:
    vias, rubros, productos, proveedores, nombres = leer_ordenes()
    lic, gan, nom = leer_licitaciones()
    print(f"  ordenes: {vias['unidad'].nunique()} unidades · licitaciones: {lic['unidad'].nunique()} unidades")

    perfiles: dict[str, dict] = {}

    def perfil(u):
        return perfiles.setdefault(u, {"unidad": u, "nombre": None, "datos": {}})

    for f in nombres.itertuples(index=False):
        # En las ordenes "organismo" suele venir como codigo: solo sirve si trae letras.
        if any(ch.isalpha() for ch in str(f.organismo)) and str(f.organismo) != "nan":
            perfil(f.unidad)["nombre"] = str(f.organismo)[:150]
    for f in nom.itertuples(index=False):
        p = perfil(f.unidad)
        p["nombre"] = str(f.nombre)[:150]
        if f.comuna:
            p["datos"]["comuna"] = str(f.comuna)[:80]
        if f.region:
            p["datos"]["region"] = str(f.region)[:80]
    for u, t in vias.groupby("unidad", sort=False):
        p = perfil(u)["datos"]
        p["monto_12m"] = int(round(t["monto"].sum()))
        p["ordenes_12m"] = int(t["ordenes"].sum())
        p["por_via"] = [{"via": VIAS.get(str(r.mecanismo), str(r.mecanismo)), "monto": int(round(r.monto))}
                        for r in t.sort_values("monto", ascending=False).itertuples(index=False) if r.monto > 0]
    for u, t in _top(rubros, "rubro", TOPE).groupby("unidad", sort=False):
        perfil(u)["datos"]["rubros"] = [{"rubro": r.rubro[:80], "monto": int(round(r.monto))} for r in t.itertuples(index=False)]
    for u, t in _top(productos, "prod", TOPE).groupby("unidad", sort=False):
        perfil(u)["datos"]["productos"] = [{"producto": r.prod, "monto": int(round(r.monto)), "veces": int(r.veces)}
                                           for r in t.itertuples(index=False)]
    for u, t in _top(proveedores, "prov", 5).groupby("unidad", sort=False):
        perfil(u)["datos"]["proveedores"] = [{"proveedor": r.prov[:90], "monto": int(round(r.monto))} for r in t.itertuples(index=False)]
    for u, t in lic.groupby("unidad", sort=False):
        of = pd.to_numeric(t["oferentes"], errors="coerce")
        perfil(u)["datos"]["licitaciones_24m"] = {
            "publicadas": int(len(t)), "adjudicadas": int(t["adjudicada"].sum()),
            "desiertas": int(t["desierta"].sum()),
            "oferentes_promedio": round(float(of.mean()), 1) if of.notna().any() else None}
    if not gan.empty:
        for u, t in _top(gan, "prov", 5).groupby("unidad", sort=False):
            perfil(u)["datos"]["ganadores"] = [{"proveedor": r.prov[:90], "ganadas": int(r.ganadas), "monto": int(round(r.monto))}
                                               for r in t.itertuples(index=False)]
    return [p for p in perfiles.values() if p["unidad"].isdigit() and p["datos"]]


def rut_norm(rut) -> str:
    return "".join(ch for ch in str(rut or "").upper() if ch.isdigit() or ch == "K")


def resumen_convenio_marco(ruts: set[str], meses: int = 12) -> list[dict]:
    """
    Pantalla «Convenio Marco» de CupidoLicita: lo que cada RUT cliente vendio por
    Convenio Marco en 12 meses, por convenio, comprador, producto y mes.
    Solo los RUT de los suscriptores: la tabla es del cliente, no un directorio.
    """
    if not ruts:
        return []
    corte = (date.today() - timedelta(days=meses * 31)).strftime("%Y-%m")
    trozos = []
    for archivo in sorted(BODEGA_OC.glob("*.parquet")):
        if archivo.stem < corte:
            continue
        hay = set(pq.read_schema(archivo).names)
        pedidas = [c for c in ["rut_proveedor", "mecanismo", "convenio_marco", "organismo", "unidad",
                               "producto", "generico", "orden", "total"] if c in hay]
        if "rut_proveedor" not in pedidas or "total" not in pedidas:
            continue
        m = pd.read_parquet(archivo, columns=pedidas)
        m["rut"] = m["rut_proveedor"].map(rut_norm)
        m = m[m["rut"].isin(ruts)]
        if "mecanismo" in m:
            m = m[m["mecanismo"].astype(str) == "CM"]
        if m.empty:
            continue
        m["mes"] = archivo.stem[:7]
        trozos.append(m)
    filas = []
    for rut in ruts:
        d = pd.concat([t[t["rut"] == rut] for t in trozos], ignore_index=True) if trozos else pd.DataFrame()
        if d.empty:
            filas.append({"rut": rut, "datos": {"monto_12m": 0, "ordenes_12m": 0}})
            continue
        d["monto"] = pd.to_numeric(d["total"], errors="coerce").fillna(0.0)
        prod = d["generico"] if "generico" in d else d.get("producto", pd.Series("", index=d.index))
        d["prod"] = _texto(prod).str.slice(0, 70).str.capitalize()

        def top(col, n=8):
            if col not in d:
                return []
            t = d.groupby(_texto(d[col]), sort=False)["monto"].agg(["sum", "size"]).sort_values("sum", ascending=False).head(n)
            return [{"nombre": str(k)[:90], "monto": int(round(v["sum"])), "lineas": int(v["size"])}
                    for k, v in t.iterrows() if str(k) not in ("", "nan")]
        por_mes = d.groupby("mes")["monto"].sum().sort_index()
        filas.append({"rut": rut, "datos": {
            "monto_12m": int(round(d["monto"].sum())),
            "ordenes_12m": int(d["orden"].nunique()) if "orden" in d else int(len(d)),
            "compradores_12m": int(d["unidad"].nunique()) if "unidad" in d else None,
            "convenios": top("convenio_marco"), "compradores": top("organismo"), "productos": top("prod"),
            "por_mes": [{"mes": k, "monto": int(round(v))} for k, v in por_mes.items()]}})
    return filas


def _pedir(metodo, ruta, cuerpo=None, extra=None):
    url = os.environ["SUPABASE_URL"].strip().rstrip("/")
    clave = os.environ["SUPABASE_SECRET_KEY"].strip()
    cab = {"apikey": clave, "Authorization": f"Bearer {clave}", "Content-Type": "application/json"}
    cab.update(extra or {})
    datos = json.dumps(cuerpo).encode("utf-8") if cuerpo is not None else None
    req = urllib.request.Request(f"{url}/rest/v1/{ruta}", data=datos, headers=cab, method=metodo)
    with urllib.request.urlopen(req, timeout=120) as r:
        return r.read()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--prueba", action="store_true")
    args = ap.parse_args()
    perfiles = armar_perfiles()
    print(f"  {len(perfiles)} perfiles de organismo")
    if args.prueba:
        for p in perfiles[:3]:
            print(json.dumps(p, ensure_ascii=False)[:800])
        return
    hoy = date.today().isoformat()
    for i in range(0, len(perfiles), TANDA):
        tanda = [dict(p, actualizado_en=hoy) for p in perfiles[i:i + TANDA]]
        _pedir("POST", "organismo_perfil?on_conflict=unidad", tanda,
               {"Prefer": "resolution=merge-duplicates,return=minimal"})
    print(f"  subidos {len(perfiles)} perfiles")

    filas = json.loads(_pedir("GET", "suscriptores?select=rut_empresa&rut_empresa=not.is.null") or b"[]")
    ruts = {r for r in (rut_norm(f.get("rut_empresa")) for f in filas) if r}
    cm = resumen_convenio_marco(ruts)
    if cm:
        _pedir("POST", "cm_resumen?on_conflict=rut", [dict(c, actualizado_en=hoy) for c in cm],
               {"Prefer": "resolution=merge-duplicates,return=minimal"})
    print(f"  Convenio Marco: {len(cm)} RUT cliente(s), " +
          ", ".join(f"{c['rut']}: ${c['datos'].get('monto_12m', 0):,}" for c in cm))


if __name__ == "__main__":
    main()
