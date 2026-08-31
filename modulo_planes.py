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


def origen_de(plan: str, extras=()) -> dict[str, str]:
    """De donde viene cada modulo para una cuenta: 'plan', 'extra' o ''.

    Es lo que dibuja los interruptores de Soporte, y vive aca —y no en la
    pantalla— para poder probarlo sin abrir un navegador.

    'plan'   lo incluye el plan. El interruptor va encendido y bloqueado:
             apagarlo seria cobrar un plan y no entregarlo.
    'extra'  se le regalo a esta cuenta. Se puede apagar.
    ''       no lo tiene. Se puede encender.
    """
    # El MISMO respaldo que `plan_de`: un plan desconocido cae en `soporte` y
    # ve todo. Si aca se usara otra regla, Soporte mostraria una cosa y el
    # cliente veria otra, que es la peor pantalla de soporte posible.
    limpio = str(plan or "").strip().lower()
    del_plan = PLANES[limpio if limpio in PLANES else "soporte"]
    dados = {str(m) for m in (extras or ())}
    salida = {}
    for modulo in MODULOS:
        if modulo in del_plan:
            salida[modulo] = "plan"
        elif modulo in dados:
            salida[modulo] = "extra"
        else:
            salida[modulo] = ""
    return salida


def extras_para_abrir_todo(plan: str) -> list[str]:
    """Los modulos que hay que regalar para que una cuenta lo vea todo.

    Es la oferta de la feria: paga el plan de entrada y recibe el de arriba.
    Se excluyen `mercado_publico` y `cotizador` a proposito: leen el Drive de
    Emergenza, no le sirven a ningun otro cliente y no estan a la venta.
    """
    limpio = str(plan or "").strip().lower()
    del_plan = PLANES[limpio if limpio in PLANES else "soporte"]
    return sorted(m for m, ficha in MODULOS.items()
                  if not ficha.get("extra") and m not in del_plan)


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
    quedan = _dias_que_quedan(usuario)
    if quedan is None or quedan > 5:
        return
    if quedan >= 1:
        st.warning(f"Te quedan **{quedan} días** de prueba. Después el panel "
                   "queda con lo que incluya tu plan.")
    elif quedan == 0:
        st.warning("**Hoy es el último día** de tu prueba.")
    else:
        st.error("Tu prueba terminó.")


# --------------------------------------------------------------------------
#  El muro del día 21
# --------------------------------------------------------------------------
#
# Diseño de Serling: la prueba no se corta de golpe. Se extiende dos veces, y
# cada extensión se paga con un dato — el teléfono primero, el motivo después.
#
# Un vencimiento normal solo pierde clientes. Este los convierte en una
# conversación y en información de producto: quien no contesta el teléfono
# igual deja escrito qué le faltó para pagar.

DIAS_DE_EXTENSION = 10
EXTENSIONES_MAXIMAS = 2


def _dias_que_quedan(usuario: dict):
    """Días hasta el fin de la prueba. None si esta cuenta no vence."""
    from datetime import date, datetime

    hasta = usuario.get("hasta")
    if not hasta:
        return None
    try:
        fin = datetime.fromisoformat(str(hasta)[:10]).date()
    except ValueError:
        return None
    return (fin - date.today()).days


def muro_de_prueba(usuario: dict) -> bool:
    """La pantalla de fin de prueba. True si hay que parar el panel acá.

    Se dibuja ANTES que las pestañas: quien se quedó sin prueba no debería
    ver un panel a medias, sino una sola pregunta clara.
    """
    from datetime import date, timedelta

    quedan = _dias_que_quedan(usuario)
    if quedan is None or quedan >= 0:
        return False

    usadas = int(usuario.get("extensiones") or 0)
    nombre = usuario.get("empresa") or "tu empresa"

    # Ya usó las dos extensiones: hasta acá llega el panel.
    if usadas >= EXTENSIONES_MAXIMAS:
        st.subheader("Tu prueba terminó")
        st.write(
            f"El panel de **{nombre}** queda cerrado, pero **el correo diario "
            "sigue llegando**: cada mañana vas a seguir viendo lo que se "
            "publicó en tus rubros.")
        st.info("Para volver a abrirlo, escríbenos a **webuplevel@gmail.com** "
                "y lo activamos el mismo día.")
        return True

    # Le queda extensión. Se pide el dato que la paga.
    primera = usadas == 0
    st.subheader("Tu prueba terminó")
    st.write(f"Podemos extenderla **{DIAS_DE_EXTENSION} días más** para "
             f"{nombre}, sin costo.")

    if primera:
        st.caption("Solo necesitamos un teléfono para poder llamarte y "
                   "resolver dudas. No lo usamos para nada más.")
        etiqueta, campo, marcador = "Tu teléfono", "telefono", "+56 9 1234 5678"
    else:
        st.caption("Esta vez solo queremos entender qué te faltó. Nos sirve "
                   "para mejorar, y es la razón por la que podemos seguir "
                   "regalando días.")
        etiqueta, campo, marcador = ("¿Qué te falta para contratarlo?",
                                     "motivo_no_paga",
                                     "El precio, me falta tal cosa, todavía "
                                     "no lo pruebo bien…")

    with st.form("muro_prueba"):
        escrito = st.text_input(etiqueta, placeholder=marcador)
        enviar = st.form_submit_button(
            f"Extender {DIAS_DE_EXTENSION} días", type="primary")

    if enviar:
        limpio = str(escrito or "").strip()
        if len(limpio) < 4:
            st.error("Escribe algo primero: con eso se extiende la prueba.")
            return True
        from modulo_cuentas import extender_prueba
        nueva = (date.today() + timedelta(days=DIAS_DE_EXTENSION)).isoformat()
        if extender_prueba(usuario.get("cuenta_id", ""), nueva, usadas + 1,
                           campo, limpio):
            st.cache_data.clear()
            st.success(f"Listo. Tienes {DIAS_DE_EXTENSION} días más.")
            st.rerun()
        else:
            st.error("No se pudo extender. Escríbenos a webuplevel@gmail.com "
                     "y lo hacemos nosotros.")
    return True
