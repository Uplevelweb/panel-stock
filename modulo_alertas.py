"""
MÓDULO ALERTAS — configurar el correo diario y ver antes que llegaria
=====================================================================

La pantalla donde se decide QUE avisa el correo de cada manana. Tres maneras
de decirlo, y se pueden combinar:

  Por RUT       se escribe el RUT y las palabras salen solas de lo que ese
                proveedor ya ha vendido en Convenio Marco. Cero configuracion.
  Por rubro     se eligen rubros de los que traen las propias licitaciones.
  Por palabras  se escriben a mano.

POR QUE EL RUT NO BASTA SOLO
----------------------------
Si el RUT no tiene Convenio Marco registrado, la bodega no sabe que vende y
el atajo no dice nada. Por eso las otras dos no son un plan B decorativo:
son la unica via para un proveedor que recien parte o que solo va a
licitaciones. La pantalla lo dice en cuanto pasa, en vez de quedarse muda.

LA VISTA PREVIA ES LO QUE HACE QUE ESTO SIRVA
---------------------------------------------
Configurar a ciegas y esperar hasta manana para ver si sirvio es la manera
mas rapida de que alguien lo abandone. Aca, apenas se cambia algo, se
recalcula contra las licitaciones del ultimo mes que ya estan en la bodega y
se muestra que habria llegado. Usa EXACTAMENTE las mismas funciones que
`alertador.py`, no una imitacion: si la vista previa miente, el correo
tambien miente.
"""
import json
import os
from pathlib import Path

import pandas as pd
import streamlit as st

import alertador

CARPETA = Path(__file__).parent
RUTA_BODEGA = CARPETA / "bodega"

REGIONES = [
    "Región de Arica y Parinacota", "Región de Tarapacá", "Región de Antofagasta",
    "Región de Atacama", "Región de Coquimbo", "Región de Valparaíso",
    "Región Metropolitana de Santiago",
    "Región del Libertador General Bernardo O´Higgins", "Región del Maule",
    "Región del Ñuble", "Región del Biobío", "Región de la Araucanía",
    "Región de Los Ríos", "Región de Los Lagos",
    "Región de Aysén del General Carlos Ibáñez del Campo",
    "Región de Magallanes y de la Antártica",
]


# --------------------------------------------------------------------------
#  Bodega
# --------------------------------------------------------------------------
def _sello() -> str:
    """Cambia cuando el bodeguero deja datos nuevos, para soltar la cache."""
    archivo = RUTA_BODEGA / "estado.json"
    if not archivo.exists():
        return "vacia"
    try:
        return str(json.loads(archivo.read_text(encoding="utf-8")).get("actualizado") or "vacia")
    except Exception:
        return "vacia"


@st.cache_data(show_spinner="Abriendo la bodega…")
def cargar_ordenes(sello: str) -> pd.DataFrame:
    """
    Las ordenes de compra con la columna `producto`, que es de donde salen las
    palabras del RUT. `modulo_oportunidades` carga las mismas filas pero sin
    esa columna, asi que no se puede reaprovechar su cache.
    """
    partes = []
    for archivo in sorted((RUTA_BODEGA / "detalle").glob("*.parquet")):
        partes.append(pd.read_parquet(archivo, columns=[
            "unidad", "convenio_marco", "rut_proveedor", "proveedor", "producto", "total"]))
    if not partes:
        return pd.DataFrame()
    tabla = pd.concat(partes, ignore_index=True)
    tabla["unidad"] = tabla["unidad"].astype(str)
    tabla["total"] = pd.to_numeric(tabla["total"], errors="coerce").fillna(0.0)
    tabla["rut_limpio"] = tabla["rut_proveedor"].astype(str).map(alertador.solo_digitos_rut)
    # Ver `comprimir_textos` en alertador.py: de 198 MB a 71 MB.
    return alertador.comprimir_textos(tabla)


