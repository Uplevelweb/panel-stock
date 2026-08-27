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
    tabla["rut_limpio"] = tabla["rut_proveedor"].map(alertador.solo_digitos_rut)
    return tabla


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

        rubros = st.multiselect(
            "Rubros", options=rubros_disponibles(sello), key="al_rubros",
            help="Los que traen las propias licitaciones.")

        palabras_texto = st.text_input(
            "Palabras clave", key="al_palabras",
            placeholder="alimentos, aseo, papelería",
            help="Separadas por coma.")
        palabras_clave = [p.strip() for p in palabras_texto.split(",") if p.strip()]

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

            elegidas = []
            for op in universo:
                encaje = alertador.le_sirve(op, bolsa, config)
                if encaje < alertador.MINIMO_COINCIDENCIAS:
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

    if st.button("Guardar configuración", type="primary", key="al_guardar"):
        if not config["email"] or "@" not in config["email"]:
            st.error("Falta el correo.")
        elif not alertador.bolsa_de_terminos(config, oc)[0]:
            st.error("Falta decir qué avisar: un RUT con Convenio Marco, "
                     "rubros o palabras clave.")
        else:
            salio, aviso = guardar_en_supabase(config)
            if salio:
                st.success(aviso)
                # Se guarda para que el boton de «mándamelo ahora» siga en
                # pantalla despues de que Streamlit vuelva a dibujar todo.
                st.session_state["al_guardado"] = config
            else:
                st.error(aviso)
                st.download_button(
                    "Bajar la configuración como archivo",
                    data=json.dumps({"suscriptores": [config]}, ensure_ascii=False, indent=2),
                    file_name="alertas_config.json", mime="application/json",
                    help="Sirve para probar el correo en el computador mientras "
                         "no estén las credenciales de Supabase.")

    # Aparece recien despues de guardar: quien acaba de inscribirse esta
    # caliente y decirle «te llega mañana» lo enfria. Esto le pone el producto
    # en el correo mientras todavia esta mirando la pantalla.
    if st.session_state.get("al_guardado"):
        st.markdown("#### ¿Y hasta mañana?")
        st.caption("No hace falta esperar. Esto te manda el primero ahora mismo, "
                   "con lo que está abierto en este momento.")
        if st.button("Mándamelo ahora", type="primary", key="al_ahora"):
            with st.spinner("Preguntando a Mercado Público qué hay abierto…"):
                salio, aviso = enviar_ahora(st.session_state["al_guardado"], oc)
            if salio:
                st.success(aviso + " Revisa tu bandeja.")
            else:
                st.warning(aviso)


# --------------------------------------------------------------------------
#  «Mándamelo ahora»
# --------------------------------------------------------------------------
def enviar_ahora(config: dict, oc) -> tuple[bool, str]:
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

    universo = (alertador.licitaciones_abiertas(ticket, bolsa, techo=20)
                + alertador.compras_agiles_abiertas(ticket))
    if not universo:
        return False, "Hoy no se publicó nada. Mañana a primera hora se revisa de nuevo."

    bolsa = alertador.quitar_palabras_de_todos(bolsa, universo)
    elegidas = []
    for op in universo:
        encaje = alertador.le_sirve(op, bolsa, config)
        if encaje < alertador.MINIMO_COINCIDENCIAS:
            continue
        retrato = alertador.retrato_del_comprador(op.get("unidad"), oc, convenios)
        valor, clase = alertador.nota(retrato)
        elegidas.append({**op, "encaje": encaje, "retrato": retrato, "nota": valor,
                         "clase": clase, "enlace": alertador.enlace(op)})

    elegidas.sort(key=lambda x: (x["encaje"], x["nota"]), reverse=True)
    elegidas = elegidas[:alertador.MAXIMO_POR_CORREO]

    if not elegidas:
        return False, ("Hoy no hay nada que calce con lo tuyo. No se envía un correo "
                       "vacío: el silencio también es información.")

    html = alertador.armar_correo(
        {**config, "token_baja": "prueba", "rut_empresa": config.get("rut_proveedor")},
        elegidas)
    asunto = f"{len(elegidas)} oportunidades de hoy · Uplevel"

    if alertador.enviar(alertador.destinatarios(config), asunto, html):
        return True, f"Enviado a {config['email']} · {len(elegidas)} oportunidades."
    return False, "Resend no aceptó el envío. Revisa la clave."
