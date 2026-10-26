"""Loading: the services of the coming week, the device register with its health, the vendors and their support hours, the incident log
and settings.json, with forgiving column names, into plain dataclasses."""
from __future__ import annotations

import csv
import json
import re
import unicodedata
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from pathlib import Path

SERVICE_ALIASES = {
    "service_id": ["service id", "id", "ref", "servicio id"],
    "outlet": ["outlet", "area", "venue", "local", "zona", "punto de venta"],
    "name": ["service", "name", "title", "servicio", "nombre"],
    "kind": ["type", "kind", "category", "tipo"],
    "start": ["start", "opens", "start time", "inicio", "apertura"],
    "end": ["end", "closes", "end time", "fin", "cierre"],
    "guests": ["guests", "covers", "expected guests", "pax", "aforo", "cubiertos", "check ins", "arrivals"],
    "on_duty": ["on duty", "it on duty", "it", "support", "on call", "tecnico", "guardia"],
    "check_done": ["opening check", "opening check done", "check done", "check", "prueba de apertura", "chequeo"],
    "notes": ["notes", "comments", "notas"],
}
DEVICE_ALIASES = {
    "device_id": ["device id", "device", "name", "asset", "hostname", "dispositivo"],
    "outlet": ["outlet", "area", "location", "zona", "ubicacion"],
    "kind": ["type", "kind", "device type", "category", "tipo"],
    "model": ["model", "product", "hardware", "modelo"],
    "status": ["status", "state", "health", "estado"],
    "last_seen": ["last seen", "last contact", "last sync", "last heartbeat", "ultima conexion", "ultimo contacto"],
    "version": ["version", "software version", "firmware", "app version"],
    "target": ["target version", "target", "latest version", "available version"],
    "next_update": ["next update", "update scheduled", "scheduled update", "maintenance", "proxima actualizacion"],
    "vendor": ["vendor", "supplier", "provider", "proveedor"],
    "role": ["role", "link", "rol"],
    "cash": ["cash level", "cash", "float", "efectivo", "fondo"],
    "fill": ["fill", "fill pct", "stacker fill", "cassette fill", "llenado"],
    "queue": ["queue", "pending postings", "pending", "cola", "pendientes"],
}
VENDOR_ALIASES = {
    "vendor": ["vendor", "supplier", "provider", "name", "proveedor"],
    "covers": ["covers", "scope", "device types", "types", "cubre", "alcance"],
    "hours": ["support hours", "hours", "cover", "horario", "horario soporte"],
    "sla_hours": ["sla hours", "sla", "fix time", "resolution hours", "sla horas"],
    "contract_end": ["contract end", "contract", "renewal", "fin contrato", "vencimiento"],
    "contact": ["support line", "contact", "phone", "contacto"],
}
INCIDENT_ALIASES = {
    "ticket": ["ticket", "id", "number", "ref", "incidencia"],
    "opened": ["opened", "date", "created", "apertura", "fecha"],
    "closed": ["closed", "resolved", "cierre", "resuelto"],
    "outlet": ["outlet", "area", "zona"],
    "device_id": ["device", "device id", "asset", "dispositivo"],
    "vendor": ["vendor", "supplier", "assigned to", "proveedor"],
    "category": ["category", "type", "categoria"],
    "minutes_lost": ["minutes lost", "service minutes lost", "minutes", "minutos perdidos"],
    "summary": ["summary", "description", "short description", "resumen"],
}
YES = {"yes", "y", "true", "1", "si", "x"}
KINDS = {"restaurant": "restaurant", "restaurante": "restaurant", "breakfast": "restaurant", "desayuno": "restaurant", "dinner": "restaurant",
         "lunch": "restaurant", "brunch": "restaurant", "bar": "bar", "cocktail": "bar", "pool": "pool", "pool club": "pool", "beach": "pool",
         "piscina": "pool", "event": "event", "evento": "event", "party": "event", "fiesta": "event", "hotel": "hotel", "arrivals": "hotel",
         "check in": "hotel", "llegadas": "hotel", "rooms": "hotel"}
