"""
AGENTE DE QA DE CUPIDOLICITA
============================

Prueba la version PUBLICADA de https://territorio.uplevelweb.art/cupido/ como lo
haria una persona, con una cuenta propia de prueba que vive en su propia empresa
(«Empresa de Prueba QA»): nunca toca datos de clientes ni manda correos.

Que revisa, en este orden:
  1. Cache: que /cupido/ se sirva con no-cache y que la version cargada sea la publicada;
     que /cupido/?limpiar=1 limpie lo guardado.
  2. Pantallas a 375 px: tablero, nueva licitacion, checklist, comentario en vivo, editor de
     anexos con firma, revision, sello, clave y postulacion, chat en vivo, Sala de Guerra,
     boveda (subir y borrar) y ROI. Sin desborde lateral, sin errores de consola, sin
     llamadas fallidas a Supabase.
  3. Las mismas pantallas en escritorio, solo carga.
  4. Estres: 120 llamadas a Supabase con 20 a la vez, y 5 navegadores abriendo a la vez.
  5. Seguridad: lo que la clave publica NO debe poder leer, lo que la cuenta de prueba NO
     debe poder ver ni escribir de otra empresa, y la revision de RLS contra la linea base
     qa/linea_base_seguridad.json.

Cada falla queda en la tabla qa_eventos (origen 'agente') y el workflow termina en rojo,
asi GitHub avisa por correo. Al final borra todo lo que creo.

Necesita SUPABASE_URL y SUPABASE_SECRET_KEY. Uso: python qa_cupido.py [--sin-estres]
"""
import json
import os
import random
import re
import statistics
import string
import sys
import time
import traceback
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from datetime import date, timedelta

from playwright.sync_api import sync_playwright

SITIO = "https://territorio.uplevelweb.art"
CUPIDO = SITIO + "/cupido/"
PUBLICA = "sb_publishable_kgLRqlc49ebATAS4DWt7Xg_IBtzSoZr"
CORREO = "qa-agente@qa.cupidolicita.invalid"
SUPA = os.environ["SUPABASE_URL"].strip().rstrip("/")
SECRETA = os.environ["SUPABASE_SECRET_KEY"].strip()
CAPTURAS = "qa_capturas"
CORRIDA = time.strftime("%m%d%H%M") + "".join(random.choices(string.ascii_uppercase, k=3))
LINEA_BASE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "qa", "linea_base_seguridad.json")

resultados = []   # (grupo, nombre, ok, detalle)
version_publicada = None


# ---------------------------------------------------------------- utilidades HTTP
def http(metodo, ruta, clave=None, token=None, cuerpo=None, extra=None, timeout=30):
    """Devuelve (status, cuerpo_json_o_texto, segundos). Nunca lanza por status."""
    cab = {"apikey": clave or PUBLICA, "Content-Type": "application/json"}
    if token:
        cab["Authorization"] = "Bearer " + token
    elif clave:
        cab["Authorization"] = "Bearer " + clave
    cab.update(extra or {})
    datos = json.dumps(cuerpo).encode() if cuerpo is not None else None
    req = urllib.request.Request(SUPA + ruta, data=datos, headers=cab, method=metodo)
    t = time.time()
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            txt = r.read().decode()
            st = r.status
    except urllib.error.HTTPError as e:
        txt, st = e.read().decode(errors="replace"), e.code
    except Exception as e:  # red caida, tiempo agotado
        return 0, str(e), time.time() - t
    try:
        return st, json.loads(txt) if txt else None, time.time() - t
    except ValueError:
        return st, txt, time.time() - t


def servicio(metodo, ruta, cuerpo=None, extra=None):
    return http(metodo, ruta, clave=SECRETA, cuerpo=cuerpo, extra=extra)


def anotar(grupo, nombre, ok, detalle=""):
    resultados.append((grupo, nombre, bool(ok), str(detalle)[:600]))
    print(("  OK   " if ok else "  FALLA") + f" [{grupo}] {nombre}" + ("" if ok else f" -> {detalle}"), flush=True)


