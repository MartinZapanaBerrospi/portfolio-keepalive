"""Mantiene despiertas las apps del portafolio alojadas en planes gratuitos.

- Streamlit Community Cloud: duerme las apps tras ~12 h sin visitas. Una petición
  HTTP simple no cuenta como visita, así que se abre la app con un navegador real
  (Playwright) y, si está dormida, se pulsa "Yes, get this app back up!".
- Supabase Free: pausa el proyecto tras 7 días sin actividad. Basta con ejecutar
  una consulta real contra la base de datos (vía REST o vía Postgres directo).

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
        while time.monotonic() < deadline:
            if app_is_rendered(page):
                # Unos segundos extra para que la sesión websocket quede registrada.
                page.wait_for_timeout(15_000)
                return ("despertada" if woke else "activa"), True
            button = page.get_by_role("button", name=WAKE_BUTTON)
            if not woke and button.count() > 0 and button.first.is_visible():
                button.first.click()
                woke = True
            page.wait_for_timeout(5_000)
        page.screenshot(path=str(ROOT / f"{target['name']}.png"), full_page=True)
        return "no cargó a tiempo", False
    finally:
        page.close()


def check_supabase_rest(target):
    import requests

    url, key = os.getenv(target["url_env"]), os.getenv(target["key_env"])
    if not url or not key:
        return "sin credenciales (omitido)", None
    resp = requests.get(
        f"{url.rstrip('/')}/rest/v1/{target['table']}",
        params={"select": "*", "limit": "1"},
        headers={"apikey": key, "Authorization": f"Bearer {key}"},
        timeout=60,
    )
    if resp.ok:
        return "consulta OK", True
    return f"HTTP {resp.status_code}", False


def check_supabase_postgres(target):
    import psycopg

    dsn = os.getenv(target["dsn_env"])
    if not dsn:
        return "sin credenciales (omitido)", None
    with psycopg.connect(dsn, connect_timeout=30) as conn:
        conn.execute("select count(*) from pg_stat_user_tables").fetchone()
    return "consulta OK", True


def run_checks():
    results = []

    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        browser = p.chromium.launch()
        for target in TARGETS.get("streamlit", []):
            results.append(("Streamlit", target, safe(check_streamlit, browser, target)))
        browser.close()

    for target in TARGETS.get("supabase_rest", []):
        results.append(("Supabase", target, safe(check_supabase_rest, target)))
    for target in TARGETS.get("supabase_postgres", []):
        results.append(("Supabase", target, safe(check_supabase_postgres, target)))

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
        shown = "OK" if ok and platform == "Streamlit" else detail
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
