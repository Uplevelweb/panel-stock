"""
LICITADOR — llena la bodega de licitaciones desde los datos abiertos de ChileCompra
===================================================================================

Hermano de `bodeguero.py`. Misma mecanica: un zip por mes, se abre en memoria, se
reparte a parquet mensual. Lo que cambia es la fuente y el grano.

  bodeguero.py  ->  oc-da/AAAA-M.zip   ->  bodega/detalle/AAAA-MM.parquet
  licitador.py  ->  lic-da/AAAA-M.zip  ->  bodega/licitaciones/AAAA-MM.parquet

TRES COSAS QUE SE VERIFICARON EN EL ARCHIVO REAL Y QUE HAY QUE TENER PRESENTES:

1. EL ARCHIVO SOLO TRAE LICITACIONES YA CERRADAS.
   Revisado el 26-08-2026 sobre `lic-da/2026-8.zip`: 2.799 licitaciones, ninguna
   en estado «Publicada», y la fecha de cierre mas nueva era el 25-08 (ayer).
   Cero licitaciones con plazo abierto.
   Es decir: esta bodega es el HISTORIAL de licitaciones, no el radar de las que
   estan recibiendo ofertas. Para avisar de una licitacion a tiempo hay que
   preguntarle a la API de Mercado Publico por las activas. Este archivo sirve
   para saber quien licita que, cada cuanto, y quien se lo gana.

2. EL ARCHIVO YA VIENE ORDENADO POR FECHA DE PUBLICACION.
   En oc-da una orden de enero podia haberse creado en diciembre, y por eso el
   bodeguero tiene que repartir las filas entre meses. Aca no: las 130.495 filas
   del archivo de julio se publicaron las 130.495 en julio. Igual se reparte por
   fecha de publicacion, porque cuesta lo mismo y protege si algun mes se sale.

3. EL CSV TRAE UNA FILA POR LICITACION x LINEA x OFERTA, Y ASI SE GUARDA.
   El de julio: 130.495 filas para solo 7.784 licitaciones. Cada linea de compra
   se repite una vez por cada empresa que oferto.
   Se guarda con ese grano, no resumido, para conservar QUIEN OFERTO y QUIEN
   GANO cada linea. Cuesta poco: 49 MB contra 40 MB a 20 meses, porque parquet
   comprime las columnas que se repiten. Separarlo en dos archivos salia peor
   (80 MB), porque habria que repetir las llaves en los dos.
   El RUT del proveedor viene con el MISMO formato que en la bodega de ordenes
   de compra («77.700.813-7»), asi que se cruza directo, sin normalizar: se
   puede seguir a un proveedor desde que gana una licitacion hasta las ordenes
   de compra que le emiten despues.

Y una trampa heredada del bodeguero, que aca es igual: la unidad compradora es
el PREFIJO DEL CODIGO de la licitacion, no la columna `CodigoUnidad` del archivo.
Son dos numeros distintos. Sobre el archivo de julio, el prefijo cruza con 1.421
unidades que tienen orden de compra en la bodega; `CodigoUnidad` solo con 811.
El prefijo es el que usa el resto del sistema.
"""
import argparse
import csv, io, json, sys, time, urllib.request, zipfile
from datetime import date
from pathlib import Path

import pandas as pd

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

BASE = "https://transparenciachc.blob.core.windows.net/lic-da/"
AQUI = Path(__file__).parent
BODEGA = AQUI / "bodega" / "licitaciones"
DESCARGAS = AQUI / "descargas_temporales"
PRIMER_MES = (2025, 1)

# Las descripciones de bases traen parrafos enteros en una sola celda y pasan
# holgadamente el limite por defecto de csv (128 KB), que corta la lectura con
# «field larger than field limit».
csv.field_size_limit(10 ** 9)

