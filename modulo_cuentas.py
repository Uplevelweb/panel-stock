"""
MÓDULO CUENTAS — quién entró, de qué empresa es y qué le toca ver
==================================================================

Es la «fase TERRITORIO» que la spec original dejó fuera del MVP, y es lo que
habilita el plan Empresa: un RUT es una cuenta, el admin de esa cuenta crea a
sus comerciales y a cada uno le asigna su territorio.

TRES ROLES Y NADA MAS
---------------------
    superadmin  Uplevel. Ve TODAS las cuentas y desbloquea clientes
    admin       ve toda su empresa y administra a los demas
    comercial   ve solo su territorio

Se resistio la tentacion de inventar mas —«supervisor», «solo lectura»—
porque no los pidio nadie y cada rol nuevo es una regla mas que revisar en
cada pantalla.

`superadmin` no esta en `ROLES` a proposito: es lo que un admin puede repartir
dentro de su empresa, y un cliente no puede darse a si mismo la llave de las
cuentas de los demas.

NADIE TIENE CLAVE, Y ESO CAMBIA QUE SIGNIFICA «DESBLOQUEAR»
-----------------------------------------------------------
Se entra por correo, no por contraseña, asi que «se me olvido la clave» no
existe. Los bloqueos de verdad son otros: una empresa que desactivo a su
unico admin y desde adentro no tiene salida, o un correo mal escrito que deja
a alguien afuera sin ningun mensaje que lo explique. Eso es lo que arregla
`seccion_soporte`.

LA REGLA QUE MAS IMPORTA: NUNCA DEJAR A NADIE AFUERA
----------------------------------------------------
Si las tablas de Supabase todavia no existen, si faltan las credenciales, si
Streamlit no entrega el correo de quien entro, o si la consulta falla — el
panel se comporta EXACTAMENTE como antes de que existiera este modulo: se ve
todo. Un sistema de permisos que se cae dejando la puerta cerrada convierte
cualquier problema chico en «no puedo trabajar hoy».

La puerta de verdad sigue siendo otra: hoy es la lista de Streamlit («Manage
app ▸ Settings ▸ Sharing»), que decide quien puede ABRIR la app. Esto de aca
decide que ve adentro cada uno. Son dos cosas distintas y conviene no
confundirlas: mientras la puerta sea esa lista, agregar un comercial son dos
pasos, aca y alla. El dia que se quiera vender el plan Empresa de verdad hay
que cambiar la puerta por un login propio, y este modulo no cambia.

DE DONDE SALE EL CORREO
-----------------------
De `st.user`, que Streamlit llena solo cuando la app tiene identificacion de
usuarios. En local viene vacio, y por eso en local se ve todo.

POR QUE LA CLAVE SECRETA Y NO LA PUBLICA
----------------------------------------
Las consultas van con la clave secreta, del lado del servidor, que se salta
RLS. O sea: el que decide quien ve que es ESTE codigo, no la base. Es la misma
decision que ya estaba tomada en el resto del panel. La contrapartida es que
toda consulta tiene que filtrar por `cuenta_id` a mano; por eso el territorio
se aplica en un solo lugar, `filtrar_por_territorio`, y no repartido por las
pantallas.
"""
import json
import urllib.error
import urllib.parse
import urllib.request

import pandas as pd
import streamlit as st

# Los que un admin puede repartir dentro de su empresa. `superadmin` NO esta
# aca a proposito: es de Uplevel y no se lo puede dar un cliente a si mismo.
ROLES = ("admin", "comercial")
ROLES_TODOS = ("superadmin", "admin", "comercial")

# Lo que se devuelve cuando no hay a quien preguntarle: ve todo, como antes.
SIN_RESTRICCION = {
    "identificado": False,
    "email": "",
    "nombre": "",
    "rol": "admin",
    "cuenta_id": "",
    "empresa": "",
    "rut": "",
    "regiones": [],
    "comunas": [],
    "motivo": "sin cuentas configuradas",
}


