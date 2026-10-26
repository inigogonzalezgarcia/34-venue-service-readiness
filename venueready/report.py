"""Outputs: report.html, opening-pack.md and the CSVs (service readiness, device health, vendor cover, incidents by outlet, actions,
findings)."""
from __future__ import annotations

import csv
import html
from collections import Counter
from pathlib import Path

from .checks import (AREAS, CRITICAL, INFO, WARNING, Finding, area_status, device_state, now_label, open_incidents, recent_incidents,
                     service_rows, vendor_cover)
from .model import KIND_LABEL, Data, venue_wide

e = html.escape
KIND_ORDER = list(KIND_LABEL)


def build(d: Data) -> dict:
    rows = service_rows(d)
    devices = [device_state(d, x) for x in d.devices]
    return dict(rows=rows, devices=devices, cover=vendor_cover(d, rows), open=open_incidents(d))


def summary(d: Data, findings: list[Finding], b: dict) -> dict:
    rows = b["rows"]
    v = Counter(r["verdict"] for r in rows)
    today = [r for r in rows if r["service"].start.date() <= d.today]
    return dict(services=len(rows), today=len(today), at_risk=v["at risk"], attention=v["attention"], ready=v["ready"],
                today_at_risk=sum(r["verdict"] == "at risk" for r in today),
                checks_missing=sum(r["check"] == "missing" for r in rows), devices=len(b["devices"]),
                down=sum(x["down"] for x in b["devices"]), degraded=sum(x["degraded"] and not x["down"] for x in b["devices"]),
                open=len(b["open"]), late=sum(x["late"] for x in b["open"]),
                incidents=len(recent_incidents(d)), minutes_lost=sum(i.minutes_lost for i in recent_incidents(d)),
                critical=sum(f.severity == CRITICAL for f in findings), warning=sum(f.severity == WARNING for f in findings),
                info=sum(f.severity == INFO for f in findings))


# ---------------------------------------------------------------- csv