DEVICE_KINDS = {
    "till": ["till", "pos", "pos terminal", "tpv", "caja", "register"],
    "handheld": ["handheld", "pda", "comandero", "mobile pos", "order taker"],
    "kitchen": ["kitchen printer", "kds", "kitchen display", "impresora cocina", "bar printer", "comandas"],
    "printer": ["receipt printer", "ticket printer", "printer", "impresora"],
    "card": ["card terminal", "pin pad", "pinpad", "payment terminal", "datafono", "card reader"],
    "cash": ["cash machine", "cashdro", "cash recycler", "cash drawer", "cajon", "cajon inteligente"],
    "ap": ["access point", "ap", "wifi", "wi fi", "punto de acceso"],
    "switch": ["switch", "poe switch"],
    "firewall": ["firewall", "router", "gateway", "cortafuegos"],
    "uplink": ["uplink", "internet", "wan", "line", "fibre", "fiber", "4g", "5g", "linea"],
    "pms": ["pms interface", "pms", "interface", "interfaz pms"],
    "headend": ["iptv headend", "headend", "cabecera"],
    "stb": ["iptv box", "set top box", "stb", "tv", "iptv"],
    "encoder": ["key encoder", "encoder", "codificador", "key card encoder"],
}
KIND_LABEL = {"till": "till", "handheld": "handheld", "kitchen": "kitchen printer / KDS", "printer": "receipt printer", "card": "card terminal",
              "cash": "cash machine", "ap": "access point", "switch": "switch", "firewall": "firewall", "uplink": "internet line", "pms": "PMS interface",
              "headend": "IPTV headend", "stb": "IPTV box", "encoder": "key encoder", "other": "device"}
STATUS = {"online": "online", "ok": "online", "up": "online", "healthy": "online", "connected": "online", "degraded": "degraded",
          "warning": "degraded", "slow": "degraded", "paper low": "degraded", "offline": "offline", "down": "offline", "disconnected": "offline",
          "unreachable": "offline", "unknown": "offline", "error": "error", "fault": "error", "jammed": "error", "failed": "error"}
DATE_FORMATS = ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d", "%d/%m/%Y %H:%M", "%d/%m/%Y", "%d %b %Y")
VENUE_WIDE = {"venue", "all", "shared", "site", "general", "todo", "comun"}


def _norm(s: str) -> str:
    s = unicodedata.normalize("NFKD", str(s).lower())
    return re.sub(r"[^a-z0-9]+", " ", "".join(ch for ch in s if not unicodedata.combining(ch))).strip()


def parse_dt(v) -> datetime | None:
    s = str(v or "").strip().replace("Z", "")
    if not s or _norm(s) in {"never", "n a", "na", "none", "nunca"}:
        return None
    for f in DATE_FORMATS:
        try:
            return datetime.strptime(s[:19] if "T" in s else s, f)
        except ValueError:
            continue
    return None


def parse_date(v) -> date | None:
    d = parse_dt(v)
    return d.date() if d else None


def num(v, default: float | None = 0.0) -> float | None:
    s = str(v or "").strip().replace(" ", "").lower().replace("%", "").replace("eur", "").replace("€", "").replace("min", "")
    if not s:
        return default
    if "," in s and "." in s:
        s = s.replace(".", "").replace(",", ".") if s.rfind(",") > s.rfind(".") else s.replace(",", "")
    elif "," in s:
        s = s.replace(",", ".")
    try:
        return float(s)
    except ValueError:
        return default


def _rows(path: Path, aliases: dict[str, list[str]]) -> list[dict]:
    with open(path, newline="", encoding="utf-8-sig") as fh:
        sample = fh.read(4096)
        fh.seek(0)
        try:
            dialect = csv.Sniffer().sniff(sample, delimiters=",;\t")
        except csv.Error:
            dialect = csv.excel
        reader = csv.DictReader(fh, dialect=dialect)
        heads = {_norm(h): h for h in (reader.fieldnames or [])}
        cols = {}
        for key, names in aliases.items():
            for n in [key.replace("_", " ")] + names:
                if _norm(n) in heads and heads[_norm(n)] not in cols.values():
                    cols[key] = heads[_norm(n)]
                    break
        return [{k: (r.get(c) or "").strip() for k, c in cols.items()} for r in reader]


def yes(v) -> bool:
    return _norm(v) in YES


def kind_of(v: str, name: str = "") -> str:
    for text in (v, name):
        n = _norm(text)
        if not n:
            continue
        if n in KINDS:
            return KINDS[n]
        for k, out in KINDS.items():
            if n.startswith(k + " ") or (text is name and re.search(rf"\b{k}\b", n)):
                return out
    return "other"


def device_kind(v: str) -> str:
    n = _norm(v)
    for k, names in DEVICE_KINDS.items():
        if n == k or n in names:
            return k
    for k, names in DEVICE_KINDS.items():
        if any(re.search(rf"\b{x}\b", n) for x in names if len(x) > 3):
            return k
    return "other"


def status_of(v: str) -> str:
    n = _norm(v)
    return STATUS.get(n) or STATUS.get((n.split() or ["online"])[0], "offline") if n else "online"


def version(v: str) -> tuple:
    return tuple(int(x) for x in re.findall(r"\d+", str(v or ""))[:4])


def venue_wide(outlet: str) -> bool:
    return not outlet or _norm(outlet) in VENUE_WIDE


