"""
MÓDULO SEGUIMIENTO — en qué quedó cada oportunidad que se avisó
================================================================

EL AGUJERO QUE TAPA
-------------------
Hasta hoy el correo mandaba y se olvidaba. `envios` guardaba que algo se
envio, no que paso despues: nadie sabia si esa licitacion se postulo, se gano
o se dejo pasar. Al cabo de un año no se podia decir «esto te consiguio $X»,
que es justamente la frase de la que depende que alguien renueve.

SEIS ETAPAS
-----------
    por revisar   recien llego, nadie la ha mirado
    siguiendo     interesa, se esta juntando informacion
    ofertando     se presento oferta
    ganada        adjudicada
    perdida       se la llevo otro
    descartada    no servia. Se guarda: saber que NO sirve tambien es dato

«Por revisar» no se guarda en ninguna parte: es simplemente no tener fila en
`seguimiento`. Asi el embudo funciona desde el primer dia, incluso con lo que
se envio antes de que la tabla existiera.

CUATRO DIFERENCIAS CON LO QUE HACEN OTROS
-----------------------------------------
1. EL EMBUDO ES DE LA EMPRESA, NO DE LA PERSONA. La llave es el RUT. Si el
   comercial del norte marca una como «ofertando», su jefa lo ve sin
   preguntar. Se guarda quien la movio, para saber de quien fue.

2. LAS TARJETAS MUESTRAN PLATA, NO SOLO CUENTA. «8 oportunidades» no le dice
   nada a nadie; «$14 M en juego» si. Y es la cifra que al año contesta si
   esto sirvio o no.

3. LA URGENCIA SE CALCULA Y DEPENDE DEL TIPO. Una compra agil que cierra en
   20 horas es normal: se responde con un precio. Una licitacion que cierra
   en 20 horas es otra cosa —hay que preparar bases, anexos, a veces visita a
   terreno— y avisar «cierra pronto» sin decir que ya no alcanza es enviar a
   alguien a perder la tarde.

4. EL «POR QUE CALZO» SON LAS PALABRAS REALES. No «match perfecto», que no se
   puede comprobar ni discutir, sino «alimentos, emergencia, colchon»: el que
   lo lee sabe al tiro si el sistema entendio su negocio, y si no, sabe que
   palabra corregir.
"""
import urllib.parse

import pandas as pd
import streamlit as st

import modulo_cuentas

# El orden importa: es el del embudo, de la primera etapa a la ultima.
ETAPAS = {
    "por_revisar": "Por revisar",
    "siguiendo": "Siguiendo",
    "ofertando": "Ofertando",
    "ganada": "Ganada",
    "perdida": "Perdida",
    "descartada": "Descartada",
}

# Las que cuentan como «seguimiento vigente»: ni cerradas ni descartadas.
VIGENTES = ("por_revisar", "siguiendo", "ofertando")

# Cuantas horas antes del cierre se considera que ya no se alcanza a preparar.
# Distinto por tipo, y esa es la gracia: una compra agil se contesta con un
# precio, una licitacion hay que armarla.
HORAS_JUSTAS = {"compra_agil": 12, "licitacion": 72}


# --------------------------------------------------------------------------
#  Datos
# --------------------------------------------------------------------------
def _pedir(ruta: str, metodo: str = "GET", cuerpo=None, extra: dict | None = None):
    """Reusa el cliente de `modulo_cuentas`: una sola forma de hablarle a Supabase."""
    return modulo_cuentas._pedir(ruta, metodo, cuerpo, extra)


