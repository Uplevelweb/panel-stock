"""
CEREBRO — sugerencia inteligente de palabras clave para las alertas
=====================================================================

Hermano de `licitador.py` en el espiritu: un script que lee la bodega y deja
un resultado precalculado en `bodega/`, para que la app nunca tenga que
recorrer el corpus completo en caliente.

QUE PROBLEMA RESUELVE
----------------------
Hoy, en el formulario de Alertas (`modulo_alertas.py`), quien escribe una
palabra propia en «¿Que vendes?» la manda TAL CUAL a la bolsa de terminos de
`alertador.py`. Si escribe «notebook», la bolsa lleva «notebook» y nada mas
-pierde «notebook i7 16gb», «notebook corporativo», «arriendo de notebook»,
que son las frases con las que las licitaciones de verdad piden lo mismo.

Este modulo no reemplaza esa bolsa ni el motor de filtrado diario: le agrega
UNA fuente mas de terminos, igual de simple que las que ya existen (RUT,
rubro, palabra escrita a mano). El resultado de `generar_sugerencias()` son
frases que el proveedor puede aceptar o no antes de guardar su alerta.

DE DONDE SALE EL APRENDIZAJE
------------------------------
Solo de `bodega/licitaciones/*.parquet` (los datos abiertos de licitaciones
YA CERRADAS, desde enero 2025). Compras Agiles queda FUERA del entrenamiento
a proposito: no existe una bodega historica de compras agiles -se consultan
en vivo, con una ventana de 1 a 7 dias- asi que no hay corpus de donde
aprender combinaciones. El filtrado diario de compras agiles sigue
funcionando igual que siempre, con las palabras que este modulo aporte.

COMO SE MIDE LA RELEVANCIA
----------------------------
Con PMI (Pointwise Mutual Information) sobre colocaciones, no con TF-IDF.
TF-IDF pondera palabras dentro de UN documento; lo que se necesita aca es
medir que tan pegadas van dos o tres palabras EN TODO EL CORPUS, frente a
que tan pegadas irian si aparecieran por azar. Formula (bigrama):

    PMI(w1, w2) = log2( P(w1, w2) / (P(w1) * P(w2)) )

con las probabilidades estimadas por LICITACION (una licitacion que repite
un par diez veces cuenta una sola vez), para que una licitacion con muchas
lineas no infle el conteo. El ranking final combina el PMI (que tan pegadas
van) con la frecuencia (que tan seguido aparecen), para no premiar pares
rarisimos que salieron una sola vez por azar de redaccion.

EL FALLBACK ES POR RUBRO, NO POR EMBEDDINGS
----------------------------------------------
La bodega de licitaciones trae `rubro1/rubro2/rubro3` y `codigo_onu` (el
UNSPSC) en cada fila -confirmado revisando `licitador.py`-, asi que cuando
las palabras semilla no alcanzan el minimo de sugerencias, se completa con
los n-gramas mejor rankeados del rubro que mas se asocia a esas palabras.
Sin llamar a ningun modelo de embeddings: mas barato, mas rapido, y ya esta
la data para hacerlo.

Esto NO cubre Compras Agiles (no trae esa clasificacion) ni cubre casos
donde la palabra semilla no aparece en ninguna licitacion de los ultimos 20
meses -ahi se devuelve lo que se haya encontrado, aunque sea menos de 10-.

COMO SE ACTUALIZA
-------------------
    python cerebro_keywords.py

Lee toda la bodega de licitaciones y reescribe `bodega/indice_ngramas.parquet`
y `bodega/indice_token_rubro.parquet` enteros -no es incremental, y no hace
falta: recalcular sobre 20 meses tarda segundos, no horas-. Corre una vez por
semana (`.github/workflows/cerebro.yml`), no a diario: el corpus de
licitaciones cerradas no cambia lo bastante rapido como para justificar un
calculo pesado cada dia.
"""
import argparse
import math
import re
import sys
import unicodedata
from collections import Counter, defaultdict
from pathlib import Path

import pandas as pd

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