def prueba(grupo, nombre):
    """Decorador: corre la funcion, anota OK o la excepcion como FALLA."""
    def envolver(fn):
        def correr(*a, **k):
            try:
                r = fn(*a, **k)
                anotar(grupo, nombre, True, r or "")
                return True
            except Exception as e:
                anotar(grupo, nombre, False, f"{type(e).__name__}: {e}")
                return False
        return correr
    return envolver


# ---------------------------------------------------------------- cuenta de prueba
def preparar_cuenta():
    st, r, _ = servicio("POST", "/auth/v1/admin/users", {"email": CORREO, "email_confirm": True})
    if st not in (200, 201, 422):
        raise RuntimeError(f"no se pudo crear la cuenta de prueba: {st} {r}")
    st, r, _ = servicio("POST", "/rest/v1/rpc/qa_preparar", {"p_email": CORREO})
    if st != 200 or not r.get("ok"):
        raise RuntimeError(f"qa_preparar: {st} {r}")
    limpiar_archivos(r["user_id"])
    return r["user_id"], r.get("otro_owner")


def limpiar_archivos(uid):
    """Borra los archivos de la empresa de prueba (Supabase no deja hacerlo por SQL)."""
    rutas, pendientes = [], [uid]
    while pendientes:
        prefijo = pendientes.pop()
        st, lista, _ = servicio("POST", "/storage/v1/object/list/boveda", {"prefix": prefijo + "/", "limit": 1000})
        if st != 200:
            return
        for o in lista or []:
            if o.get("id"):
                rutas.append(prefijo + "/" + o["name"])
            else:
                pendientes.append(prefijo + "/" + o["name"])
    if rutas:
        servicio("DELETE", "/storage/v1/object/boveda", {"prefixes": rutas})


def sesion():
    """Sesion de Supabase Auth sin contrasena: enlace magico generado por el servidor."""
    st, r, _ = servicio("POST", "/auth/v1/admin/generate_link", {"type": "magiclink", "email": CORREO})
    if st != 200:
        raise RuntimeError(f"generate_link: {st} {r}")
    token_hash = r.get("hashed_token") or (r.get("properties") or {}).get("hashed_token")
    st, s, _ = http("POST", "/auth/v1/verify", cuerpo={"type": "magiclink", "token_hash": token_hash})
    if st != 200 or "access_token" not in (s or {}):
        raise RuntimeError(f"verify: {st} {s}")
    return s


# ---------------------------------------------------------------- navegador
class Pantalla:
    def __init__(self, navegador, s, ancho, alto):
        self.ctx = navegador.new_context(viewport={"width": ancho, "height": alto}, locale="es-CL",
                                         timezone_id="America/Santiago")
        guardada = json.dumps({**s, "expires_at": s.get("expires_at") or int(time.time()) + int(s.get("expires_in", 3600))})
        # La sesion se pone antes de que corra la pagina, en la misma llave que usa el panel.
        self.ctx.add_init_script(
            "if (location.host === 'territorio.uplevelweb.art' && !sessionStorage.getItem('qa_puesta')) {"
            f" localStorage.setItem('territorio_auth', {json.dumps(guardada)}); sessionStorage.setItem('qa_puesta', '1'); }}")
        self.page = self.ctx.new_page()
        self.errores = []
        self.page.on("pageerror", lambda e: self.errores.append("pageerror: " + str(e)))
        self.page.on("console", lambda m: m.type == "error" and self.errores.append("consola: " + m.text))
        self.page.on("response", self._respuesta)
        self.page.on("dialog", lambda d: d.accept())
        self.ancho = ancho

    def _respuesta(self, r):
        if r.status >= 400 and ("supabase.co" in r.url or "uplevelweb.art" in r.url):
            self.errores.append(f"HTTP {r.status} {r.request.method} {r.url.split('?')[0]}")

    def ir(self, hash_):
        self.page.evaluate(f"location.hash = {json.dumps(hash_)}")
        self.listo()

    def listo(self, vista=None, espera=15000):
        self.page.wait_for_function(
            "() => { const m = document.getElementById('vista'); return m && m.dataset.listo && m.dataset.listo !== 'no'; }",
            timeout=espera)
        estado = self.page.evaluate("document.getElementById('vista').dataset.listo")
        if estado != "si":
            raise RuntimeError("la vista termino con error")
        if vista:
            v = self.page.evaluate("document.getElementById('vista').dataset.vista")
            if v != vista:
                raise RuntimeError(f"se esperaba la vista {vista} y cargo {v}")

    def sin_desborde(self):
        w = self.page.evaluate("document.documentElement.scrollWidth")
        if w > self.ancho + 1:
            raise RuntimeError(f"desborde lateral: {w}px en {self.ancho}px")

    def sin_errores(self, desde=0):
        nuevos = self.errores[desde:]
        if nuevos:
            raise RuntimeError("; ".join(nuevos[:5]))

    def boton(self, texto):
        return self.page.locator("button", has_text=texto).first

    def captura(self, nombre):
        os.makedirs(CAPTURAS, exist_ok=True)
        try:
            self.page.screenshot(path=f"{CAPTURAS}/{nombre}.png", full_page=True)
        except Exception:
            pass


