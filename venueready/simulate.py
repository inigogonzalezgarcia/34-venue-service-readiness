"""Fictional demo: Solenne Beach Club & Hotel, a week of services in a restaurant, a pool club, a sunset bar and a 24-room hotel, the
devices behind them, five vendors and 60 days of incidents. Every name is made up; the problems are placed on purpose."""
from __future__ import annotations

import csv
import json
import random
from datetime import datetime, timedelta
from pathlib import Path

ORG = "Solenne Beach Club & Hotel"
AS_OF = datetime(2026, 10, 26, 9, 30)
SEED = 34
POS_TARGET = "6.4.2"


def _at(text: str) -> datetime:
    return datetime.strptime(text, "%Y-%m-%d %H:%M")


def _ago(hours: float) -> str:
    return (AS_OF - timedelta(hours=hours)).strftime("%Y-%m-%d %H:%M")


# id, outlet, service, type, start, end, guests, IT on duty, opening check
SERVICES = [
    ("S01", "Restaurant", "Breakfast", "restaurant", "2026-10-26 07:30", "2026-10-26 11:00", 46, "IT technician", "2026-10-26 07:05"),
    ("S02", "Pool Club", "Pool club · lunch", "pool", "2026-10-26 12:00", "2026-10-26 18:00", 240, "IT technician", ""),
    ("S03", "Hotel", "Arrivals", "hotel", "2026-10-26 14:00", "2026-10-26 22:00", 18, "Front office · IT on call", ""),
    ("S04", "Sunset Bar", "Sunset sessions", "bar", "2026-10-26 18:00", "2026-10-27 01:00", 260, "", ""),
    ("S05", "Restaurant", "Dinner", "restaurant", "2026-10-26 20:00", "2026-10-26 23:30", 110, "IT on call", ""),
    ("S06", "Restaurant", "Breakfast", "restaurant", "2026-10-27 07:30", "2026-10-27 11:00", 40, "IT technician", ""),
    ("S07", "Pool Club", "Pool club · lunch", "pool", "2026-10-27 12:00", "2026-10-27 18:00", 160, "IT technician", ""),
    ("S08", "Restaurant", "Dinner", "restaurant", "2026-10-27 20:00", "2026-10-27 23:30", 90, "IT on call", ""),
    ("S09", "Pool Club", "Pool club · lunch", "pool", "2026-10-28 12:00", "2026-10-28 18:00", 150, "IT technician", ""),
    ("S10", "Restaurant", "Dinner", "restaurant", "2026-10-28 20:00", "2026-10-28 23:30", 80, "IT on call", ""),
    ("S11", "Sunset Bar", "Sunset sessions", "bar", "2026-10-29 18:00", "2026-10-30 01:00", 220, "IT on call", ""),
    ("S12", "Hotel", "Arrivals", "hotel", "2026-10-30 14:00", "2026-10-30 22:00", 22, "Front office · IT on call", ""),
    ("S13", "Restaurant", "Dinner", "restaurant", "2026-10-30 20:00", "2026-10-30 23:30", 130, "IT on call", ""),
    ("S14", "Restaurant", "Dinner", "restaurant", "2026-10-31 20:00", "2026-10-31 23:30", 140, "IT on call", ""),
    ("S15", "Pool Club", "Halloween night", "event", "2026-10-31 22:00", "2026-11-01 04:00", 900, "", ""),
    ("S16", "Restaurant", "Sunday brunch", "restaurant", "2026-11-01 11:00", "2026-11-01 15:00", 120, "IT technician", ""),
    ("S00", "Pool Club", "Pool club · lunch", "pool", "2026-10-25 12:00", "2026-10-25 18:00", 280, "IT technician", "2026-10-25 10:40"),
]

