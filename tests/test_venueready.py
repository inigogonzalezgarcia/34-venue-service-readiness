import csv
import hashlib
import tempfile
import unittest
from datetime import date, datetime, timedelta
from pathlib import Path

from venueready import cli
from venueready.checks import CRITICAL, INFO, ORDER, WARNING, device_state, open_incidents, run_all, service_rows, vendor_cover
from venueready.model import (Data, Device, Incident, Service, Vendor, covered, device_kind, kind_of, load, load_devices, load_services,
                              load_vendors, settings_from_dict, status_of, version)

AS_OF = datetime(2026, 10, 26, 9, 30)


def write(path: Path, header: list[str], rows: list[list], delimiter: str = ",") -> Path:
    with open(path, "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh, delimiter=delimiter)
        w.writerow(header)
        w.writerows(rows)
    return path


def at(days: float, hour: int = 20) -> datetime:
    return datetime.combine(AS_OF.date() + timedelta(days=days), datetime.min.time()) + timedelta(hours=hour)


def service(sid="S1", days=2, outlet="Restaurant", kind="restaurant", **kw) -> Service:
    hour = kw.pop("hour", 20)
    base = dict(guests=80, on_duty="IT on call", check_done=None)
    base.update(kw)
    st = at(days, hour)
    return Service(sid, outlet, kw.pop("name", f"Service {sid}"), st, st + timedelta(hours=3), kind, **base)


def dev(did, kind, outlet="Restaurant", **kw) -> Device:
    base = dict(model="", status="online", last_seen=AS_OF - timedelta(minutes=5))
    base.update(kw)
    return Device(did, outlet, kind, **base)


def outlet_kit(outlet="Restaurant") -> list[Device]:
    p = outlet[0]
    return [dev(f"TILL-{p}1", "till", outlet), dev(f"HH-{p}1", "handheld", outlet), dev(f"KP-{p}1", "kitchen", outlet),
            dev(f"CT-{p}1", "card", outlet), dev(f"AP-{p}1", "ap", outlet)]


def data(services=None, devices=None, vendors=None, incidents=None, **raw) -> Data:
    s = settings_from_dict({"guests_per_till": 60, **raw})
    return Data(s, AS_OF, services or [service()], devices if devices is not None else outlet_kit(), vendors or [], incidents or [])


def issues(d: Data, sid: str = "S1") -> tuple[dict, dict]:
    r = next(x for x in service_rows(d) if x["service"].service_id == sid)
    out = {}
    for i in r["issues"]:
        out.setdefault(i.code, i)
    return out, r


class TestLoading(unittest.TestCase):
    def test_services_with_spanish_names_and_semicolons(self):
        with tempfile.TemporaryDirectory() as t:
            p = write(Path(t) / "s.csv", ["ID", "Zona", "Servicio", "Tipo", "Inicio", "Fin", "Cubiertos", "Guardia", "Prueba de apertura"],
                      [["1", "Terraza", "Cena", "", "26/10/2026 20:00", "26/10/2026 23:30", "110", "Ana", "26/10/2026 18:10"],
                       ["2", "Bar", "Sunset sessions", "bar", "2026-10-26 18:00", "2026-10-26 01:00", "260", "", ""],
                       ["3", "Pool", "Fiesta de Halloween", "", "2026-10-31 22:00", "", "900", "", ""]], delimiter=";")
            sv = load_services(p)
        self.assertEqual([(s.kind, s.guests, s.on_duty) for s in sv], [("other", 110, "Ana"), ("bar", 260, ""), ("event", 900, "")])
        self.assertEqual(sv[0].check_done, datetime(2026, 10, 26, 18, 10))
        self.assertEqual(sv[1].end, datetime(2026, 10, 27, 1, 0))             # closes after midnight
        self.assertEqual(sv[2].end, datetime(2026, 11, 1, 2, 0))
        self.assertEqual((kind_of("", "Sunday brunch"), kind_of("Piscina")), ("restaurant", "pool"))

    def test_devices_and_vendors(self):
        with tempfile.TemporaryDirectory() as t:
            v = write(Path(t) / "d.csv", ["Hostname", "Zona", "Tipo", "Estado", "Ultimo contacto", "Efectivo", "Llenado", "Cola"],
                      [["CD-1", "Bar", "CashDro", "OK", "2026-10-26T09:20:00", "1.250,50 €", "92 %", ""],
                       ["DF-1", "Bar", "Datáfono", "Desconectado", "", "", "", ""],
                       ["IF-1", "Venue", "Interfaz PMS", "", "", "", "", "37"]])
            ds = load_devices(v)
            w = write(Path(t) / "v.csv", ["Proveedor", "Cubre", "Horario soporte", "SLA horas", "Fin contrato"],
                      [["Mesa", "TPV; comandero; impresora cocina", "Mon-Fri 09:00-19:00", "8", "2027-03-31"]])
            vs = load_vendors(w)
        self.assertEqual([(x.kind, x.status, x.cash, x.fill, x.queue) for x in ds],
                         [("cash", "online", 1250.5, 92.0, None), ("card", "offline", None, None, None), ("pms", "online", None, None, 37.0)])
        self.assertEqual((vs[0].covers, vs[0].sla_hours, vs[0].contract_end), (["till", "handheld", "kitchen"], 8.0, date(2027, 3, 31)))
        self.assertEqual((device_kind("Internet line"), device_kind("4G router"), status_of("Paper low"), status_of("jammed")),
                         ("uplink", "firewall", "degraded", "error"))
        self.assertLess(version("6.3.9"), version("6.4.2"))

    def test_support_hours(self):
        self.assertTrue(covered("24x7", datetime(2026, 10, 31, 3, 0)))
        h = "Mon-Fri 09:00-19:00, Sat 10:00-14:00"
        self.assertEqual([covered(h, datetime(2026, 10, d, hh, 0)) for d, hh in [(26, 9), (26, 19), (31, 12), (31, 20), (25, 12)]],
                         [True, False, True, False, False])
        night = "Fri-Sat 20:00-04:00"                                         # runs past midnight
        self.assertEqual([covered(night, t) for t in (datetime(2026, 10, 30, 23), datetime(2026, 10, 31, 3), datetime(2026, 11, 1, 3),
                                                      datetime(2026, 10, 29, 23))], [True, True, True, False])

    def test_settings_and_required_file(self):
        s = settings_from_dict({"as_of": "2026-10-26 09:30", "owners": {"pos": "POS team"}, "cash_float_min": "250", "food_kinds": ["Piscina"]})
        self.assertEqual((s.owner("pos"), s.owner("network"), s.cash_float_min, s.food_kinds), ("POS team", "Network provider", 250.0, ["pool"]))
        with tempfile.TemporaryDirectory() as t, self.assertRaises(FileNotFoundError):
            load(Path(t))


class TestServices(unittest.TestCase):
    def test_ready_service_and_horizon(self):
        d = data(services=[service(), service("S2", days=9), service("S0", days=-2)])
        iss, r = issues(d)
        self.assertEqual((iss, r["verdict"], r["check"]), ({}, "ready", "not due"))
        self.assertEqual([x["service"].service_id for x in service_rows(d)], ["S1"])

    def test_opening_check_rules(self):
        cases = {"S1": service("S1", days=0, hour=12),                                       # opens in 2.5 h: critical
                 "S2": service("S2", days=0, hour=20),                                       # tonight: due later
                 "S3": service("S3", days=0, hour=11, check_done=at(0, 10)),                 # done
                 "S4": service("S4", days=0, hour=8),                                        # already open without a check
                 "S5": service("S5", days=0, hour=12, kind="other")}                         # not required
        d = data(services=list(cases.values()))
        got = {sid: (issues(d, sid)[0]["SVC-01"].severity if "SVC-01" in issues(d, sid)[0] else issues(d, sid)[1]["check"]) for sid in cases}
        self.assertEqual(got, {"S1": CRITICAL, "S2": "due Mon 14:00–20:00", "S3": "done 10:00", "S4": WARNING, "S5": "not required"})

    def test_it_cover_and_freeze(self):
        big = service(guests=400, on_duty="")
        kit = outlet_kit() + [dev("FW-1", "firewall", "Venue", next_update=big.start - timedelta(hours=10)),
                              dev("SW-1", "switch", "Venue", next_update=big.start - timedelta(hours=30))]
        iss, r = issues(data(services=[big], devices=kit))
        self.assertEqual(iss["SVC-02"].severity, WARNING)
        self.assertEqual([i.text.split(" update")[0] for i in r["issues"] if i.code == "SVC-03"], ["firewall FW-1"])
        self.assertIn("SVC-02", issues(data(services=[service(kind="event", guests=40, on_duty="")]))[0])


class TestPosAndPayments(unittest.TestCase):
    def test_tills_kitchen_and_cards(self):
        kit = outlet_kit() + [dev("HH-R2", "handheld", status="offline"), dev("HH-R3", "handheld", last_seen=AS_OF - timedelta(days=3)),
                              dev("CT-R2", "card", status="offline")]
        iss, r = issues(data(services=[service(guests=150)], devices=kit))
        self.assertEqual((iss["POS-01"].severity, iss["PAY-01"].severity), (WARNING, WARNING))
        self.assertIn("2 tills and handhelds working for 150 guests (3 needed", iss["POS-01"].text)
        self.assertNotIn("POS-02", iss)
        broken = [x for x in outlet_kit() if x.kind not in ("till", "handheld")] + [dev("TILL-X", "till", status="error"),
                                                                                   dev("KP-R1", "kitchen", status="error")]
        broken = [x for x in broken if not (x.device_id == "KP-R1" and x.status == "online")]
        iss, r = issues(data(devices=broken))
        self.assertEqual((iss["POS-01"].severity, iss["POS-02"].severity, r["verdict"]), (CRITICAL, CRITICAL, "at risk"))
        bar = issues(data(services=[service(kind="bar")], devices=broken))[0]
        self.assertNotIn("POS-02", bar)                                        # no food in a bar service

    def test_cash_machine_today_only(self):
        kit = outlet_kit() + [dev("CASH-1", "cash", cash=150.0, fill=90.0)]
        today = issues(data(services=[service(days=0)], devices=kit))[1]
        self.assertEqual([i.text for i in today["issues"] if i.code == "PAY-02"],
                         ["cash machine CASH-1: cash for change 150 (minimum 300)", "cash machine CASH-1: stacker 90% full"])
        self.assertNotIn("PAY-02", issues(data(devices=kit))[0])
        kit[-1].status = "error"
        self.assertEqual(issues(data(devices=kit))[0]["PAY-02"].severity, CRITICAL)


class TestNetworkAndGuest(unittest.TestCase):
    def test_internet_lines_wifi_and_switches(self):
        lines = [dev("WAN-1", "uplink", "Venue", role="primary"), dev("WAN-2", "uplink", "Venue", role="backup", status="offline")]
        d = data(devices=outlet_kit() + lines + [dev("AP-R2", "ap", status="offline"), dev("SW-1", "switch", "Venue", status="degraded")])
        iss, _ = issues(d)
        self.assertNotIn("NET-01", iss)
        self.assertEqual((iss["NET-02"].severity, iss["NET-03"].severity), (WARNING, WARNING))
        self.assertIn("NET-04", {f.code for f in run_all(d)})
        lines[0].status, lines[1].status = "offline", "online"
        self.assertIn("running on WAN-2", issues(d)[0]["NET-01"].text)
        lines[1].status = "offline"
        self.assertEqual(issues(d)[0]["NET-01"].severity, CRITICAL)

    def test_pms_iptv_and_encoders(self):
        boxes = [dev(f"STB-{n}", "stb", "Hotel", status="offline" if n < 4 else "online") for n in range(10)]
        kit = outlet_kit() + boxes + [dev("PMS-1", "pms", "Venue", queue=25.0), dev("ENC-1", "encoder", "Hotel", status="offline")]
        d = data(services=[service(days=0), service("H1", days=0, outlet="Hotel", kind="hotel", hour=14), service("B1", days=2, kind="bar")],
                 devices=kit)
        self.assertEqual(issues(d)[0]["GST-01"].severity, WARNING)
        h = issues(d, "H1")[0]
        self.assertEqual((h["GST-01"].severity, h["GST-02"].severity, h["GST-03"].severity), (WARNING, WARNING, CRITICAL))
        self.assertNotIn("GST-01", issues(d, "B1")[0])                         # queue is a today problem
        kit[-2].status = "offline"
        self.assertEqual(issues(d, "B1")[0]["GST-01"].severity, CRITICAL)


class TestVendorsAndIncidents(unittest.TestCase):
    def test_sla_contracts_and_hours(self):
        vendors = [Vendor("Mesa", ["till", "handheld", "kitchen"], "Mon-Fri 09:00-19:00", 8, date(2027, 3, 31)),
                   Vendor("Net", ["ap", "uplink"], "24x7", 4, date(2026, 9, 30))]
        kit = outlet_kit() + [dev("KP-R2", "kitchen", status="error")]
        inc = [Incident(AS_OF - timedelta(hours=18), None, "Restaurant", "KP-R2", category="Kitchen printing", ticket="T1"),
               Incident(AS_OF - timedelta(hours=2), None, "Restaurant", "HH-R1", ticket="T2")]
        d = data(services=[service(days=0), service("S2", days=3)], devices=kit, vendors=vendors, incidents=inc)
        self.assertEqual([(o["incident"].ticket, o["vendor"].vendor, o["late"]) for o in open_incidents(d)], [("T1", "Mesa", True), ("T2", "Mesa", False)])
        self.assertEqual((issues(d)[0]["VND-01"].severity, issues(d, "S2")[0]["VND-01"].severity), (CRITICAL, WARNING))
        cover = {c["vendor"].vendor: c for c in vendor_cover(d, service_rows(d))}
        self.assertEqual((len(cover["Mesa"]["gaps"]), cover["Net"]["gaps"], cover["Net"]["days_left"]), (2, [], -26))
        f = {x.code: x for x in run_all(d)}
        self.assertEqual((f["VND-02"].severity, f["VND-03"].severity, f["VND-04"].severity), (WARNING, INFO, INFO))

    def test_repeat_incidents_and_minutes(self):
        inc = [Incident(AS_OF - timedelta(days=k * 15), AS_OF - timedelta(days=k * 15) + timedelta(hours=1), "Restaurant", "CT-R1",
                        category="Card payments", minutes_lost=10, ticket=f"T{k}") for k in range(1, 4)]
        inc.append(Incident(AS_OF - timedelta(days=90), AS_OF - timedelta(days=90), "Restaurant", "CT-R1", minutes_lost=60))   # outside
        d = data(incidents=inc)
        self.assertEqual(issues(d)[0]["INC-01"].text, "CT-R1: 3 incidents in 60 days (Card payments)")
        self.assertEqual({x.code: x for x in run_all(d)}["INC-02"].subject, "3 incidents and 30 service minutes lost in 60 days")
        st = device_state(d, dev("X", "till", version="6.3.9", target="6.4.2"))
        self.assertTrue(st["behind"])


class TestDemo(unittest.TestCase):
    def test_demo_end_to_end_is_deterministic(self):
        hashes = []
        with tempfile.TemporaryDirectory() as t:
            for k in range(2):
                out = Path(t) / f"out{k}"
                self.assertEqual(cli.main(["demo", "--data", str(Path(t) / f"data{k}"), "--out", str(out)]), 0)
                self.assertEqual(sorted(p.name for p in out.iterdir()), sorted(cli.OUTPUTS))
                hashes.append({n: hashlib.sha1((out / n).read_bytes()).hexdigest() for n in cli.OUTPUTS})
            self.assertEqual(hashes[0], hashes[1])
            d = load(Path(t) / "data0")
        f = run_all(d)
        self.assertEqual([x.severity for x in f], sorted((x.severity for x in f), key=ORDER.get))
        for c in ("SVC-01", "SVC-02", "SVC-03", "POS-01", "POS-02", "POS-03", "PAY-01", "PAY-02", "NET-02", "NET-03", "NET-04", "GST-01", "GST-02",
                  "VND-01", "VND-02", "VND-03", "VND-04", "INC-01", "INC-02"):
            self.assertIn(c, {x.code for x in f})
        verdicts = {r["service"].service_id: r["verdict"] for r in service_rows(d)}
        self.assertEqual(sorted(k for k, v in verdicts.items() if v == "ready"), ["S06", "S08", "S10", "S16"])
        self.assertEqual(sorted(k for k, v in verdicts.items() if v == "at risk"), ["S02", "S07", "S09", "S15"])
        self.assertNotIn("S00", verdicts)
        self.assertEqual(d.settings.organisation, "Solenne Beach Club & Hotel")

    def test_review_reports_a_missing_service_list(self):
        with tempfile.TemporaryDirectory() as t:
            self.assertEqual(cli.main(["review", t, "--out", str(Path(t) / "o")]), 2)


if __name__ == "__main__":
    unittest.main()
