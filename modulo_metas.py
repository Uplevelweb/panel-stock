# -*- coding: utf-8 -*-
"""
MODULO METAS — las tres puertas del mes, sacadas solas de la bodega
====================================================================

NUEVO      nunca te ha comprado, pero compra lo que tu vendes
RECOMPRA   te compro y se enfrio
CRECER     te compra hoy, pero no todo

Diseño de Serling (30-08-2026): la meta del mes son TRES CLIENTES, uno de cada
tipo. No son intercambiables y juegan en tiempos distintos —CRECER paga este
mes y se acaba, NUEVO paga el año que viene—, por eso se persiguen los tres.

LO QUE ESTE MODULO NO HACE, A PROPOSITO
---------------------------------------
No es un CRM y no le pide al vendedor que anote en que va. El resultado se mide
solo: si visitaste una unidad en septiembre, la bodega dice en octubre si te
empezo a comprar. Un embudo de seis etapas es el vendedor contandote como cree
que le va —el dato mas debil que existe, y ademas el que nadie llena—.

LA REGLA DE EXACTITUD, QUE NO SE PUEDE ROMPER
---------------------------------------------
**Los numeros con ID de producto y los numeros sin ID no se suman jamas.**

    Convenio Marco   100% de las lineas traen el ID del producto
    Licitacion         0%
    Trato Directo      0%
    Compra Agil        1%

Medido sobre 24 meses (30-08-2026). Convenio Marco es el 5% de la plata del
mercado publico y el 100% de su precision. De ahi salen las dos miradas, que
viven en columnas distintas y nunca en la misma suma:

    A QUE PUERTA GOLPEAR  ->  las seis vias. Es el mercado completo.
                              Sale de `alertador.resumen_de_ordenes`.
    QUE OFRECERLE         ->  solo Convenio Marco, producto a producto.
                              Sale de aca.

QUIEN SOY ES UN DATO, NO UN SUPUESTO
------------------------------------
`mercado_de()` recibe un conjunto de IDs y no le pregunta a nadie de donde
salen. Para un proveedor son los de su catalogo de Convenio Marco; para una
marca serian los productos de esa marca. La cuenta es la misma y por eso el
enfoque no esta amarrado en el codigo.

EL CATALOGO MANDA, NO LO VENDIDO
--------------------------------
Calcular con lo que ya vendio deja fuera lo que puede vender y nunca vendio
—de 22.628 productos del catalogo de Emergenza, solo 2.067 se han vendido— y
ademas arrastra productos que quizas ya se deshabilitaron. El catalogo se baja
del Drive cada vez, asi que un producto dado de baja desaparece solo.

Pero el catalogo dice lo que PUEDE vender, no lo que SABE vender: aparecieron
«viviendas de emergencia con instalacion» por $1.790 MM, que estan en su
catalogo y no son su negocio. Por eso cada linea de la oferta lleva `probado`,
y la decision queda en quien sabe.
"""
from datetime import date, timedelta

import pandas as pd

import alertador

# Cuanto tiene que haber en juego para que valga la pena mirarlo.
PISO_POR_GANAR = 5_000_000

# «Te compra hoy» se mide contra el ultimo TRIMESTRE y no contra el ultimo mes:
# un mes flojo no convierte a un cliente activo en uno perdido.
MESES_ACTIVO = 3

# Cortes de «que tan ganable es». Son perillas, no verdades: se calibran
# mirando la lista con alguien que conozca el mercado.
DOMINIO_CERRADO = 85      # % que el lider se lleva de ese producto en esa unidad
DOMINIO_REPARTIDO = 60    # bajo esto, nadie lo tiene tomado
UNIDADES_MARCA = 30       # vender el mismo producto en tantas unidades = marca


def _columnas(archivo) -> set:
    """Que trae ese parquet. La bodega cambia de forma cuando se le agrega algo
    y pedir una columna que no esta hace reventar la lectura entera."""
    import pyarrow.parquet as pq
    return set(pq.read_schema(archivo).names)