COLUMNAS = ["dia", "fecha", "codigo", "nombre", "descripcion", "estado", "tipo",
            "unidad", "nombre_unidad", "organismo", "nombre_organismo",
            "region", "comuna", "fecha_publicacion", "fecha_cierre",
            "fecha_adjudicacion", "monto_estimado", "correlativo",
            "codigo_item", "codigo_onu", "rubro1", "rubro2", "rubro3",
            "producto", "linea", "cantidad", "unidad_medida", "link",
            # Quien oferto y quien gano esta linea.
            "rut_proveedor", "proveedor", "n_oferentes", "estado_oferta",
            "seleccionada", "cantidad_ofertada", "monto_unitario",
            "total_ofertado", "cantidad_adjudicada", "monto_adjudicado"]

NUMERICAS = ("monto_estimado", "cantidad", "n_oferentes", "cantidad_ofertada",
             "monto_unitario", "total_ofertado", "cantidad_adjudicada",
             "monto_adjudicado")

# Una oferta es unica por la linea mas el proveedor que la hizo. Sin el RUT la
# llave colapsaria todas las ofertas de una linea en una sola fila y se perderia
# justo lo que interesa: contra quien se compite y quien gana.
LLAVE = ["codigo", "correlativo", "codigo_item", "rut_proveedor"]


def meses_hasta_hoy():
    """(2025,1), (2025,2)... hasta el mes en curso."""
    hoy = date.today()
    año, mes = PRIMER_MES
    while (año, mes) <= (hoy.year, hoy.month):
        yield año, mes
        mes += 1
        if mes > 12:
            año, mes = año + 1, 1


def bajar(año: int, mes: int) -> Path | None:
    """Baja el zip del mes si no esta ya en disco."""
    DESCARGAS.mkdir(exist_ok=True)
    destino = DESCARGAS / f"lic-{año}-{mes}.zip"
    if destino.exists():
        return destino
    url = f"{BASE}{año}-{mes}.zip"
    try:
        peticion = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(peticion, timeout=900) as respuesta:
            destino.write_bytes(respuesta.read())
        return destino
    except Exception as error:
        print(f"    no se pudo bajar {año}-{mes}: {type(error).__name__}", flush=True)
        return None


