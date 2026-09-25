"""
Pruebas del Cerebro de palabras clave.

No tocan la bodega real: cada prueba redirige `cerebro_keywords.BODEGA_LIC`,
`INDICE_NGRAMAS` e `INDICE_TOKEN_RUBRO` a un directorio temporal (via
`monkeypatch`), arma un corpus sintetico chico y corre `construir_indice` +
`generar_sugerencias` contra ese corpus aislado.

Se corren con:
    python -m pytest test_cerebro_keywords.py -v
"""
import pandas as pd
import pytest

import cerebro_keywords as ck


def _licitacion(codigo, nombre, descripcion, rubro="Tecnologia"):
    return {"codigo": codigo, "nombre": nombre, "descripcion": descripcion,
            "rubro1": rubro}


@pytest.fixture
def bodega_aislada(tmp_path, monkeypatch):
    """Redirige el modulo a una bodega y unos indices de prueba, vacios."""
    carpeta_lic = tmp_path / "licitaciones"
    carpeta_lic.mkdir()
    monkeypatch.setattr(ck, "BODEGA_LIC", carpeta_lic)
    monkeypatch.setattr(ck, "INDICE_NGRAMAS", tmp_path / "indice_ngramas.parquet")
    monkeypatch.setattr(ck, "INDICE_TOKEN_RUBRO", tmp_path / "indice_token_rubro.parquet")
    monkeypatch.setattr(ck, "AQUI", tmp_path)
    return carpeta_lic


def _escribir_corpus(carpeta_lic, filas):
    pd.DataFrame(filas).to_parquet(carpeta_lic / "2025-01.parquet", index=False)


# --------------------------------------------------------------------------
#  Dedupe por licitacion: la bodega trae una fila por licitacion x linea x
#  oferta, y contar sin deduplicar infla la frecuencia con el numero de
#  oferentes en vez de con el numero de licitaciones.
# --------------------------------------------------------------------------

def test_construir_indice_dedupe_por_codigo(bodega_aislada):
    filas = []
    # Una sola licitacion, pero con 40 lineas x oferta -como pasa de verdad
    # en la bodega-, todas con el mismo codigo.
    for _ in range(40):
        filas.append(_licitacion("LIC-1", "Compra de notebook corporativo",
                                  "Notebook corporativo para funcionarios"))
    _escribir_corpus(bodega_aislada, filas)

    resultado = ck.construir_indice()

    # Deduplicada, es UNA licitacion en el corpus, no 40.
    assert resultado["licitaciones_en_corpus"] == 1


# --------------------------------------------------------------------------
#  Sugerencias coherentes: toda frase devuelta por coincidencia directa
#  ("semilla") tiene que contener al menos un token de la semilla.
# --------------------------------------------------------------------------

def test_generar_sugerencias_frases_contienen_la_semilla(bodega_aislada):
    filas = []
    for _ in range(8):
        filas.append(_licitacion(f"LIC-{_}", "Adquisicion de notebook i7 16gb",
                                  "Se requiere notebook i7 16gb con garantia"))
    for _ in range(6):
        filas.append(_licitacion(f"LIC-b{_}", "Compra de notebook corporativo",
                                  "Notebook corporativo para funcionarios"))
    _escribir_corpus(bodega_aislada, filas)
    ck.construir_indice()

    sugerencias = ck.generar_sugerencias(["notebook"], limite=20)

    assert sugerencias, "debe devolver al menos una sugerencia"
    # Toda coincidencia DIRECTA (origen "semilla") tiene que contener la
    # palabra semilla. Las de "rubro afin" (fallback) no tienen por que
    # -son de un rubro relacionado, no un match literal- y en un corpus tan
    # chico como este el fallback puede activarse porque hay pocas
    # combinaciones distintas de "notebook".
    directas = [s for s in sugerencias if s["origen"] == "semilla"]
    assert directas, "debe haber al menos una coincidencia directa"
    for s in directas:
        tokens_frase = set(s["frase"].split())
        assert tokens_frase & {"notebook"}, (
            f"la frase «{s['frase']}» no contiene la palabra semilla")