@st.cache_data(show_spinner=False)
def rubros_disponibles(sello: str) -> list[str]:
    """
    Los rubros que traen las licitaciones, de mas a menos frecuentes.

    Ojo con la columna: `codigo_onu` trae el NUMERO (80141607), que no le
    dice nada a nadie. El nombre legible esta en `rubro1`.
    """
    archivos = sorted((RUTA_BODEGA / "licitaciones").glob("*.parquet"))
    if not archivos:
        return []
    d = pd.read_parquet(archivos[-1], columns=["codigo", "rubro1"])
    cuenta = d["rubro1"].dropna().astype(str).str.strip()
    cuenta = cuenta[cuenta.str.len() > 3].value_counts()
    return list(cuenta.head(300).index)


@st.cache_data(show_spinner=False)
def licitaciones_recientes(sello: str) -> list[dict]:
    """Lo publicado en el ultimo mes de la bodega, para la vista previa."""
    return alertador.fuente_de_prueba(dias=31)


# --------------------------------------------------------------------------
#  Guardar
# --------------------------------------------------------------------------
def _supabase() -> tuple[str, str]:
    """Las credenciales, si estan puestas en los secretos de Streamlit."""
    try:
        bloque = st.secrets["supabase"]
        return str(bloque["url"]).rstrip("/"), str(bloque["secret_key"])
    except Exception:
        return "", ""


def guardar_en_supabase(config: dict) -> tuple[bool, str]:
    """Da de alta al suscriptor y deja su filtro. Devuelve (salio bien, aviso)."""
    import urllib.error
    import urllib.request

    url, clave = _supabase()
    if not url or not clave:
        return False, "Faltan las credenciales de Supabase en los secretos."

    cabeceras = {
        "apikey": clave,
        "Authorization": f"Bearer {clave}",
        "Content-Type": "application/json",
        "Prefer": "return=representation,resolution=merge-duplicates",
    }

    def llamar(ruta: str, cuerpo, metodo="POST"):
        peticion = urllib.request.Request(
            f"{url}/rest/v1/{ruta}",
            data=json.dumps(cuerpo).encode("utf-8"),
            method=metodo, headers=cabeceras)
        with urllib.request.urlopen(peticion, timeout=60) as respuesta:
            texto = respuesta.read().decode("utf-8")
            return json.loads(texto) if texto.strip() else []

    try:
        # `on_conflict=email` hace que volver a guardar actualice en vez de
        # reventar por el unico de correo.
        filas = llamar("suscriptores?on_conflict=email", [{
            "email": config["email"],
            "nombre": config.get("nombre") or None,
            "empresa": config.get("empresa") or None,
            "rut_empresa": config.get("rut_proveedor") or None,
            "activo": True,
        }])
        if not filas:
            return False, "Supabase no devolvio el suscriptor."
        suscriptor_id = filas[0]["id"]

        # El filtro se reemplaza entero: es mas simple y no deja restos.
        llamar(f"filtros?suscriptor_id=eq.{suscriptor_id}", [], metodo="DELETE")
        llamar("filtros", [{
            "suscriptor_id": suscriptor_id,
            "rut_proveedor": config.get("rut_proveedor") or None,
            "correos_envio": config.get("correos_envio") or [],
            "hora_envio": int(config.get("hora_envio") or 8),
            "rubros": config.get("rubros") or [],
            "palabras_clave": config.get("palabras_clave") or [],
            "regiones": config.get("regiones") or [],
            "monto_minimo": int(config.get("monto_minimo") or 0),
            "frecuencia": "diaria",
            "incluye_licitaciones": bool(config.get("incluye_licitaciones", True)),
            "incluye_compras_agiles": bool(config.get("incluye_compras_agiles", True)),
        }])
        hora = int(config.get("hora_envio") or 8)
        return True, f"Guardado. El correo sale de lunes a viernes a las {hora}:00."
    except urllib.error.HTTPError as error:
        return False, f"Supabase respondió {error.code}: {error.read().decode('utf-8')[:200]}"
    except Exception as error:
        return False, f"{type(error).__name__}: {error}"