AQUI = Path(__file__).parent
BODEGA_LIC = AQUI / "bodega" / "licitaciones"
INDICE_NGRAMAS = AQUI / "bodega" / "indice_ngramas.parquet"
INDICE_TOKEN_RUBRO = AQUI / "bodega" / "indice_token_rubro.parquet"

# N-gramas de largo 2 a 4, como pide la especificacion.
LARGOS = (2, 3, 4)

# Bajo esta frecuencia (numero de licitaciones distintas donde aparece el
# n-grama) se descarta: un par que salio en 3 o 4 licitaciones no dice nada
# de la demanda, solo de como la redacto esa persona ese dia -medido en
# pruebas: con el piso en 3 pasaban frases sin sentido comercial («mts
# notebook cuente almuerzos») que compartian una licitacion con items muy
# distintos. En 5 ya no aparecen.
FRECUENCIA_MINIMA = 5

# Palabras que aparecen en todas las licitaciones y no aportan valor
# comercial. Amplia la lista `VACIAS` de `alertador.py` (que esta pensada
# para el matching diario, mas chica) con el ruido administrativo propio de
# las bases de licitacion, pedido explicito de la especificacion original:
# adjuntar, bases, plazo, entrega, anexo, factura, comuna, oferta...
VACIAS = {
    "de", "del", "la", "las", "el", "los", "y", "o", "para", "por", "con", "sin",
    "un", "una", "unos", "unas", "al", "en", "a", "su", "sus", "se", "que",
    "servicio", "servicios", "suministro", "adquisicion", "compra", "contratacion",
    "licitacion", "licitaciones", "publica", "publico", "bienes", "varios",
    "otros", "otras", "general", "ano", "anos", "mes", "meses", "region",
    "regional", "comunal", "municipal", "hospital", "establecimiento", "unidad",
    "unidades", "departamento", "direccion", "caja", "kit", "set", "tipo",
    "marca", "modelo", "item", "items", "linea", "cantidad", "adjuntar",
    "adjunto", "bases", "plazo", "plazos", "entrega", "entregas", "anexo",
    "anexos", "factura", "facturacion", "comuna", "oferta", "ofertas",
    "oferente", "oferentes", "propuesta", "propuestas", "requisito",
    "requisitos", "bases administrativas", "nro", "n", "codigo", "id",
    "fecha", "dia", "dias", "horas", "hrs", "chile", "conforme", "segun",
    "presente", "presentar", "mediante", "traves", "cada", "toda", "todos",
    "todas", "esta", "este", "estos", "estas", "cual", "cuales", "sera",
    "seran", "debe", "deben", "podra", "podran", "antes", "despues",
    "durante", "hasta", "desde", "sobre", "entre", "cuando", "donde",
}


# ======================================================================
#  NORMALIZACION (mismo criterio que alertador.sin_tildes / palabras)
# ======================================================================

def sin_tildes(texto: str) -> str:
    limpio = unicodedata.normalize("NFD", str(texto or ""))
    return "".join(c for c in limpio if unicodedata.category(c) != "Mn").lower()


def tokens_utiles(texto: str) -> list[str]:
    """Los tokens de un texto, en orden, sin los de relleno.

    Se filtran las vacias ANTES de armar los n-gramas: asi «notebook i7
    16gb» no se pierde entre medio de «de» o «con», y las frases que salen
    son las que un proveedor de verdad escribiria en una alerta.
    """
    trozos = re.findall(r"[a-z0-9]+", sin_tildes(texto))
    return [t for t in trozos if len(t) >= 3 and t not in VACIAS]


def normalizar_semilla(palabra: str) -> set[str]:
    """Una palabra o frase semilla, a su conjunto de tokens normalizados."""
    return set(tokens_utiles(palabra))


# ======================================================================
#  CORPUS: una fila por LICITACION (no por linea x oferta)
# ======================================================================