def mercado_de(ids: set[str], meses: int = 24, rut_propio: str = "",
               bodega=None) -> pd.DataFrame:
    """Quien compra esos productos, cuanto y a quien. Solo Convenio Marco.

    `rut_propio` trae ADEMAS sus propias ventas a esas unidades aunque el
    producto ya no este en el catalogo. Hace falta para no confundir a un
    cliente viejo con uno nuevo: si le vendio algo que despues se deshabilito,
    la relacion comercial existe igual y esa unidad NO es NUEVO. La columna
    `en_catalogo` distingue las dos cosas y evita que esas ventas inflen el
    mercado. Sin esto, diez unidades salian mal clasificadas.

    Se lee mes a mes y se resume al vuelo, como `alertador.resumen_de_ordenes`:
    la bodega entera son millones de lineas y el techo de Streamlit son ~1.000
    MB. Filtrando a Convenio Marco (16% de las lineas) y a los IDs pedidos, de
    un mes quedan unos pocos miles de filas.

    Devuelve una fila por (unidad, producto, proveedor).
    """
    carpeta = bodega or alertador.BODEGA_OC
    vacio = pd.DataFrame(columns=["unidad", "idp", "rutp", "proveedor",
                                  "total", "mes", "en_catalogo"])
    if not ids or not carpeta.exists():
        return vacio

    corte = (date.today() - timedelta(days=meses * 31)).strftime("%Y-%m")
    trozos: list[pd.DataFrame] = []
    for archivo in sorted(carpeta.glob("*.parquet")):
        if archivo.stem < corte:
            continue
        try:
            hay = _columnas(archivo)
            pedidas = [c for c in ("unidad", "id_producto", "rut_proveedor",
                                   "proveedor", "total", "fecha", "mecanismo",
                                   "convenio") if c in hay]
            if "id_producto" not in pedidas or "unidad" not in pedidas:
                continue
            mes = pd.read_parquet(archivo, columns=pedidas)
        except Exception:
            continue

        # Convenio Marco. Los archivos viejos no traen `mecanismo`: se saca del
        # sufijo del convenio, que es de donde sale igual («CM26» -> «CM»).
        if "mecanismo" in mes.columns:
            via = mes["mecanismo"].astype(str).str[:2]
        elif "convenio" in mes.columns:
            via = mes["convenio"].astype(str).str[:2]
        else:
            via = pd.Series("CM", index=mes.index)
        mes = mes[via.str.upper() == "CM"]
        if mes.empty:
            del mes
            continue

        mes["idp"] = mes["id_producto"].astype(str).str.strip()
        mes["rutp"] = mes["rut_proveedor"].astype(str).map(alertador.solo_digitos_rut)
        mes["en_catalogo"] = mes["idp"].isin(ids)
        mes = mes[mes["en_catalogo"] | (mes["rutp"] == rut_propio)]
        if mes.empty:
            del mes
            continue

        mes["mes"] = (mes["fecha"].astype(str).str[:7] if "fecha" in mes.columns
                      else archivo.stem)
        trozos.append(
            mes.groupby(["unidad", "idp", "rutp", "proveedor", "mes",
                         "en_catalogo"], as_index=False)["total"].sum())
        del mes, via

    if not trozos:
        return vacio
    return pd.concat(trozos, ignore_index=True)


def _tipo(le_vendo: float, ultimo: str, corte: str) -> str:
    if not le_vendo:
        return "NUEVO"
    return "CRECER" if ultimo >= corte else "RECOMPRA"