# --------------------------------------------------------------------------
#  Supabase
# --------------------------------------------------------------------------
def _credenciales() -> tuple[str, str]:
    """La url y la clave secreta, si estan en los secretos de Streamlit."""
    try:
        bloque = st.secrets["supabase"]
        return str(bloque["url"]).rstrip("/"), str(bloque["secret_key"])
    except Exception:
        return "", ""


def _pedir(ruta: str, metodo: str = "GET", cuerpo=None, extra: dict | None = None):
    """Una llamada a PostgREST. Devuelve la lista de filas, o None si fallo.

    Devuelve None y no una lista vacia a proposito: hay que poder distinguir
    «no hay usuarios» de «no se pudo preguntar», porque lo segundo tiene que
    dejar pasar a todos y lo primero tambien, pero por motivos distintos y
    con distinto mensaje.
    """
    url, clave = _credenciales()
    if not url or not clave:
        return None
    cabeceras = {
        "apikey": clave,
        "Authorization": f"Bearer {clave}",
        "Content-Type": "application/json",
        "Accept": "application/json",
    }
    if extra:
        cabeceras.update(extra)
    datos = json.dumps(cuerpo).encode("utf-8") if cuerpo is not None else None
    peticion = urllib.request.Request(f"{url}/rest/v1/{ruta}", data=datos,
                                      method=metodo, headers=cabeceras)
    try:
        with urllib.request.urlopen(peticion, timeout=30) as respuesta:
            texto = respuesta.read().decode("utf-8")
            return json.loads(texto) if texto.strip() else []
    except Exception:
        return None


# --------------------------------------------------------------------------
#  Quien entro
# --------------------------------------------------------------------------
def correo_de_quien_entro() -> str:
    """El correo de la sesion, en minusculas. Vacio si no hay identificación."""
    try:
        correo = getattr(st.user, "email", "") or ""
    except Exception:
        correo = ""
    return str(correo).strip().lower()


@st.cache_data(ttl=300, show_spinner=False)
def _buscar_usuario(email: str) -> dict | None:
    """La ficha del usuario y su empresa. None si no se pudo preguntar.

    Se guarda cinco minutos: es una consulta por pantalla dibujada y no
    cambia casi nunca. Cinco minutos tambien es lo que tarda en aplicarse
    quitarle el acceso a alguien, y para eso esta el boton de refrescar.
    """
    if not email:
        return None
    filas = _pedir(
        "usuarios?select=email,nombre,rol,regiones,comunas,activo,cuenta_id,"
        f"cuentas(nombre,rut,activa)&email=eq.{urllib.parse.quote(email)}&limit=1")
    if filas is None:
        return None
    return filas[0] if filas else {}


def quien_soy() -> dict:
    """Quién entró y qué puede ver. Nunca revienta y nunca deja a nadie fuera."""
    email = correo_de_quien_entro()
    if not email:
        return dict(SIN_RESTRICCION, motivo="la app no identifica usuarios")

    ficha = _buscar_usuario(email)
    if ficha is None:
        return dict(SIN_RESTRICCION, email=email,
                    motivo="no se pudo consultar las cuentas")
    if not ficha:
        # El correo entro a la app pero no esta en ninguna cuenta. Se deja
        # pasar viendo todo, igual que antes: la puerta la controla la lista
        # de Streamlit, y ahi alguien ya decidio que esta persona puede entrar.
        return dict(SIN_RESTRICCION, email=email,
                    motivo="ese correo no está en ninguna cuenta")

    empresa = ficha.get("cuentas") or {}
    if isinstance(empresa, list):
        empresa = empresa[0] if empresa else {}

    if not ficha.get("activo", True) or not empresa.get("activa", True):
        return {
            "identificado": True, "email": email,
            "nombre": ficha.get("nombre") or "", "rol": "suspendido",
            "cuenta_id": ficha.get("cuenta_id") or "",
            "empresa": empresa.get("nombre") or "", "rut": empresa.get("rut") or "",
            "regiones": [], "comunas": [], "motivo": "cuenta o usuario desactivado",
        }

    rol = str(ficha.get("rol") or "comercial")
    return {
        "identificado": True,
        "email": email,
        "nombre": ficha.get("nombre") or "",
        "rol": rol if rol in ROLES_TODOS else "comercial",
        "cuenta_id": ficha.get("cuenta_id") or "",
        "empresa": empresa.get("nombre") or "",
        "rut": empresa.get("rut") or "",
        "regiones": list(ficha.get("regiones") or []),
        "comunas": list(ficha.get("comunas") or []),
        "motivo": "",
    }


