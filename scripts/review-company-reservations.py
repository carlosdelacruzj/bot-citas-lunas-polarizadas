"""On-demand, resumable read-only company reservation review."""
# ruff: noqa: E501

import argparse
import json
import logging
import os
import time
import webbrowser
from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, wait
from dataclasses import asdict, replace
from datetime import UTC, datetime
from html import escape
from pathlib import Path
from uuid import uuid4

import psycopg
from psycopg.rows import dict_row

from appointment_bot.browser.ownership import BrowserOwnershipLease
from appointment_bot.browser.session import open_page
from appointment_bot.configuration.loading import load_settings
from appointment_bot.configuration.reservation import settings_for_order
from appointment_bot.db.browser_ownership import BrowserOwnershipConflict
from appointment_bot.db.order_credentials import get_service_order_runtime
from appointment_bot.reservation_engine.login import InvalidPortalCredentials, login
from appointment_bot.reservation_engine.programs import open_program_detail_for_review
from appointment_bot.reservation_engine.stages import read_process_stages

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / ".runtime/company-reservations"
LABELS = {
    "company_confirmed": "Empresa confirmada",
    "no_company_section": "Sin datos de empresa",
    "access_lost": "Sin acceso",
    "unverified": "No verificable",
    "company_data_incomplete": "Datos incompletos",
    "busy": "Cuenta ocupada",
    "pending": "Pendiente",
    "running": "Revisando",
}


def review(row, configuration):
    rt, rs, _, es, _, _ = configuration
    out = OUT
    record = dict(row)
    record["checked_at"] = datetime.now(UTC).isoformat()
    oid = row["order_id"]
    try:
        order = get_service_order_runtime(oid, settings=rt)
        if order is None:
            raise ValueError("Order unavailable")
        with BrowserOwnershipLease.acquire(
            rt,
            oid,
            owner_token="post-appointment-company-" + uuid4().hex,
            purpose="post_appointment",
        ) as lease:
            with open_page(
                runtime_settings=replace(rt, headless=True), evidence_settings=es, headless=True
            ) as page:
                try:
                    login(
                        page,
                        reservation_settings=replace(
                            settings_for_order(
                                username=order.username,
                                password=order.password,
                                document_type=order.document_type,
                                reservation_settings=rs,
                            ),
                            auto_reserve=False,
                            monitor_window_seconds=0,
                        ),
                    )
                    if lease.lost:
                        raise RuntimeError("Lease lost")
                    open_program_detail_for_review(
                        page,
                        program_expediente=row["program_expediente"] or order.program_expediente,
                        program_plate=row["program_plate"] or order.program_plate,
                    )
                    page.wait_for_timeout(350)
                    record["stages"] = [asdict(s) for s in read_process_stages(page)]
                    if not record["stages"]:
                        raise RuntimeError("Missing process stages")
                    record["status"] = "no_company_section"
                    tab = page.locator("#__tab_MainContent_TabContainer1_TabPanel2")
                    if tab.count() == 1 and tab.is_visible():
                        tab.click()
                        ruc = page.locator("#MainContent_TabContainer1_TabPanel2_txtRuc")
                        company = page.locator(
                            "#MainContent_TabContainer1_TabPanel2_txtRazonSocial"
                        )
                        company.wait_for(state="visible", timeout=10000)
                        record["company_ruc"] = ruc.input_value().strip()
                        record["company_name"] = company.input_value().strip()
                        record["status"] = (
                            "company_confirmed"
                            if record["company_ruc"] and record["company_name"]
                            else "company_data_incomplete"
                        )
                    if record["status"] in {"company_confirmed", "company_data_incomplete"}:
                        page.screenshot(path=str(out / (oid + "-company.png")), full_page=True)
                        record["screenshot"] = str(out / (oid + "-company.png"))
                except Exception:
                    try:
                        page.screenshot(path=str(out / (oid + "-error.png")), full_page=True)
                    except Exception:
                        pass
                    raise
    except InvalidPortalCredentials:
        record["status"] = "access_lost"
    except BrowserOwnershipConflict:
        record["status"] = "busy"
    except Exception as exc:
        record["status"] = "unverified"
        record["error_type"] = type(exc).__name__
    return record