@dataclass
class Service:
    service_id: str
    outlet: str
    name: str
    start: datetime
    end: datetime
    kind: str = "other"               # restaurant | bar | pool | event | hotel | other
    guests: int = 0
    on_duty: str = ""
    check_done: datetime | None = None
    notes: str = ""


@dataclass
class Device:
    device_id: str
    outlet: str = ""                  # empty or "Venue": shared by every outlet (internet, firewall, PMS interface)
    kind: str = "other"
    model: str = ""
    status: str = "online"            # online | degraded | offline | error
    last_seen: datetime | None = None
    version: str = ""
    target: str = ""
    next_update: datetime | None = None
    vendor: str = ""
    role: str = ""                    # internet lines: primary | backup
    cash: float | None = None         # cash machines: cash available for change
    fill: float | None = None         # cash machines: stacker / cassette fill %
    queue: float | None = None        # PMS interface: postings waiting


@dataclass
class Vendor:
    vendor: str
    covers: list[str] = field(default_factory=list)
    hours: str = ""
    sla_hours: float | None = None
    contract_end: date | None = None
    contact: str = ""


@dataclass
class Incident:
    opened: datetime
    closed: datetime | None = None
    outlet: str = ""
    device_id: str = ""
    vendor: str = ""
    category: str = ""
    minutes_lost: float = 0.0
    summary: str = ""
    ticket: str = ""


@dataclass
class Settings:
    organisation: str = "Venue"
    as_of: datetime | None = None
    horizon_days: int = 7
    check_kinds: list = field(default_factory=lambda: ["restaurant", "bar", "pool", "event", "hotel"])
    check_window_hours: int = 6
    check_lead_hours: int = 3
    duty_min_guests: int = 150
    heartbeat_hours: int = 24
    freeze_hours: int = 24
    guests_per_till: int = 60
    food_kinds: list = field(default_factory=lambda: ["restaurant", "pool", "event"])
    room_charge_kinds: list = field(default_factory=lambda: ["restaurant", "bar", "pool"])
    cash_float_min: float = 300.0
    cash_full_pct: float = 85.0
    pms_queue_max: int = 10
    stb_offline_max: int = 2
    contract_warn_days: int = 60
    repeat_incidents: int = 3
    incident_window_days: int = 60
    owners: dict = field(default_factory=lambda: {"services": "Venue IT manager", "pos": "POS vendor", "network": "Network provider",
                                                  "guest": "Front office systems", "vendors": "Venue IT manager", "incidents": "Venue IT manager"})

    def owner(self, key: str) -> str:
        return self.owners.get(key, "")


def settings_from_dict(raw: dict) -> Settings:
    s = Settings()
    for k, v in raw.items():
        if not hasattr(s, k):
            continue
        cur = getattr(s, k)
        if k == "as_of":
            v = parse_dt(v)
        elif k == "owners":
            v = {**cur, **v}
        elif k in ("check_kinds", "food_kinds", "room_charge_kinds"):
            v = [kind_of(x) for x in v]
        elif isinstance(cur, bool):
            v = bool(v)
        elif isinstance(cur, int):
            v = int(v)
        elif isinstance(cur, float):
            v = float(v)
        setattr(s, k, v)
    return s


def _int(v) -> int:
    return int(num(v, 0) or 0)


def load_services(path: Path) -> list[Service]:
    out = []
    for r in _rows(path, SERVICE_ALIASES):
        st, en = parse_dt(r.get("start")), parse_dt(r.get("end"))
        if not st:
            continue
        if en and en <= st:
            en += timedelta(days=1)       # closes after midnight
        out.append(Service(r.get("service_id") or f"S{len(out) + 1:02d}", r.get("outlet", ""), r.get("name", ""), st, en or st + timedelta(hours=4),
                           kind_of(r.get("kind", ""), r.get("name", "")), _int(r.get("guests")), r.get("on_duty", ""), parse_dt(r.get("check_done")),
                           r.get("notes", "")))
    return out


def load_devices(path: Path) -> list[Device]:
    out = []
    for r in _rows(path, DEVICE_ALIASES):
        if not r.get("device_id"):
            continue
        out.append(Device(r["device_id"], r.get("outlet", ""), device_kind(r.get("kind", "")), r.get("model", ""), status_of(r.get("status", "")),
                          parse_dt(r.get("last_seen")), r.get("version", ""), r.get("target", ""), parse_dt(r.get("next_update")),
                          r.get("vendor", ""), _norm(r.get("role", "")), num(r.get("cash"), None), num(r.get("fill"), None), num(r.get("queue"), None)))
    return out