def pdf_de_prueba():
    """PDF minimo valido de una pagina, escrito a mano (sin dependencias)."""
    objetos = [b"<< /Type /Catalog /Pages 2 0 R >>",
               b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
               b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] /Contents 4 0 R /Resources << /Font << /F1 5 0 R >> >> >>",
               None,
               b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>"]
    flujo = b"BT /F1 14 Tf 60 780 Td (ANEXO DE PRUEBA QA) Tj ET"
    objetos[3] = b"<< /Length %d >>\nstream\n" % len(flujo) + flujo + b"\nendstream"
    salida, pos = b"%PDF-1.4\n", []
    for i, o in enumerate(objetos, 1):
        pos.append(len(salida))
        salida += b"%d 0 obj\n" % i + o + b"\nendobj\n"
    xref = len(salida)
    salida += b"xref\n0 %d\n0000000000 65535 f \n" % (len(objetos) + 1)
    salida += b"".join(b"%010d 00000 n \n" % p for p in pos)
    salida += b"trailer\n<< /Size %d /Root 1 0 R >>\nstartxref\n%d\n%%%%EOF\n" % (len(objetos) + 1, xref)
    return salida


def png_de_prueba():
    import struct
    import zlib
    w, h = 120, 40
    filas = b"".join(b"\x00" + b"".join(b"\x0f\x17\x2a\xff" if abs(x - y * 3) < 3 else b"\x00\x00\x00\x00"
                                       for x in range(w)) for y in range(h))
    def trozo(t, d):
        return struct.pack(">I", len(d)) + t + d + struct.pack(">I", zlib.crc32(t + d) & 0xffffffff)
    return (b"\x89PNG\r\n\x1a\n" + trozo(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 6, 0, 0, 0))
            + trozo(b"IDAT", zlib.compress(filas)) + trozo(b"IEND", b""))