POS = "POS terminal 15\" (cloud POS)"
HH = "Android handheld (cloud POS)"
# id, outlet, type, model, status, last seen (hours ago), version, target, next update, vendor, role, cash, fill, queue
DEVICES = [
    ("TILL-R1", "Restaurant", "Till", POS, "online", 0.1, POS_TARGET, POS_TARGET, "2026-10-30 04:00", "", "", "", "", ""),
    ("TILL-R2", "Restaurant", "Till", POS, "online", 0.1, POS_TARGET, POS_TARGET, "2026-10-30 04:00", "", "", "", "", ""),
    ("HH-R1", "Restaurant", "Handheld", HH, "online", 0.2, POS_TARGET, POS_TARGET, "", "", "", "", "", ""),
    ("HH-R2", "Restaurant", "Handheld", HH, "online", 0.3, POS_TARGET, POS_TARGET, "", "", "", "", "", ""),
    ("KP-R1", "Restaurant", "Kitchen printer", "Thermal kitchen printer · hot line", "online", 0.1, "", "", "", "", "", "", "", ""),
    ("KDS-R1", "Restaurant", "KDS", "Kitchen display 22\" · pass", "online", 0.1, "", "", "", "", "", "", "", ""),
    ("RP-R1", "Restaurant", "Receipt printer", "Thermal receipt printer", "online", 0.1, "", "", "", "", "", "", "", ""),
    ("CT-R1", "Restaurant", "Card terminal", "Portable card terminal", "online", 0.1, "", "", "", "", "", "", "", ""),
    ("CT-R2", "Restaurant", "Card terminal", "Portable card terminal", "online", 0.2, "", "", "", "", "", "", "", ""),
    ("CASH-R1", "Restaurant", "Cash machine", "Cash recycler (notes + coins)", "online", 0.1, "", "", "", "", "", "640", "38", ""),
    ("AP-R1", "Restaurant", "Access point", "Wi-Fi 6 ceiling AP", "online", 0.1, "", "", "", "", "", "", "", ""),
    ("AP-R2", "Restaurant", "Access point", "Wi-Fi 6 ceiling AP", "online", 0.1, "", "", "", "", "", "", "", ""),
    ("TILL-P1", "Pool Club", "Till", POS, "online", 0.1, POS_TARGET, POS_TARGET, "", "", "", "", "", ""),
    ("TILL-P2", "Pool Club", "Till", POS, "online", 0.1, POS_TARGET, POS_TARGET, "", "", "", "", "", ""),
    ("TILL-P3", "Pool Club", "Till", POS, "online", 0.2, POS_TARGET, POS_TARGET, "", "", "", "", "", ""),
    ("HH-P1", "Pool Club", "Handheld", HH, "online", 0.3, POS_TARGET, POS_TARGET, "", "", "", "", "", ""),
    ("HH-P2", "Pool Club", "Handheld", HH, "online", 0.4, POS_TARGET, POS_TARGET, "", "", "", "", "", ""),
    ("HH-P3", "Pool Club", "Handheld", HH, "offline", 20.3, POS_TARGET, POS_TARGET, "", "", "", "", "", ""),
    ("HH-P4", "Pool Club", "Handheld", HH, "online", 70.5, "6.3.9", POS_TARGET, "", "", "", "", "", ""),
    ("KP-P1", "Pool Club", "Kitchen printer", "Thermal kitchen printer · beach kitchen", "error", 17.8, "", "", "", "", "", "", "", ""),
    ("RP-P1", "Pool Club", "Receipt printer", "Thermal receipt printer", "online", 0.2, "", "", "", "", "", "", "", ""),
    ("CT-P1", "Pool Club", "Card terminal", "Portable card terminal", "online", 0.2, "", "", "", "", "", "", "", ""),
    ("CT-P2", "Pool Club", "Card terminal", "Portable card terminal", "online", 0.2, "", "", "", "", "", "", "", ""),
    ("CT-P3", "Pool Club", "Card terminal", "Portable card terminal", "online", 0.3, "", "", "", "", "", "", "", ""),
    ("CASH-P1", "Pool Club", "Cash machine", "Cash recycler (notes + coins)", "online", 0.1, "", "", "", "", "", "180", "41", ""),
    ("AP-P1", "Pool Club", "Access point", "Wi-Fi 6 outdoor AP", "online", 0.1, "", "", "", "", "", "", "", ""),
    ("AP-P2", "Pool Club", "Access point", "Wi-Fi 6 outdoor AP", "online", 0.1, "", "", "", "", "", "", "", ""),
    ("AP-P3", "Pool Club", "Access point", "Wi-Fi 6 outdoor AP", "offline", 41.0, "", "", "", "", "", "", "", ""),
    ("AP-P4", "Pool Club", "Access point", "Wi-Fi 6 outdoor AP", "online", 0.1, "", "", "", "", "", "", "", ""),
    ("TILL-B1", "Sunset Bar", "Till", POS, "online", 0.1, "6.3.9", POS_TARGET, "", "", "", "", "", ""),
    ("TILL-B2", "Sunset Bar", "Till", POS, "online", 0.1, "6.3.9", POS_TARGET, "", "", "", "", "", ""),
    ("HH-B1", "Sunset Bar", "Handheld", HH, "online", 0.6, "6.3.9", POS_TARGET, "", "", "", "", "", ""),
    ("HH-B2", "Sunset Bar", "Handheld", HH, "online", 0.6, "6.3.9", POS_TARGET, "", "", "", "", "", ""),
    ("KP-B1", "Sunset Bar", "Kitchen printer", "Thermal bar printer", "online", 0.2, "", "", "", "", "", "", "", ""),
    ("CT-B1", "Sunset Bar", "Card terminal", "Countertop card terminal", "online", 0.1, "", "", "", "", "", "", "", ""),
    ("CT-B2", "Sunset Bar", "Card terminal", "Countertop card terminal", "offline", 1.4, "", "", "", "", "", "", "", ""),
    ("CASH-B1", "Sunset Bar", "Cash machine", "Cash recycler (notes + coins)", "online", 0.1, "", "", "", "", "", "520", "92", ""),
    ("AP-B1", "Sunset Bar", "Access point", "Wi-Fi 6 outdoor AP", "online", 0.1, "", "", "", "", "", "", "", ""),
    ("AP-B2", "Sunset Bar", "Access point", "Wi-Fi 6 outdoor AP", "online", 0.1, "", "", "", "", "", "", "", ""),
    ("SW-B1", "Sunset Bar", "Switch", "24-port PoE switch · bar rack", "degraded", 0.1, "", "", "", "", "", "", "", ""),
    ("TILL-H1", "Hotel", "Till", POS, "online", 0.1, POS_TARGET, POS_TARGET, "", "", "", "", "", ""),
    ("CT-H1", "Hotel", "Card terminal", "Countertop card terminal", "online", 0.1, "", "", "", "", "", "", "", ""),
    ("ENC-H1", "Hotel", "Key encoder", "RFID key card encoder · reception", "online", 0.2, "", "", "", "", "", "", "", ""),
    ("ENC-H2", "Hotel", "Key encoder", "RFID key card encoder · back office", "online", 0.4, "", "", "", "", "", "", "", ""),
    ("FW-01", "Venue", "Firewall", "Next-generation firewall (HA pair)", "online", 0.1, "7.4.4", "7.4.5", "2026-10-31 03:00", "", "", "", "", ""),
    ("SW-CORE", "Venue", "Switch", "Core switch stack", "online", 0.1, "", "", "", "", "", "", "", ""),
    ("WAN-1", "Venue", "Internet line", "Fibre 1 Gbps", "online", 0.1, "", "", "", "", "primary", "", "", ""),
    ("WAN-2", "Venue", "Internet line", "4G/5G router (backup)", "offline", 119.5, "", "", "", "", "backup", "", "", ""),
    ("PMS-IF", "Venue", "PMS interface", "POS-PMS interface service", "online", 0.1, "3.2.0", "3.2.0", "", "", "", "", "", "37"),
    ("IPTV-HE", "Venue", "IPTV headend", "IPTV headend + channel encoder", "online", 0.1, "", "", "", "", "", "", "", ""),
]
STB_DOWN = {"STB-107": 30.0, "STB-114": 77.0, "STB-121": 13.5}