# --------------------------------------------------------------------------
#  La pantalla
# --------------------------------------------------------------------------
def seccion_alertas():
    st.subheader("Alertas por correo")
    st.caption("Lo que se configure acá es lo que llega cada mañana a las 08:00, "
               "de lunes a viernes. Si un día no hay nada que calce, no se envía.")

    # Los desplegables con muchas etiquetas —16 regiones, por ejemplo— crecen
    # hacia abajo y se montaban encima del campo siguiente. Con un poco de aire
    # entre widgets y dejando que la caja crezca, cada uno se queda en su sitio.
    st.markdown(
        """
        <style>
        [data-testid="stMultiSelect"] { margin-bottom: 14px; }
        [data-testid="stMultiSelect"] div[data-baseweb="select"] > div {
            max-height: none; min-height: 42px; flex-wrap: wrap;
        }
        [data-testid="stTextInput"], [data-testid="stNumberInput"] { margin-bottom: 10px; }
        </style>
        """,
        unsafe_allow_html=True,
    )

    sello = _sello()
    oc = cargar_ordenes(sello)

    izquierda, derecha = st.columns([1, 1], gap="large")

    with izquierda:
        st.markdown("**A quién llega**")
        email = st.text_input(
            "Correo registrado", key="al_email", placeholder="nombre@empresa.cl",
            help="Es la cuenta: identifica la suscripción y respalda el "
                 "consentimiento. Siempre recibe el correo.")
        nombre = st.text_input("Nombre", key="al_nombre", placeholder="Nombre y apellido")

        # Una cuenta, un correo. Decidido el 27-08-2026.
        #
        # Hubo un campo para agregar destinatarios en copia y se saco: el correo
        # ES la identidad de la cuenta y el respaldo del consentimiento, y si el
        # aviso puede llegar a direcciones que nadie inscribio, esa cadena se
        # rompe —quien recibe no puede darse de baja de algo que no pidio—.
        # Quien quiera recibirlo, se inscribe.
        #
        # La columna `correos_envio` sigue existiendo en la base y `alertador.py`
        # la sabe leer; simplemente llega siempre vacia. Si algun dia se decide
        # al reves, es volver a poner el campo y nada mas.
        correos_envio: list[str] = []

        st.markdown("**Qué avisar**")
        rut = st.text_input(
            "RUT del proveedor (opcional)", key="al_rut", placeholder="77.082.051-0",
            help="Con esto las palabras salen solas de lo que ese RUT ya vendió "
                 "en Convenio Marco. Si no tiene Convenio Marco, hay que usar "
                 "los rubros o las palabras de abajo.")

        del_rut, convenios = set(), []
        if rut.strip():
            del_rut, convenios = alertador.terminos_del_rut(rut, oc)
            if del_rut:
                st.success(f"Ese RUT vende en {len(convenios)} convenios marco. "
                           f"De ahí salieron {len(del_rut)} palabras solas.")
            else:
                st.warning("Ese RUT no aparece vendiendo en Convenio Marco. "
                           "El RUT solo no alcanza: hay que elegir rubros o "
                           "escribir palabras.")

        # UN SOLO CAMPO, no dos.
        #
        # Antes habia «Rubros» y «Palabras clave» separados, y nadie sabia cual
        # usar. Ahora es una sola pregunta con los 58 rubros ya cargados: se
        # empieza a escribir «alim» y aparecen los rubros de alimentos para
        # elegir. Si ninguno calza, la palabra propia se agrega igual.
        #
        # Eso resuelve las dos cosas a la vez: quien no quiere pensar elige de
        # la lista —que es lo que pidio Serling para gente mayor, que prefiere
        # reconocer antes que escribir— y quien sabe exactamente lo que vende
        # escribe su palabra y sigue.
        catalogo = rubros_disponibles(sello)
        try:
            elegidas_qv = st.multiselect(
                "¿Qué vendes?", options=catalogo, key="al_que_vendes",
                accept_new_options=True,
                placeholder="Escribe «alimentos», «aseo»… y elige de la lista",
                help="Empieza a escribir y te muestra los rubros que se parecen. "
                     "Si ninguno calza, escribe tu palabra y aprieta Enter: "
                     "queda igual.")
        except TypeError:
            # `accept_new_options` existe desde Streamlit 1.48. En una version
            # mas vieja esto reventaria y dejaria la pantalla en blanco; asi al
            # menos se pueden elegir rubros de la lista.
            elegidas_qv = st.multiselect(
                "¿Qué vendes?", options=catalogo, key="al_que_vendes",
                placeholder="Elige de la lista")

        # Lo elegido se separa: lo que estaba en la lista es rubro; lo que
        # escribio de su cabeza es palabra clave. La base los guarda aparte.
        conocidos = set(catalogo)
        rubros = [x for x in elegidas_qv if x in conocidos]
        palabras_clave = [x for x in elegidas_qv if x not in conocidos]

        if elegidas_qv:
            partes = []
            if rubros:
                partes.append(f"{len(rubros)} rubro" + ("s" if len(rubros) > 1 else ""))
            if palabras_clave:
                partes.append(f"{len(palabras_clave)} palabra" +
                              ("s propias" if len(palabras_clave) > 1 else " propia"))
            st.caption("Vas con " + " y ".join(partes) + ".")
        else:
            st.caption("Si escribiste tu RUT arriba, esto es opcional: las "
                       "palabras salen solas de lo que ya has vendido.")

        st.markdown("**Dónde y desde cuánto**")
        regiones = st.multiselect("Regiones", options=REGIONES, key="al_regiones",
                                  help="Vacío = todo Chile.")
        monto_minimo = st.number_input("Monto mínimo (CLP)", min_value=0, step=100_000,
                                       value=0, key="al_monto")

        st.markdown("**Qué tipo de aviso**")
        incluye_lic = st.checkbox("Licitaciones", value=True, key="al_lic")
        incluye_agil = st.checkbox("Compras ágiles (cierran en 24-72 horas)",
                                   value=True, key="al_agil")

        st.markdown("**A qué hora**")
        hora_envio = st.radio(
            "Turno", options=[8, 13, 18], horizontal=True, key="al_hora",
            format_func=lambda h: f"{h}:00",
            help="Hora de Chile, de lunes a viernes. Las 08:00 es después de "
                 "que la bodega se actualiza de madrugada.")

    config = {
        "email": email.strip(),
        "nombre": nombre.strip(),
        "rut_proveedor": rut.strip(),
        "correos_envio": correos_envio,
        "hora_envio": hora_envio,
        "rubros": rubros,
        "palabras_clave": palabras_clave,
        "regiones": regiones,
        "monto_minimo": monto_minimo,
        "incluye_licitaciones": incluye_lic,
        "incluye_compras_agiles": incluye_agil,
    }

    with derecha:
        st.markdown("**Qué habría llegado**")
        st.caption("Calculado contra las licitaciones del último mes que ya están "
                   "en la bodega, con las mismas reglas que usa el correo.")

        bolsa, _, origen = alertador.bolsa_de_terminos(config, oc)

        if not bolsa:
            st.info("Todavía no hay con qué filtrar. Escribe un RUT que venda en "
                    "Convenio Marco, elige rubros o escribe palabras clave.")
        else:
            universo = licitaciones_recientes(sello)
            bolsa = alertador.quitar_palabras_de_todos(bolsa, universo)
            minimo = alertador.minimo_coincidencias(bolsa)

            elegidas = []
            for op in universo:
                encaje = alertador.le_sirve(op, bolsa, config)
                if encaje < minimo:
                    continue
                retrato = alertador.retrato_del_comprador(op.get("unidad"), oc, convenios)
                valor, clase = alertador.nota(retrato)
                elegidas.append({**op, "encaje": encaje, "retrato": retrato,
                                 "nota": valor, "clase": clase})
            elegidas.sort(key=lambda x: (x["nota"], x["encaje"]), reverse=True)

            uno, dos, tres = st.columns(3)
            uno.metric("En el último mes", len(elegidas))
            dos.metric("Al día", f"{len(elegidas)/30:.1f}")
            tres.metric("Filtro", origen.split(" + ")[0] if origen else "—")

            if not elegidas:
                st.warning("Con esta configuración no habría llegado nada. "
                           "Conviene agregar palabras o quitar el filtro de región.")
            else:
                tabla = pd.DataFrame([{
                    "Prioridad": f"{o['clase']} {o['nota']}",
                    "Oportunidad": o["nombre"][:70],
                    "Comprador": (o["nombre_unidad"] or o["organismo"])[:40],
                    "Gasto 24m": o["retrato"]["gasto"],
                } for o in elegidas[:20]])
                st.dataframe(tabla, hide_index=True, use_container_width=True,
                             column_config={"Gasto 24m": st.column_config.NumberColumn(
                                 format="localized")})
                if len(elegidas) > 20:
                    st.caption(f"y {len(elegidas) - 20} más. El correo manda "
                               f"máximo {alertador.MAXIMO_POR_CORREO} por vez, "
                               "las de mejor prioridad.")

    st.divider()

    # La explicacion va ANTES de los botones, no despues: se lee para decidir
    # cual apretar, no para entender lo que uno ya apreto.
    st.markdown("#### ¿Y ahora qué?")
    uno, dos = st.columns([1, 1])
    uno.info("**Dejarla programada**\n\nLa alerta queda activa y el correo te "
             f"llega **cada día a las {hora_envio}:00**, de lunes a viernes. "
             "Si un día no hay nada que calce, no se envía.")
    dos.info("**Programarla y recibir la primera ahora**\n\nLo mismo de la "
             "izquierda, y además te manda **un correo en este momento** con "
             "lo que está abierto hoy. Tarda hasta un minuto.")

    boton_guardar, boton_ahora = st.columns([1, 1])
    with boton_guardar:
        guardar = st.button("Programar la alerta diaria", type="primary",
                            width="stretch", key="al_guardar")
    with boton_ahora:
        guardar_y_enviar = st.button("Programar y enviármela ahora",
                                     width="stretch", key="al_guardar_envia")

    if guardar or guardar_y_enviar:
        if not config["email"] or "@" not in config["email"]:
            st.error("Falta el correo.")
        elif not alertador.bolsa_de_terminos(config, oc)[0]:
            st.error("Falta decir qué avisar: un RUT con Convenio Marco, "
                     "rubros o palabras clave.")
        else:
            salio, aviso = guardar_en_supabase(config)
            if salio:
                st.success(aviso)
                st.session_state["al_guardado"] = config
                if guardar_y_enviar:
                    aviso_paso = st.empty()
                    fue, detalle = enviar_ahora(config, oc, aviso_paso)
                    aviso_paso.empty()
                    if fue:
                        st.success(detalle + " Revisa tu bandeja.")
                    else:
                        st.warning(detalle)
            else:
                st.error(aviso)
                st.download_button(
                    "Bajar la configuración como archivo",
                    data=json.dumps({"suscriptores": [config]}, ensure_ascii=False, indent=2),
                    file_name="alertas_config.json", mime="application/json",
                    help="Sirve para probar el correo en el computador mientras "
                         "no estén las credenciales de Supabase.")

    st.caption(
        "El botón de la derecha hace las dos cosas: deja la alerta configurada "
        "y manda el primer correo en el momento, sin esperar al turno de mañana."
    )


