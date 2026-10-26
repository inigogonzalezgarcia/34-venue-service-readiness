"""The checks: for every service in the horizon, the opening check and the IT cover, the tills, kitchen printers, card terminals and cash
machines of its outlet, the network it runs on, the guest systems behind it and the vendors that would fix them, with a verdict per
service. Each finding says what to do and who owns it."""
from __future__ import annotations

import math
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timedelta

from .model import KIND_LABEL, Data, Device, Service, _norm, covered, venue_wide, version

CRITICAL, WARNING, INFO = "critical", "warning", "info"
ORDER = {CRITICAL: 0, WARNING: 1, INFO: 2}
AREAS = ("Services", "POS & payments", "Network", "Guest systems", "Vendors", "Incidents")
VERDICT = {CRITICAL: "at risk", WARNING: "attention", None: "ready"}
SELLING = ("till", "handheld")
FIX_KINDS = ("till", "handheld", "kitchen", "card", "cash", "ap", "switch", "firewall", "uplink", "pms", "encoder")


@dataclass
class Finding:
    severity: str
    area: str
    code: str
    subject: str
    detail: str
    fix: str
    owner: str = ""
    items: list[str] = field(default_factory=list)


@dataclass
class Issue:
    severity: str
    code: str
    text: str


def _n(k: int, word: str, plural: str | None = None) -> str:
    return f"{k} {word if k == 1 else (plural or word + 's')}"


def _top(items: list[str], k: int = 6) -> str:
    return ", ".join(items[:k]) + (f" and {len(items) - k} more" if len(items) > k else "")


def _when(s: Service) -> str:
    return f"{s.start:%a %d %b %H:%M}"


# ---------------------------------------------------------------- devices

def device_state(d: Data, dev: Device) -> dict:
    s = d.settings
    stale = dev.last_seen is not None and (d.as_of - dev.last_seen) > timedelta(hours=s.heartbeat_hours)
    down = dev.status in ("offline", "error") or stale
    notes = []
    if dev.status == "error":
        notes.append("error")
    elif dev.status == "offline":
        notes.append("offline")
    elif stale:
        notes.append("not seen")
    if dev.last_seen and down:
        notes[-1] += f" since {dev.last_seen:%a %d %b %H:%M}"
    if dev.status == "degraded":
        notes.append("degraded")
    if dev.kind == "cash" and not down:
        if dev.cash is not None and dev.cash < s.cash_float_min:
            notes.append(f"cash for change {dev.cash:g} (minimum {s.cash_float_min:g})")
        if dev.fill is not None and dev.fill >= s.cash_full_pct:
            notes.append(f"stacker {dev.fill:g}% full")
    if dev.kind == "pms" and not down and dev.queue is not None and dev.queue > s.pms_queue_max:
        notes.append(f"{dev.queue:g} postings waiting")
    behind = bool(dev.target and dev.version and version(dev.version) < version(dev.target))
    return dict(device=dev, down=down, stale=stale, degraded=dev.status == "degraded", behind=behind, notes=notes)


def recent_incidents(d: Data) -> list:
    since = d.as_of - timedelta(days=d.settings.incident_window_days)
    return [i for i in d.incidents if since <= i.opened <= d.as_of]


def open_incidents(d: Data) -> list[dict]:
    """Open tickets with the vendor that should fix them and whether the vendor's SLA has passed."""
    out = []
    for i in d.incidents:
        if i.closed or i.opened > d.as_of:
            continue
        dev = d.device(i.device_id) if i.device_id else None
        v = next((x for x in d.vendors if i.vendor and _norm(x.vendor) == _norm(i.vendor)), None) or (d.vendor_of(dev) if dev else None)
        age = (d.as_of - i.opened).total_seconds() / 3600
        late = bool(v and v.sla_hours is not None and age > v.sla_hours)
        out.append(dict(incident=i, device=dev, vendor=v, age=age, late=late))
    return out


def repeat_devices(d: Data) -> dict[str, list]:
    by = defaultdict(list)
    for i in recent_incidents(d):
        if i.device_id:
            by[_norm(i.device_id)].append(i)
    return {k: v for k, v in by.items() if len(v) >= d.settings.repeat_incidents}


def _label(st: dict) -> str:
    dv = st["device"]
    return f"{dv.device_id} ({', '.join(st['notes']) or dv.status})"


# ---------------------------------------------------------------- per service