def _corpus_licitaciones() -> pd.DataFrame:
    """Nombre + descripcion + rubro, una fila por licitacion.

    `bodega/licitaciones` trae una fila por licitacion x linea x oferta -ver
    `licitador.py`-, asi que una licitacion con 40 ofertas pesaria 40 veces
    en el conteo si no se dedupe primero. Se toma una fila por `codigo`.
    """
    if not BODEGA_LIC.exists():
        return pd.DataFrame(columns=["codigo", "nombre", "descripcion", "rubro1"])

    partes = []
    for parquet in sorted(BODEGA_LIC.glob("*.parquet")):
        trozo = pd.read_parquet(
            parquet, columns=["codigo", "nombre", "descripcion", "rubro1"])
        partes.append(trozo)
    if not partes:
        return pd.DataFrame(columns=["codigo", "nombre", "descripcion", "rubro1"])

    todas = pd.concat(partes, ignore_index=True)
    return todas.drop_duplicates(subset="codigo", keep="last")


# ======================================================================
#  CONTEO: unigramas, n-gramas contiguos y su rubro
# ======================================================================

def _contar(corpus: pd.DataFrame) -> tuple[Counter, dict[int, Counter], dict, int]:
    """Recorre el corpus una vez y deja:

    - `doc_unigrama`: en cuantas licitaciones distintas aparece cada token.
    - `doc_ngrama[n]`: en cuantas licitaciones distintas aparece cada n-grama
      contiguo de largo `n` (2, 3 o 4).
    - `rubro_de_ngrama`: para cada n-grama, el rubro1 mas frecuente entre las
      licitaciones donde aparecio (para el fallback y para mostrarlo).
    - `total_docs`: cuantas licitaciones tiene el corpus (el N de la formula).
    """
    doc_unigrama: Counter = Counter()
    doc_ngrama: dict[int, Counter] = {n: Counter() for n in LARGOS}
    rubro_de_ngrama: dict[str, Counter] = defaultdict(Counter)
    token_rubro: dict[str, Counter] = defaultdict(Counter)
    total_docs = 0

    for fila in corpus.itertuples(index=False):
        texto = f"{fila.nombre or ''} {fila.descripcion or ''}"
        tokens = tokens_utiles(texto)
        if not tokens:
            continue
        total_docs += 1
        rubro = str(getattr(fila, "rubro1", "") or "").strip() or "sin rubro"

        # Unigramas: una vez por licitacion, no por repeticion dentro del texto.
        for token in set(tokens):
            doc_unigrama[token] += 1
            token_rubro[token][rubro] += 1

        # N-gramas contiguos (2 a 4), tambien una vez por licitacion.
        for n in LARGOS:
            if len(tokens) < n:
                continue
            vistos_en_esta = set()
            for i in range(len(tokens) - n + 1):
                grupo = tuple(tokens[i:i + n])
                # Un n-grama con palabras repetidas ("aseo de aseo") no aporta.
                if len(set(grupo)) != n:
                    continue
                vistos_en_esta.add(grupo)
            for grupo in vistos_en_esta:
                doc_ngrama[n][grupo] += 1
                rubro_de_ngrama[" ".join(grupo)][rubro] += 1

    return doc_unigrama, doc_ngrama, {
        "rubro_de_ngrama": rubro_de_ngrama,
        "token_rubro": token_rubro,
    }, total_docs


def _pmi(grupo: tuple[str, ...], freq_grupo: int, doc_unigrama: Counter,
         total_docs: int) -> float:
    """PMI generalizado a n palabras: log2( P(grupo) / prod(P(w_i)) )."""
    if total_docs == 0 or freq_grupo == 0:
        return 0.0
    p_grupo = freq_grupo / total_docs
    p_individual = 1.0
    for token in grupo:
        p_individual *= max(doc_unigrama.get(token, 0), 1) / total_docs
    if p_individual <= 0:
        return 0.0
    razon = p_grupo / p_individual
    if razon <= 0:
        return 0.0
    return math.log2(razon)


# ======================================================================
#  CONSTRUCCION DEL INDICE (lo que corre el workflow semanal)
# ======================================================================