# vendor, covers, support hours, SLA hours, contract end, support line
VENDORS = [
    ("Mesa POS Systems", "till;handheld;kitchen printer;receipt printer", "Mon-Fri 09:00-19:00, Sat 10:00-14:00", 8, "2027-03-31", "on file"),
    ("Bancal Payments", "card terminal", "24x7", 24, "2027-12-31", "on file"),
    ("Cambio Cash Solutions", "cash machine", "Mon-Sat 09:00-21:00", 24, "2026-11-30", "on file"),
    ("Litoral Networks", "access point;switch;firewall;internet line", "24x7", 4, "2026-09-30", "on file"),
    ("Roomline Hotel Systems", "pms interface;iptv headend;iptv box;key encoder", "Mon-Sun 08:00-22:00", 12, "2027-06-30", "on file"),
]

# placed incidents: opened (hours ago), closed (hours ago, None = open), outlet, device, category, minutes lost, summary
PLACED = [
    (17.75, None, "Pool Club", "KP-P1", "Kitchen printing", 25, "Beach kitchen printer in error (paper cutter); orders taken to the kitchen by hand"),
    (20.2, None, "Pool Club", "HH-P3", "Handheld", 0, "Handheld does not power on after charging; swapped with a till for the afternoon"),
    (119.5, None, "Venue", "WAN-2", "Internet", 0, "Backup 4G router not reachable; failover test failed"),
    (66.0, None, "Hotel", "STB-114", "IPTV", 0, "Guest reports no TV channels in room 114"),
    (1.3, None, "Sunset Bar", "CT-B2", "Card payments", 10, "Card terminal 2 offline at the end of the night; payments moved to terminal 1"),
    (230.0, 228.5, "Sunset Bar", "CT-B2", "Card payments", 20, "Card terminal 2 lost its connection to the till"),
    (520.0, 517.0, "Sunset Bar", "CT-B2", "Card payments", 15, "Card terminal 2 rejecting contactless; restarted"),
    (900.0, 896.0, "Sunset Bar", "CT-B2", "Card payments", 30, "Card terminal 2 frozen during the busiest hour"),
    (380.0, 378.4, "Venue", "WAN-1", "Internet", 95, "Fibre cut by roadworks; failover to 4G worked, slow card payments for 95 minutes"),
    (300.0, 299.0, "Venue", "PMS-IF", "Room charges", 40, "Room charges not posting to the PMS; interface restarted, 23 charges posted by hand"),
    (160.0, 158.0, "Pool Club", "AP-P3", "Wi-Fi", 35, "Handhelds dropping by the sun loungers; access point rebooted"),
    (40.0, 30.0, "Pool Club", "AP-P3", "Wi-Fi", 20, "Access point by the sun loungers offline; PoE port reset"),
    (610.0, 608.0, "Pool Club", "CASH-P1", "Cash machine", 15, "Coin hopper jammed"),
    (200.0, 199.0, "Sunset Bar", "CASH-B1", "Cash machine", 10, "Note stacker full during service"),
]
FILLER = [("Restaurant", "Kitchen printing", "Kitchen printer out of paper during service"),
          ("Restaurant", "Handheld", "Handheld not syncing the menu after a price change"),
          ("Hotel", "Key cards", "Key card not opening the door; re-encoded"),
          ("Pool Club", "Card payments", "Card terminal low battery mid-service"),
          ("Sunset Bar", "Till", "Till slow to print the bill; restarted"),
          ("Hotel", "IPTV", "TV in a guest room stuck on the welcome screen")]