# ---------------------------------------------------------------- 1. cache
def pruebas_cache(navegador, s):
    global version_publicada

    @prueba("cache", "/cupido/ se sirve sin cache y trae VERSION")
    def cabecera():
        global version_publicada
        req = urllib.request.Request(CUPIDO + "?qa=" + CORRIDA, headers={"User-Agent": "qa-cupido"})
        with urllib.request.urlopen(req, timeout=30) as r:
            cc, html = r.headers.get("Cache-Control", ""), r.read().decode()
        if "no-cache" not in cc:
            raise RuntimeError(f"Cache-Control = {cc!r}")
        m = re.search(r'const VERSION = "([^"]+)"', html)
        if not m:
            raise RuntimeError("no se encontro VERSION en la pagina publicada")
        version_publicada = m.group(1)
        return version_publicada
    cabecera()

    @prueba("cache", "?limpiar=1 borra lo guardado y la version cargada es la publicada")
    def limpiar():
        p = Pantalla(navegador, s, 375, 812)
        try:
            p.page.goto(CUPIDO + "#/", wait_until="domcontentloaded")
            p.listo()
            p.page.evaluate("localStorage.setItem('cupido_tema', 'oscuro'); localStorage.setItem('cupido_prueba', 'x')")
            p.page.goto(CUPIDO + "?limpiar=1#/", wait_until="domcontentloaded")
            p.page.wait_for_url(re.compile(r"/cupido/#/$"), timeout=15000)
            p.listo()
            quedan = p.page.evaluate("Object.keys(localStorage).filter(k => k.startsWith('cupido_') && k !== 'cupido_pestana')")
            if quedan:
                raise RuntimeError(f"quedaron llaves: {quedan}")
            v = p.page.evaluate("window.cupidoQA && cupidoQA.version")
            if version_publicada and v != version_publicada:
                raise RuntimeError(f"version vieja en el navegador: {v} (publicada {version_publicada})")
            if not p.page.evaluate("localStorage.getItem('territorio_auth')"):
                raise RuntimeError("la limpieza borro la sesion del panel")
            p.sin_errores()
        finally:
            p.ctx.close()
    limpiar()