def construir_indice() -> dict:
    """Recalcula el indice completo y lo deja en `bodega/`.

    No es incremental a proposito: recontar sobre 20 meses de licitaciones
    tarda segundos (son decenas de miles de licitaciones, no millones de
    lineas), y evita arrastrar un n-grama que dejo de tener sentido.
    """
    corpus = _corpus_licitaciones()
    doc_unigrama, doc_ngrama, extra, total_docs = _contar(corpus)
    rubro_de_ngrama = extra["rubro_de_ngrama"]
    token_rubro = extra["token_rubro"]

    filas = []
    for n in LARGOS:
        for grupo, freq in doc_ngrama[n].items():
            if freq < FRECUENCIA_MINIMA:
                continue
            frase = " ".join(grupo)
            pmi = _pmi(grupo, freq, doc_unigrama, total_docs)
            if pmi <= 0:
                continue
            rubro_top = (rubro_de_ngrama[frase].most_common(1)[0][0]
                         if rubro_de_ngrama[frase] else "sin rubro")
            # Puntaje de ranking: el PMI mide que tan pegadas van las
            # palabras, pero solo, un par que aparecio 3 veces por
            # casualidad puede sacar un PMI mas alto que uno solido y
            # frecuente -medido en pruebas: "impresoras multifuncionales"
            # (244 licitaciones) quedaba por debajo de frases con 3
            # apariciones-. Multiplicar por la frecuencia MISMA (no su
            # logaritmo) es lo que de verdad corrige eso: log1p(244) es
            # solo 4x log1p(3), la frecuencia cruda es 80x. Se necesita
            # ese peso para que "oportunidad real de negocio" gane sobre
            # "combinacion rara que salio una vez por como la redacto
            # alguien".
            puntaje = pmi * freq
            filas.append({
                "frase": frase,
                "tokens": list(grupo),
                "largo": n,
                "pmi": round(pmi, 4),
                "frecuencia": freq,
                "puntaje": round(puntaje, 4),
                "rubro1": rubro_top,
            })

    indice = pd.DataFrame(filas)
    AQUI_BODEGA = AQUI / "bodega"
    AQUI_BODEGA.mkdir(exist_ok=True)
    if not indice.empty:
        indice = indice.sort_values("puntaje", ascending=False).reset_index(drop=True)
        indice.to_parquet(INDICE_NGRAMAS, index=False, compression="zstd")
    else:
        pd.DataFrame(columns=["frase", "tokens", "largo", "pmi", "frecuencia",
                               "puntaje", "rubro1"]).to_parquet(
            INDICE_NGRAMAS, index=False, compression="zstd")

    filas_tr = []
    for token, contador in token_rubro.items():
        rubro_top, veces = contador.most_common(1)[0]
        filas_tr.append({"token": token, "rubro1": rubro_top, "veces": veces})
    tabla_tr = pd.DataFrame(filas_tr)
    if not tabla_tr.empty:
        tabla_tr.to_parquet(INDICE_TOKEN_RUBRO, index=False, compression="zstd")
    else:
        pd.DataFrame(columns=["token", "rubro1", "veces"]).to_parquet(
            INDICE_TOKEN_RUBRO, index=False, compression="zstd")

    return {
        "licitaciones_en_corpus": total_docs,
        "n_gramas_guardados": len(indice),
        "tokens_indexados": len(doc_unigrama),
    }


# ======================================================================
#  CONSULTA (lo que llama la app, en caliente, sin recalcular nada)
# ======================================================================

def _cargar_indice() -> tuple[pd.DataFrame, pd.DataFrame]:
    if not INDICE_NGRAMAS.exists() or not INDICE_TOKEN_RUBRO.exists():
        vacio_ng = pd.DataFrame(columns=["frase", "tokens", "largo", "pmi",
                                          "frecuencia", "puntaje", "rubro1"])
        vacio_tr = pd.DataFrame(columns=["token", "rubro1", "veces"])
        return vacio_ng, vacio_tr
    return pd.read_parquet(INDICE_NGRAMAS), pd.read_parquet(INDICE_TOKEN_RUBRO)