def _w(path: Path, header: list[str], rows: list[list]) -> None:
    with open(path, "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(header)
        w.writerows(rows)


def _t(v, f="%Y-%m-%d %H:%M") -> str:
    return v.strftime(f) if v else ""


def write_findings(findings: list[Finding], path: Path) -> None:
    _w(path, ["severity", "area", "code", "subject", "detail", "next_step", "owner", "items"],
       [[f.severity, f.area, f.code, f.subject, f.detail, f.fix, f.owner, "; ".join(f.items)] for f in findings])


def write_actions(findings: list[Finding], path: Path) -> None:
    _w(path, ["ref", "action", "next_step", "owner", "severity", "due", "done"],
       [[f.code, f.subject, f.fix, f.owner, f.severity, "", ""] for f in findings if f.severity != INFO])


def write_services(b: dict, path: Path) -> None:
    _w(path, ["service_id", "outlet", "service", "type", "start", "end", "guests", "on_duty", "opening_check", "verdict", "issues"],
       [[s.service_id, s.outlet, s.name, s.kind, _t(s.start), _t(s.end), s.guests, s.on_duty, r["check"], r["verdict"],
         " | ".join(f"{i.code} {i.text}" for i in r["issues"])] for r in b["rows"] for s in [r["service"]]])


def _status(x: dict) -> str:
    return "down" if x["down"] else "attention" if x["notes"] else "ok"


def write_devices(d: Data, b: dict, path: Path) -> None:
    _w(path, ["device", "outlet", "type", "model", "status", "last_seen", "version", "target_version", "next_update", "vendor", "state", "notes"],
       [[v.device_id, v.outlet, KIND_LABEL[v.kind], v.model, v.status, _t(v.last_seen), v.version, v.target, _t(v.next_update),
         (d.vendor_of(v).vendor if d.vendor_of(v) else ""), _status(x), "; ".join(x["notes"] + (["behind target version"] if x["behind"] else []))]
        for x in sorted(b["devices"], key=lambda x: (x["device"].outlet, KIND_ORDER.index(x["device"].kind), x["device"].device_id))
        for v in [x["device"]]])


def write_vendors(b: dict, path: Path) -> None:
    _w(path, ["vendor", "covers", "support_hours", "sla_hours", "contract_end", "days_left", "devices", "open_tickets", "past_sla",
              "services_outside_hours"],
       [[v.vendor, ", ".join(KIND_LABEL[k] for k in v.covers), v.hours, "" if v.sla_hours is None else f"{v.sla_hours:g}", _t(v.contract_end, "%Y-%m-%d"),
         "" if c["days_left"] is None else c["days_left"], len(c["devices"]),
         sum(o["vendor"] is v for o in b["open"]), sum(o["vendor"] is v and o["late"] for o in b["open"]),
         "; ".join(f"{s.service_id} {s.name} {_t(s.start)}" for s in c["gaps"])] for c in b["cover"] for v in [c["vendor"]]])


def write_incidents(d: Data, path: Path) -> None:
    by = {}
    for i in recent_incidents(d):
        by.setdefault(i.outlet or "Venue", []).append(i)
    rows = sorted(by.items(), key=lambda kv: (-sum(i.minutes_lost for i in kv[1]), -len(kv[1]), kv[0]))
    _w(path, ["outlet", "incidents", "open", "minutes_lost", "categories", "devices", "last_incident", "last_summary"],
       [[k, len(v), sum(i.closed is None for i in v), f"{sum(i.minutes_lost for i in v):g}",
         ", ".join(f"{c} {n}" for c, n in Counter(i.category for i in v).most_common()),
         ", ".join(f"{c} {n}" for c, n in Counter(i.device_id for i in v if i.device_id).most_common(4)),
         _t(max(v, key=lambda i: i.opened).opened), max(v, key=lambda i: i.opened).summary] for k, v in rows])


# ---------------------------------------------------------------- opening pack

def opening_md(d: Data, findings: list[Finding], b: dict) -> str:
    s, sm = d.settings, summary(d, findings, b)
    out = [f"# Service readiness · {s.organisation}", "",
           f"As of {now_label(d.as_of)} · services in the next {s.horizon_days} days.", "", "## Summary", "",
           f"- Services: {sm['services']} ({sm['today']} today): {sm['at_risk']} at risk, {sm['attention']} need attention, {sm['ready']} ready.",
           f"- Devices: {sm['down']} down and {sm['degraded']} degraded out of {sm['devices']}.",
           f"- Vendor tickets: {sm['open']} open, {sm['late']} past the SLA.",
           f"- Incidents: {sm['incidents']} in {s.incident_window_days} days, {sm['minutes_lost']:g} service minutes lost.",
           f"- Findings: {sm['critical']} critical, {sm['warning']} warnings, {sm['info']} for information.", "", "## Decisions", ""]
    out += [f"- [ ] **{f.code} {f.subject}** ({f.owner or 'owner?'}) → {f.fix}" for f in findings if f.severity != INFO] or ["- None."]
    out += ["", "## Service by service", ""]
    day = None
    for r in b["rows"]:
        sv = r["service"]
        if sv.start.date() != day:
            day = sv.start.date()
            out += [f"### {day:%A %d %B}", ""]
        out += [f"#### {sv.start:%H:%M}–{sv.end:%H:%M} · {sv.outlet} · {sv.name} — {r['verdict'].upper()}", ""]
        out.append(f"- {sv.kind.title()}, {sv.guests} guests. IT: {sv.on_duty or '**nobody on duty**'}.")
        if r["needs_check"]:
            out.append(f"- [{'x' if r['check'].startswith('done') else ' '}] Opening check: {r['check']}.")
        kinds = Counter(x["device"].kind for x in r["devices"])
        downk = Counter(x["device"].kind for x in r["devices"] if x["down"])
        if kinds:
            out.append("- [" + (" " if downk else "x") + "] Devices: " + ", ".join(
                f"{kinds[k] - downk[k]}/{kinds[k]} {KIND_LABEL[k]}" for k in KIND_ORDER if kinds[k]) + " working.")
        for i in sorted(r["issues"], key=lambda i: i.severity != CRITICAL):
            out.append(f"- [ ] {i.code}: {i.text}")
        out.append("")
    out += ["## For information", ""]
    out += [f"- {f.code} {f.subject}: {f.detail}" for f in findings if f.severity == INFO] or ["- Nothing."]
    out += ["", "Generated by venueready from the service plan, the device register, the vendor list and the incident log.", ""]
    return "\n".join(out)


# ---------------------------------------------------------------- html

CSS = """
:root{--bg:#f6f7f8;--card:#fff;--ink:#1b2128;--muted:#66717c;--line:#e2e5e9;--ok:#1e7a4c;--warn:#a46200;--bad:#b42318;--info:#0b6bcb}
@media (prefers-color-scheme:dark){:root{--bg:#13171b;--card:#1b2127;--ink:#e7eaee;--muted:#9aa5b0;--line:#2b333b;--ok:#4cc38a;--warn:#f0a83a;--bad:#f2685c;--info:#5aa9f0}}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--ink);font:15px/1.5 system-ui,-apple-system,Segoe UI,sans-serif}
main{max-width:1100px;margin:0 auto;padding:28px 18px 60px}h1{font-size:26px;margin:0 0 4px}h2{font-size:18px;margin:34px 0 12px}
.muted{color:var(--muted)}.tiles{display:grid;grid-template-columns:repeat(auto-fit,minmax(118px,1fr));gap:10px;margin-top:20px}
.tile{background:var(--card);border:1px solid var(--line);border-radius:10px;padding:14px 16px}.tile b{display:block;font-size:26px}
.areas{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:10px}
.area{background:var(--card);border:1px solid var(--line);border-left:5px solid var(--ok);border-radius:10px;padding:10px 14px}
.area.critical{border-left-color:var(--bad)}.area.warning{border-left-color:var(--warn)}
.area .lbl{display:block;font-size:12px;text-transform:uppercase;letter-spacing:.04em;color:var(--muted);margin-bottom:4px}.area .cnt{display:block;font-size:13px;color:var(--muted);margin-top:4px}
table{width:100%;border-collapse:collapse;background:var(--card);border:1px solid var(--line);border-radius:10px;overflow:hidden}
th,td{text-align:left;padding:8px 10px;border-bottom:1px solid var(--line);vertical-align:top}th{font-size:12px;text-transform:uppercase;letter-spacing:.04em;color:var(--muted)}
tr:last-child td{border-bottom:0}.wrap{overflow-x:auto}.num{text-align:right;font-variant-numeric:tabular-nums;white-space:nowrap}
.pill{display:inline-block;white-space:nowrap;padding:1px 8px;border-radius:99px;font-size:12px;font-weight:600;border:1px solid currentColor}
.critical{color:var(--bad)}.warning{color:var(--warn)}.info{color:var(--info)}.ok{color:var(--ok)}
.area.critical,.area.warning,.area.ok{color:inherit}
.pill.ready{color:var(--ok)}.pill.attention{color:var(--warn)}.pill.at-risk{color:var(--bad)}
.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(230px,1fr));gap:10px}
.outlet{background:var(--card);border:1px solid var(--line);border-radius:10px;padding:12px 14px}.outlet h3{margin:0 0 8px;font-size:15px}
.dev{display:flex;justify-content:space-between;gap:8px;font-size:13px;padding:2px 0}.dev span:last-child{white-space:nowrap}
.bar{display:inline-block;height:9px;border-radius:5px;background:var(--warn);vertical-align:middle;margin-right:8px}.day td{background:var(--bg);font-weight:600;font-size:13px}td.nw{white-space:nowrap}td.fix{font-size:13px;color:var(--muted);max-width:380px}
footer{margin-top:40px;font-size:13px}
"""


def _pill(cls: str, text: str) -> str:
    return f"<span class='pill {cls}'>{e(text)}</span>"


def _vpill(v: str) -> str:
    return _pill(v.replace(" ", "-"), v.upper())


def render_html(d: Data, findings: list[Finding], title: str, b: dict) -> str:
    s, sm, st = d.settings, summary(d, findings, b), area_status(findings)
    h = [f"<!doctype html><html lang='en'><head><meta charset='utf-8'><meta name='viewport' content='width=device-width,initial-scale=1'>"
         f"<title>{e(title)}</title><style>{CSS}</style></head><body><main>",
         f"<h1>{e(title)}</h1><p class='muted'>Tills, payments, network, guest systems and vendors behind every service in the next "
         f"{s.horizon_days} days · as of {now_label(d.as_of)}</p><div class='tiles'>"]
    tiles = [("Services", str(sm["services"]), f"{sm['today']} today"),
             ("At risk", str(sm["at_risk"]), f"{sm['today_at_risk']} today"),
             ("Attention", str(sm["attention"]), f"{sm['ready']} ready"),
             ("Opening checks missing", str(sm["checks_missing"]), "close to opening"),
             ("Devices down", f"{sm['down']}/{sm['devices']}", f"{sm['degraded']} degraded"),
             ("Tickets past SLA", f"{sm['late']}/{sm['open']}", "open with vendors"),
             ("Minutes lost", f"{sm['minutes_lost']:g}", f"{sm['incidents']} incidents, {s.incident_window_days} days"),
             ("Critical", str(sm["critical"]), f"{sm['warning']} warnings · {sm['info']} info")]
    h += [f"<div class='tile'><span class='muted'>{e(a)}</span><b>{e(x)}</b><span class='muted'>{e(y)}</span></div>" for a, x, y in tiles]
    h.append("</div><h2>Status by area</h2><div class='areas'>")
    for a in AREAS:
        n = sum(f.area == a and f.severity != INFO for f in findings)
        h.append(f"<div class='area {st[a]}'><span class='lbl'>{e(a)}</span>{_pill(st[a], 'OK' if st[a] == 'ok' else st[a].upper())}"
                 f"<span class='cnt'>{n} to act on</span></div>")
    h.append("</div>")
    # services
    h.append("<h2>Services</h2><div class='wrap'><table><tr><th>Time</th><th>Service</th><th>Outlet</th><th>Opening check</th><th>Status</th>"
             "<th>What to fix</th></tr>")
    day = None
    for r in b["rows"]:
        sv = r["service"]
        if sv.start.date() != day:
            day = sv.start.date()
            h.append(f"<tr class='day'><td colspan='6'>{day:%A %d %B}</td></tr>")
        iss = "<br>".join(f"<span class='{i.severity}'>●</span> {e(i.text)}" for i in sorted(r["issues"], key=lambda i: i.severity != CRITICAL))
        h.append(f"<tr><td class='nw'>{sv.start:%H:%M}–{sv.end:%H:%M}</td><td><b>{e(sv.name)}</b><br><span class='muted'>{e(sv.kind)} · "
                 f"{sv.guests} guests · IT: {e(sv.on_duty) or 'nobody'}</span></td><td>{e(sv.outlet)}</td>"
                 f"<td class='nw {'warning' if r['check'] == 'missing' else ''}'>{e(r['check'])}</td>"
                 f"<td>{_vpill(r['verdict'])}</td><td>{iss or '–'}</td></tr>")
    h.append("</table></div>")
    crit = [f for f in findings if f.severity == CRITICAL]
    if crit:
        h.append("<h2>Fix first</h2><div class='wrap'><table><tr><th>Subject</th><th>What</th><th>Next step</th><th>Owner</th></tr>")
        h += [f"<tr><td><b>{e(f.subject)}</b><br><span class='muted'>{e(f.area)} · {e(f.code)}</span></td><td>{e(f.detail)}</td>"
              f"<td class='fix'>{e(f.fix)}</td><td class='nw'>{e(f.owner)}</td></tr>" for f in crit]
        h.append("</table></div>")
    # devices by outlet
    h.append("<h2>Devices by outlet</h2><div class='grid'>")
    outlets = sorted({x["device"].outlet or "Venue" for x in b["devices"]}, key=lambda o: (venue_wide(o), o))
    for ol in outlets:
        xs = [x for x in b["devices"] if (x["device"].outlet or "Venue") == ol]
        h.append(f"<div class='outlet'><h3>{e(ol)}</h3>")
        for k in KIND_ORDER:
            ks = [x for x in xs if x["device"].kind == k]
            if not ks:
                continue
            bad = [x for x in ks if x["down"]]
            warn = [x for x in ks if not x["down"] and x["notes"]]
            cls = "critical" if bad else "warning" if warn else "ok"
            label = f"{len(ks) - len(bad)}/{len(ks)}" + (f" · {', '.join(x['device'].device_id for x in bad + warn)}" if bad or warn else "")
            h.append(f"<div class='dev'><span>{e(KIND_LABEL[k])}</span><span class='{cls}'>{e(label)}</span></div>")
        h.append("</div>")
    h.append("</div>")
    # devices with something to do
    todo = [x for x in b["devices"] if x["down"] or x["notes"]]
    if todo:
        h.append(f"<h2>Devices with something to do ({len(todo)} of {len(b['devices'])})</h2><div class='wrap'><table><tr><th>Device</th>"
                 "<th>Outlet</th><th>State</th><th>Vendor</th><th>Open ticket</th></tr>")
        for x in sorted(todo, key=lambda x: (not x["down"], x["device"].outlet, x["device"].device_id)):
            v = x["device"]
            ven = d.vendor_of(v)
            tk = next((o for o in b["open"] if o["device"] is v), None)
            tks = (f"{e(tk['incident'].ticket)} · {tk['age']:.0f} h" + (" · <span class='critical'>past SLA</span>" if tk["late"] else "")) if tk else "–"
            h.append(f"<tr><td class='nw'><b>{e(v.device_id)}</b><br><span class='muted'>{e(KIND_LABEL[v.kind])} · {e(v.model)}</span></td>"
                     f"<td>{e(v.outlet or 'Venue')}</td><td class='{'critical' if x['down'] else 'warning'}'>{e('; '.join(x['notes']))}</td>"
                     f"<td>{e(ven.vendor) if ven else '–'}</td><td class='nw'>{tks}</td></tr>")
        h.append("</table></div>")
    # vendors
    if b["cover"]:
        h.append("<h2>Vendors</h2><div class='wrap'><table><tr><th>Vendor</th><th>Covers</th><th>Support hours</th><th>Contract</th>"
                 "<th class='num'>Open · past SLA</th><th>Services outside hours</th></tr>")
        for c in b["cover"]:
            v = c["vendor"]
            dl = c["days_left"]
            ccls = "critical" if dl is not None and dl < 0 else "warning" if dl is not None and dl <= s.contract_warn_days else ""
            op = [o for o in b["open"] if o["vendor"] is v]
            h.append(f"<tr><td class='nw'><b>{e(v.vendor)}</b><br><span class='muted'>{len(c['devices'])} devices</span></td>"
                     f"<td>{e(', '.join(KIND_LABEL[k] for k in v.covers))}</td><td class='nw'>{e(v.hours) or '–'}"
                     f"{f'<br><span class=muted>SLA {v.sla_hours:g} h</span>' if v.sla_hours is not None else ''}</td>"
                     f"<td class='nw {ccls}'>{_t(v.contract_end, '%d %b %Y') or '–'}</td>"
                     f"<td class='num'>{len(op)} · {sum(o['late'] for o in op)}</td><td>{len(c['gaps']) or '–'}</td></tr>")
        h.append("</table></div>")
    inc = recent_incidents(d)
    if inc:
        mins, cnt = Counter(), Counter()
        for i in inc:
            k = i.outlet or "Venue"
            cnt[k] += 1
            mins[k] += i.minutes_lost
        top = max(mins.values()) or 1
        h.append(f"<h2>Incidents in the last {s.incident_window_days} days</h2><div class='wrap'><table><tr><th>Outlet</th>"
                 "<th class='num'>Incidents</th><th>Service minutes lost</th></tr>")
        h += [f"<tr><td>{e(k)}</td><td class='num'>{n}</td><td class='nw'><span class='bar' style='width:{max(4, round(160 * mins[k] / top))}px'></span>"
              f"{mins[k]:g}</td></tr>" for k, n in sorted(cnt.items(), key=lambda kv: (-mins[kv[0]], kv[0]))]
        h.append("</table></div>")
    h.append("<h2>All findings</h2><div class='wrap'><table><tr><th>Severity</th><th>Area</th><th>Subject</th><th>Detail</th><th>Next step</th><th>Owner</th></tr>")
    h += [f"<tr><td>{_pill(f.severity, f.severity.upper())}</td><td class='nw'>{e(f.area)}</td><td>{e(f.subject)}</td>"
          f"<td>{e(f.detail)}</td><td class='fix'>{e(f.fix)}</td><td class='nw'>{e(f.owner)}</td></tr>" for f in findings]
    h.append("</table></div><footer class='muted'>Generated by venueready. Fictional demo data unless you ran it on your own exports.</footer></main></body></html>")
    return "".join(h)