@st.cache_data(ttl=60, show_spinner=False)
def cargar(rut: str) -> pd.DataFrame:
    """Todo lo avisado a ese RUT, con la etapa en que va cada una.

    Un minuto de cache: es una lista que se mira y se mueve, y esperar cinco
    minutos a que aparezca el cambio que uno acaba de hacer se siente roto.
    """
    if not rut:
        return pd.DataFrame()

    enviados = _pedir(
        "envios?select=codigo_licitacion,tipo,nombre,comprador,region,monto,"
        f"cierre,encaje,motivo,enlace,creado&rut=eq.{urllib.parse.quote(rut)}"
        "&order=codigo_licitacion")
    if enviados is None:
        # Puede que la columna `creado` no exista en esta base: se reintenta
        # sin ella antes de darse por vencido.
        enviados = _pedir(
            "envios?select=codigo_licitacion,tipo,nombre,comprador,region,monto,"
            f"cierre,encaje,motivo,enlace&rut=eq.{urllib.parse.quote(rut)}")
    if not enviados:
        return pd.DataFrame()

    tabla = pd.DataFrame(enviados).rename(columns={"codigo_licitacion": "codigo"})
    tabla = tabla.drop_duplicates(subset="codigo", keep="last")

    etapas = _pedir("seguimiento?select=codigo,estado,quien,cuando,nota,"
                    f"monto_ofertado&rut=eq.{urllib.parse.quote(rut)}")
    if etapas:
        tabla = tabla.merge(pd.DataFrame(etapas), on="codigo", how="left")
    for columna in ("estado", "quien", "cuando", "nota", "monto_ofertado"):
        if columna not in tabla:
            tabla[columna] = None
    # Sin fila de seguimiento significa «por revisar». No se escribe nada al
    # enviar: la etapa inicial es la ausencia de dato.
    tabla["estado"] = tabla["estado"].fillna("por_revisar")
    tabla["monto"] = pd.to_numeric(tabla["monto"], errors="coerce").fillna(0.0)
    return tabla


def guardar_etapa(rut: str, codigo: str, estado: str, quien: str,
                  nota: str = "") -> bool:
    """Mueve una oportunidad de etapa. `on_conflict` porque la llave es (rut, codigo)."""
    filas = _pedir("seguimiento?on_conflict=rut,codigo", "POST", [{
        "rut": rut, "codigo": codigo, "estado": estado,
        "quien": quien or None, "nota": nota or None,
        "cuando": pd.Timestamp.now("UTC").isoformat(),
    }], extra={"Prefer": "return=representation,resolution=merge-duplicates"})
    return filas is not None


def ultima_visita(rut: str, email: str) -> pd.Timestamp | None:
    """Cuándo miró esta persona por última vez. None si es la primera."""
    if not rut or not email:
        return None
    filas = _pedir(f"visitas?select=cuando&rut=eq.{urllib.parse.quote(rut)}"
                   f"&email=eq.{urllib.parse.quote(email)}&limit=1")
    if not filas:
        return None
    return pd.to_datetime(filas[0]["cuando"], errors="coerce", utc=True)


def anotar_visita(rut: str, email: str) -> None:
    """Deja la marca de que esta persona ya miró, para el «nuevas desde…»."""
    if not rut or not email:
        return
    _pedir("visitas?on_conflict=rut,email", "POST", [{
        "rut": rut, "email": email,
        "cuando": pd.Timestamp.now("UTC").isoformat(),
    }], extra={"Prefer": "resolution=merge-duplicates"})


# --------------------------------------------------------------------------
#  La urgencia, que es lo que de verdad se mira
# --------------------------------------------------------------------------
def _cuando_cierra(texto) -> pd.Timestamp | None:
    """La fecha de cierre, venga como venga.

    La API la entrega de varias formas: «2026-08-31», «2026-08-31T16:00:00»,
    a veces con hora y a veces no. Se intenta el formato ISO primero, que es
    el que llega casi siempre, y solo si falla se prueba con el dia adelante.
    """
    crudo = str(texto or "").strip()
    if crudo in ("", "None", "nan", "NaT"):
        return None
    # ISO primero, que es como llega casi siempre, y con formato explicito
    # para que pandas no tenga que adivinar ni avisar por consola.
    for formato in ("ISO8601", None):
        try:
            fecha = (pd.to_datetime(crudo, format=formato, errors="coerce", utc=True)
                     if formato else
                     pd.to_datetime(crudo, errors="coerce", utc=True, dayfirst=True))
        except Exception:
            continue
        if not pd.isna(fecha):
            return fecha
    return None


def urgencia(cierre, tipo: str) -> tuple[str, str]:
    """Devuelve (etiqueta para mostrar, gravedad).

    La gravedad depende del TIPO, y ahi esta la diferencia con avisar «cierra
    pronto» a secas. Una compra agil que cierra en 20 horas se contesta con un
    precio y no tiene nada de raro. Una licitacion que cierra en 20 horas ya
    no se alcanza a preparar, y decirle a alguien que corra hacia algo que no
    va a llegar a tiempo es peor que no decirle nada.
    """
    fecha = _cuando_cierra(cierre)
    if fecha is None:
        return "sin fecha", "ninguna"

    horas = (fecha - pd.Timestamp.now("UTC")).total_seconds() / 3600
    if horas < 0:
        return "cerrada", "cerrada"

    justo = HORAS_JUSTAS.get(tipo, 48)
    if horas < 24:
        dice = f"cierra en {int(horas)} h"
    else:
        dice = f"quedan {int(horas // 24)} días"

    if horas <= justo and tipo == "licitacion":
        return f"⚠️ {dice} — no alcanzas a preparar", "no_alcanza"
    if horas <= justo:
        return f"⚡ {dice}", "apura"
    return dice, "normal"