def load_vendors(path: Path) -> list[Vendor]:
    out = []
    for r in _rows(path, VENDOR_ALIASES):
        if not r.get("vendor"):
            continue
        covers = [device_kind(x) for x in re.split(r"[;|,]", r.get("covers", "")) if x.strip()]
        out.append(Vendor(r["vendor"], covers, r.get("hours", ""), num(r.get("sla_hours"), None), parse_date(r.get("contract_end")), r.get("contact", "")))
    return out


def load_incidents(path: Path) -> list[Incident]:
    out = []
    for r in _rows(path, INCIDENT_ALIASES):
        t = parse_dt(r.get("opened"))
        if not t:
            continue
        out.append(Incident(t, parse_dt(r.get("closed")), r.get("outlet", ""), r.get("device_id", ""), r.get("vendor", ""), r.get("category", ""),
                            num(r.get("minutes_lost")) or 0.0, r.get("summary", ""), r.get("ticket", "")))
    return out


DAYS = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"]


def support_windows(hours: str) -> list[tuple[set, int, int]] | None:
    """'24x7' -> None (always covered). 'Mon-Fri 09:00-19:00, Sat 10:00-14:00' -> [(days, start minute, end minute)].
    An end before the start runs past midnight."""
    n = _norm(hours)
    if not n or n in {"24x7", "24 7", "24h", "24 h", "always"} or n.startswith("24x7") or n.startswith("24 7"):
        return None
    out = []
    for part in re.split(r"[,;]", hours):
        m = re.search(r"([A-Za-z]{3})(?:\s*-\s*([A-Za-z]{3}))?\s+(\d{1,2}):(\d{2})\s*-\s*(\d{1,2}):(\d{2})", part)
        if not m:
            continue
        a, b = m.group(1).lower()[:3], (m.group(2) or m.group(1)).lower()[:3]
        if a not in DAYS or b not in DAYS:
            continue
        i, j = DAYS.index(a), DAYS.index(b)
        days = {DAYS[k % 7] for k in range(i, (j if j >= i else j + 7) + 1)}
        out.append((days, int(m.group(3)) * 60 + int(m.group(4)), int(m.group(5)) * 60 + int(m.group(6))))
    return out


def covered(hours: str, when: datetime) -> bool:
    w = support_windows(hours)
    if w is None:
        return True
    minute = when.hour * 60 + when.minute
    today, yesterday = DAYS[when.weekday()], DAYS[(when.weekday() - 1) % 7]
    for days, a, b in w:
        if b > a and today in days and a <= minute < b:
            return True
        if b <= a and ((today in days and minute >= a) or (yesterday in days and minute < b)):
            return True
    return False


@dataclass
class Data:
    settings: Settings
    as_of: datetime
    services: list[Service]
    devices: list[Device] = field(default_factory=list)
    vendors: list[Vendor] = field(default_factory=list)
    incidents: list[Incident] = field(default_factory=list)

    @property
    def today(self) -> date:
        return self.as_of.date()

    def device(self, device_id: str) -> Device | None:
        key = _norm(device_id)
        return next((x for x in self.devices if _norm(x.device_id) == key), None)

    def vendor_of(self, dev: Device) -> Vendor | None:
        if dev.vendor:
            v = next((x for x in self.vendors if _norm(x.vendor) == _norm(dev.vendor)), None)
            if v:
                return v
        return next((x for x in self.vendors if dev.kind in x.covers), None)

    def outlet_devices(self, outlet: str, shared: bool = True) -> list[Device]:
        key = _norm(outlet)
        return [x for x in self.devices if _norm(x.outlet) == key or (shared and venue_wide(x.outlet))]

    def upcoming(self) -> list[Service]:
        end = self.as_of + timedelta(days=self.settings.horizon_days)
        return sorted([s for s in self.services if s.end > self.as_of and s.start < end], key=lambda s: (s.start, s.service_id))


def load(folder: Path, as_of: datetime | date | None = None) -> Data:
    folder = Path(folder)
    if not (folder / "services.csv").exists():
        raise FileNotFoundError(f"{folder / 'services.csv'} not found: the list of services is required")
    sp = folder / "settings.json"
    s = settings_from_dict(json.loads(sp.read_text(encoding="utf-8"))) if sp.exists() else Settings()
    services = load_services(folder / "services.csv")
    if not services:
        raise ValueError("services.csv has no rows with a start time")
    opt = lambda name, fn: fn(folder / name) if (folder / name).exists() else []  # noqa: E731
    dev, ven, inc = opt("devices.csv", load_devices), opt("vendors.csv", load_vendors), opt("incidents.csv", load_incidents)
    if isinstance(as_of, date) and not isinstance(as_of, datetime):
        as_of = datetime.combine(as_of, datetime.min.time()) + timedelta(hours=9)
    when = as_of or s.as_of or datetime.now().replace(second=0, microsecond=0)
    return Data(s, when, services, dev, ven, inc)
