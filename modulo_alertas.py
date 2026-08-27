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
        copias_texto = st.text_input(
            "Enviar también a (opcional)", key="al_copias",
            placeholder="comercial@empresa.cl, gerencia@empresa.cl",
            help="Separados por coma. Van en el MISMO mensaje, así que "
                 "gastan un envío de la cuota, no uno cada uno.")
        correos_envio = [c.strip() for c in copias_texto.split(",")
                         if c.strip() and "@" in c]
        if correos_envio:
            st.caption(f"Llegará a {len(correos_envio) + 1} personas en un solo envío.")

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
            else:
                st.error(aviso)
                st.download_button(
                    "Bajar la configuración como archivo",
                    data=json.dumps({"suscriptores": [config]}, ensure_ascii=False, indent=2),
                    file_name="alertas_config.json", mime="application/json",
                    help="Sirve para probar el correo en el computador mientras "
                         "no estén las credenciales de Supabase.")
