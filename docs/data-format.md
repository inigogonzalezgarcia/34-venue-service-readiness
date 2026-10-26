# Data format

Put the files in one folder and run `python -m venueready review <folder>`. Only `services.csv` is required; every other file adds its checks when present. Comma, semicolon or tab separated, UTF-8. Column names are matched loosely (case, accents and punctuation are ignored), and the common alternatives below, in English and Spanish, are accepted.

## services.csv (required)

The services of the coming week: every opening of an outlet that sells, and the hotel's arrival days.

| Column | Also accepted | Notes |
|---|---|---|
| Service ID | id, ref | |
| Outlet | area, zona, local | Must match the outlet of the devices |
| Service | name, servicio | "Dinner", "Pool club · lunch", "Halloween night" |
| Type | kind, tipo | restaurant, bar, pool, event, hotel, other. If empty, it is guessed from the name ("Brunch", "Fiesta") |
| Start, End | opens, closes, inicio, fin | `YYYY-MM-DD HH:MM`, ISO or `DD/MM/YYYY HH:MM`. An end before the start closes after midnight; a missing end means four hours |
| Guests | covers, pax, cubiertos, arrivals | Compared with the working tills (`guests_per_till`) and `duty_min_guests` |
| IT on duty | on call, guardia | Who answers if something fails |
| Opening check | check done, prueba de apertura | Date and time. It counts if done within `check_window_hours` before the start |

## devices.csv

The device register with the state of each device. `scripts/Test-VenueDevices.ps1` writes it from an inventory by probing every device; add what only the vendor consoles show.

| Column | Also accepted | Notes |
|---|---|---|
| Device, Outlet | hostname, zona | Outlet empty or `Venue` for shared systems (internet lines, firewall, core switch, PMS interface, IPTV headend) |
| Type | tipo | till (TPV), handheld (comandero), kitchen printer or KDS, receipt printer, card terminal (datáfono), cash machine, access point, switch, firewall, internet line, PMS interface, IPTV headend, IPTV box, key encoder |
| Model | | Free text |
| Status | estado | online, degraded (paper low, slow), offline, error |
| Last seen | last contact, ultimo contacto | A device not seen for `heartbeat_hours` counts as down |
| Version, Target version, Next update | firmware | Versions behind the target are listed; updates inside the `freeze_hours` before a service are flagged |
| Vendor | proveedor | Optional: otherwise the vendor whose `Covers` include the type |
| Role | | Internet lines: `primary` or `backup` |
| Cash level, Fill % | efectivo, llenado | Cash machines: cash available for change and stacker fill |
| Queue | pending postings, cola | PMS interface: postings waiting |

## vendors.csv

| Column | Also accepted | Notes |
|---|---|---|
| Vendor | proveedor | |
| Covers | scope, cubre | Device types separated by `;` |
| Support hours | horario soporte | `24x7`, or `Mon-Fri 09:00-19:00, Sat 10:00-14:00`; a window ending before it starts runs past midnight |
| SLA hours | sla | Hours to fix; open tickets older than this are past the SLA |
| Contract end | fin contrato | Ended contracts are a warning; ending within `contract_warn_days`, information |

## incidents.csv

The tickets of the last weeks, open and closed, from the service desk or the vendors' portals.

| Column | Also accepted | Notes |
|---|---|---|
| Ticket | id, incidencia | |
| Opened, Closed | apertura, cierre | Empty Closed means open |
| Outlet, Device | zona, dispositivo | The device links the ticket to its vendor and its outlet |
| Category, Minutes lost, Summary | categoria, minutos perdidos | Service minutes lost (orders by hand, payments moved, tables waiting) |

## settings.json

| Key | Default | What |
|---|---|---|
| `organisation`, `as_of` | | Name for the reports; review time (otherwise now) |
| `horizon_days` | 7 | Services included |
| `check_kinds`, `check_window_hours`, `check_lead_hours` | all but other, 6, 3 | Services that need an opening check; how early it counts; how close to opening it becomes critical |
| `duty_min_guests` | 150 | Services this big (and every event) need someone from IT on duty or on call |
| `heartbeat_hours` | 24 | A device not seen for longer is down |
| `freeze_hours` | 24 | No updates this long before a service |
| `guests_per_till` | 60 | Working tills and handhelds needed per guest |
| `food_kinds`, `room_charge_kinds` | restaurant, pool, event · restaurant, bar, pool | Services that need the kitchen printers · that post to the PMS |
| `cash_float_min`, `cash_full_pct` | 300, 85 | Cash machine float and stacker fill |
| `pms_queue_max`, `stb_offline_max` | 10, 2 | PMS postings waiting · IPTV boxes offline before it is flagged |
| `contract_warn_days`, `repeat_incidents`, `incident_window_days` | 60, 3, 60 | |
| `owners` | | Owner per area: services, pos, network, guest, vendors, incidents |

Cash levels and the PMS queue describe the moment of the review, so they are checked only for today's services; devices down count for every service until they are fixed.