# ---------------------------------------------------------------- 2. flujo completo en el telefono
def pruebas_movil(navegador, s):
    p = Pantalla(navegador, s, 375, 812)
    codigo = "QA-" + CORRIDA
    pin = "".join(random.choices(string.digits, k=6))
    g = "movil"
    try:
        @prueba(g, "tablero carga")
        def tablero():
            p.page.goto(CUPIDO + "#/", wait_until="domcontentloaded")
            p.listo("licitaciones")
            if "Empresa de Prueba QA" not in p.page.inner_text("main"):
                raise RuntimeError("no entro a la empresa de prueba")
            p.sin_desborde()
        if not tablero():
            p.captura("tablero")
            return

        @prueba(g, "crear licitacion desde «+ Nueva»")
        def nueva():
            p.boton("+ Nueva").click()
            p.page.fill("#nCodigo", codigo)
            p.page.fill("#nNombre", "Licitacion de prueba del agente QA")
            p.boton("Crear").click()
            p.page.wait_for_url(re.compile(r"#/l/[0-9a-f-]{36}$"), timeout=15000)
            p.listo()
            if codigo not in p.page.inner_text("main"):
                raise RuntimeError("la ficha no muestra el codigo")
            p.sin_desborde()
        if not nueva():
            p.captura("nueva")
            return
        ficha = p.page.url.split("#")[1]

        @prueba(g, "checklist: agregar y marcar Cumplido")
        def checklist():
            p.page.fill("input[placeholder^='Agregar punto']", "Garantia de seriedad (QA)")
            p.boton("Agregar").click()
            p.page.wait_for_selector(".check", timeout=10000)
            p.page.locator(".check .tri button", has_text="Cumplido").first.click()
            p.page.wait_for_selector(".check .tri button.Cumplido[aria-pressed='true']", timeout=10000)
        checklist() or p.captura("checklist")

        @prueba(g, "comentario aparece en vivo (Realtime)")
        def comentario():
            texto = "Comentario del agente " + CORRIDA
            p.page.fill("textarea[placeholder^='Escribe un comentario']", texto)
            p.boton("Comentar").click()
            p.page.locator(".comentario", has_text=texto).wait_for(timeout=15000)
        comentario() or p.captura("comentario")

        @prueba(g, "editor de anexos: PDF, dato, firma y guardar en la ficha")
        def anexo():
            p.page.locator("a", has_text="Llenar y firmar un anexo").click()
            p.listo()
            p.page.set_input_files("input[accept='application/pdf']",
                                   files=[{"name": "anexo-qa.pdf", "mimeType": "application/pdf", "buffer": pdf_de_prueba()}])
            p.page.wait_for_selector(".hoja canvas", timeout=20000)
            p.page.locator(".campos-anexo .fila button").first.click()
            p.page.set_input_files("input[accept='image/png']",
                                   files=[{"name": "firma.png", "mimeType": "image/png", "buffer": png_de_prueba()}])
            p.page.wait_for_selector(".pieza img", timeout=10000)
            if p.page.locator(".pieza").count() < 2:
                raise RuntimeError("no quedaron el dato y la firma en la hoja")
            p.sin_desborde()
            p.boton("Guardar en la ficha").click()
            p.page.wait_for_url(re.compile(r"#/l/[0-9a-f-]{36}$"), timeout=20000)
            p.listo()
            p.page.locator(".doc .nombre-archivo", has_text="anexo-qa").wait_for(timeout=10000)
        anexo() or p.captura("anexo")
        if "#" + ficha not in p.page.url:
            p.page.goto(CUPIDO + "#" + ficha)
            p.listo()

        @prueba(g, "enviar a revision")
        def revision():
            p.boton("Enviar a revisión").click()
            p.page.locator(".chip", has_text="En revisión").first.wait_for(timeout=15000)
        revision() or p.captura("revision")

        @prueba(g, "aprobar con sello")
        def aprobar():
            p.boton("Aprobar con sello").click()
            p.page.wait_for_selector(".sello .hash", timeout=15000)
            h = p.page.inner_text(".sello .hash")
            if not re.search(r"[0-9a-f]{64}", h):
                raise RuntimeError(f"sello sin codigo de auditoria: {h!r}")
        aprobar() or p.captura("aprobar")

        @prueba(g, "postular con clave de 6 numeros")
        def postular():
            p.boton("Postular").click()
            p.page.fill("#pinA", pin)
            p.page.fill("#pinB", pin)
            p.boton("Guardar clave").click()
            p.page.fill("#pinPedido", pin)
            p.boton("Confirmar").click()
            p.page.locator(".chip", has_text="Postulada").first.wait_for(timeout=15000)
        postular() or p.captura("postular")

        @prueba(g, "clave equivocada se rechaza")
        def pin_malo():
            st, r, _ = http("POST", "/rest/v1/rpc/clave_pin_definir", token=s["access_token"],
                            cuerpo={"p_pin_nuevo": "123456", "p_pin_actual": "000000" if pin != "000000" else "111111"})
            if st == 200 and isinstance(r, dict) and r.get("ok") is not False:
                raise RuntimeError(f"cambio la clave con la clave actual equivocada: {r}")
        pin_malo()

        @prueba(g, "chat: mensaje aparece en vivo")
        def chat():
            p.ir("#/chat")
            texto = "Hola equipo, prueba del agente " + CORRIDA
            p.page.fill("textarea", texto)
            p.boton("Enviar").click()
            p.page.locator(".burbuja", has_text=texto).wait_for(timeout=15000)
            p.sin_desborde()
        chat() or p.captura("chat")

        @prueba(g, "Sala de Guerra: abre Jitsi y avisa en el chat")
        def sala():
            p.page.locator("button", has_text="Sala de Guerra").first.click()
            with p.ctx.expect_page(timeout=15000) as nueva_pag:
                p.boton("Abrir Jitsi").click()
            ventana = nueva_pag.value
            ventana.wait_for_url(re.compile(r"meet\.jit\.si/CupidoLicita-"), timeout=20000, wait_until="commit")
            ventana.close()
            p.page.locator(".burbuja", has_text="Sala de Guerra abierta").first.wait_for(timeout=15000)
        sala() or p.captura("sala")

        @prueba(g, "boveda: subir, ver estado y borrar")
        def boveda():
            p.ir("#/boveda")
            p.boton("+ Subir").click()
            p.page.set_input_files("#bArchivo", files=[{"name": "certificado-qa.pdf", "mimeType": "application/pdf",
                                                         "buffer": pdf_de_prueba()}])
            p.page.fill("#bVence", (date.today() + timedelta(days=10)).isoformat())
            p.page.locator(".modal button", has_text="Subir").click()
            fila = p.page.locator(".doc", has_text="certificado-qa.pdf")
            fila.wait_for(timeout=15000)
            if "Vence pronto" not in fila.inner_text():
                raise RuntimeError("no marco «Vence pronto» a 10 dias")
            p.sin_desborde()
            fila.locator("button", has_text="Borrar").click()
            fila.wait_for(state="detached", timeout=15000)
        boveda() or p.captura("boveda")

        @prueba(g, "ROI carga")
        def roi():
            p.ir("#/roi")
            p.page.wait_for_selector(".cifra, main .aviso", timeout=20000)
            if p.page.locator("img.cupi").count() == 0:
                raise RuntimeError("no aparecio Cupi")
            p.sin_desborde()
        roi() or p.captura("roi")

        @prueba(g, "sin errores de consola ni llamadas fallidas")
        def limpio():
            p.sin_errores()
        limpio()
    finally:
        p.ctx.close()