def service_rows(d: Data) -> list[dict]:
    s = d.settings
    states = {_norm(x.device_id): device_state(d, x) for x in d.devices}
    opened = open_incidents(d)
    repeats = repeat_devices(d)
    rows = []
    for sv in d.upcoming():
        iss: list[Issue] = []
        add = lambda sev, code, text: iss.append(Issue(sev, code, text))  # noqa: E731
        today = sv.start.date() <= d.today
        own = [states[_norm(x.device_id)] for x in d.outlet_devices(sv.outlet, shared=False)]
        shared = [states[_norm(x.device_id)] for x in d.devices if venue_wide(x.outlet)]
        mine = own + shared
        of = lambda *kinds: [x for x in own if x["device"].kind in kinds]  # noqa: E731
        venue = lambda *kinds: [x for x in mine if x["device"].kind in kinds]  # noqa: E731
        # opening check
        needs = sv.kind in s.check_kinds
        check = "not required"
        if needs:
            lo = sv.start - timedelta(hours=s.check_window_hours)
            if sv.check_done and lo <= sv.check_done <= sv.start:
                check = f"done {sv.check_done:%H:%M}"
            elif sv.start <= d.as_of:
                check = "missing"
                add(WARNING, "SVC-01", "service started without an opening check")
            elif sv.start - d.as_of <= timedelta(hours=s.check_lead_hours):
                check = "missing"
                add(CRITICAL, "SVC-01", f"opens at {sv.start:%H:%M} and no opening check yet")
            else:
                check = f"due {lo:%a %H:%M}–{sv.start:%H:%M}" if today else "not due"
        # IT cover
        if not sv.on_duty and (sv.guests >= s.duty_min_guests or sv.kind == "event"):
            add(WARNING, "SVC-02", f"{sv.guests} guests and nobody from IT on duty or on call")
        # changes inside the freeze
        for st in mine:
            dv = st["device"]
            if dv.next_update and sv.start - timedelta(hours=s.freeze_hours) <= dv.next_update <= sv.end:
                add(WARNING, "SVC-03", f"{KIND_LABEL[dv.kind]} {dv.device_id} update scheduled {dv.next_update:%a %d %b %H:%M}, inside the "
                                       f"{s.freeze_hours} h freeze")
        # selling points
        sell = of(*SELLING)
        if sell:
            ok = [x for x in sell if not x["down"]]
            need = math.ceil(sv.guests / s.guests_per_till) if sv.guests and s.guests_per_till else 1
            down = [x for x in sell if x["down"]]
            if not ok:
                add(CRITICAL, "POS-01", f"no till or handheld working: {_top([_label(x) for x in down])}")
            elif len(ok) < need:
                add(WARNING, "POS-01", f"{len(ok)} tills and handhelds working for {sv.guests} guests ({need} needed at {s.guests_per_till} per till)"
                    + (f"; down: {_top([_label(x) for x in down])}" if down else ""))
            elif down:
                add(WARNING, "POS-01", f"down: {_top([_label(x) for x in down])}")
        if sv.kind in s.food_kinds:
            kit = of("kitchen")
            if kit and not [x for x in kit if not x["down"]]:
                add(CRITICAL, "POS-02", f"no kitchen printer or KDS working, orders will not reach the kitchen: {_top([_label(x) for x in kit])}")
            elif [x for x in kit if x["down"]]:
                add(WARNING, "POS-02", f"kitchen printer or KDS down: {_top([_label(x) for x in kit if x['down']])}")
        rp = [x for x in of("printer") if x["down"]]
        if rp:
            add(WARNING, "POS-02", f"receipt printer down: {_top([_label(x) for x in rp])}")
        # payments
        cards = of("card")
        if sell and not cards:
            add(WARNING, "PAY-01", "no card terminal registered in the outlet")
        elif cards and not [x for x in cards if not x["down"]]:
            add(CRITICAL, "PAY-01", f"no card terminal working: {_top([_label(x) for x in cards])}")
        elif [x for x in cards if x["down"]]:
            add(WARNING, "PAY-01", f"card terminal down: {_top([_label(x) for x in cards if x['down']])}")
        for st in of("cash"):
            if st["down"]:
                add(CRITICAL, "PAY-02", f"cash machine {_label(st)}")
            elif today:
                for t in st["notes"]:
                    if t != "degraded":
                        add(WARNING, "PAY-02", f"cash machine {st['device'].device_id}: {t}")
        # network
        lines = venue("uplink")
        if lines and not [x for x in lines if not x["down"]]:
            add(CRITICAL, "NET-01", "no internet line working: card payments, PMS and cloud POS are down")
        elif [x for x in lines if x["down"] and x["device"].role != "backup"]:
            up = [x["device"].device_id for x in lines if not x["down"]]
            add(WARNING, "NET-01", f"primary internet line down, running on {', '.join(up)}")
        aps = of("ap")
        if aps and not [x for x in aps if not x["down"]]:
            add(CRITICAL, "NET-02", f"no Wi-Fi access point working, handhelds and wireless card terminals are off: {_top([_label(x) for x in aps])}")
        elif [x for x in aps if x["down"]]:
            add(WARNING, "NET-02", f"access point down: {_top([_label(x) for x in aps if x['down']])}")
        for st in venue("switch", "firewall"):
            if st["down"]:
                add(CRITICAL, "NET-03", f"{KIND_LABEL[st['device'].kind]} {_label(st)}")
            elif st["degraded"]:
                add(WARNING, "NET-03", f"{KIND_LABEL[st['device'].kind]} {st['device'].device_id} degraded")
        # guest systems
        if sv.kind in s.room_charge_kinds or sv.kind == "hotel":
            for st in venue("pms"):
                if st["down"]:
                    add(CRITICAL, "GST-01", f"PMS interface {_label(st)}: room charges and guest lookups fail")
                elif today and any("postings" in t for t in st["notes"]):
                    add(WARNING, "GST-01", f"PMS interface {st['device'].device_id}: {st['notes'][-1]} (room charges not reaching the folio)")
        if sv.kind == "hotel":
            for st in venue("headend"):
                if st["down"]:
                    add(CRITICAL, "GST-02", f"IPTV headend {_label(st)}: no TV in any room")
            boxes = [x for x in venue("stb") if x["down"]]
            if len(boxes) > s.stb_offline_max:
                add(WARNING, "GST-02", f"{len(boxes)} IPTV boxes offline in guest rooms ({_top([x['device'].device_id for x in boxes])})")
            enc = venue("encoder")
            if enc and not [x for x in enc if not x["down"]]:
                add(CRITICAL, "GST-03", f"no key card encoder working: {_top([_label(x) for x in enc])}")
        # vendors and incidents
        ids = {_norm(x["device"].device_id) for x in own}
        for o in opened:
            dv = o["device"]
            if not dv or _norm(dv.device_id) not in ids or not o["late"]:
                continue
            st = states[_norm(dv.device_id)]
            sev = CRITICAL if st["down"] and today and dv.kind in FIX_KINDS else WARNING
            add(sev, "VND-01", f"{o['incident'].ticket or 'ticket'} on {dv.device_id} open {o['age']:.0f} h with {o['vendor'].vendor} "
                               f"(SLA {o['vendor'].sla_hours:g} h)")
        for key, inc in repeats.items():
            if key in {_norm(x["device"].device_id) for x in own}:
                cats = Counter(i.category for i in inc if i.category)
                add(WARNING, "INC-01", f"{inc[0].device_id}: {len(inc)} incidents in {s.incident_window_days} days "
                                       f"({', '.join(c for c, _ in cats.most_common(2))})")
        sev = CRITICAL if any(i.severity == CRITICAL for i in iss) else WARNING if iss else None
        rows.append(dict(service=sv, check=check, needs_check=needs, issues=iss, devices=own, verdict=VERDICT[sev], severity=sev))
    return rows


