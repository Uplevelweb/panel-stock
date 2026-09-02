"""
EXPORTAR — el mismo botón de bajar, en todos los módulos
=========================================================

Serling lo pidió el 01-09-2026: «el informe que me arroje previa consulta puedo
exportarlo en PDF o Excel en TODOS los módulos». Hasta esa fecha solo Mercado
Público y el Cotizador tenían botón; Oportunidades, Visitas y Mi equipo no.

POR QUE UN ARCHIVO APARTE Y NO UNA COPIA EN CADA MODULO
-------------------------------------------------------
`a_excel` vive en `app.py`, y `app.py` importa los módulos: si un módulo
importara `app` arriba, sería un círculo. Por eso el import va DENTRO de la
función, que es el mismo truco que ya usa `modulo_alertas.cargar_ordenes`.

Y va acá y no copiado en cada módulo para que el día que haya que arreglar el
formato del Excel se arregle en un solo lugar.

POR QUE EXCEL Y NO PDF EN LAS TABLAS
------------------------------------
Ella pidió «PDF o Excel». Para una lista de 235 unidades compradoras el PDF no
sirve para trabajar: lo que hace un KAM con esa lista es ordenarla, marcarla y
repartirla. El PDF sigue donde de verdad se usa —la cotización que le manda a
la institución—, que ya lo tiene.
"""
from __future__ import annotations

import datetime as dt

import pandas as pd
import streamlit as st


def _hoy() -> str:
    return dt.date.today().strftime("%d-%m-%Y")


def boton_excel(tabla: pd.DataFrame, nombre: str, clave: str,
                hoja: str = "Datos", etiqueta: str = "Bajar en Excel",
                ancho: str = "content") -> None:
    """Dibuja el botón de bajar la tabla que se está mirando.

    `tabla` es lo que se está viendo en pantalla YA FILTRADO, no la tabla
    entera: si alguien filtró una región y baja el archivo, espera esa región,
    no Chile completo.

    `nombre` es el nombre del archivo sin extensión ni fecha; la fecha se le
    agrega acá para que dos descargas del mismo día no se pisen en la carpeta
    de bajadas y para saber de cuándo es el dato sin abrirlo.
    """
    if tabla is None or tabla.empty:
        return

    from app import a_excel  # dentro, para no cerrar el círculo de imports

    try:
        datos = a_excel(tabla, nombre_hoja=hoja[:31] or "Datos")
    except Exception as error:  # openpyxl puede caerse con un nombre de hoja raro
        st.caption(f"No se pudo armar el Excel: {error}")
        return

    st.download_button(
        etiqueta,
        data=datos,
        file_name=f"{nombre}-{_hoy()}.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        key=f"bajar_{clave}",
        width=ancho,
        help=f"{len(tabla):,}".replace(",", ".") + " filas, tal como están filtradas acá.",
    )
