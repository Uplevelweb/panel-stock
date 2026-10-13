"""Abre la app como lo haría una persona (con navegador) para que Streamlit no la duerma.
Si está dormida, aprieta «Yes, get this app back up!» y espera a que despierte."""
import sys, time
from playwright.sync_api import sync_playwright
URL = "https://panel-stock-uplevel.streamlit.app/"
with sync_playwright() as p:
    b = p.chromium.launch()
    pg = b.new_page()
    pg.goto(URL, wait_until="domcontentloaded", timeout=90000)
    time.sleep(8)
    for _ in range(2):
        for fr in [pg] + pg.frames:
            try:
                btn = fr.get_by_text("Yes, get this app back up!")
                if btn.count():
                    print("estaba dormida: despertando")
                    btn.first.click()
                    time.sleep(60)
            except Exception as e:
                print("aviso:", e)
    time.sleep(25)  # sesión abierta unos segundos = actividad real
    print("ok", pg.title())
    b.close()