def tres_metas(mercado: pd.DataFrame, rut: str,
               piso: float = PISO_POR_GANAR) -> pd.DataFrame:
    """Una fila por unidad compradora, con su tipo y lo que hay por ganar.

    `por_ganar` es un TECHO, no un pronostico: es lo que se llevan otros
    suponiendo que se les pudiera quitar todo. Sirve para ordenar, no para
    prometer una cifra.
    """
    columnas = ["unidad", "tipo", "compra", "le_vendo", "por_ganar",
                "mi_parte", "proveedores", "ultimo", "relacion"]
    if mercado.empty or not rut:
        return pd.DataFrame(columns=columnas)

    meses = sorted(mercado["mes"].dropna().unique())
    corte = meses[-MESES_ACTIVO] if len(meses) >= MESES_ACTIVO else meses[0]
    dentro = (mercado["en_catalogo"] if "en_catalogo" in mercado.columns
              else pd.Series(True, index=mercado.index))

    # LA RELACION se mide con TODAS sus ventas: si le vendio algo que despues
    # se deshabilito, esa unidad ya lo conoce y no es NUEVO.
    mio = mercado[mercado["rutp"] == rut]
    suyo = mio.groupby("unidad").agg(ultimo=("mes", "max"),
                                     relacion=("total", "sum"))

    # LO QUE HAY POR GANAR se mide solo con el catalogo: lo que hoy puede
    # vender. Mezclarlo con lo de arriba inflaria el mercado con productos que
    # ya no ofrece.
    vivo = mercado[dentro]
    todo = vivo.groupby("unidad").agg(compra=("total", "sum"),
                                      proveedores=("rutp", "nunique"))
    suyo_vivo = (vivo[vivo["rutp"] == rut].groupby("unidad")["total"]
                 .sum().rename("le_vendo"))

    u = todo.join(suyo, how="left").join(suyo_vivo, how="left")
    u["le_vendo"] = u["le_vendo"].fillna(0.0)
    u["relacion"] = u["relacion"].fillna(0.0)
    u["ultimo"] = u["ultimo"].fillna("")
    u["por_ganar"] = u["compra"] - u["le_vendo"]
    u["mi_parte"] = (u["le_vendo"] / u["compra"] * 100).round(1)
    u["tipo"] = [_tipo(v, m, corte) for v, m in zip(u["relacion"], u["ultimo"])]

    u = u[u["por_ganar"] >= piso].reset_index()
    orden = {"CRECER": 0, "RECOMPRA": 1, "NUEVO": 2}
    u["_o"] = u["tipo"].map(orden)
    u = u.sort_values(["_o", "por_ganar"], ascending=[True, False])
    return u[columnas]


def que_tan_ganable(mercado: pd.DataFrame, rut: str) -> pd.DataFrame:
    """Por cada (unidad, producto): quien lo tiene hoy y si se le puede pelear.

    LO PIDIO SERLING, Y CAMBIA EL ORDEN DE TODO. Ordenar por cuanta plata hay
    manda al vendedor a pelear contra la marca en su propio producto. Contra
    Macro Food no se gana por precio; se gana por servicio, y solo donde ya
    tienes la puerta abierta.

    Un proveedor que vende el MISMO producto en muchas unidades del pais es la
    marca o el importador; uno que lo vende en tres es un distribuidor igual
    que ella, y a ese si se le pelea.

    Ojo con el dato que esto destapo: Macro Food se queda con el 36% de su
    propia marca en el mercado publico. El otro 64% lo mueven noventa
    distribuidores. La pelea casi nunca es contra la marca.
    """
    columnas = ["unidad", "idp", "proveedor", "dominio", "amplitud",
                "pie_adentro", "ganable", "total_par"]
    if mercado.empty:
        return pd.DataFrame(columns=columnas)

    if "en_catalogo" in mercado.columns:
        mercado = mercado[mercado["en_catalogo"]]
    # En cuantas unidades distintas vende cada proveedor ese mismo producto.
    amplitud = (mercado.groupby(["idp", "rutp"])["unidad"].nunique()
                .rename("amplitud"))

    par = mercado.groupby(["unidad", "idp", "rutp", "proveedor"],
                          as_index=False)["total"].sum()
    total = par.groupby(["unidad", "idp"])["total"].sum().rename("total_par")

    lider = (par.sort_values("total", ascending=False)
                .drop_duplicates(["unidad", "idp"])
                .join(total, on=["unidad", "idp"])
                .join(amplitud, on=["idp", "rutp"]))
    lider["dominio"] = (lider["total"] / lider["total_par"] * 100).round(0)

    # Donde ya le vende ALGO a esa unidad tiene con quien hablar, y ahi el
    # servicio es una palanca de verdad.
    adentro = set(mercado.loc[mercado["rutp"] == rut, "unidad"])
    lider["pie_adentro"] = lider["unidad"].isin(adentro)
    lider = lider[lider["rutp"] != rut]

    def como(f):
        if f["pie_adentro"] and f["dominio"] < DOMINIO_CERRADO:
            return "SERVICIO"
        if f["amplitud"] >= UNIDADES_MARCA and f["dominio"] >= 70:
            return "DURO"
        if f["dominio"] < DOMINIO_REPARTIDO:
            return "ABIERTO"
        return "PELEA"

    lider["ganable"] = lider.apply(como, axis=1)
    return lider[columnas]


