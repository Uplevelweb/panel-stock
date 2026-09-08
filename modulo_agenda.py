"""
MÓDULO AGENDA — la puerta de entrada a Inteligencia
====================================================

Pedido de Serling (08-09-2026): que el Asistente Diario (`agenda.uplevelweb.art`,
vive en `deploy-project/agenda/`, código aparte y con su propio CLAUDE.md) sea
**lo primero que se ve** al entrar a Inteligencia, como si fuera el centro de
mando del vendedor — y que desde ahí se pueda ir a los demás módulos y volver
sin perder nada.

POR QUÉ ES UN IFRAME Y NO UNA REESCRITURA
------------------------------------------
La Agenda es una página estática aparte (HTML/JS, con su propia llave y su
propio Supabase), no Streamlit. Meterla aquí como código sería mantener dos
copias de lo mismo. `agenda.uplevelweb.art` no manda `X-Frame-Options` ni
`frame-ancestors` (comprobado el 08-09-2026 con `curl -I`), así que se puede
incrustar tal cual.

POR QUÉ NO HACE FALTA UN BOTÓN DE «CONFIRMAR ANTES DE SALIR»
--------------------------------------------------------------
Esta pestaña vive en el MISMO panel de Streamlit que las demás: pasar de
«Agenda» a «Oportunidades» y volver es cambiar de pestaña, no navegar a otra
página. Streamlit no vuelve a correr el script ni se pierde nada de lo que
había en las otras pestañas —RUT escrito, filtros elegidos—, así que el riesgo
de perder datos que preocupaba no existe con este diseño. Si el día de mañana
la Agenda deja de ser un iframe y pasa a ser una redirección de verdad, ahí sí
habría que agregar esa confirmación.
"""
import streamlit as st
import streamlit.components.v1 as components

URL_AGENDA = "https://agenda.uplevelweb.art/"


def seccion_agenda() -> None:
    st.subheader("🗓️ Agenda")
    st.caption(
        "Tu día: la ruta de visitas, el horario y las notas por institución. "
        "Es la misma Agenda de siempre, mostrada aquí para no tener que "
        "cambiar de pestaña del navegador.")

    izquierda, derecha = st.columns([3, 1])
    with derecha:
        st.link_button("Abrir en pestaña nueva ↗", URL_AGENDA, width="stretch",
                        help="Por si el recuadro de abajo no carga bien en tu "
                             "pantalla, o prefieres verla más grande.")

    # 800px: suficiente para ver el día sin scroll doble (el de la pagina y el
    # del iframe). `scrolling=True` deja que la Agenda se desplace por dentro
    # si el contenido no entra.
    components.iframe(URL_AGENDA, height=800, scrolling=True)