# ---------------------------------------------------------------- 3. escritorio
def pruebas_escritorio(navegador, s):
    p = Pantalla(navegador, s, 1280, 900)
    try:
        p.page.goto(CUPIDO + "#/", wait_until="domcontentloaded")
        p.listo()
        for ruta, vista in [("#/", "licitaciones"), ("#/chat", "chat"), ("#/boveda", "boveda"), ("#/roi", "roi")]:
            @prueba("escritorio", f"{ruta} carga a 1280 px")
            def cargar():
                antes = len(p.errores)
                p.ir(ruta)
                p.listo(vista)
                p.sin_desborde()
                p.sin_errores(antes)
            cargar() or p.captura("escritorio-" + vista)
    finally:
        p.ctx.close()


# ---------------------------------------------------------------- 4. estres
def pruebas_estres(navegador, s):
    tok = s["access_token"]
    llamadas = [
        ("POST", "/rest/v1/rpc/cupido_contexto", {}),
        ("GET", "/rest/v1/postulaciones?select=id,estado&order=actualizado_en.desc&limit=20", None),
        ("GET", "/rest/v1/chat_mensajes?select=id,texto&order=creado_en.desc&limit=40", None),
        ("GET", "/rest/v1/company_documents?select=id,status&limit=50", None),
    ]

    @prueba("estres", "120 llamadas a Supabase, 20 a la vez")
    def api():
        def una(i):
            m, ruta, cuerpo = llamadas[i % len(llamadas)]
            return http(m, ruta, token=tok, cuerpo=cuerpo)
        with ThreadPoolExecutor(20) as ex:
            res = list(ex.map(una, range(120)))
        malos = [(st, str(r)[:80]) for st, r, _ in res if st != 200]
        t = sorted(x[2] for x in res)
        p50, p95 = statistics.median(t), t[int(len(t) * 0.95) - 1]
        detalle = f"p50 {p50*1000:.0f} ms, p95 {p95*1000:.0f} ms, fallidas {len(malos)}"
        if malos:
            raise RuntimeError(detalle + f" {malos[:3]}")
        if p95 > 3.0:
            raise RuntimeError("lento: " + detalle)
        return detalle
    api()

    @prueba("estres", "5 navegadores abren /cupido/ a la vez")
    def paginas():
        ps = [Pantalla(navegador, s, 375, 812) for _ in range(5)]
        try:
            t = time.time()
            for x in ps:
                x.page.goto(CUPIDO + "#/", wait_until="commit")
            for x in ps:
                x.listo(espera=30000)
            seg = time.time() - t
            for x in ps:
                x.sin_errores()
            if seg > 20:
                raise RuntimeError(f"lento: {seg:.1f} s")
            return f"{seg:.1f} s las 5"
        finally:
            for x in ps:
                x.ctx.close()
    paginas()


# ---------------------------------------------------------------- 5. seguridad
SENSIBLES = ["postulaciones", "postulacion_checklist", "postulacion_anexos", "comentarios_licitacion",
             "chat_mensajes", "company_documents", "claves_seguridad", "perfiles", "qa_eventos", "qa_cuentas",
             "adjudicaciones_publicas", "suscriptores", "salas_guerra", "organization_members", "boveda_avisos"]


def vacio_o_negado(st, r):
    return st in (401, 403) or (st == 200 and r == []) or (st == 404)


