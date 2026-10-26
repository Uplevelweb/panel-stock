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

# 26-10-2026: el subdominio agenda.uplevelweb.art quedo sin certificado en
# Hostinger ("envio una respuesta no valida"). Es la misma carpeta
# public_html/agenda, servida desde el dominio principal, que si tiene SSL.
URL_AGENDA = "https://uplevelweb.art/agenda/"


def _url_agenda(yo: dict | None) -> str:
    """La direccion de la Agenda, con la llave adentro si es Serling.

    26-10-2026, pedido de Serling: "quiero ingresar automaticamente y solo
    tener acceso una vez logueada", sin pegar llave en ningun lado. Los dias,
    notas y ajustes viven atados a una llave (llave_hash), asi que la base
    genero una llave interna para ella, le mudo sus datos y la guarda en
    `agenda_llave_auto`, que solo lee la clave secreta del servidor
    (`agenda_llave_automatica`, ver agenda-entrada-automatica-para-copiar.txt).
    Aqui se pide SOLO para el superadmin ya identificado; la Agenda acepta
    `?llave=` desde el 14-09-2026, la guarda y la borra de la direccion.
    """
    from modulo_cuentas import es_soporte, _pedir
    if not yo or not es_soporte(yo):
        return URL_AGENDA
    llave = st.session_state.get("_agenda_llave_auto")
    if not llave:
        respuesta = _pedir("rpc/agenda_llave_automatica", metodo="POST", cuerpo={})
        llave = respuesta.strip() if isinstance(respuesta, str) else ""
        if llave:
            st.session_state["_agenda_llave_auto"] = llave
    return f"{URL_AGENDA}?llave={llave}" if llave else URL_AGENDA


def seccion_agenda(yo: dict | None = None) -> None:
    url = _url_agenda(yo)
    st.subheader("🗓️ Agenda")
    st.caption(
        "Tu día: la ruta de visitas, el horario y las notas por institución. "
        "Es la misma Agenda de siempre, mostrada aquí para no tener que "
        "cambiar de pestaña del navegador.")

    izquierda, derecha = st.columns([3, 1])
    with derecha:
        st.link_button("Abrir en pestaña nueva ↗", url, width="stretch",
                        help="Por si el recuadro de abajo no carga bien en tu "
                             "pantalla, o prefieres verla más grande.")

    # `st.components.v1.iframe` depende de que la página de adentro le avise
    # su alto por `postMessage` (como hacen los componentes de Streamlit); la
    # Agenda es una página cualquiera y nunca manda ese aviso, así que el
    # marco quedaba en 0x0 (comprobado el 08-09-2026). Un <iframe> de HTML
    # normal, con alto fijo en el estilo, no depende de eso.
    # 800px: suficiente para ver el día sin scroll doble (el de la página y el
    # del iframe). El iframe se desplaza por dentro si el contenido no entra.
    st.markdown(
        f'<iframe src="{url}" width="100%" height="800" '
        f'style="border:1px solid rgba(128,128,128,.25);border-radius:12px;" '
        f'loading="lazy"></iframe>',
        unsafe_allow_html=True,
    )
