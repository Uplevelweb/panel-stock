"""
FICHA — lee de la pagina publica lo que la API no entrega
==========================================================

Los CRITERIOS DE EVALUACION —con que se puntua y cuanto pesa cada cosa— son
lo que decide si vale la pena preparar una oferta. Un 60% al precio y un 30%
a la calidad tecnica es una licitacion; 60% a la calidad tecnica y 20% al
precio es otra completamente distinta, y no se compite igual.

NO ESTAN EN LA API. Comprobado el 27-08-2026:
  - 93 campos distintos en 12 licitaciones: ninguno de criterios
  - cinco endpoints posibles (`criterios.json`, `evaluacion.json`,
    `licitaciones/criterios.json`...): los cinco 404

PERO NO HACE FALTA LEER LOS PDF. Estan en el HTML de la ficha publica, en
una tabla de tres columnas —Item, Observaciones, Ponderacion—. Es mucho mas
facil de leer que un PDF y no depende de que las bases esten adjuntas.

COMO SE LLEGA A LA FICHA
------------------------
La direccion que se ve en el navegador lleva un parametro cifrado
(`?qs=i3XnhlXX0TK+VXxvII6lFQ==`) que no se puede construir. Pero el sitio
acepta tambien el codigo de la licitacion y redirige solo:

    DetailsAcquisition.aspx?idlicitacion=1000813-15-LE26

Ojo: `fichaLicitacion.html?idLicitacion=...` NO sirve —devuelve 934 bytes de
una pagina puente sin contenido—. Tiene que ser `DetailsAcquisition.aspx`.

ESTO ES RASPADO DE PAGINA, NO UNA API
-------------------------------------
Lo que se lee es informacion publica de compras del Estado, la misma que
cualquiera ve en el navegador. Pero al ser HTML y no un contrato de datos,
puede cambiar sin aviso: si un dia ChileCompra reordena la tabla, esto deja
de encontrarla. Por eso todo devuelve vacio en vez de reventar, y el correo
simplemente no muestra la seccion.
"""
import html as _html
import re
import urllib.parse
import urllib.request

FICHA = ("https://www.mercadopublico.cl/Procurement/Modules/RFB/"
         "DetailsAcquisition.aspx?idlicitacion=")

NAVEGADOR = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}

# Las celdas de porcentaje llevan una clase que contiene «entaje».
CELDA_PORCENTAJE = re.compile(
    r'class="[^"]*entaje[^"]*"[^>]*>\s*(?:<[^>]+>\s*)*(\d{1,3})\s*%', re.IGNORECASE)


def _limpiar(trozo: str) -> str:
    """Saca las etiquetas y deja el texto de una celda."""
    return " ".join(_html.unescape(re.sub(r"<[^>]+>", " ", trozo)).split())


def bajar_ficha(codigo: str, espera: int = 45) -> str:
    """El HTML de la ficha publica. Vacio si no se pudo."""
    if not codigo:
        return ""
    try:
        peticion = urllib.request.Request(FICHA + urllib.parse.quote(codigo),
                                          headers=NAVEGADOR)
        with urllib.request.urlopen(peticion, timeout=espera) as respuesta:
            return respuesta.read().decode("utf-8", errors="replace")
    except Exception:
        return ""


def criterios_de_evaluacion(documento: str) -> list[dict]:
    """
    La tabla de criterios: [{item, observaciones, ponderacion}, ...]

    Se parte de la cabecera «Ponderación» y de ahi se leen las filas. No se
    busca por posicion ni por indice de tabla: la pagina trae siete tablas y
    el orden cambia segun lo que la licitacion tenga.
    """
    if not documento:
        return []

    # La palabra «Ponderación» aparece SIETE veces en la pagina: la primera es
    # el menu de secciones de arriba, no la tabla. Partir de la primera dejaba
    # el bloque en el indice y la tabla quedaba fuera de los 40.000 caracteres.
    # Se busca la aparicion que va seguida de filas con porcentaje.
    bloque = ""
    for aparicion in re.finditer("Ponderaci", documento):
        candidato = documento[aparicion.start():aparicion.start() + 40000]
        if len(CELDA_PORCENTAJE.findall(candidato)) >= 2:
            bloque = candidato
            break
    if not bloque:
        return []

    criterios = []
    for fila in re.split(r"<tr[\s>]", bloque)[1:]:
        # Se corta en el CIERRE de la etiqueta, no en su comienzo: partiendo
        # por «<td» los atributos (`style="width:45%;"`) se quedaban pegados
        # al texto de la celda y salian dentro del nombre del criterio.
        celdas = [_limpiar(c) for c in re.split(r"<t[dh][^>]*>", fila)[1:]]
        celdas = [c for c in celdas if c]
        porcentaje = CELDA_PORCENTAJE.search(fila)
        if not porcentaje or len(celdas) < 2:
            continue
        # La primera celda suele ser el numero de orden; se descarta.
        texto = [c for c in celdas if not c.isdigit() and not c.endswith("%")]
        if not texto:
            continue
        # La celda del item viene como «3 Plazo de ejecución»: el numero de
        # orden pegado adelante. Y la ultima fila arrastra la cola de la
        # pagina («20% Subir 7. Montos y duracion...»), que se corta.
        item = re.sub(r"^\d+\s+", "", texto[0]).strip()
        observaciones = texto[1] if len(texto) > 1 else ""
        observaciones = re.split(r"\d+%|Subir", observaciones)[0].strip()
        criterios.append({
            "item": item[:70],
            "observaciones": observaciones[:110],
            "ponderacion": int(porcentaje.group(1)),
        })

    # Si suman mucho mas de 100 es que se colaron filas de otra tabla.
    if criterios and sum(c["ponderacion"] for c in criterios) > 130:
        return []
    return criterios


def menciona_visita_en_ficha(documento: str) -> str:
    """
    Si la ficha nombra una visita a terreno, devuelve la frase.

    La ficha trae las bases desplegadas en secciones, asi que aca aparece lo
    que el campo de la API deja vacio.
    """
    if not documento:
        return ""
    limpio = _limpiar(documento)
    encontrado = re.search(
        r"[^.]{0,90}(?:visita\s+a\s+terreno|visita\s+en\s+terreno|"
        r"visita\s+obligatoria|charla\s+informativa)[^.]{0,110}",
        limpio, re.IGNORECASE)
    return encontrado.group(0).strip() if encontrado else ""
