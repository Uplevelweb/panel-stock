"""
MÓDULO PLANES — qué abre cada plan, y qué ve el que no lo tiene.

UNA SOLA FUENTE DE VERDAD. Si en algún archivo aparece otra lista de qué
incluye cada plan, están de más: se desincronizan siempre y el día que pasa
nadie se entera, porque una pestaña que no aparece no da error.

POR QUÉ LA LISTA VIVE EN EL CÓDIGO Y NO EN UNA TABLA
----------------------------------------------------
Con cinco clientes, una fila mal escrita en Supabase deja a alguien sin su
pestaña y no queda rastro de por qué. En el código queda en el historial, se
revisa antes de subir y se prueba. Cuando haya cincuenta clientes y cambiar
un plan sea cosa de todos los días, se mueve a la base.

LO QUE NO SE ESCONDE
--------------------
Una pestaña que el plan no incluye NO desaparece: se dibuja igual y dice qué
es y en qué plan viene. Es la única publicidad que se lee, porque la mira
alguien que ya está adentro y ya sabe para qué sirve el resto.

Esconderla sería peor por dos motivos: el cliente no sabe que existe —así que
nunca la va a pedir— y cuando le llegue el correo de fin de prueba no va a
entender de qué le hablan.
"""

from __future__ import annotations

import streamlit as st


# --------------------------------------------------------------------------
#  Los módulos
# --------------------------------------------------------------------------
# La clave es interna y no se muestra nunca. El nombre y la explicación sí:
# son lo que lee el cliente cuando la pestaña está cerrada.

MODULOS = {
    "alertas": {
        "nombre": "Alertas",
        "que_es": "Configura qué te llega cada mañana: tus rubros, tu RUT, "
                  "a qué hora y de qué tipo.",
    },
    "seguimiento": {
        "nombre": "Seguimiento",
        "que_es": "El embudo de lo que ya te avisamos: en qué quedó cada "
                  "oportunidad, cuál ofertaste y cuál se te pasó.",
    },
    "oportunidades": {
        "nombre": "Oportunidades",
        "que_es": "Escribe un RUT y sale a quién le puede vender y todavía no "
                  "le vende, con cuánto gasta cada comprador en sus rubros y "
                  "quién se lo está llevando hoy.",
    },
    "ipt": {
        "nombre": "Itinerario de visitas",
        "que_es": "A qué instituciones ir, en qué orden y por qué. Se arma "
                  "solo con lo que compran y lo que ya te compraron.",
    },
    "equipo": {
        "nombre": "Mi equipo",
        "que_es": "Suma a tus comerciales, dales un rol y repárteles "
                  "territorios. Cada uno ve solo lo suyo.",
    },
    # Los dos de abajo NO son parte de ningún plan. Leen el catálogo de
    # Emergenza desde su Drive: no le sirven a ningún otro cliente. Se
    # entregan por cuenta, con `cuentas.modulos_extra`.
    "mercado_publico": {"nombre": "Mercado Público", "que_es": "", "extra": True},
    "cotizador": {"nombre": "Módulo Cotizador", "que_es": "", "extra": True},
}


# --------------------------------------------------------------------------
#  Los planes
# --------------------------------------------------------------------------

PLANES = {
    # El de entrada: el correo diario y el embudo. Seguimiento va aquí a
    # propósito aunque se pueda cobrar: es lo que hace volver al panel, y un
    # cliente que solo recibe correos se olvida de que existes.
    "alertas": {"alertas", "seguimiento"},

    # Suma el mapa por RUT, que es «a quién venderle». Adentro va también el
    # panorama de mercado, porque es la misma pantalla y cortarla al medio
    # dejaría media respuesta.
    "comercial": {"alertas", "seguimiento", "oportunidades"},

    # Suma el itinerario y el reparto entre comerciales. Lo que separa a
    # Empresa son PERSONAS, no funciones.
    "empresa": {"alertas", "seguimiento", "oportunidades", "ipt", "equipo"},

    # La prueba ve todo lo de Empresa. Perder algo que ya usabas pesa más que
    # nunca haberlo tenido: eso es lo que empuja a elegir plan, no un folleto.
    "piloto": {"alertas", "seguimiento", "oportunidades", "ipt", "equipo"},

    # Uplevel. Ve todo, extras incluidos.
    "soporte": set(MODULOS),
}

