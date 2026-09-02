"""
MÓDULO ENVÍOS DE OFERTAS, CATÁLOGO Y MAILING
=============================================

LA PUERTA ÚNICA DEL ENVÍO. Serling lo pidió el 01-09-2026: «esta opción de
envío, tanto del Panel de Oportunidades como del Panel Armada, debe reposar en
el módulo de Envíos de Ofertas, Catálogo y Mailing».

POR QUE ES UNA PUERTA Y NO EL ENVÍO MISMO
------------------------------------------
El mismo día se decidió que **el envío se queda en Gmail**: sale como
`svera@emergenza.cl` y mudarlo a Resend obligaría a tocar el DNS de
`emergenza.cl`, que es dominio de Emergenza y no de ella. Así que los dos
paneles siguen donde están, en Apps Script, y este módulo es el lugar desde el
que se llega a los dos.

Eso es exactamente lo que se eligió: **dos apps, una puerta**. Esta pantalla es
la puerta. El envío no se toca porque no tiene ninguna falla: funciona.

LO QUE SÍ ARREGLA, Y NO ES POCO
--------------------------------
Los dos paneles se parecen muchísimo —mismo aspecto, misma planilla, botones
iguales— y se distinguen solo por el título y por un trozo de la URL. Eso ya
costó caro dos veces:

  30-08-2026  se pegó el código de la empresa en el proyecto Armada y el envío
              empezó a leer FACH y municipalidades. Lo detectó ella, con un
              borrador dirigido a `hospitalfach.cl`.
  01-09-2026  un archivo nuevo pisó el título del panel, que es justamente el
              letrero que avisa en cuál de los dos está parada.

Acá se entra desde un solo lugar donde cada panel dice, en letras, a quién le
va a escribir. Ver [[configuracion-completa-en-el-archivo]] en la memoria.
"""
import pandas as pd
import streamlit as st

import cartera

# Las dos Web App publicadas. Se distinguen a simple vista: la de la empresa
# lleva `/a/macros/emergenza.cl/` y la personal no.
PANELES = [
    {
        "nombre": "Ofertas y Catálogo",
        "cuenta": "svera@emergenza.cl",
        "contactos": 224,
        "alcance": "Todas las instituciones menos Armada",
        "url": ("https://script.google.com/a/macros/emergenza.cl/s/"
                "AKfycbzf9b0csN17coRdlvnshmyrQ9uGDZb_9Yld0sLwxjyAZxCC7wu7hLRPEh2KYsSJGM53/exec"),
        "titulo_en_pantalla": "Panel de Catálogo y Ofertas",
    },
    {
        "nombre": "Armada",
        "cuenta": "serlingvera@gmail.com",
        "contactos": 27,
        "alcance": "Solo la pestaña Armada",
        "url": ("https://script.google.com/macros/s/"
                "AKfycbzc5VFwOYb9A5AxBgwYga2R61WA-AxJ4ccBvuAFFbRqRSIH40Gw7uOXJjlGPaEQiG1X/exec"),
        "titulo_en_pantalla": "Panel Armada",
    },
]


def seccion_envios(usuario: dict) -> None:
    st.subheader("Envíos de Ofertas, Catálogo y Mailing")
    st.caption(
        "Desde acá salen todos los envíos. Los dos paneles mandan desde tu "
        "propio Gmail, con tu firma y tu dirección: por eso siguen en Google y "
        "no adentro de esta app.")

    izquierda, derecha = st.columns(2, gap="medium")
    for columna, panel in zip((izquierda, derecha), PANELES):
        with columna:
            with st.container(border=True):
                st.markdown(f"#### {panel['nombre']}")
                st.caption(f"**{panel['alcance']}**")
                a, b = st.columns(2)
                a.metric("Contactos", panel["contactos"])
                b.metric("Envía desde", "Gmail",
                         help=f"La cuenta {panel['cuenta']}")
                st.caption(f"Cuenta: `{panel['cuenta']}`")
                st.link_button(f"Abrir {panel['nombre']}", panel["url"],
                               width="stretch", type="primary")
                st.caption(
                    "Al abrirlo, arriba tiene que decir "
                    f"**«{panel['titulo_en_pantalla']}»**.")

    # EL AVISO VA DESPUES DE LOS BOTONES Y NO ANTES, a proposito: se lee cuando
    # ya se eligio uno, que es el momento en que sirve comprobar.
    st.warning(
        "**Antes de mandar, mira el título del panel.** Los dos se ven casi "
        "iguales y le escriben a listas distintas. El 30-08 se mandó por la "
        "pestaña equivocada y se detectó por un borrador dirigido a "
        "`hospitalfach.cl`.")

    _a_quien_le_toca(usuario)

    st.divider()
    st.caption(
        "La cotización a una institución puntual **no** se manda desde acá: "
        "sale de **🏛️ Mercado Público**, pegada a la cotización que estás "
        "armando. Esto es para los envíos a muchos: ofertas, catálogo y mailing.")


def _a_quien_le_toca(usuario: dict) -> None:
    """La cartera, como recordatorio de a quién conviene escribirle.

    NO se cruza con la lista de contactos, y es a propósito: la cartera trae
    unidades con el nombre de ChileCompra y sin correo; los correos están en la
    planilla, con nombres escritos a mano. Cruzarlos por nombre no calza solo y
    se decidió el 01-09-2026 no hacerlo, porque el envío funciona bien como
    está. Acá solo se muestra, para tenerla a mano al armar la tanda.
    """
    mia = cartera.leer(usuario)
    if mia.empty:
        return

    for columna in ("gasto", "por_ganar"):
        if columna in mia:
            mia[columna] = pd.to_numeric(mia[columna], errors="coerce")

    with st.expander(f"Tu cartera — {len(mia)} unidades que decidiste trabajar"):
        st.caption(
            "Sale de **🎯 Oportunidades**. Es a quién dicen los datos que le "
            "vendas; sirve para saber a quién buscar en la planilla al armar "
            "la tanda. Los dos paneles siguen mandando a su propia lista.")
        visibles = [c for c in ["nombre_unidad", "nombre_organismo", "region",
                                "comuna", "por_ganar"] if c in mia.columns]
        st.dataframe(
            mia[visibles], width="stretch", hide_index=True, height=260,
            column_config={
                "nombre_unidad": st.column_config.TextColumn("Unidad compradora", width="large"),
                "nombre_organismo": st.column_config.TextColumn("Organismo", width="large"),
                "region": st.column_config.TextColumn("Región", width="small"),
                "comuna": st.column_config.TextColumn("Comuna", width="small"),
                "por_ganar": st.column_config.NumberColumn("Por ganar", format="localized",
                                                           width="small"),
            })
