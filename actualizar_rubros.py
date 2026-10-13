"""Territorio · cifras de la sección «¿Cuánto se publica en lo tuyo?»
Lee la bodega (bodega/licitaciones y bodega/detalle) y escribe rubros.json con:
  - licitaciones publicadas en lo que va del año, por rubro
  - compras ágiles (órdenes de compra emitidas) en lo que va del año, por rubro
Uso:  python actualizar_rubros.py --bodega bodega --salida rubros.json
Pensado para correr cada día después de que se llena la bodega.
"""
import argparse, glob, json, os, re, sys, unicodedata
from datetime import date, datetime
import pandas as pd

def norm(t):
    t = unicodedata.normalize("NFD", str(t).strip().upper())
    return "".join(c for c in t if unicodedata.category(c) != "Mn")

def rubro_valido(t):
    return 3 < len(t) < 110 and not re.search(r'[\d"]', t)

# nombre corto para mostrar y palabra con la que se parte la alerta (clave = rubro normalizado)
NOMBRES = {
 "EQUIPAMIENTO Y SUMINISTROS MEDICOS": ("Insumos y equipamiento médico", "insumos médicos"),
 "SERVICIOS DE CONSTRUCCION Y MANTENIMIENTO": ("Construcción y mantenimiento", "construcción"),
 "SERVICIOS PROFESIONALES, ADMINISTRATIVOS Y CONSULTORIAS DE GESTION EMPRESARIAL": ("Servicios profesionales y consultorías", "consultoría"),
 "MEDICAMENTOS Y PRODUCTOS FARMACEUTICOS": ("Medicamentos y farmacéuticos", "medicamentos"),
 "TECNOLOGIAS DE LA INFORMACION, TELECOMUNICACIONES Y RADIODIFUSION": ("Tecnología y telecomunicaciones", "tecnología"),
 "SERVICIOS DE TRANSPORTE, ALMACENAJE Y CORREO": ("Transporte, almacenaje y correo", "transporte"),
 "ARTICULOS PARA ESTRUCTURAS, OBRAS Y CONSTRUCCIONES": ("Materiales para obras", "materiales de construcción"),
 "EQUIPAMIENTO PARA LABORATORIOS": ("Equipamiento para laboratorios", "laboratorio"),
 "SALUD, SERVICIOS SANITARIOS Y ALIMENTACION": ("Salud, servicios sanitarios y alimentación", "alimentación"),
 "SERVICIOS DE LIMPIEZA INDUSTRIAL": ("Limpieza industrial", "limpieza"),
 "VEHICULOS Y EQUIPAMIENTO EN GENERAL": ("Vehículos y equipamiento", "vehículos"),
 "ROPA, MALETAS Y PRODUCTOS DE ASEO PERSONAL": ("Ropa y aseo personal", "ropa"),
 "EQUIPOS, ACCESORIOS Y SUMINISTROS DE OFICINA": ("Oficina y papelería", "papelería"),
 "ALIMENTOS, BEBIDAS Y TABACO": ("Alimentos y bebidas", "alimentos"),
 "PRODUCTOS DE PAPEL": ("Productos de papel", "papel"),
}

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--bodega", default="bodega"); ap.add_argument("--salida", default="rubros.json")
    ap.add_argument("--anio", type=int, default=date.today().year); ap.add_argument("--top", type=int, default=12)
    a = ap.parse_args(); y = a.anio
    # --- licitaciones
    L = []
    for f in sorted(glob.glob(os.path.join(a.bodega, "licitaciones", f"{y}-*.parquet"))):
        L.append(pd.read_parquet(f, columns=["codigo", "fecha_publicacion", "rubro1"]))
    L = pd.concat(L); L["fp"] = pd.to_datetime(L.fecha_publicacion, errors="coerce")
    L = L[L.fp.dt.year == y]; L["r"] = L.rubro1.map(norm)
    # --- compras ágiles (órdenes de compra, mecanismo AG)
    A = []
    for f in sorted(glob.glob(os.path.join(a.bodega, "detalle", f"{y}-*.parquet"))):
        d = pd.read_parquet(f, columns=["orden", "mecanismo", "rubro1", "dia"]); A.append(d[d.mecanismo == "AG"])
    A = pd.concat(A); A["d"] = pd.to_datetime(A.dia, errors="coerce"); A["r"] = A.rubro1.map(norm)
    # --- corte común: el último día que tienen ambas fuentes
    hasta = min(L.fp.max(), A.d.max()).normalize()
    L = L[L.fp <= hasta + pd.Timedelta(days=1)]; A = A[A.d <= hasta + pd.Timedelta(days=1)]
    L = L[L.r.map(rubro_valido)]; A = A[A.r.map(rubro_valido)]
    cl = L.drop_duplicates(["codigo", "r"]).groupby("r").size()
    ca = A.drop_duplicates(["orden", "r"]).groupby("r").size()
    # un rubro sucio aparece muy pocas veces: se descarta lo que no llega a 10 en ninguna vía
    todos = sorted(set(cl.index) | set(ca.index), key=lambda r: -(cl.get(r, 0) + ca.get(r, 0)))
    todos = [r for r in todos if cl.get(r, 0) + ca.get(r, 0) >= 10]
    filas = []
    for r in todos:
        n, k = NOMBRES.get(r, (r.capitalize(), r.split(",")[0].split(" Y ")[0].lower()))
        filas.append({"rubro": n, "palabra": k, "lic": int(cl.get(r, 0)), "ag": int(ca.get(r, 0))})
    top = sorted(filas, key=lambda f: -f["lic"])[: a.top]
    out = {
        "actualizado": datetime.now().strftime("%Y-%m-%d"),
        "desde": f"{y}-01-01", "hasta": hasta.strftime("%Y-%m-%d"),
        "total_lic": int(L.codigo.nunique()), "total_ag": int(A.orden.nunique()), "rubros_n": len(filas),
        "rubros": top,
    }
    with open(a.salida, "w", encoding="utf-8") as fh: json.dump(out, fh, ensure_ascii=False, indent=1)
    print(json.dumps({k: v for k, v in out.items() if k != "rubros"}, ensure_ascii=False)); print(top[:3])

if __name__ == "__main__":
    main()