def generar_sugerencias(semillas: list[str], limite: int = 20,
                         minimo: int = 10) -> list[dict]:
    """El nucleo del Cerebro: de 5-10 palabras semilla a 10-20 frases.

    Devuelve una lista de dicts con las claves que necesita el frontend para
    dibujar los chips seleccionables:
        {"frase": str, "puntaje": float, "frecuencia": int,
         "rubro1": str, "origen": "semilla" | "rubro afin"}

    Sin indice construido todavia (primera corrida, antes de que el workflow
    semanal haya dejado los parquet) devuelve una lista vacia: falla abierto,
    igual que el resto de la app -el formulario simplemente no muestra
    sugerencias, no se cae-.
    """
    indice, token_rubro = _cargar_indice()
    if indice.empty:
        return []

    tokens_semilla: set[str] = set()
    for semilla in semillas:
        tokens_semilla |= normalizar_semilla(semilla)
    if not tokens_semilla:
        return []

    # Paso 1: n-gramas que contienen directamente alguna palabra semilla.
    def calza(tokens_ng) -> bool:
        return bool(set(tokens_ng) & tokens_semilla)

    directas = indice[indice["tokens"].apply(calza)]

    candidatos: list[dict] = []
    vistas: set[str] = set()
    for fila in directas.itertuples(index=False):
        if fila.frase in vistas:
            continue
        vistas.add(fila.frase)
        candidatos.append({
            "frase": fila.frase, "puntaje": fila.puntaje,
            "frecuencia": fila.frecuencia, "rubro1": fila.rubro1,
            "origen": "semilla",
        })

    # Paso 2 (fallback): si la coincidencia directa no alcanza el minimo, se
    # completa con los mejores n-gramas del rubro que mas se asocia a las
    # palabras semilla. No es un mecanismo distinto: usa la misma tabla,
    # solo cambia el criterio de seleccion (rubro en vez de coincidencia
    # literal), y el resultado se reordena junto con lo directo -nunca se
    # devuelve la coincidencia por rubro colgando al final sin importar su
    # puntaje: eso rompia el orden por relevancia (probado en
    # `test_generar_sugerencias_ordena_por_puntaje_descendente`)-.
    if len(candidatos) < minimo and not token_rubro.empty:
        candidatos_rubro = token_rubro[token_rubro["token"].isin(tokens_semilla)]
        if not candidatos_rubro.empty:
            rubros_afines = set(
                candidatos_rubro.groupby("rubro1")["veces"].sum()
                .sort_values(ascending=False)
                .head(3)  # los tres rubros mas asociados, no todo el catalogo
                .index.tolist()
            )
            del_rubro = indice[indice["rubro1"].isin(rubros_afines)]
            for fila in del_rubro.itertuples(index=False):
                if fila.frase in vistas:
                    continue
                vistas.add(fila.frase)
                candidatos.append({
                    "frase": fila.frase, "puntaje": fila.puntaje,
                    "frecuencia": fila.frecuencia, "rubro1": fila.rubro1,
                    "origen": "rubro afin",
                })

    candidatos.sort(key=lambda c: c["puntaje"], reverse=True)
    return candidatos[:limite]


# ======================================================================
#  LINEA DE COMANDOS
# ======================================================================

def main() -> None:
    argumentos = argparse.ArgumentParser(
        description="Recalcula el indice de n-gramas del Cerebro de palabras clave")
    argumentos.add_argument("--probar", metavar="PALABRA", action="append",
                             help="Despues de construir, muestra las sugerencias "
                                  "para esta palabra semilla (se puede repetir).")
    opciones = argumentos.parse_args()

    print("CEREBRO · reconstruyendo el indice de n-gramas...\n")
    resultado = construir_indice()
    print(f"  licitaciones en el corpus : {resultado['licitaciones_en_corpus']:,}")
    print(f"  tokens indexados          : {resultado['tokens_indexados']:,}")
    print(f"  n-gramas guardados        : {resultado['n_gramas_guardados']:,}")

    if opciones.probar:
        print(f"\n  probando con semillas: {opciones.probar}")
        sugerencias = generar_sugerencias(opciones.probar)
        if not sugerencias:
            print("  sin sugerencias (indice vacio o semillas sin coincidencia)")
        for s in sugerencias:
            print(f"    [{s['origen']:10s}] {s['frase']:40s} "
                  f"puntaje={s['puntaje']:.2f} freq={s['frecuencia']} "
                  f"rubro={s['rubro1']}")


if __name__ == "__main__":
    main()
