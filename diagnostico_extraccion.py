import json, os, time, urllib.error, urllib.request
from datetime import date, timedelta
from concurrent.futures import ThreadPoolExecutor
T = os.environ["TICKET_MP"].strip()
V2 = "https://api2.mercadopublico.cl/v2/compra-agil"
HOY = date.today(); AYER = (HOY - timedelta(days=1)).isoformat(); HOYS = HOY.isoformat()
def nota(t, m): print(f"::notice title={t}::{m}"[:900])
def get(q):
    t0 = time.time()
    r = urllib.request.Request(f"{V2}?{q}", headers={"User-Agent": "Uplevel-Inteligencia/1.0", "ticket": T, "Accept": "application/json"})
    try:
        with urllib.request.urlopen(r, timeout=120) as x:
            d = json.loads(x.read().decode()); p = d.get("payload", {})
            return x.status, time.time() - t0, len(p.get("items", [])), p
    except urllib.error.HTTPError as e:
        return e.code, time.time() - t0, 0, {}
    except Exception as e:
        return 0, time.time() - t0, 0, {}
def m(titulo, q):
    c, s, n, p = get(q)
    extra = {k: v for k, v in p.items() if k != "items"}
    nota(titulo, f"HTTP {c} · {s:.1f}s · {n} items · meta {json.dumps(extra)[:200]}")
    return c, s, n, p
base = "estado=publicada"
m("A tam10 p1 desde hoy", f"{base}&tamano_pagina=10&numero_pagina=1&publicado_desde={HOYS}")
m("B tam10 p1 desde ayer", f"{base}&tamano_pagina=10&numero_pagina=1&publicado_desde={AYER}")
m("C tam10 p1 SIN fecha", f"{base}&tamano_pagina=10&numero_pagina=1")
m("D tam10 p1 sin estado", f"tamano_pagina=10&numero_pagina=1&publicado_desde={HOYS}")
m("E tam10 p30 desde ayer", f"{base}&tamano_pagina=10&numero_pagina=30&publicado_desde={AYER}")
m("F tam10 p150 desde ayer", f"{base}&tamano_pagina=10&numero_pagina=150&publicado_desde={AYER}")
m("G tam10 p1 ayer y publicado_hasta", f"{base}&tamano_pagina=10&numero_pagina=1&publicado_desde={AYER}&publicado_hasta={HOYS}")
m("H tam10 p1 pidiendo solo 1 dia exacto", f"{base}&tamano_pagina=10&numero_pagina=1&publicado_desde={AYER}&publicado_hasta={AYER}")
# paralelo real: 6 paginas de 10 a la vez
t0 = time.time()
with ThreadPoolExecutor(6) as ex:
    rs = list(ex.map(lambda p: get(f"{base}&tamano_pagina=10&numero_pagina={p}&publicado_desde={AYER}"), range(1, 7)))
nota("I 6 paginas de 10 en paralelo", f"total {time.time()-t0:.1f}s · cada una: {[f'{r[0]}/{r[1]:.0f}s' for r in rs]}")
# 12 hilos
t0 = time.time()
with ThreadPoolExecutor(12) as ex:
    rs = list(ex.map(lambda p: get(f"{base}&tamano_pagina=10&numero_pagina={p}&publicado_desde={AYER}"), range(1, 13)))
nota("J 12 paginas de 10 en paralelo", f"total {time.time()-t0:.1f}s · codigos: {[r[0] for r in rs]} · tiempos: {[round(r[1]) for r in rs]}")
# ¿cuantas hay en total? (pagina muy alta para encontrar el final)
for p in (100, 200, 300, 500):
    c, s, n, _ = get(f"{base}&tamano_pagina=10&numero_pagina={p}&publicado_desde={AYER}")
    nota(f"K ayer p{p}", f"HTTP {c} · {s:.1f}s · {n} items")
    if n == 0 and c == 200: break
