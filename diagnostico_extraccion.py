"""Diagnostico de SOLO LECTURA: que entrega ChileCompra hoy. No envia nada ni escribe en Supabase.
Imprime anotaciones ::notice:: (visibles sin bajar el log)."""
import json, os, sys, urllib.parse, urllib.request, urllib.error
from datetime import date

T = os.environ.get("TICKET_MP", "").strip()
V1 = "https://api.mercadopublico.cl/servicios/v1/publico/licitaciones.json"
V2 = "https://api2.mercadopublico.cl/v2/compra-agil"
CODIGO = sys.argv[1] if len(sys.argv) > 1 else "3265-56-LE26"
n = [0]

def nota(titulo, msg):
    n[0] += 1
    print(f"::notice title={titulo}::{msg}"[:900])

def pedir(url, cab=None):
    r = urllib.request.Request(url, headers={"User-Agent": "Uplevel-Inteligencia/1.0", "Accept": "application/json", **(cab or {})})
    try:
        with urllib.request.urlopen(r, timeout=120) as x:
            return x.status, x.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode("utf-8", "replace")[:300]
    except Exception as e:
        return 0, f"{type(e).__name__}: {e}"

def lista(txt):
    try:
        d = json.loads(txt)
    except Exception:
        return None, []
    return d, (d.get("Listado") if isinstance(d, dict) else None) or []

# 1. activas
c, t = pedir(f"{V1}?estado=activas&ticket={urllib.parse.quote(T)}")
d, filas = lista(t)
cods = [str(f.get("CodigoExterno")) for f in filas if isinstance(f, dict)]
nota("1 activas", f"HTTP {c} · {len(filas)} filas · esta {CODIGO}: {CODIGO in cods} · cantidad declarada: {d.get('Cantidad') if isinstance(d, dict) else '?'} · version: {d.get('FechaCreacion') if isinstance(d, dict) else '?'}")
hoy = [f for f in filas if isinstance(f, dict) and str(f.get('CodigoExterno','')).endswith('-LE26')]
nota("1b muestra", " | ".join(f"{f.get('CodigoExterno')}:{str(f.get('Nombre'))[:40]}" for f in filas[:3]))

# 2. el codigo puntual
c, t = pedir(f"{V1}?codigo={CODIGO}&ticket={urllib.parse.quote(T)}")
d, filas2 = lista(t)
f0 = filas2[0] if filas2 and isinstance(filas2[0], dict) else {}
nota("2 codigo", f"HTTP {c} · nombre: {f0.get('Nombre')} · estado: {f0.get('Estado')} · publicada: {(f0.get('Fechas') or {}).get('FechaPublicacion')} · cierre: {(f0.get('Fechas') or {}).get('FechaCierre')} · crudo: {t[:150] if not f0 else ''}")

# 3. listado por fecha de hoy (otra via para ver lo publicado hoy)
hoyddmm = date.today().strftime("%d%m%Y")
c, t = pedir(f"{V1}?fecha={hoyddmm}&estado=publicada&ticket={urllib.parse.quote(T)}")
d, filas3 = lista(t)
cods3 = [str(f.get("CodigoExterno")) for f in filas3 if isinstance(f, dict)]
nota("3 publicadas hoy", f"fecha {hoyddmm} · HTTP {c} · {len(filas3)} filas · esta {CODIGO}: {CODIGO in cods3}")

# 4. compras agiles pagina 1
c, t = pedir(f"{V2}?estado=publicada&tamano_pagina=10&numero_pagina=1&publicado_desde={date.today().isoformat()}", {"ticket": T})
nota("4 compras agiles", f"HTTP {c} · {t[:200].replace(chr(10),' ')}")