def filas_de_licitaciones(archivo: Path):
    """Las lineas del archivo, ya en el formato de la bodega."""
    z = zipfile.ZipFile(archivo)
    with z.open(z.namelist()[0]) as bruto:
        texto = io.TextIOWrapper(bruto, encoding="latin-1", newline="")
        for fila in csv.DictReader(texto, delimiter=";"):
            codigo = str(fila.get("CodigoExterno") or "").strip()
            tramos = codigo.split("-")
            if len(tramos) < 3:
                continue
            publicacion = str(fila.get("FechaPublicacion") or "")[:10]
            # La fecha se valida entera, no solo el largo y el año. Unas 35
            # filas de cada 2 millones traen una comilla sin cerrar y el lector
            # de csv corre las columnas: aparecen estados que dicen «Castro» y
            # fechas que dicen «RFB_TIME_P». Con la validacion floja se colaban
            # y creaban parquet basura («202603-.parquet»). Ademas ChileCompra
            # usa 1900-01-01 como «sin fecha», que no es un mes de la bodega.
            try:
                if date.fromisoformat(publicacion).year < 2000:
                    continue
            except ValueError:
                continue
            yield {
                "dia": publicacion, "fecha": publicacion,
                "codigo": codigo,
                "nombre": str(fila.get("Nombre") or "").strip(),
                "descripcion": str(fila.get("Descripcion") or "").strip(),
                "estado": str(fila.get("Estado") or "").strip(),
                # LE, LP, L1, LR... LR son las licitaciones de convenio marco.
                "tipo": str(fila.get("Tipo") or "").strip(),
                # El prefijo del codigo, no CodigoUnidad. Ver el encabezado.
                "unidad": tramos[0].strip(),
                "nombre_unidad": str(fila.get("NombreUnidad") or "").strip(),
                "organismo": str(fila.get("CodigoOrganismo") or "").strip(),
                "nombre_organismo": str(fila.get("NombreOrganismo") or "").strip(),
                # El archivo trae region y comuna en cada fila, asi que la
                # geografia no depende de que la unidad este en el catalogo.
                "region": str(fila.get("RegionUnidad") or "").strip(),
                "comuna": str(fila.get("ComunaUnidad") or "").strip(),
                "fecha_publicacion": publicacion,
                "fecha_cierre": str(fila.get("FechaCierre") or "")[:10],
                "fecha_adjudicacion": str(fila.get("FechaAdjudicacion") or "")[:10],
                # Viene en notacion cientifica («6e+07») y a veces como «NA».
                "monto_estimado": fila.get("MontoEstimado"),
                "correlativo": str(fila.get("Correlativo") or "").strip(),
                "codigo_item": str(fila.get("Codigoitem") or "").strip(),
                "codigo_onu": str(fila.get("CodigoProductoONU") or "").strip(),
                "rubro1": str(fila.get("Rubro1") or "").strip(),
                "rubro2": str(fila.get("Rubro2") or "").strip(),
                "rubro3": str(fila.get("Rubro3") or "").strip(),
                # El nombre de esta columna viene con la errata en el origen.
                "producto": str(fila.get("Nombre producto genrico") or "").strip(),
                "linea": str(fila.get("Nombre linea Adquisicion") or "").strip(),
                "cantidad": fila.get("Cantidad"),
                "unidad_medida": str(fila.get("UnidadMedida") or "").strip(),
                "link": str(fila.get("Link") or "").strip(),
                # Mismo formato que `rut_proveedor` de la bodega de ordenes de
                # compra («77.700.813-7»): cruza sin tocarlo.
                "rut_proveedor": str(fila.get("RutProveedor") or "").strip(),
                "proveedor": str(fila.get("NombreProveedor") or "").strip(),
                "n_oferentes": fila.get("NumeroOferentes"),
                "estado_oferta": str(fila.get("Estado Oferta") or "").strip(),
                # «Seleccionada» / «No Seleccionada»: quien se llevo la linea.
                "seleccionada": str(fila.get("Oferta seleccionada") or "").strip(),
                "cantidad_ofertada": fila.get("Cantidad Ofertada"),
                "monto_unitario": fila.get("MontoUnitarioOferta"),
                "total_ofertado": fila.get("Valor Total Ofertado"),
                "cantidad_adjudicada": fila.get("CantidadAdjudicada"),
                "monto_adjudicado": fila.get("MontoLineaAdjudica"),
            }


def guardar(por_mes: dict[str, list[dict]]) -> None:
    """Escribe cada mes, mezclando con lo que ya hubiera y sin repetir lineas."""
    BODEGA.mkdir(parents=True, exist_ok=True)
    for mes, filas in por_mes.items():
        nuevas = pd.DataFrame(filas, columns=COLUMNAS)
        for c in NUMERICAS:
            # OJO: el archivo mezcla dos formatos de numero en la MISMA columna.
            # `MontoEstimado` viene a veces «100000000», a veces «6e+07» y en el
            # 27% de las filas «3,5e+07», con COMA DECIMAL. Sin cambiar la coma
            # por punto, `to_numeric` devuelve nulo y se pierde uno de cada
            # cuatro montos, justo el dato que mas pesa en SCORE_POTENCIAL.
            # Se comprobo que ningun valor trae mas de una coma, asi que la coma
            # siempre es decimal y nunca separador de miles. `Cantidad` tiene el
            # mismo formato, aunque ahi son pocas filas.
            texto = nuevas[c].astype("string").str.replace(",", ".", regex=False)
            nuevas[c] = pd.to_numeric(texto, errors="coerce")
        archivo = BODEGA / f"{mes}.parquet"
        if archivo.exists():
            nuevas = pd.concat([pd.read_parquet(archivo), nuevas], ignore_index=True)
        # `keep="last"` a proposito, al reves del bodeguero: una licitacion
        # cambia de estado con el tiempo (Cerrada -> Adjudicada -> Desierta), y
        # lo que acaba de bajarse va al final del concat. Quedarse con la
        # primera dejaria el estado viejo congelado para siempre.
        nuevas = nuevas.drop_duplicates(subset=LLAVE, keep="last")
        nuevas.to_parquet(archivo, index=False, compression="zstd")