def test_generar_sugerencias_ordena_por_puntaje_descendente(bodega_aislada):
    filas = []
    # «notebook 16gb» aparece mucho mas seguido que «notebook workstation».
    for _ in range(20):
        filas.append(_licitacion(f"LIC-a{_}", "notebook 16gb ram", "notebook 16gb ram ssd"))
    for _ in range(5):
        filas.append(_licitacion(f"LIC-b{_}", "notebook workstation grafico",
                                  "notebook workstation grafico dedicado"))
    _escribir_corpus(bodega_aislada, filas)
    ck.construir_indice()

    sugerencias = ck.generar_sugerencias(["notebook"], limite=20)
    puntajes = [s["puntaje"] for s in sugerencias]
    assert puntajes == sorted(puntajes, reverse=True)


# --------------------------------------------------------------------------
#  Fallback por rubro: si la semilla no tiene (o casi no tiene) coincidencia
#  directa, se completa con n-gramas del rubro mas asociado a esa palabra.
# --------------------------------------------------------------------------

def test_fallback_por_rubro_cuando_faltan_coincidencias(bodega_aislada):
    filas = []
    # Pocas licitaciones con la palabra semilla exacta -por debajo del
    # minimo pedido-, pero todas del mismo rubro que tiene mucho mas material.
    for _ in range(5):
        filas.append(_licitacion(f"LIC-a{_}", "insumo especializado raro",
                                  "insumo especializado raro para laboratorio",
                                  rubro="Laboratorio"))
    for _ in range(20):
        filas.append(_licitacion(f"LIC-b{_}", "reactivos quimicos laboratorio",
                                  "compra de reactivos quimicos para laboratorio",
                                  rubro="Laboratorio"))
    for _ in range(20):
        filas.append(_licitacion(f"LIC-c{_}", "tubos ensayo laboratorio",
                                  "tubos de ensayo para laboratorio clinico",
                                  rubro="Laboratorio"))
    _escribir_corpus(bodega_aislada, filas)
    ck.construir_indice()

    sugerencias = ck.generar_sugerencias(["especializado"], limite=20, minimo=10)

    origenes = {s["origen"] for s in sugerencias}
    assert "rubro afin" in origenes, "debio completar con el fallback de rubro"
    assert len(sugerencias) >= 5


# --------------------------------------------------------------------------
#  Casos borde
# --------------------------------------------------------------------------

def test_sin_indice_construido_devuelve_lista_vacia(bodega_aislada):
    # No se llamo a construir_indice(): no existen los parquet todavia.
    assert ck.generar_sugerencias(["notebook"]) == []


def test_semilla_sin_coincidencia_ni_rubro_devuelve_lo_que_haya(bodega_aislada):
    filas = [_licitacion("LIC-1", "notebook corporativo", "notebook corporativo oficina")
             for _ in range(6)]
    _escribir_corpus(bodega_aislada, filas)
    ck.construir_indice()

    # Palabra que no aparece en ninguna licitacion del corpus.
    sugerencias = ck.generar_sugerencias(["xyzinexistente"], limite=20)
    assert sugerencias == []


def test_normalizar_semilla_quita_tildes_y_relleno():
    assert ck.normalizar_semilla("Alimentación de Servicios") == {"alimentacion"}
    assert ck.normalizar_semilla("aseo") == {"aseo"}


def test_tokens_utiles_descarta_administrativas():
    tokens = ck.tokens_utiles("Adjuntar bases y anexo antes del plazo de entrega")
    assert tokens == []


def test_construir_indice_respeta_frecuencia_minima(bodega_aislada):
    filas = []
    # Solo 2 licitaciones con esta frase: por debajo de FRECUENCIA_MINIMA.
    for _ in range(2):
        filas.append(_licitacion(f"LIC-{_}", "combinacion rarisima unica",
                                  "combinacion rarisima unica de prueba"))
    _escribir_corpus(bodega_aislada, filas)
    ck.construir_indice()

    sugerencias = ck.generar_sugerencias(["rarisima"], limite=20)
    assert sugerencias == [], (
        "un n-grama con menos apariciones que FRECUENCIA_MINIMA no debe salir")