def oferta_para(mercado: pd.DataFrame, rut: str, unidades: set,
                catalogo: dict[str, str] | None = None,
                vendidos: set[str] | None = None) -> pd.DataFrame:
    """Producto a producto: que le compra a otros y quien se lo lleva.

    Es «el calculo de oferta para clientes actuales» que pidio Serling, y es la
    misma consulta dada vuelta: en vez de mirar la unidad, se miran sus lineas.
    """
    columnas = ["unidad", "idp", "rubro", "probado", "compra", "le_vendo",
                "por_ganar", "proveedor", "ganable"]
    if mercado.empty or not unidades:
        return pd.DataFrame(columns=columnas)

    dentro = (mercado["en_catalogo"] if "en_catalogo" in mercado.columns
              else pd.Series(True, index=mercado.index))
    det = mercado[dentro & mercado["unidad"].isin(unidades)]
    compra = det.groupby(["unidad", "idp"], as_index=False)["total"].sum() \
                .rename(columns={"total": "compra"})
    mio = (det[det["rutp"] == rut].groupby(["unidad", "idp"], as_index=False)
           ["total"].sum().rename(columns={"total": "le_vendo"}))

    o = compra.merge(mio, on=["unidad", "idp"], how="left")
    o["le_vendo"] = o["le_vendo"].fillna(0.0)
    o["por_ganar"] = o["compra"] - o["le_vendo"]
    o = o[o["por_ganar"] > 0]

    gan = que_tan_ganable(det, rut)
    o = o.merge(gan[["unidad", "idp", "proveedor", "ganable"]],
                on=["unidad", "idp"], how="left")

    o["rubro"] = o["idp"].map(catalogo or {})
    # Lo probado y lo posible no son lo mismo: el catalogo dice lo que PUEDE
    # vender y esto dice lo que YA despacho alguna vez. Se marca y ella decide.
    o["probado"] = o["idp"].isin(vendidos or set())
    return o.sort_values("por_ganar", ascending=False)[columnas]


def ids_vendidos(rut: str, meses: int = 24, bodega=None) -> set[str]:
    """Los IDs de Convenio Marco que ese RUT ha vendido.

    PARA EL CORREO DIARIO, que corre en GitHub Actions con solo pandas y
    pyarrow instalados: ahi no se puede leer el catalogo del Drive —hace falta
    openpyxl, y el lector vive en `app.py`, que arrastra streamlit—.

    Y esta bien que sea asi: el correo manda a golpear PUERTAS, y una puerta no
    se echa a perder porque un producto se haya deshabilitado. La oferta
    producto a producto, que si depende del catalogo vigente, vive en el panel.

    Se leen tres columnas angostas, mes a mes.
    """
    carpeta = bodega or alertador.BODEGA_OC
    if not rut or not carpeta.exists():
        return set()

    corte = (date.today() - timedelta(days=meses * 31)).strftime("%Y-%m")
    salida: set[str] = set()
    for archivo in sorted(carpeta.glob("*.parquet")):
        if archivo.stem < corte:
            continue
        try:
            hay = _columnas(archivo)
            pedidas = [c for c in ("id_producto", "rut_proveedor", "mecanismo",
                                   "convenio") if c in hay]
            if "id_producto" not in pedidas or "rut_proveedor" not in pedidas:
                continue
            mes = pd.read_parquet(archivo, columns=pedidas)
        except Exception:
            continue
        mias = mes[mes["rut_proveedor"].astype(str).map(alertador.solo_digitos_rut) == rut]
        if not mias.empty:
            idp = mias["id_producto"].astype(str).str.strip()
            salida |= set(idp[idp.str.isdigit()])
        del mes
    return salida


def nombres_de_unidades(bodega=None) -> pd.DataFrame:
    """Codigo de unidad -> como se llama y donde queda.

    El correo no puede decir «unidad 1411»: tiene que decir «Gendarmeria,
    Puente Alto». Sale del mismo parquet que arma el bodeguero.
    """
    carpeta = bodega or alertador.BODEGA_OC.parent
    archivo = carpeta / "unidades.parquet"
    if not archivo.exists():
        return pd.DataFrame()
    try:
        u = pd.read_parquet(archivo).drop_duplicates("codigo_unidad")
    except Exception:
        return pd.DataFrame()

    # El parquet viene de un CSV en latin-1 y los acentos llegan al reves.
    def arreglar(s):
        try:
            return str(s).encode("latin-1").decode("utf-8")
        except Exception:
            return str(s)

    for col in ("nombre_unidad", "nombre_organismo", "comuna", "region"):
        if col in u.columns:
            u[col] = u[col].map(arreglar)
    return u.set_index("codigo_unidad")