def anotar_cobertura() -> str:
    """Deja anotado en `bodega/estado.json` hasta que dia llega la bodega.

    Se escribe la clave «licitaciones» sin tocar el resto del archivo: la clave
    «detalle» la maneja el bodeguero, que corre a otra hora, y los dos guardan
    en el mismo json.
    """
    ultimo = ""
    for archivo in BODEGA.glob("*.parquet"):
        dias = pd.read_parquet(archivo, columns=["dia"])["dia"].dropna()
        if len(dias):
            ultimo = max(ultimo, str(dias.max())[:10])
    if len(ultimo) != 10:
        return ""

    archivo = BODEGA.parent / "estado.json"
    estado = {}
    if archivo.exists():
        try:
            estado = json.loads(archivo.read_text(encoding="utf-8"))
        except Exception:
            estado = {}
    estado["licitaciones"] = {
        "desde": f"{PRIMER_MES[0]}-{PRIMER_MES[1]:02d}-01",
        "hasta": ultimo,
        "fuente": "datos abiertos ChileCompra (lic-da)",
        "ojo": "solo licitaciones ya cerradas; no sirve para avisar de plazos abiertos",
    }
    estado["actualizado"] = time.strftime("%Y-%m-%dT%H:%M:%S")
    archivo.write_text(json.dumps(estado, indent=1, ensure_ascii=False), encoding="utf-8")
    return ultimo


def completar_comunas() -> str:
    """Rellena la comuna y la region que le faltan al catalogo de unidades.

    `bodega/unidades.parquet` lo escribia el bodeguero viejo, que ya no corre.
    380 de sus 4.298 unidades quedaron sin comuna NI region porque la API de
    ordenes de compra no las informa, y sin comuna no se pueden armar rutas de
    visita. Los datos abiertos de licitaciones si las traen —`ComunaUnidad` y
    `RegionUnidad` vienen en cada fila—, asi que se rellenan desde aca: gratis,
    sin una sola consulta extra, y al dia porque esto corre todas las mañanas.

    Medido el 27-08-2026: de las 326 unidades sin comuna que ademas compran,
    se rellenan 243, que son $38.248 M de los $43.286 M en juego. Las 83 que
    quedan ($5.038 M) nunca han licitado, solo compran por otras vias.

    Solo se rellena lo que esta vacio. Lo que el catalogo ya sabe no se toca.
    """
    archivo = BODEGA.parent / "unidades.parquet"
    if not archivo.exists():
        return "no hay catalogo de unidades que completar"

    unidades = pd.read_parquet(archivo)
    if not {"codigo_unidad", "comuna", "region"} <= set(unidades.columns):
        return "el catalogo de unidades no tiene las columnas esperadas"

    conocidas = []
    for parquet in sorted(BODEGA.glob("*.parquet")):
        # Tres columnas y no mas: la bodega entera no cabe comoda en memoria.
        trozo = pd.read_parquet(parquet, columns=["unidad", "comuna", "region"])
        tiene = trozo["comuna"].notna() & (trozo["comuna"].astype(str).str.strip() != "")
        conocidas.append(trozo[tiene])
    if not conocidas:
        return "la bodega de licitaciones esta vacia"

    mapa = pd.concat(conocidas, ignore_index=True)
    mapa["unidad"] = mapa["unidad"].astype(str).str.strip()
    # `keep="last"`: si una unidad se muda de direccion, manda la licitacion
    # mas nueva, igual que con el estado en `guardar`.
    mapa = mapa.drop_duplicates(subset="unidad", keep="last").set_index("unidad")

    codigos = unidades["codigo_unidad"].astype(str).str.strip()
    rellenadas = 0
    for columna in ("comuna", "region"):
        vacias = (unidades[columna].isna()
                  | (unidades[columna].astype(str).str.strip() == ""))
        traido = codigos.map(mapa[columna])
        aplicar = vacias & traido.notna()
        if columna == "comuna":
            rellenadas = int(aplicar.sum())
        unidades.loc[aplicar, columna] = traido[aplicar]

    if not rellenadas:
        return "no habia comunas que rellenar"

    unidades.to_parquet(archivo, index=False, compression="zstd")
    quedan = int((unidades["comuna"].isna()
                  | (unidades["comuna"].astype(str).str.strip() == "")).sum())
    return f"{rellenadas} unidades recuperaron comuna · quedan {quedan} sin ella"