# --------------------------------------------------------------------------
#  El territorio
# --------------------------------------------------------------------------
def es_soporte(usuario: dict) -> bool:
    """Si esta persona es de Uplevel y puede entrar a cualquier cuenta."""
    return usuario.get("rol") == "superadmin"


def tiene_territorio(usuario: dict) -> bool:
    """Si no se le asigno nada, ve toda la cuenta. Es a proposito.

    Una empresa con un solo vendedor no tiene por que configurar territorios
    para poder usar el panel.
    """
    if usuario.get("rol") in ("admin", "superadmin"):
        return False
    return bool(usuario.get("regiones") or usuario.get("comunas"))


def filtrar_por_territorio(tabla: pd.DataFrame, usuario: dict,
                           columna_region: str = "region",
                           columna_comuna: str = "comuna") -> pd.DataFrame:
    """Deja solo las filas que le tocan a esa persona.

    UN SOLO LUGAR PARA ESTA REGLA, a proposito. Repartida por las pantallas,
    tarde o temprano una se olvida y ahi el comercial de Antofagasta ve la
    cartera de Santiago sin que nadie se entere.

    Si tiene comunas asignadas mandan las comunas —es el caso de partir la
    Region Metropolitana entre dos personas— y si no, las regiones.
    """
    if tabla.empty or not tiene_territorio(usuario):
        return tabla

    comunas = {str(c).strip().lower() for c in usuario.get("comunas") or []}
    if comunas and columna_comuna in tabla.columns:
        suyas = tabla[columna_comuna].astype(str).str.strip().str.lower()
        return tabla[suyas.isin(comunas)]

    regiones = {str(r).strip().lower() for r in usuario.get("regiones") or []}
    if regiones and columna_region in tabla.columns:
        suyas = tabla[columna_region].astype(str).str.strip().str.lower()
        # Se compara «contiene» y no «igual»: la region viene escrita de
        # varias formas —«Region de Valparaiso», «Valparaiso»— segun de que
        # tabla salga, y un igualdad estricta descarta filas que si le tocan.
        return tabla[suyas.apply(lambda x: any(r in x or x in r for r in regiones))]

    return tabla


def resumen_de_territorio(usuario: dict) -> str:
    """Una linea para mostrar en pantalla qué está viendo esta persona."""
    if es_soporte(usuario):
        return "todas las cuentas (soporte Uplevel)"
    if usuario.get("rol") == "admin":
        return "toda la empresa"
    if usuario.get("comunas"):
        return f"{len(usuario['comunas'])} comunas"
    if usuario.get("regiones"):
        return ", ".join(usuario["regiones"])
    return "toda la empresa (sin territorio asignado)"


# --------------------------------------------------------------------------
#  La pantalla del admin
# --------------------------------------------------------------------------
def _guardar_usuario(cuenta_id: str, email: str, nombre: str, rol: str,
                     regiones: list, comunas: list, creado_por: str) -> tuple[bool, str]:
    """Da de alta o actualiza a una persona del equipo."""
    email = str(email).strip().lower()
    if "@" not in email or "." not in email.split("@")[-1]:
        return False, "Ese correo no se entiende."
    if rol not in ROLES:
        return False, "Rol desconocido."

    filas = _pedir("usuarios?on_conflict=email", "POST", [{
        "cuenta_id": cuenta_id,
        "email": email,
        "nombre": (nombre or "").strip() or None,
        "rol": rol,
        "regiones": regiones or [],
        "comunas": comunas or [],
        "activo": True,
        "creado_por": creado_por,
    }], extra={"Prefer": "return=representation,resolution=merge-duplicates"})
    if filas is None:
        return False, "No se pudo guardar. Revisa las credenciales de Supabase."
    return True, f"{email} quedó como {rol}."


