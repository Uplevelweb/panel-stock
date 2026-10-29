"""
Una sola vez: el monto estimado de las licitaciones abiertas que ya estaban en
`fichas_licitacion` antes de que el radar empezara a guardarlo (29-10-2026).
Las nuevas ya llegan con monto desde alertador.py.

No manda correos ni toca suscriptores. Pide el detalle V1 de a uno, con la
misma espera de 2 s del radar, y se detiene al primer 429 (cuota del dia).
"""
import json
import os
import time
import urllib.parse
import urllib.request
from datetime import date

from alertador import ESPERA_V1, V1, _pedir, _primera_lista

TECHO = int(os.environ.get("TECHO", "2500"))


def main():
    url = os.environ["SUPABASE_URL"].strip()
    clave = os.environ["SUPABASE_SECRET_KEY"].strip()
    ticket = os.environ["TICKET_MP"].strip()
    cab = {"apikey": clave, "Authorization": f"Bearer {clave}", "Content-Type": "application/json"}
    consulta = (f"{url}/rest/v1/fichas_licitacion?select=codigo&monto=is.null"
                f"&cierre=gte.{date.today().isoformat()}&order=cierre&limit={TECHO}")
    with urllib.request.urlopen(urllib.request.Request(consulta, headers=cab), timeout=60) as r:
        codigos = [f["codigo"] for f in json.loads(r.read().decode("utf-8"))]
    print(f"{len(codigos)} licitaciones abiertas sin monto")
    hechas = 0
    for i, codigo in enumerate(codigos, 1):
        if i > 1:
            time.sleep(ESPERA_V1)
        datos = _pedir(f"{V1}?codigo={urllib.parse.quote(codigo)}&ticket={urllib.parse.quote(ticket)}")
        if datos is None:
            print("Sin respuesta (posible cuota agotada): se para aqui.")
            break
        detalle = _primera_lista(datos)
        d = detalle[0] if detalle and isinstance(detalle[0], dict) else {}
        # 0 = la ficha no publica monto; queda anotado para no volver a pedirla.
        monto = float(d.get("MontoEstimado") or 0)
        urllib.request.urlopen(urllib.request.Request(
            f"{url}/rest/v1/fichas_licitacion?codigo=eq.{urllib.parse.quote(codigo)}",
            method="PATCH", headers=cab, data=json.dumps({"monto": monto}).encode("utf-8")), timeout=60).read()
        hechas += 1
        if i % 100 == 0:
            print(f"  {i}/{len(codigos)}")
    print(f"::notice title=Montos::{hechas} de {len(codigos)} licitaciones con monto revisado")


if __name__ == "__main__":
    main()