def render(rows, state, active):
    counts = {key: sum(r["status"] == key for r in rows) for key in LABELS}
    finished = sum(r["status"] not in {"pending", "running"} for r in rows)
    table = []
    for row in sorted(rows, key=lambda r: (r["status"] != "company_confirmed", r["full_name"])):
        stage = next((s for s in row.get("stages", []) if s["stage"] == "Separa Cita Peritaje"), {})
        values = [
            row["full_name"],
            row["order_id"],
            LABELS.get(row["status"], row["status"]),
            row.get("company_name", ""),
            row.get("company_ruc", ""),
            str(row.get("appointment_day", "")),
            stage.get("status", ""),
            row.get("checked_at", ""),
        ]
        cells = "".join("<td>" + escape(str(v)) + "</td>" for v in values)
        screenshot = Path(row.get("screenshot", ""))
        link = (
            '<a href="' + escape(screenshot.resolve().as_uri(), quote=True) + '">Captura</a>'
            if screenshot.is_file()
            else ""
        )
        table.append(
            '<tr data-status="' + row["status"] + '">' + cells + "<td>" + link + "</td></tr>"
        )
    options = "".join(
        '<option value="' + key + '">' + label + "</option>" for key, label in LABELS.items()
    )
    html = """<!doctype html><html lang="es"><meta charset="utf-8"><meta name="viewport" content="width=device-width">
<title>Reservas para empresas</title><style>body{font:16px system-ui;background:#f4f6f8;color:#172b36;margin:28px}h1{color:#145644}table{border-collapse:collapse;width:100%;background:white}td,th{text-align:left;padding:12px;border-bottom:1px solid #ddd}th{position:sticky;top:0;background:#145644;color:white}input,select{padding:10px;margin:8px}small{color:#536471}.table{overflow:auto}td{font-size:14px}</style>
<h1>Reservas para empresas</h1>"""
    html += f"<p><strong>{escape(state)}</strong> · {finished}/{len(rows)} revisados · {counts['company_confirmed']} empresas · {counts['access_lost']} sin acceso · {active} consultas activas</p>"
    html += "<p>Actualizado: " + datetime.now().astimezone().isoformat(timespec="seconds") + "</p>"
    html += "<small>Reserva confirmada en nuestra base. Empresa verificada en el expediente. Cita pasada no acredita asistencia. Los resultados conservan su fecha de consulta. Reporte local privado.</small>"
    html += (
        '<p><input id="q" placeholder="Buscar cliente, orden, empresa o RUC"><select id="filter"><option value="">Todos</option>'
        + options
        + "</select></p>"
    )
    html += (
        '<div class="table"><table><thead><tr>'
        + "".join(
            "<th>" + s + "</th>"
            for s in [
                "Cliente",
                "Orden",
                "Resultado",
                "Empresa",
                "RUC",
                "Cita",
                "Estado cita",
                "Verificado (UTC)",
                "Evidencia",
            ]
        )
        + "</tr></thead><tbody>"
        + "".join(table)
        + "</tbody></table></div>"
    )
    html += """<script>const q=document.querySelector('#q'),f=document.querySelector('#filter');const params=new URLSearchParams(location.hash.slice(1));q.value=params.get('q')||'';f.value=params.get('f')||'';function filter(){document.querySelectorAll('tbody tr').forEach(r=>r.hidden=!(r.textContent.toLowerCase().includes(q.value.toLowerCase())&&(!f.value||r.dataset.status===f.value)));history.replaceState(null,'','#'+new URLSearchParams({q:q.value,f:f.value}));}q.oninput=filter;f.onchange=filter;filter();setTimeout(()=>location.reload(),5000);</script></html>"""
    temporary = OUT / "index.tmp"
    temporary.write_text(html, encoding="utf-8")
    temporary.replace(OUT / "index.html")
    (OUT / "progress.json").write_text(
        json.dumps(
            {
                "state": state,
                "finished": finished,
                "total": len(rows),
                "active": active,
                "counts": counts,
            }
        ),
        encoding="utf-8",
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workers", type=int, choices=range(1, 5), default=4)
    parser.add_argument("--refresh-all", action="store_true")
    parser.add_argument("--order-id")
    parser.add_argument("--open-report", action="store_true")
    args = parser.parse_args()
    os.chdir(ROOT)
    OUT.mkdir(parents=True, exist_ok=True)
    import msvcrt

    lock = (OUT / "run.lock").open("a+b")
    lock.seek(0)
    if not lock.read(1):
        lock.write(b"0")
        lock.flush()
    lock.seek(0)
    try:
        msvcrt.locking(lock.fileno(), msvcrt.LK_NBLCK, 1)
    except OSError:
        raise SystemExit("Ya existe una revision activa.") from None
    configuration = load_settings(require_login=False)
    with psycopg.connect(configuration[0].database_url, row_factory=dict_row) as conn:
        conn.execute("SET TRANSACTION READ ONLY")
        rows = conn.execute(
            """SELECT r.reservation_id,r.order_id,r.appointment_day,r.program_expediente,r.program_plate,r.run_id,a.full_name,p.outcome AS previous_outcome FROM reservations r JOIN service_orders o USING(order_id) JOIN applicants a USING(applicant_id) LEFT JOIN LATERAL(SELECT outcome FROM post_appointment_reviews p WHERE p.order_id=r.order_id ORDER BY created_at DESC LIMIT 1)p ON true WHERE r.status='confirmed' AND (r.appointment_day < (now() AT TIME ZONE 'America/Lima')::date OR p.outcome='completed') ORDER BY r.appointment_day DESC,r.order_id"""
        ).fetchall()
    if args.order_id:
        rows = [r for r in rows if r["order_id"] == args.order_id]
    previous = {}
    for path in [ROOT / ".runtime/company-audit-20260908/results.jsonl", OUT / "results.jsonl"]:
        if path.exists():
            for line in path.read_text(encoding="utf-8").splitlines():
                try:
                    r = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if r["status"] not in {"company_candidate", "unverified", "busy"}:
                    previous[r["reservation_id"]] = {
                        k: v
                        for k, v in r.items()
                        if k not in {"fields", "company_nodes", "visible_text"}
                    }
    for row in rows:
        cached = previous.get(row["reservation_id"])
        if cached and not args.refresh_all:
            row.update(cached)
        else:
            row["status"] = "pending"
    pending = [r for r in rows if r["status"] == "pending"]
    capacity = args.workers
    errors = 0
    futures = {}
    render(rows, "En ejecución", 0)
    if args.open_report:
        webbrowser.open((OUT / "index.html").as_uri())
    try:
        with ThreadPoolExecutor(max_workers=args.workers) as pool:
            while pending or futures:
                while pending and len(futures) < capacity:
                    row = pending.pop(0)
                    row["status"] = "running"
                    futures[pool.submit(review, dict(row), configuration)] = row
                render(
                    rows,
                    "En ejecución" if capacity else "Detenida por errores del portal",
                    len(futures),
                )
                if not futures:
                    break
                completed, _ = wait(futures, timeout=2, return_when=FIRST_COMPLETED)
                for future in completed:
                    row = futures.pop(future)
                    try:
                        result = future.result()
                    except Exception as exc:
                        result = {**row, "status": "unverified", "error_type": type(exc).__name__}
                    row.update(result)
                    with (OUT / "results.jsonl").open("a", encoding="utf-8") as file:
                        file.write(json.dumps(result, default=str, ensure_ascii=False) + "\n")
                    if result["status"] == "unverified":
                        errors += 1
                        capacity = min(capacity, 1)
                        if errors >= 3:
                            capacity = 0
                    elif capacity:
                        errors = 0
                    print(row["order_id"], row["status"], flush=True)
                if completed:
                    time.sleep(1)
        render(rows, "Finalizada" if not pending else "Detenida: pendientes conservados", 0)
    finally:
        for row in rows:
            if row["status"] == "running":
                row["status"] = "pending"
        render(
            rows,
            "Finalizada"
            if all(r["status"] != "pending" for r in rows)
            else "Interrumpida: pendientes conservados",
            0,
        )
        lock.close()


if __name__ == "__main__":
    logging.basicConfig(level=logging.CRITICAL)
    main()
