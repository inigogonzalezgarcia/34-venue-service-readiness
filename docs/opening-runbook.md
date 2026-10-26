# Service readiness runbook

A 15-minute check every morning before the first service, and again on the morning of every big event, with the venue IT technician and the outlet managers on the call when something is red. The tool only reads exports; devices, contracts and tickets are changed in their own tools.

## Before the check (10 minutes)

1. Probe the devices from a machine on the venue network (read-only):
   ```powershell
   .\scripts\Test-VenueDevices.ps1 -Inventory .\data\inventory.csv -OutputFile .\data\devices.csv
   ```
2. Copy what the probe cannot see from the vendor consoles: cash machine levels and fill, the PMS interface queue, devices showing an error on screen, scheduled updates.
3. Update `services.csv` with the week's services, expected guests and who from IT is on duty, and export the open and last 60 days of tickets into `incidents.csv`.
4. Build the outputs and share `opening-pack.md` with the outlet managers:
   ```bash
   python -m venueready review data/ --title "Service readiness · Monday"
   ```

## Agenda

| Minutes | Topic | Output |
|---|---|---|
| 5 | Today's services at risk: kitchen printers, tills, card terminals, internet, opening checks due | `report.html` → Fix first |
| 4 | Vendor tickets past their SLA and what to escalate | `vendor-cover.csv`, `device-health.csv` |
| 3 | The week ahead: events with no IT cover, updates inside the freeze, outlets short of tills | `service-readiness.csv` |
| 3 | Devices that keep failing and spares to move | `incidents-by-outlet.csv` |

## How to read it

- **The verdict is per service, not per device.** A card terminal down in a bar with three terminals is a note; the only kitchen printer down before a 240-guest lunch is a decision.
- **Not seen is not fine.** A handheld that has not checked in for three days is in a drawer, on a charger that does not work, or gone.
- **The backup line counts only if it works.** A failover that has not been tested this month is a guess; the backup 4G router is checked like any other device.
- **Vendor hours are part of the plan.** If the POS vendor answers until 19:00 and the bar closes at 01:00, the fallback (spare handheld, paper order pads, the manual card procedure) has to be on site.
- **Nothing changes inside the freeze.** A POS or firewall update the night before a big event is a change nobody tested with a full venue.

## Opening check (each outlet, before doors open)

- One sale on every till and handheld, printed to the kitchen and on the receipt printer.
- One card payment (contactless and chip) on every terminal.
- Cash machine: float loaded, stacker emptied, no error.
- Wi-Fi: a handheld walked to the far end of the outlet (the sun loungers, the terrace).
- Room charge to a test folio where the outlet posts to the PMS.
- Record the time in `services.csv`.
