"""Command line: `demo` builds everything from the fictional venue, `review` runs on your own exports."""
from __future__ import annotations

import argparse
import sys
from datetime import datetime
from pathlib import Path

from . import report, simulate
from .checks import run_all
from .model import load, parse_dt

OUTPUTS = ("report.html", "opening-pack.md", "service-readiness.csv", "device-health.csv", "vendor-cover.csv", "incidents-by-outlet.csv",
           "actions.csv", "findings.csv")


def run(data: Path, out: Path, title: str, as_of: datetime | None = None) -> dict:
    d = load(data, as_of)
    b = report.build(d)
    findings = run_all(d, b["rows"])
    out.mkdir(parents=True, exist_ok=True)
    (out / "report.html").write_text(report.render_html(d, findings, title, b), encoding="utf-8")
    (out / "opening-pack.md").write_text(report.opening_md(d, findings, b), encoding="utf-8")
    report.write_services(b, out / "service-readiness.csv")
    report.write_devices(d, b, out / "device-health.csv")
    report.write_vendors(b, out / "vendor-cover.csv")
    report.write_incidents(d, out / "incidents-by-outlet.csv")
    report.write_actions(findings, out / "actions.csv")
    report.write_findings(findings, out / "findings.csv")
    return report.summary(d, findings, b)


def _when(value: str) -> datetime:
    d = parse_dt(value)
    if not d:
        raise argparse.ArgumentTypeError(f"not a date (YYYY-MM-DD or 'YYYY-MM-DD HH:MM'): {value}")
    return d


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="venueready", description=__doc__)
    sub = p.add_subparsers(dest="cmd", required=True)
    dm = sub.add_parser("demo", help="write the fictional venue to sample_data/ and build the outputs")
    dm.add_argument("--data", type=Path, default=Path("sample_data"))
    dm.add_argument("--out", type=Path, default=Path("output"))
    rv = sub.add_parser("review", help="build the outputs from your own exports")
    rv.add_argument("data", type=Path, help="folder with services.csv (required) and devices.csv, vendors.csv, incidents.csv, settings.json (optional)")
    rv.add_argument("--out", type=Path, default=Path("output"))
    rv.add_argument("--title", default="Service readiness")
    rv.add_argument("--as-of", type=_when, help="review time (default: settings.json, or now)")
    a = p.parse_args(argv)
    if a.cmd == "demo":
        simulate.write(a.data)
        sm = run(a.data, a.out, f"{simulate.ORG} · Service readiness")
    else:
        try:
            sm = run(a.data, a.out, a.title, a.as_of)
        except (FileNotFoundError, ValueError) as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 2
    print(f"{sm['services']} services ({sm['at_risk']} at risk, {sm['attention']} attention, {sm['ready']} ready; {sm['today']} today) · "
          f"opening checks missing {sm['checks_missing']} · devices down {sm['down']}/{sm['devices']} · vendor tickets past SLA "
          f"{sm['late']}/{sm['open']} · {sm['minutes_lost']:g} service minutes lost · {sm['critical']} critical, {sm['warning']} warnings")
    print(f"outputs in {a.out}/: {', '.join(OUTPUTS)}")
    return 0