def pruebas_seguridad(s, uid, otro):
    tok = s["access_token"]
    for t in SENSIBLES:
        @prueba("seguridad", f"clave publica no lee {t}")
        def anon():
            st, r, _ = http("GET", f"/rest/v1/{t}?select=*&limit=1")
            if not vacio_o_negado(st, r):
                raise RuntimeError(f"{st}: {str(r)[:120]}")
        anon()

    @prueba("seguridad", "clave publica no llama cupido_contexto ni qa_salud")
    def anon_rpc():
        for f in ["cupido_contexto", "qa_salud", "qa_reportar"]:
            st, r, _ = http("POST", f"/rest/v1/rpc/{f}", cuerpo={})
            if st == 200 and r not in (None, {}) and not (isinstance(r, dict) and r.get("ok") is False):
                raise RuntimeError(f"{f}: {st} {str(r)[:120]}")
    anon_rpc()

    if not otro:
        anotar("seguridad", "otra empresa para comparar", False, "no hay otra empresa con cuenta")
        return
    for tabla, col in [("postulaciones", "owner_id"), ("chat_mensajes", "owner_id"),
                       ("company_documents", "company_id"), ("salas_guerra", "owner_id")]:
        @prueba("seguridad", f"cuenta de prueba no ve {tabla} de otra empresa")
        def ver():
            st, r, _ = http("GET", f"/rest/v1/{tabla}?select=*&{col}=eq.{otro}&limit=1", token=tok)
            if not vacio_o_negado(st, r):
                raise RuntimeError(f"{st}: {str(r)[:120]}")
        ver()

    @prueba("seguridad", "cuenta de prueba no escribe en otra empresa")
    def escribir():
        for tabla, cuerpo in [("postulaciones", {"owner_id": otro, "codigo_licitacion": "QA-INTRUSO"}),
                              ("chat_mensajes", {"owner_id": otro, "texto": "intruso"}),
                              ("company_documents", {"company_id": otro, "doc_type": "x", "file_name": "x",
                                                     "file_path": f"{otro}/x.pdf"})]:
            st, r, _ = http("POST", f"/rest/v1/{tabla}", token=tok, cuerpo=cuerpo, extra={"Prefer": "return=minimal"})
            if st < 400:
                servicio("DELETE", f"/rest/v1/{tabla}?{'company_id' if tabla == 'company_documents' else 'owner_id'}=eq.{otro}"
                         f"&{'file_name=eq.x' if tabla == 'company_documents' else ('codigo_licitacion=eq.QA-INTRUSO' if tabla == 'postulaciones' else 'texto=eq.intruso')}")
                raise RuntimeError(f"{tabla} acepto la escritura ({st})")
    escribir()

    @prueba("seguridad", "cuenta de prueba no lista archivos de otra empresa")
    def archivos():
        st, r, _ = http("POST", "/storage/v1/object/list/boveda", token=tok, cuerpo={"prefix": otro + "/", "limit": 5})
        if not vacio_o_negado(st, r):
            raise RuntimeError(f"{st}: {str(r)[:120]}")
    archivos()

    @prueba("seguridad", "cuenta de prueba no ve ROI ni salud ajenos")
    def rpc_ajenas():
        st, r, _ = http("POST", "/rest/v1/rpc/roi_tablero", token=tok, cuerpo={"p_owner": otro})
        if st == 200 and r.get("ok") is not False:
            raise RuntimeError("roi_tablero de otra empresa respondio datos")
        st, r, _ = http("POST", "/rest/v1/rpc/qa_salud", token=tok, cuerpo={})
        if st == 200 and r.get("ok") is not False:
            raise RuntimeError("qa_salud respondio a una cuenta comun")
    rpc_ajenas()

    @prueba("seguridad", "el estado no se cambia escribiendo directo")
    def estado_directo():
        st, r, _ = http("POST", "/rest/v1/postulaciones", token=tok, extra={"Prefer": "return=representation"},
                        cuerpo={"owner_id": uid, "codigo_licitacion": "QA-ESTADO-" + CORRIDA})
        if st >= 400:
            raise RuntimeError(f"no pudo crear su propio borrador: {st} {r}")
        pid = r[0]["id"]
        st, r, _ = http("PATCH", f"/rest/v1/postulaciones?id=eq.{pid}", token=tok, cuerpo={"estado": "Postulada"},
                        extra={"Prefer": "return=representation"})
        if st < 400 and r and r[0].get("estado") == "Postulada":
            raise RuntimeError("se salto la aprobacion escribiendo el estado directo")
    estado_directo()

    @prueba("seguridad", "RLS y permisos contra la linea base")
    def linea_base():
        st, r, _ = servicio("POST", "/rest/v1/rpc/qa_revision_seguridad", {})
        if st != 200:
            raise RuntimeError(f"qa_revision_seguridad: {st} {r}")
        base = json.load(open(LINEA_BASE, encoding="utf-8"))
        problemas = []
        for clave in ["tablas_sin_rls", "buckets_publicos", "tablas_anon_lectura"]:
            if r[clave]:
                problemas.append(f"{clave}: {r[clave]}")
        for clave in ["funciones_anon", "politicas_anon"]:
            nuevas = sorted(set(r[clave]) - set(base[clave]))
            if nuevas:
                problemas.append(f"{clave} nuevas: {nuevas}")
        if problemas:
            raise RuntimeError("; ".join(problemas))
        return f"{len(r['funciones_anon'])} funciones publicas, todas conocidas"
    linea_base()