def meses_por_procesar(completo: bool) -> list[tuple[int, int]]:
    """Que meses bajar en esta corrida.

    La primera vez hay que bajarlos todos. Despues basta el mes en curso y el
    anterior, igual que en el bodeguero.

    OJO: una licitacion publicada en marzo puede adjudicarse en septiembre, y
    con el refresco de dos meses su estado queda congelado en «Cerrada». Si
    interesa el estado final de la historia completa, hay que correr
    `--completo` de vez en cuando.
    """
    todos = list(meses_hasta_hoy())
    if completo or not any(BODEGA.glob("*.parquet")):
        return todos
    return todos[-2:]


def main() -> None:
    argumentos = argparse.ArgumentParser(description="Llena la bodega de licitaciones")
    argumentos.add_argument("--completo", action="store_true",
                            help="rehacer toda la historia, no solo los últimos meses")
    opciones = argumentos.parse_args()

    t0 = time.time()
    total = 0
    procesados = []
    pendientes = meses_por_procesar(opciones.completo)
    if opciones.completo:
        # Se vacia ANTES de bajar: rehacer la historia sobre los parquet que ya
        # estaban solo sirve para acumular filas repetidas.
        for parquet_viejo in BODEGA.glob("*.parquet"):
            parquet_viejo.unlink()
    print(f"LICITADOR · {len(pendientes)} mes/es por procesar\n", flush=True)
    for año, mes in pendientes:
        inicio = time.time()
        archivo = bajar(año, mes)
        if archivo is None:
            if opciones.completo:
                raise SystemExit(f"Se detiene: falto el archivo de {año}-{mes:02d}. "
                                 "Media historia es peor que la de ayer completa.")
            continue
        por_mes: dict[str, list[dict]] = {}
        n = 0
        for fila in filas_de_licitaciones(archivo):
            por_mes.setdefault(fila["fecha"][:7], []).append(fila)
            n += 1
        guardar(por_mes)
        total += n
        procesados.append(f"{año}-{mes:02d}")
        print(f"  {año}-{mes:02d}: {n:>7,} líneas de licitación · "
              f"{archivo.stat().st_size/1e6:.0f} MB · {time.time()-inicio:.0f}s", flush=True)

    hasta_donde = anotar_cobertura()
    print(f"  la bodega de licitaciones llega hasta: {hasta_donde or 'sin datos'}")
    print(f"  comunas del catalogo de unidades: {completar_comunas()}")

    for zip_viejo in DESCARGAS.glob("lic-*.zip"):
        zip_viejo.unlink()          # pesan decenas de MB, no se guardan

    licitaciones = 0
    for parquet in BODEGA.glob("*.parquet"):
        licitaciones += pd.read_parquet(parquet, columns=["codigo"])["codigo"].nunique()
    peso = sum(p.stat().st_size for p in BODEGA.glob("*.parquet"))

    print()
    print(f"{'='*60}")
    print(f"  meses procesados : {len(procesados)}")
    print(f"  líneas guardadas : {total:,}")
    print(f"  licitaciones     : {licitaciones:,}")
    print(f"  peso de la bodega: {peso/1e6:.1f} MB")
    print(f"  tiempo total     : {(time.time()-t0)/60:.1f} minutos")


if __name__ == "__main__":
    main()