def _cambiar_estado(email: str, activo: bool) -> bool:
    """Prender o apagar el acceso de alguien. Ver `_cambiar_campo`, más abajo."""
    return _cambiar_campo(email, "activo", activo)


def seccion_equipo(usuario: dict, regiones_posibles: list[str],
                   comunas_posibles: list[str]) -> None:
    """La pantalla donde el admin arma su equipo. Solo la ve el admin."""
    st.subheader("Mi equipo")

    if not usuario.get("identificado"):
        st.info(
            "**Todavía no hay cuentas configuradas**, así que el panel se "
            "comporta como siempre: quien puede abrirlo lo decide la lista de "
            "Streamlit y adentro se ve todo.\n\n"
            "Para activar cuentas y roles hay que pegar una vez el SQL de "
            "`supabase-cuentas-para-copiar.txt` en Supabase. Después esta "
            "pantalla se llena sola.")
        st.caption(f"Motivo exacto: {usuario.get('motivo')}.")
        return

    if usuario.get("rol") != "admin":
        st.warning("Esta pantalla es solo para el administrador de la cuenta.")
        st.caption(f"Tú entras como **comercial** y ves: "
                   f"{resumen_de_territorio(usuario)}.")
        return

    st.caption(f"Empresa **{usuario['empresa']}** · RUT {usuario['rut']}")

    filas = _pedir(f"usuarios?select=email,nombre,rol,regiones,comunas,activo"
                   f"&cuenta_id=eq.{usuario['cuenta_id']}&order=rol,email")
    if filas is None:
        st.error("No se pudo leer el equipo. Revisa las credenciales de Supabase.")
        return

    equipo = pd.DataFrame(filas)
    if not equipo.empty:
        vista = equipo.copy()
        vista["territorio"] = [
            f"{len(c)} comunas" if c else (", ".join(r) if r else "toda la empresa")
            for r, c in zip(vista["regiones"], vista["comunas"])]
        vista["estado"] = ["activo" if a else "desactivado" for a in vista["activo"]]
        st.dataframe(
            vista[["email", "nombre", "rol", "territorio", "estado"]],
            width="stretch", hide_index=True,
            column_config={
                "email": st.column_config.TextColumn("Correo", width="medium"),
                "nombre": st.column_config.TextColumn("Nombre"),
                "rol": st.column_config.TextColumn("Rol", width="small"),
                "territorio": st.column_config.TextColumn("Ve", width="medium"),
                "estado": st.column_config.TextColumn("Estado", width="small"),
            })

    st.divider()
    st.markdown("**Agregar o cambiar a alguien**")
    st.caption(
        "El correo tiene que ser el mismo con el que esa persona abre el "
        "panel. Si ya está en la lista, se actualiza en vez de duplicarse.")

    with st.form("equipo_alta", clear_on_submit=False):
        arriba_izq, arriba_der = st.columns(2)
        with arriba_izq:
            correo = st.text_input("Correo", placeholder="vendedor@empresa.cl")
        with arriba_der:
            nombre = st.text_input("Nombre", placeholder="Nombre y apellido")

        rol = st.radio("Rol", ROLES, horizontal=True,
                       help="El admin ve toda la empresa y puede administrar "
                            "esta pantalla. El comercial ve solo su territorio.")
        st.caption("El territorio se deja vacío si esa persona tiene que ver "
                   "toda la empresa.")
        elegidas_regiones = st.multiselect("Regiones que le tocan",
                                           options=regiones_posibles)
        elegidas_comunas = st.multiselect(
            "…o comunas exactas", options=comunas_posibles,
            help="Solo si hay que partir una región entre dos personas. Si "
                 "pones comunas, mandan las comunas y se ignoran las regiones.")

        if st.form_submit_button("Guardar", type="primary"):
            bien, aviso = _guardar_usuario(
                usuario["cuenta_id"], correo, nombre, rol,
                elegidas_regiones, elegidas_comunas, usuario["email"])
            if bien:
                _buscar_usuario.clear()
                st.success(aviso)
                st.rerun()
            else:
                st.error(aviso)

    if not equipo.empty:
        st.divider()
        st.markdown("**Quitar o devolver el acceso**")
        st.caption(
            "Desactivar no borra nada: la persona deja de ver datos y se puede "
            "volver a activar. Los datos de quién hizo qué se conservan.")
        # No se ofrece desactivarse a uno mismo: es la forma mas rapida de que
        # una cuenta se quede sin ningun administrador.
        otros = equipo[equipo["email"] != usuario["email"]]
        if otros.empty:
            st.caption("Todavía no hay nadie más en el equipo.")
        else:
            izquierda, derecha = st.columns([3, 2])
            with izquierda:
                a_quien = st.selectbox("Persona", otros["email"].tolist(),
                                       key="equipo_estado_quien")
            with derecha:
                st.write("")
                activo_hoy = bool(
                    otros[otros["email"] == a_quien]["activo"].iloc[0])
                etiqueta = "Desactivar" if activo_hoy else "Volver a activar"
                if st.button(etiqueta, width="stretch", key="equipo_estado_boton"):
                    if _cambiar_estado(a_quien, not activo_hoy):
                        _buscar_usuario.clear()
                        st.success(f"{a_quien}: {etiqueta.lower()} listo.")
                        st.rerun()
                    else:
                        st.error("No se pudo cambiar el estado.")

    st.divider()
    st.caption(
        "⚠️ **Esto decide qué ve cada uno adentro, no quién puede entrar.** "
        "Quién puede abrir el panel lo sigue decidiendo la lista de Streamlit "
        "(*Manage app ▸ Settings ▸ Sharing*), así que a cada persona nueva hay "
        "que agregarla en los dos lugares.")