def _rows() -> dict[str, list[list]]:
    rnd = random.Random(SEED)
    services = [list(s) for s in SERVICES]
    devices = []
    for row in DEVICES:
        dv, outlet, kind, model, status, seen, ver, target, upd, ven, role, cash, fill, queue = row
        devices.append([dv, outlet, kind, model, status, _ago(seen), ver, target, upd, ven, role, cash, fill, queue])
    for n in range(101, 125):
        dv = f"STB-{n}"
        down = STB_DOWN.get(dv)
        devices.append([dv, "Hotel", "IPTV box", f"Set-top box · room {n}", "offline" if down else "online", _ago(down or 0.2 + (n % 5) / 10),
                        "", "", "", "", "", "", "", ""])
    vendors = [list(v) for v in VENDORS]
    inc = []
    for opened, closed, outlet, dev, cat, mins, text in PLACED:
        inc.append([AS_OF - timedelta(hours=opened), "" if closed is None else _ago(closed), outlet, dev, cat, mins, text])
    for k in range(12):
        outlet, cat, text = FILLER[k % len(FILLER)]
        t = AS_OF - timedelta(days=rnd.randint(2, 58), hours=rnd.randint(0, 9))
        inc.append([t, (t + timedelta(minutes=rnd.choice([20, 35, 50, 90]))).strftime("%Y-%m-%d %H:%M"), outlet, "", cat,
                    rnd.choice([0, 5, 5, 10, 15]), text])
    inc.sort(key=lambda x: x[0])
    inc = [[f"INC{7300 + i}", t.strftime("%Y-%m-%d %H:%M")] + rest for i, (t, *rest) in enumerate(inc)]
    return dict(services=services, devices=devices, vendors=vendors, incidents=inc)