# ---------------------------------------------------------------- findings

def _collect(rows: list[dict], code: str) -> list[tuple[dict, Issue]]:
    return [(r, i) for r in rows for i in r["issues"] if i.code == code]


def vendor_cover(d: Data, rows: list[dict]) -> list[dict]:
    """For every vendor: contract status, the devices it covers and the services whose opening or closing time falls outside its hours."""
    out = []
    for v in d.vendors:
        devs = [x for x in d.devices if d.vendor_of(x) is v]
        outlets = {_norm(x.outlet) for x in devs}
        shared = any(venue_wide(x.outlet) for x in devs)
        gaps = []
        for r in rows:
            sv = r["service"]
            if not (shared or _norm(sv.outlet) in outlets):
                continue
            last = sv.end - timedelta(minutes=1)
            if not covered(v.hours, sv.start) or not covered(v.hours, last):
                gaps.append(sv)
        days = (v.contract_end - d.today).days if v.contract_end else None
        out.append(dict(vendor=v, devices=devs, gaps=gaps, days_left=days))
    return out


def run_all(d: Data, rows: list[dict] | None = None) -> list[Finding]:
    s = d.settings
    rows = rows if rows is not None else service_rows(d)
    o = s.owner
    out: list[Finding] = []

    def per_service(code, area, owner, word, fix):
        hits = _collect(rows, code)
        for sev in (CRITICAL, WARNING):
            hs = [(r, i) for r, i in hits if i.severity == sev]
            if not hs:
                continue
            ids = sorted({r["service"].service_id for r, _ in hs})
            det = [f"{r['service'].outlet} · {r['service'].name} ({_when(r['service'])}): {i.text}" for r, i in hs]
            out.append(Finding(sev, area, code, f"{_n(len(ids), 'service')} {word}", _top(det, 8), fix, owner, ids))

    per_service("SVC-01", "Services", o("services"), "without an opening check",
                "Run the opening check with the outlet manager before doors open: one sale and one card payment on every till, a ticket to the "
                "kitchen, the cash machine float, Wi-Fi on a handheld; record the time in services.csv.")
    per_service("SVC-02", "Services", o("services"), "with many guests and no IT cover",
                "Name who is on duty or on call for the service, with the vendor numbers and the fallback kit (spare handheld, 4G router, "
                "paper order pads) at hand.")
    per_service("SVC-03", "Services", o("services"), "with a device update scheduled inside the freeze",
                "Move the update to the morning after the service, or apply it now and repeat the opening check.")
    per_service("POS-01", "POS & payments", o("pos"), "short of working tills or handhelds",
                "Bring the down tills and handhelds back (power, network, POS service sign-in), move spares from a closed outlet, or rent "
                "handhelds for the busiest services.")
    per_service("POS-02", "POS & payments", o("pos"), "with a kitchen or receipt printer down",
                "Replace the printer or reroute the kitchen tickets to another printer or KDS in the POS back office, and test one order end to end.")
    per_service("PAY-01", "POS & payments", o("pos"), "with card terminals down",
                "Swap the terminal with the acquirer's spare, or pair a working terminal to the till; check it on the same network as the till.")
    per_service("PAY-02", "POS & payments", o("pos"), "with a cash machine that needs attention",
                "Load the change float or empty the stacker before the service, and clear any error with the cash machine vendor.")
    per_service("NET-01", "Network", o("network"), "running without the primary internet line",
                "Open a priority ticket with the carrier and confirm the backup line carries payments and the PMS; tell the outlet managers.")
    per_service("NET-02", "Network", o("network"), "with Wi-Fi access points down",
                "Check the access point's power (PoE port) and uplink; move a spare access point into place before the service.")
    per_service("NET-03", "Network", o("network"), "behind a switch or firewall that is down or degraded",
                "Check power, PoE budget and uplinks, and keep the provider on the line until the outlet's tills and terminals are back.")
    per_service("GST-01", "Guest systems", o("guest"), "with the PMS interface down or behind",
                "Restart the interface service and check the postings reach the guest folios; post the waiting charges by hand if needed.")
    per_service("GST-02", "Guest systems", o("guest"), "with IPTV not working in guest rooms",
                "Reboot or replace the boxes in the rooms with arrivals first, and check the headend channels.")
    per_service("GST-03", "Guest systems", o("guest"), "with no key card encoder working",
                "Restart the encoder and its link to the PMS; keep pre-encoded master and spare guest cards at reception.")
    per_service("VND-01", "Vendors", o("vendors"), "affected by vendor tickets past their SLA",
                "Escalate with the vendor's service manager, ask for a fix time before the service, and log the breach for the monthly review.")
    per_service("INC-01", "Incidents", o("incidents"), "with a device that keeps failing",
                "Replace the device instead of fixing it again, or find the common cause (cable, power, network port) before the service.")

    # venue-wide
    late_shared = [x for x in open_incidents(d) if x["late"] and x["device"] and venue_wide(x["device"].outlet)]
    if late_shared:
        out.append(Finding(WARNING, "Vendors", "VND-01", f"{_n(len(late_shared), 'ticket')} on shared systems past the vendor SLA",
                           _top([f"{x['incident'].ticket} {x['device'].device_id} open {x['age']:.0f} h with {x['vendor'].vendor} "
                                 f"(SLA {x['vendor'].sla_hours:g} h)" for x in late_shared]),
                           "Escalate with the vendor's service manager and agree a fix date; these systems serve every outlet.", o("vendors"),
                           [x["device"].device_id for x in late_shared]))
    lines = [device_state(d, x) for x in d.devices if x.kind == "uplink"]
    backup_down = [x for x in lines if x["down"] and x["device"].role == "backup"]
    if backup_down and [x for x in lines if not x["down"]]:
        out.append(Finding(WARNING, "Network", "NET-04", "internet failover not available: the backup line is down",
                           _top([_label(x) for x in backup_down]),
                           "Fix the backup line before the weekend and test the failover with one card payment; until then keep a 4G router "
                           "and the carrier's number at the bar.", o("network"), [x["device"].device_id for x in backup_down]))
    cover = vendor_cover(d, rows)
    for c in cover:
        v = c["vendor"]
        if c["days_left"] is not None and c["days_left"] < 0 and c["devices"]:
            out.append(Finding(WARNING, "Vendors", "VND-02", f"{v.vendor}: support contract ended {v.contract_end:%d %b %Y}",
                               f"{_n(len(c['devices']), 'device')} covered: {_top([x.device_id for x in c['devices']])}",
                               "Renew or replace the contract before the next incident; confirm in writing who fixes these devices meanwhile.",
                               o("vendors"), [x.device_id for x in c["devices"]]))
        elif c["days_left"] is not None and c["days_left"] <= s.contract_warn_days and c["devices"]:
            out.append(Finding(INFO, "Vendors", "VND-02", f"{v.vendor}: support contract ends {v.contract_end:%d %b %Y}",
                               f"{c['days_left']} days left · {_n(len(c['devices']), 'device')} covered",
                               "Start the renewal now: compare the incidents and the SLA met this year before signing.", o("vendors"),
                               [x.device_id for x in c["devices"]]))
    gaps = [c for c in cover if c["gaps"]]
    if gaps:
        out.append(Finding(INFO, "Vendors", "VND-03", f"{_n(len(gaps), 'vendor')} not covering every service hour",
                           _top([f"{c['vendor'].vendor} ({c['vendor'].hours}): {_n(len(c['gaps']), 'service')}, e.g. {c['gaps'][0].name} "
                                 f"{_when(c['gaps'][0])}" for c in gaps], 4),
                           "Agree an out-of-hours number or extended cover for the busy weeks, and keep spares on site for what the vendor cannot fix "
                           "at night.", o("vendors"), [c["vendor"].vendor for c in gaps]))
    behind = [device_state(d, x) for x in d.devices]
    behind = [x for x in behind if x["behind"]]
    if behind:
        out.append(Finding(INFO, "POS & payments", "POS-03", f"{_n(len(behind), 'device')} behind the target software version",
                           _top([f"{x['device'].device_id} {x['device'].version} (target {x['device'].target})" for x in behind]),
                           "Schedule the updates on quiet mornings, outside the freeze before busy services, one outlet at a time.", o("pos"),
                           [x["device"].device_id for x in behind]))
    stale_open = [x for x in open_incidents(d) if not x["late"]]
    if stale_open:
        out.append(Finding(INFO, "Vendors", "VND-04", f"{_n(len(stale_open), 'open ticket')} inside the SLA",
                           _top([f"{x['incident'].ticket} {x['incident'].device_id} {x['age']:.0f} h" for x in stale_open]),
                           "Follow up at the next check.", o("vendors")))
    inc = recent_incidents(d)
    if inc:
        lost = Counter()
        for i in inc:
            lost[i.category or "Other"] += i.minutes_lost
        out.append(Finding(INFO, "Incidents", "INC-02", f"{_n(len(inc), 'incident')} and {sum(lost.values()):g} service minutes lost in "
                                                        f"{s.incident_window_days} days",
                           ", ".join(f"{c} {m:g} min" for c, m in lost.most_common(5)),
                           "Review the top categories with each vendor at the monthly service review.", o("incidents")))
    out.sort(key=lambda f: (ORDER[f.severity], AREAS.index(f.area), f.code))
    return out


def area_status(findings: list[Finding]) -> dict[str, str]:
    st = {}
    for a in AREAS:
        sev = [f.severity for f in findings if f.area == a and f.severity != INFO]
        st[a] = CRITICAL if CRITICAL in sev else WARNING if sev else "ok"
    return st


def now_label(when: datetime) -> str:
    return f"{when:%a %d %b %Y %H:%M}"