# --------------------------------------------------------------------------
#  Soporte de Uplevel — el rol que puede desbloquear a cualquiera
# --------------------------------------------------------------------------
#
# ACLARACION QUE HAY QUE TENER PRESENTE: aca nadie tiene clave. Se entra por
# correo, asi que «se me olvido la contraseña» no existe como problema y esta
# pantalla no resetea ninguna. Lo que arregla es el bloqueo de verdad, que es
# otro: una empresa que desactivo a su unico admin y desde adentro ya no tiene
# como salir, o un correo mal escrito que deja a alguien afuera para siempre
# sin ningun mensaje de error.
#
# LO QUE ESTA PANTALLA NO PUEDE HACER: dejar entrar a alguien que no esta en
# la lista de Streamlit. Esa sigue siendo la puerta y se abre en otro lado.

def _anotar(quien: str, accion: str, sobre: str = "", cuenta: str = "",
            detalle: str = "") -> None:
    """Deja la huella en `bitacora_soporte`.

    Nunca interrumpe: si la bitacora fallara, es peor dejar al cliente
    bloqueado que perder una linea de registro.
    """
    _pedir("bitacora_soporte", "POST", [{
        "quien": quien, "accion": accion,
        "sobre_email": sobre or None, "cuenta": cuenta or None,
        "detalle": detalle or None,
    }])


def _todas_las_cuentas():
    filas = _pedir("cuentas?select=id,rut,nombre,plan,activa&order=nombre")
    return None if filas is None else pd.DataFrame(filas)


def _todos_los_usuarios():
    filas = _pedir("usuarios?select=email,nombre,rol,activo,cuenta_id,regiones,"
                   "comunas&order=email")
    return None if filas is None else pd.DataFrame(filas)


def _cambiar_campo(email: str, campo: str, valor) -> bool:
    """Cambia un campo de un usuario. True si quedo."""
    filas = _pedir(f"usuarios?email=eq.{urllib.parse.quote(email)}", "PATCH",
                   {campo: valor}, extra={"Prefer": "return=representation"})
    return filas is not None