# --------------------------------------------------------------------------
#  Pantalla
# --------------------------------------------------------------------------
def _plata(monto: float) -> str:
    if abs(monto) >= 1e9:
        return f"${monto/1e6:,.0f} M".replace(",", ".")
    return f"${monto:,.0f}".replace(",", ".")


def _rut_en_juego(usuario: dict) -> str:
    """De qué empresa es este seguimiento.

    Primero el RUT de la cuenta de quien entró; si todavía no hay cuentas
    configuradas, el que se haya escrito en la pestaña Oportunidades. Así
    esto sirve antes y después de activar los roles.
    """
    from modulo_oportunidades import normalizar
    if usuario.get("rut") and usuario["rut"] != "UPLEVEL":
        return normalizar(usuario["rut"])
    return normalizar(st.session_state.get("op_rut", ""))


def seccion_seguimiento() -> None:
    st.subheader("Mis oportunidades")
    st.caption(
        "Todo lo que el correo te avisó, y en qué quedó cada una. Marca la "
        "etapa y el equipo entero lo ve: el seguimiento es de la empresa, no "
        "de quien lo anotó.")

    usuario = modulo_cuentas.quien_soy()
    rut = _rut_en_juego(usuario)
    if not rut:
        st.info(
            "No sé de qué empresa mostrarte el seguimiento. Escribe tu RUT en "
            "la pestaña **🎯 Oportunidades** —o pídele a tu administrador que "
            "lo deje puesto en la cuenta— y vuelve acá.")
        return

    datos = cargar(rut)
    if datos.empty:
        st.info(
            "Todavía no hay nada que seguir. Acá van a aparecer solas las "
            "oportunidades que te mande el correo diario.\n\n"
            "Si ya te llegaron correos y esto sigue vacío, es porque se "
            "enviaron antes de que existiera esta pantalla: desde el próximo "
            "correo empiezan a guardarse con todos sus datos.")
        return

    # ----------------------------------------------------------------------
    #  Lo nuevo desde la última visita
    # ----------------------------------------------------------------------
    visto = ultima_visita(rut, usuario.get("email") or "")
    nuevas = pd.DataFrame()
    if visto is not None and "creado" in datos.columns:
        llegada = pd.to_datetime(datos["creado"], errors="coerce", utc=True)
        nuevas = datos[llegada > visto]
        if len(nuevas):
            st.info(f"🆕 **{len(nuevas)} oportunidad(es) nueva(s)** desde tu "
                    f"última visita ({visto.tz_convert(None).strftime('%d/%m/%Y %H:%M')}).")

    # ----------------------------------------------------------------------
    #  El embudo, en plata
    # ----------------------------------------------------------------------
    # PLATA Y NO CUENTA: «8 oportunidades» no le dice nada a nadie. «$14 M en
    # juego» es la cifra que al año contesta si esto sirvio.
    cuenta = datos["estado"].value_counts()
    plata = datos.groupby("estado")["monto"].sum()
    tarjetas = st.columns(5)
    for columna, clave in zip(tarjetas, ("por_revisar", "siguiendo", "ofertando",
                                         "ganada", "perdida")):
        with columna:
            st.metric(ETAPAS[clave], f"{int(cuenta.get(clave, 0))}",
                      help=f"{_plata(float(plata.get(clave, 0)))} en esta etapa")
            st.caption(_plata(float(plata.get(clave, 0))))

    ganado = float(plata.get("ganada", 0))
    if ganado:
        st.success(f"**{_plata(ganado)} adjudicados** de oportunidades que salieron "
                   "de este correo.")

    # ----------------------------------------------------------------------
    #  Filtro
    # ----------------------------------------------------------------------
    st.divider()
    izquierda, derecha = st.columns([3, 2])
    with izquierda:
        mostrar = st.multiselect(
            "Qué etapas ver", list(ETAPAS), default=list(VIGENTES),
            format_func=lambda e: ETAPAS[e], key="sg_etapas")
    with derecha:
        ocultar_cerradas = st.checkbox("Esconder las que ya cerraron", value=True,
                                       key="sg_cerradas")

    vista = datos[datos["estado"].isin(mostrar)] if mostrar else datos
    marcas = [urgencia(c, t) for c, t in zip(vista["cierre"], vista["tipo"])]
    vista = vista.assign(plazo=[m[0] for m in marcas],
                         gravedad=[m[1] for m in marcas])
    if ocultar_cerradas:
        vista = vista[vista["gravedad"] != "cerrada"]

    if vista.empty:
        st.caption("Nada que mostrar con esos filtros.")
        return

    # Lo que apremia primero, y dentro de eso lo que más encaja.
    orden = {"no_alcanza": 0, "apura": 1, "normal": 2, "ninguna": 3, "cerrada": 4}
    vista = vista.assign(_o=vista["gravedad"].map(orden)).sort_values(
        ["_o", "encaje"], ascending=[True, False]).drop(columns="_o")

    st.caption(f"{len(vista)} oportunidad(es) · ordenadas por lo que apremia")
    st.dataframe(
        vista[["plazo", "nombre", "comprador", "region", "monto", "motivo",
               "encaje", "estado"]],
        width="stretch", hide_index=True, height=420,
        column_config={
            "plazo": st.column_config.TextColumn("Plazo", width="medium"),
            "nombre": st.column_config.TextColumn("Oportunidad", width="large"),
            "comprador": st.column_config.TextColumn("Comprador", width="medium"),
            "region": st.column_config.TextColumn("Región", width="medium"),
            "monto": st.column_config.NumberColumn("Monto", format="localized"),
            "motivo": st.column_config.TextColumn(
                "Por qué te llegó", width="medium",
                help="Las palabras tuyas que aparecieron en esta oportunidad"),
            "encaje": st.column_config.NumberColumn(
                "Encaje", help="Cuántas de tus palabras coincidieron"),
            "estado": st.column_config.TextColumn("Etapa", width="small"),
        })

    # ----------------------------------------------------------------------
    #  Mover una de etapa
    # ----------------------------------------------------------------------
    st.divider()
    st.markdown("**Mover una de etapa**")
    cual = st.selectbox(
        "¿Cuál?", vista["codigo"].tolist(), key="sg_cual",
        format_func=lambda c: (
            f"{str(vista[vista['codigo'] == c]['nombre'].iloc[0])[:70]} "
            f"({ETAPAS.get(vista[vista['codigo'] == c]['estado'].iloc[0], '')})"))
    fila = vista[vista["codigo"] == cual].iloc[0]

    a, b = st.columns([2, 3])
    with a:
        actual = str(fila["estado"])
        nueva = st.selectbox("Pasa a", list(ETAPAS),
                             index=list(ETAPAS).index(actual)
                             if actual in ETAPAS else 0,
                             format_func=lambda e: ETAPAS[e], key="sg_nueva")
    with b:
        nota = st.text_input("Nota (opcional)", key="sg_nota",
                             placeholder="Por qué, o con quién hablaste")

    # `pd.notna` y no un `if` a secas: la fila viene de un merge y lo que no
    # tiene seguimiento llega como NaN, que es «verdadero» para Python. Sin
    # esto la pantalla decia «La movió nan · nan» en todo lo que nadie habia
    # tocado, que es justamente el caso mas comun.
    quien = fila.get("quien")
    if pd.notna(quien) and str(quien).strip():
        cuando = fila.get("cuando")
        cuando = "" if pd.isna(cuando) else str(cuando)[:16].replace("T", " ")
        st.caption(f"La movió {quien}" + (f" · {cuando}" if cuando else ""))

    if st.button("Guardar etapa", type="primary", key="sg_guardar"):
        quien = usuario.get("email") or "(sin identificar)"
        if guardar_etapa(rut, cual, nueva, quien, nota):
            cargar.clear()
            st.success(f"Queda como **{ETAPAS[nueva]}**.")
            st.rerun()
        else:
            st.error("No se pudo guardar. ¿Corriste "
                     "`supabase-seguimiento-para-copiar.txt`?")

    # Se anota la visita AL FINAL, cuando ya se dibujo todo: si se anotara al
    # entrar, el «3 nuevas desde tu ultima visita» se borraria a si mismo
    # antes de que alcanzaran a leerlo.
    anotar_visita(rut, usuario.get("email") or "")