# En qué plan se desbloquea cada módulo. Se calcula del diccionario de arriba
# para que no haya dos listas que puedan contradecirse.
ORDEN_DE_PLANES = ["alertas", "comercial", "empresa"]

NOMBRE_DE_PLAN = {
    "alertas": "Alertas",
    "comercial": "Comercial",
    "empresa": "Empresa",
    "piloto": "prueba",
    "soporte": "Uplevel",
}


def plan_que_lo_abre(modulo: str) -> str:
    """El plan más barato que incluye ese módulo. '' si es un extra."""
    for plan in ORDEN_DE_PLANES:
        if modulo in PLANES.get(plan, set()):
            return plan
    return ""


# --------------------------------------------------------------------------
#  Qué puede ver quien entró
# --------------------------------------------------------------------------

def plan_de(usuario: dict) -> str:
    """El plan de la cuenta de quien entró.

    FALLA ABIERTO, igual que el resto de `modulo_cuentas`: si no se sabe el
    plan —porque la consulta se cayó, o porque la cuenta es vieja y no lo
    tiene— se asume `soporte` y se ve todo. Dejar a un cliente que paga sin
    su pestaña por un error de lectura es mucho peor que mostrarle de más
    a alguien por un rato.
    """
    plan = str(usuario.get("plan") or "").strip().lower()
    return plan if plan in PLANES else "soporte"


def modulos_de(usuario: dict) -> set[str]:
    """Todo lo que esta persona puede abrir: su plan más sus extras."""
    abiertos = set(PLANES[plan_de(usuario)])
    # Los extras se dan por cuenta, no por plan: Mercado Público y el
    # Cotizador solo le sirven a Emergenza.
    for extra in usuario.get("modulos_extra") or []:
        clave = str(extra).strip().lower()
        if clave in MODULOS:
            abiertos.add(clave)
    return abiertos


def puede(usuario: dict, modulo: str) -> bool:
    return modulo in modulos_de(usuario)


# --------------------------------------------------------------------------
#  Lo que ve el que no lo tiene
# --------------------------------------------------------------------------

def candado(modulo: str) -> None:
    """Dibuja la pestaña cerrada: qué es y en qué plan viene.

    Sin botón de pago, a propósito: hoy no hay pasarela y un botón que no
    lleva a ninguna parte hace más daño que no tenerlo. Cuando exista, el
    botón va aquí y en un solo lugar.
    """
    ficha = MODULOS.get(modulo, {})
    nombre = ficha.get("nombre") or modulo
    plan = plan_que_lo_abre(modulo)

    st.subheader(f"{nombre} · no está en tu plan")
    if ficha.get("que_es"):
        st.write(ficha["que_es"])

    if plan:
        st.info(
            f"Viene incluido en el plan **{NOMBRE_DE_PLAN.get(plan, plan)}**. "
            "Escríbenos a webuplevel@gmail.com y lo activamos el mismo día.")
    else:
        st.info("Este módulo se activa por cuenta. Escríbenos a "
                "webuplevel@gmail.com.")


def aviso_de_prueba(usuario: dict) -> None:
    """La franja de «te quedan N días», arriba del panel.

    Solo se dibuja si la cuenta trae fecha de término. Nadie deberia enterarse
    de que se le acabo la prueba chocando con el muro.
    """
    from datetime import date, datetime

    hasta = usuario.get("hasta")
    if not hasta:
        return
    try:
        fin = datetime.fromisoformat(str(hasta)[:10]).date()
    except ValueError:
        return

    quedan = (fin - date.today()).days
    if quedan > 5:
        return
    if quedan >= 1:
        st.warning(f"Te quedan **{quedan} días** de prueba. Después el panel "
                   "queda con lo que incluya tu plan.")
    elif quedan == 0:
        st.warning("**Hoy es el último día** de tu prueba.")
    else:
        st.error("Tu prueba terminó.")