def dejaria_sin_admin(usuarios: pd.DataFrame, email: str) -> bool:
    """Si apagar a esta persona deja a su empresa sin ningún administrador.

    LA REGLA VIVE ACA Y NO DENTRO DEL BOTON a proposito. Metida en la pantalla
    no se puede probar sin abrir un navegador y apretarlo, que es justo lo que
    nadie hace antes de entregar. Aca se prueba en una linea.

    Y es la regla que mas importa de esta pantalla: seria absurdo que la
    herramienta que existe para sacar a una empresa del bloqueo fuera capaz de
    meterla en uno.
    """
    if usuarios.empty or "email" not in usuarios.columns:
        return False
    fila = usuarios[usuarios["email"] == email]
    if fila.empty:
        return False
    fila = fila.iloc[0]
    if fila.get("rol") != "admin" or not fila.get("activo"):
        return False
    hermanos = usuarios[(usuarios["cuenta_id"] == fila["cuenta_id"])
                        & (usuarios["rol"] == "admin")
                        & (usuarios["activo"])]
    return len(hermanos) <= 1


def seccion_soporte(usuario: dict) -> None:
    """La pantalla de Uplevel para desbloquear clientes."""
    st.subheader("Soporte Uplevel")

    if not es_soporte(usuario):
        st.warning("Esta pantalla es solo para el soporte de Uplevel.")
        return

    st.caption(
        "Desde acá se desbloquean las cuentas de los clientes. **Nadie tiene "
        "contraseña en este sistema** —se entra por correo—, así que acá no se "
        "resetean claves: se reactiva a quien quedó desactivado, se corrige un "
        "correo mal escrito y se le devuelve el rol de administrador a una "
        "empresa que se quedó sin ninguno.")

    cuentas = _todas_las_cuentas()
    usuarios = _todos_los_usuarios()
    if cuentas is None or usuarios is None:
        st.error("No se pudo leer las cuentas. Si acabas de crear las tablas, "
                 "revisa que hayas corrido también "
                 "`supabase-soporte-para-copiar.txt`.")
        return
    if cuentas.empty or usuarios.empty:
        st.caption("Todavía no hay cuentas ni usuarios que administrar.")
        return

    # ----------------------------------------------------------------------
    #  Lo primero: las empresas que se quedaron sin administrador
    # ----------------------------------------------------------------------
    # Va arriba de todo porque es el UNICO problema que el cliente no puede
    # resolver solo. Todo lo demas puede esperar; esto no.
    con_admin = set(usuarios[(usuarios["rol"] == "admin")
                             & (usuarios["activo"])]["cuenta_id"])
    huerfanas = cuentas[(~cuentas["id"].isin(con_admin))
                        & (cuentas["rut"] != "UPLEVEL")]
    if len(huerfanas):
        st.error(f"**{len(huerfanas)} cuenta(s) sin ningún administrador "
                 "activo.** Esa empresa no puede administrarse a sí misma: "
                 "hay que devolverle el rol a alguien desde acá.")
        st.dataframe(huerfanas[["nombre", "rut", "activa"]],
                     width="stretch", hide_index=True)
    else:
        st.success("Todas las cuentas tienen al menos un administrador activo.")

    st.divider()
    st.markdown("**Todas las cuentas**")

    nombres = dict(zip(cuentas["id"], cuentas["nombre"]))
    vista = usuarios.copy()
    vista["empresa"] = vista["cuenta_id"].map(nombres).fillna("(sin cuenta)")
    vista["estado"] = ["activo" if a else "DESACTIVADO" for a in vista["activo"]]
    st.dataframe(
        vista[["empresa", "email", "nombre", "rol", "estado"]],
        width="stretch", hide_index=True, height=300,
        column_config={
            "empresa": st.column_config.TextColumn("Empresa", width="medium"),
            "email": st.column_config.TextColumn("Correo", width="medium"),
            "nombre": st.column_config.TextColumn("Nombre"),
            "rol": st.column_config.TextColumn("Rol", width="small"),
            "estado": st.column_config.TextColumn("Estado", width="small"),
        })

    st.divider()
    st.markdown("**Desbloquear a una persona**")

    a_quien = st.selectbox(
        "¿A quién?", vista["email"].tolist(), key="sop_quien",
        format_func=lambda e: (
            f"{e} — {vista[vista['email'] == e]['empresa'].iloc[0]}"))
    fila = vista[vista["email"] == a_quien].iloc[0]
    st.caption(f"Hoy es **{fila['rol']}** de {fila['empresa']} y está "
               f"**{fila['estado'].lower()}**.")

    columna_a, columna_b, columna_c = st.columns(3)

    # --- Reactivar o desactivar -------------------------------------------
    with columna_a:
        st.markdown("*Acceso*")
        activo = bool(fila["activo"])
        etiqueta = "Desactivar" if activo else "Reactivar"
        if st.button(etiqueta, key="sop_estado", width="stretch"):
            if activo and dejaria_sin_admin(usuarios, a_quien):
                st.error("Es el único administrador activo de esa empresa. "
                         "Primero deja a otra persona como administradora.")
            elif _cambiar_campo(a_quien, "activo", not activo):
                _anotar(usuario["email"], etiqueta.lower(), a_quien,
                        str(fila["empresa"]))
                _buscar_usuario.clear()
                st.success(f"{a_quien}: {etiqueta.lower()} listo.")
                st.rerun()
            else:
                st.error("No se pudo cambiar el estado.")

    # --- Devolver el rol de administrador ---------------------------------
    with columna_b:
        st.markdown("*Rol*")
        indice = ROLES.index(fila["rol"]) if fila["rol"] in ROLES else 1
        nuevo_rol = st.selectbox("Dejarlo como", ROLES, index=indice,
                                 key="sop_rol")
        if st.button("Cambiar rol", key="sop_rol_boton", width="stretch"):
            if fila["rol"] == "superadmin":
                st.error("El soporte de Uplevel no se cambia desde acá.")
            elif _cambiar_campo(a_quien, "rol", nuevo_rol):
                _anotar(usuario["email"], "cambiar rol", a_quien,
                        str(fila["empresa"]),
                        f"{fila['rol']} pasa a {nuevo_rol}")
                _buscar_usuario.clear()
                st.success(f"{a_quien} quedó como {nuevo_rol}.")
                st.rerun()
            else:
                st.error("No se pudo cambiar el rol.")

    # --- Corregir el correo -----------------------------------------------
    with columna_c:
        st.markdown("*Correo mal escrito*")
        correo_nuevo = st.text_input("Correo correcto", key="sop_correo",
                                     placeholder=a_quien)
        if st.button("Corregir", key="sop_correo_boton", width="stretch"):
            limpio = str(correo_nuevo).strip().lower()
            if "@" not in limpio or "." not in limpio.split("@")[-1]:
                st.error("Ese correo no se entiende.")
            elif limpio == a_quien:
                st.info("Es el mismo correo que ya tenía.")
            elif limpio in set(vista["email"]):
                st.error("Ya hay alguien con ese correo.")
            elif _cambiar_campo(a_quien, "email", limpio):
                _anotar(usuario["email"], "corregir correo", a_quien,
                        str(fila["empresa"]), f"{a_quien} pasa a {limpio}")
                _buscar_usuario.clear()
                st.success(f"Ahora entra como {limpio}. **Acuérdate de "
                           "cambiarlo también en la lista de Streamlit.**")
                st.rerun()
            else:
                st.error("No se pudo corregir el correo.")

    # ----------------------------------------------------------------------
    #  La bitacora
    # ----------------------------------------------------------------------
    st.divider()
    with st.expander("Qué se ha tocado desde acá"):
        st.caption(
            "Todo lo que hace el soporte queda anotado. No es burocracia: el "
            "soporte puede entrar a los datos de cualquier cliente, y ante un "
            "reclamo lo primero que se pregunta es quién tocó qué y cuándo.")
        registro = _pedir("bitacora_soporte?select=cuando,quien,accion,"
                          "sobre_email,cuenta,detalle&order=cuando.desc&limit=100")
        if registro is None:
            st.warning("No se pudo leer la bitácora. ¿Corriste el SQL de soporte?")
        elif not registro:
            st.caption("Todavía no se ha hecho nada desde esta pantalla.")
        else:
            tabla = pd.DataFrame(registro)
            tabla["cuando"] = (tabla["cuando"].astype(str)
                               .str.replace("T", " ").str[:16])
            st.dataframe(tabla, width="stretch", hide_index=True, height=280)