# ---------------------------------------------------------------- informe
def informar():
    fallas = [x for x in resultados if not x[2]]
    for grupo, nombre, _, detalle in fallas:
        servicio("POST", "/rest/v1/rpc/qa_agente_registrar", {"p_tipo": "prueba_falla", "p_mensaje": f"[{grupo}] {nombre}: {detalle}",
                 "p_ruta": grupo, "p_version": version_publicada, "p_detalle": {"corrida": CORRIDA}})
    resumen = f"{len(resultados) - len(fallas)} de {len(resultados)} pruebas OK"
    servicio("POST", "/rest/v1/rpc/qa_agente_registrar", {"p_tipo": "prueba_ok" if not fallas else "prueba_falla",
             "p_mensaje": "Resumen: " + resumen, "p_ruta": "resumen", "p_version": version_publicada,
             "p_detalle": {"corrida": CORRIDA, "fallas": len(fallas), "total": len(resultados)}})
    lineas = [f"## Agente de QA de CupidoLicita · version {version_publicada} · corrida {CORRIDA}", "",
              f"**{resumen}**", "", "| | Grupo | Prueba | Detalle |", "|---|---|---|---|"]
    lineas += [f"| {'✅' if ok else '❌'} | {g} | {n} | {d.replace('|', '/')[:200]} |" for g, n, ok, d in resultados]
    if os.environ.get("GITHUB_STEP_SUMMARY"):
        with open(os.environ["GITHUB_STEP_SUMMARY"], "a", encoding="utf-8") as f:
            f.write("\n".join(lineas) + "\n")
    print("\n" + resumen)
    return not fallas


def main():
    print(f"AGENTE QA CUPIDOLICITA · corrida {CORRIDA}")
    uid, otro = preparar_cuenta()
    s = sesion()
    try:
        with sync_playwright() as pw:
            nav = pw.chromium.launch()
            try:
                pruebas_cache(nav, s)
                pruebas_movil(nav, s)
                pruebas_escritorio(nav, s)
                if "--sin-estres" not in sys.argv:
                    pruebas_estres(nav, s)
            finally:
                nav.close()
        pruebas_seguridad(s, uid, otro)
    except Exception:
        anotar("agente", "el agente termino sin caerse", False, traceback.format_exc()[-500:])
    finally:
        # Todo lo creado se borra, pase lo que pase.
        try:
            servicio("POST", "/rest/v1/rpc/qa_preparar", {"p_email": CORREO})
            limpiar_archivos(uid)
        except Exception as e:
            print("No se pudo limpiar:", e)
    sys.exit(0 if informar() else 1)


if __name__ == "__main__":
    main()