# --------------------------------------------------------------------------
#  «Mándamelo ahora»
# --------------------------------------------------------------------------
def enviar_ahora(config: dict, oc, aviso=None) -> tuple[bool, str]:
    """
    Manda el primer correo en el momento, sin esperar al turno de mañana.

    POR QUE ESTO IMPORTA MAS DE LO QUE PARECE
    -----------------------------------------
    Quien acaba de inscribirse esta caliente: acaba de ver su mapa y quiere
    algo. Si hay que decirle «te llega mañana a las 8», se enfria. Este boton
    le pone el producto en el correo mientras todavia esta mirando.

    NO ES LA CORRIDA COMPLETA, A PROPOSITO
    --------------------------------------
    La del workflow pide el detalle de hasta 400 licitaciones, con 2 segundos
    de espera obligatorios entre cada una: son diez minutos. Nadie espera diez
    minutos frente a una pantalla. Aca se piden solo las 20 que mas calzan,
    que es menos de un minuto, y las compras agiles del dia, que son rapidas.
    El correo de mañana ya trae el barrido entero.
    """
    ticket = ""
    try:
        ticket = str(st.secrets["mercadopublico"]["ticket"])
    except Exception:
        return False, "Falta el ticket de Mercado Público en los secretos."

    if "RESEND_API_KEY" not in os.environ:
        try:
            os.environ["RESEND_API_KEY"] = str(st.secrets["resend"]["api_key"])
        except Exception:
            return False, (
                "Falta la clave de Resend en los secretos de Streamlit. "
                "Agrega un bloque `[resend]` con `api_key = \"re_...\"` y "
                "vuelve a intentar. El correo de mañana no la necesita acá: "
                "esa vive en los secretos de GitHub."
            )

    bolsa, convenios, _ = alertador.bolsa_de_terminos(config, oc)
    if not bolsa:
        return False, "No hay con qué filtrar todavía."

    # ESTOS DOS TECHOS SON LO QUE HACE QUE ESTO SIRVA COMO BOTON.
    #
    # Sin ellos la primera version se quedo 13 minutos dando vueltas y nunca
    # llego: `compras_agiles_abiertas` trae por defecto hasta 40 paginas de 50
    # —dos mil— y esa API contesta lenta y a veces con 504. Nadie mira un
    # spinner 13 minutos: se va, y se llevo la impresion de que no funciona.
    #
    # Aca se piden 12 detalles de licitacion (12 x 2 s = 24 s) y 4 paginas de
    # compras agiles. Es una probada, no el barrido: el correo de mañana si
    # hace el recorrido completo.
    def paso(texto):
        if aviso is not None:
            aviso.info(texto)

    paso("Preguntando qué licitaciones hay abiertas…")
    universo = alertador.licitaciones_abiertas(ticket, bolsa, techo=12)
    paso(f"{len(universo)} licitaciones. Ahora las compras ágiles del día…")
    universo += alertador.compras_agiles_abiertas(ticket, techo_paginas=4)
    paso(f"{len(universo)} oportunidades abiertas. Cruzando con la bodega…")
    if not universo:
        return False, "Hoy no se publicó nada. Mañana a primera hora se revisa de nuevo."

    bolsa = alertador.quitar_palabras_de_todos(bolsa, universo)
    minimo = alertador.minimo_coincidencias(bolsa)
    elegidas = []
    for op in universo:
        encaje = alertador.le_sirve(op, bolsa, config)
        if encaje < minimo:
            continue
        retrato = alertador.retrato_del_comprador(op.get("unidad"), oc, convenios)
        valor, clase = alertador.nota(retrato)
        elegidas.append({**op, "encaje": encaje, "retrato": retrato, "nota": valor,
                         "clase": clase, "enlace": alertador.enlace(op)})

    elegidas.sort(key=lambda x: (x["encaje"], x["nota"]), reverse=True)
    elegidas = elegidas[:alertador.MAXIMO_POR_CORREO]

    if not elegidas:
        pista = ""
        if not config.get("rut_proveedor"):
            pista = (" Con solo palabras clave el filtro queda angosto: escribe "
                     "tu RUT y las palabras salen solas de lo que ya has vendido.")
        return False, ("Hoy no hay nada que calce con lo tuyo. No se manda un correo "
                       "vacío: el silencio también es información." + pista)

    html = alertador.armar_correo(
        {**config, "token_baja": "prueba", "rut_empresa": config.get("rut_proveedor")},
        elegidas)
    asunto = f"{len(elegidas)} oportunidades de hoy · Uplevel"

    if alertador.enviar(alertador.destinatarios(config), asunto, html):
        return True, f"Enviado a {config['email']} · {len(elegidas)} oportunidades."
    return False, "Resend no aceptó el envío. Revisa la clave."
