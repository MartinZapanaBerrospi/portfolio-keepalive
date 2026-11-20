"""Mantiene despiertas las apps del portafolio alojadas en planes gratuitos.

- Streamlit Community Cloud: duerme las apps tras ~12 h sin visitas. Una petición
  HTTP simple no cuenta como visita, así que se abre la app con un navegador real
  (Playwright) y, si está dormida, se pulsa "Yes, get this app back up!".
- Supabase Free: pausa el proyecto si en 7 días no hay suficiente "actividad de
  usuario en la base de datos". Una vista que devuelve una constante (select 1) o
  una consulta al catálogo NO basta (así se pausó entrenador-admision en 2026-11).
  Método preferido: conexión Postgres directa que ESCRIBE una fila de latido en
  keepalive.ping (esquema propio, no expuesto por la API). Respaldo, si no hay DSN:
  lectura REST de una tabla real con datos.

Los objetivos se definen en targets.json; las credenciales llegan por variables de
entorno (GitHub Secrets). Un objetivo sin credenciales se omite con un aviso.
"""

import json
import os
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).parent
TARGETS = json.loads((ROOT / "targets.json").read_text(encoding="utf-8"))
STATUS_FILE = ROOT / "STATUS.md"

WAKE_BUTTON = re.compile(r"get this app back up", re.I)
APP_SELECTOR = '[data-testid="stApp"], [data-testid="stAppViewContainer"]'
WAKE_TIMEOUT_S = 300
# Si la página no muestra la app ni el botón de despertar en este tiempo, se recarga.
STUCK_RELOAD_S = 60


def app_is_rendered(page):
    """La app de Streamlit vive dentro de un iframe; se busca en todos los frames."""
    for frame in page.frames:
        try:
            if frame.locator(APP_SELECTOR).count() > 0:
                return True
        except Exception:
            pass
    return False


def check_streamlit(browser, target):
    page = browser.new_page()
    woke = False
    try:
        page.goto(target["url"], wait_until="domcontentloaded", timeout=90_000)
        deadline = time.monotonic() + WAKE_TIMEOUT_S
        last_load = time.monotonic()
        while time.monotonic() < deadline:
            if app_is_rendered(page):
                # Unos segundos extra para que la sesión websocket quede registrada.
                page.wait_for_timeout(15_000)
                return ("despertada" if woke else "activa"), True
            button = page.get_by_role("button", name=WAKE_BUTTON)
            if not woke and button.count() > 0 and button.first.is_visible():
                button.first.click()
                woke = True
                last_load = time.monotonic()
            elif time.monotonic() - last_load > STUCK_RELOAD_S:
                # A veces un archivo JS de Streamlit se queda colgado y la página se
                # atasca en el spinner aunque la app esté activa: se recarga.
                try:
                    page.reload(wait_until="domcontentloaded", timeout=60_000)
                except Exception:
                    pass
                last_load = time.monotonic()
            page.wait_for_timeout(5_000)
        page.screenshot(path=str(ROOT / f"{target['name']}.png"), full_page=True)
        return "no cargó a tiempo", False
    finally:
        page.close()


PING_SQL = """
create schema if not exists keepalive;
create table if not exists keepalive.ping (
    id smallint primary key default 1 check (id = 1),
    pinged_at timestamptz not null default now(),
    pings bigint not null default 0
);
revoke all on schema keepalive from public;
"""
PING_UPSERT = """
insert into keepalive.ping (id, pinged_at, pings) values (1, now(), 1)
on conflict (id) do update set pinged_at = now(), pings = keepalive.ping.pings + 1
returning pings
"""


def supabase_postgres_ping(dsn):
    import psycopg

    # prepare_threshold=None: compatible con el pooler en modo transacción (puerto 6543).
    with psycopg.connect(dsn, connect_timeout=30, prepare_threshold=None) as conn:
        if conn.execute("select to_regclass('keepalive.ping')").fetchone()[0] is None:
            conn.execute(PING_SQL)
        pings = conn.execute(PING_UPSERT).fetchone()[0]
    return f"latido escrito por Postgres (#{pings})", True


def supabase_rest_read(url, key, table):
    import requests

    resp = requests.get(
        f"{url.rstrip('/')}/rest/v1/{table}",
        params={"select": "*", "limit": "1"},
        # Las claves nuevas (sb_publishable_/sb_secret_) no son JWT: van solo como apikey
        headers={"apikey": key, **({"Authorization": f"Bearer {key}"} if key.startswith("eyJ") else {})},
        timeout=60,
    )
    if resp.ok:
        return f"lectura REST de {table} (respaldo: falta DSN)", True
    return f"HTTP {resp.status_code}", False


def check_supabase(target):
    dsn = os.getenv(target.get("dsn_env", ""))
    if dsn:
        return supabase_postgres_ping(dsn)
    url, key = os.getenv(target.get("url_env", "")), os.getenv(target.get("key_env", ""))
    if url and key and target.get("table"):
        return supabase_rest_read(url, key, target["table"])
    return "sin credenciales (omitido)", None


def run_checks():
    results = []

    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        browser = p.chromium.launch()
        for target in TARGETS.get("streamlit", []):
            results.append(("Streamlit", target, safe(check_streamlit, browser, target)))
        browser.close()

    for target in TARGETS.get("supabase", []):
        results.append(("Supabase", target, safe(check_supabase, target)))

    return results


def safe(check, *args):
    try:
        return check(*args)
    except Exception as exc:
        return f"error: {type(exc).__name__}", False


def write_status(results):
    # Solo fecha (sin hora) para que el commit automático ocurra como máximo una vez al día.
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    icons = {True: "✅", False: "❌", None: "⚪"}
    lines = [
        "# Estado de las apps",
        "",
        f"Última verificación: **{today}** (UTC)",
        "",
        "| Plataforma | Proyecto | Estado |",
        "|---|---|---|",
    ]
    for platform, target, (detail, ok) in results:
        # "despertada" vs "activa" cambia en cada corrida; en el archivo ambas cuentan como OK.
        # El contador de latidos también cambia en cada corrida; se omite del archivo.
        shown = "OK" if ok and platform == "Streamlit" else re.sub(r" \(#\d+\)", "", detail)
        lines.append(f"| {platform} | {target['name']} | {icons[ok]} {shown} |")
    STATUS_FILE.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main():
    results = run_checks()
    for platform, target, (detail, ok) in results:
        print(f"[{'OK' if ok else 'SKIP' if ok is None else 'FAIL'}] {platform} {target['name']}: {detail}")
    write_status(results)
    if any(ok is False for _, _, (_, ok) in results):
        sys.exit(1)


if __name__ == "__main__":
    main()