HEADERS = {
    "services": ["Service ID", "Outlet", "Service", "Type", "Start", "End", "Guests", "IT on duty", "Opening check"],
    "devices": ["Device", "Outlet", "Type", "Model", "Status", "Last seen", "Version", "Target version", "Next update", "Vendor", "Role",
                "Cash level", "Fill %", "Queue"],
    "vendors": ["Vendor", "Covers", "Support hours", "SLA hours", "Contract end", "Support line"],
    "incidents": ["Ticket", "Opened", "Closed", "Outlet", "Device", "Category", "Minutes lost", "Summary"],
}

SETTINGS = {
    "organisation": ORG,
    "as_of": AS_OF.strftime("%Y-%m-%d %H:%M"),
    "horizon_days": 7,
    "check_kinds": ["restaurant", "bar", "pool", "event", "hotel"],
    "check_window_hours": 6,
    "check_lead_hours": 3,
    "duty_min_guests": 150,
    "heartbeat_hours": 24,
    "freeze_hours": 24,
    "guests_per_till": 40,
    "food_kinds": ["restaurant", "pool", "event"],
    "room_charge_kinds": ["restaurant", "bar", "pool"],
    "cash_float_min": 300,
    "cash_full_pct": 85,
    "pms_queue_max": 10,
    "stb_offline_max": 2,
    "contract_warn_days": 60,
    "repeat_incidents": 3,
    "incident_window_days": 60,
    "owners": {"services": "Venue IT manager", "pos": "POS vendor", "network": "Network provider", "guest": "Front office systems",
               "vendors": "Venue IT manager", "incidents": "Venue IT manager"},
}


def write(folder: Path) -> Path:
    folder = Path(folder)
    folder.mkdir(parents=True, exist_ok=True)
    for name, rows in _rows().items():
        with open(folder / f"{name}.csv", "w", newline="", encoding="utf-8") as fh:
            w = csv.writer(fh)
            w.writerow(HEADERS[name])
            w.writerows(rows)
    (folder / "settings.json").write_text(json.dumps(SETTINGS, indent=2) + "\n", encoding="utf-8")
    return folder
