# CLAUDE.md

## Project Overview

This is a Home Assistant custom integration for ChargePoint EV chargers. It uses the
[python-chargepoint](https://github.com/mbillow/python-chargepoint) library to interact
with the ChargePoint cloud API and surfaces charger data as HA entities.

It supports:
- **Home chargers** (e.g. CPH50): status, charging sessions, schedule, LED brightness,
  amperage limit, start/stop/restart
- **Public stations**: availability, power level, and port status (read-only, polled)
- **Account-level sensors**: balance, active session energy/cost/time

---

## Architecture

### Library (`python-chargepoint`)

`ChargePoint` is the central client class. It is created once per config entry via
`ChargePoint.create(username, coulomb_token=token)`. Do **not** pass an external
`session=` argument — the library must own its aiohttp session and cookie jar to
correctly manage the `coulomb_sess` authentication cookie.

Key client methods used by the integration:

| Method | Returns |
|--------|---------|
| `get_account()` | `Account` — user info and account balance |
| `get_user_charging_status()` | `UserChargingStatus` or `None` |
| `get_charging_session(session_id)` | `ChargingSession` |
| `get_home_chargers()` | `list[int]` — device IDs |
| `get_home_charger_status(id)` | `HomeChargerStatus` |
| `get_home_charger_technical_info(id)` | `HomeChargerTechnicalInfo` |
| `get_home_charger_config(id)` | `HomeChargerConfiguration` |
| `get_home_charger_schedule(id)` | `HomeChargerSchedule` |
| `get_nearby_stations(bounds)` | `list[MapStation]` |
| `get_station(device_id)` | `StationInfo` |

`client.coulomb_token` reads the current `coulomb_sess` cookie value directly from the
aiohttp cookie jar. It returns `None` if the cookie has expired, which causes the
library to raise `RuntimeError("Must login to use ChargePoint API")` on the next call.

### Authentication

The integration authenticates using a `coulomb_sess` cookie value stored in the config
entry as `CONF_ACCESS_TOKEN`. The config flow supports:
1. Password login → may trigger Datadome captcha → manual cookie entry fallback
2. Direct token entry (for users who obtain the cookie from their browser)

When the session cookie expires mid-operation, `_async_recreate_client()` automatically
re-creates the client with the stored token. If the token is also invalid,
`ConfigEntryAuthFailed` is raised to prompt the user to reauthenticate.

### Data Flow

```
async_setup_entry()
  └─ ChargePoint.create()           # one client per config entry
  └─ DataUpdateCoordinator          # polls on a configurable interval (default 3 min)
       └─ async_update_data()       # closure; holds nonlocal client reference
            └─ _async_coordinator_update()
                 ├─ client.get_account()
                 ├─ client.get_user_charging_status()
                 ├─ client.get_charging_session()      # if session active
                 ├─ _async_fetch_home_charger_data()   # parallel per charger
                 │    ├─ get_home_charger_status()
                 │    ├─ get_home_charger_technical_info()
                 │    ├─ get_home_charger_config()
                 │    └─ get_home_charger_schedule()
                 └─ _fetch_public_stations()           # parallel per tracked station
```

All coordinator data is stored in a single dict keyed by `ACCT_*` constants from
`const.py`. Entities read from `coordinator.data` via properties on their base classes.

### Entity / Device Structure

Entities are registered in each platform's `async_setup_entry()`, called by HA after
`__init__.py`'s `async_setup_entry()` completes. Each platform pulls `client` and
`coordinator` from `hass.data[DOMAIN][entry.entry_id]`.

**Base classes** (defined in `__init__.py`):
- `ChargePointEntity` — account-level entities (balance, session sensors)
- `ChargePointChargerEntity` — home charger entities; keyed by `charger_id`
- `CoordinatorEntity` (HA built-in) — wires up coordinator subscription for all of the above

Public station entities subclass `CoordinatorEntity` directly (no shared base class) and
carry their own `DeviceInfo` built from `StationInfo`.

**Devices:**
- One device per home charger (`identifiers={(DOMAIN, str(charger_id))}`)
- One device per tracked public station (`identifiers={(DOMAIN, "public_{device_id}")}`)

**Platforms in use:** `binary_sensor`, `button`, `number`, `select`, `sensor`, `switch`,
`time`

### Exception Handling

| Exception | Meaning | Integration response |
|-----------|---------|----------------------|
| `RuntimeError` | Session cookie expired | Auto re-login via `_async_recreate_client()`; fall back to `ConfigEntryAuthFailed` |
| `InvalidSession` | Token invalid/revoked | `ConfigEntryAuthFailed` |
| `DatadomeCaptcha` | Bot protection triggered | `ConfigEntryAuthFailed` |
| `CommunicationError` | Network / API error | `UpdateFailed` (coordinator retries) |

---

## Testing

- Use Python 3.13: `python3.13 -m venv /tmp/ha-test-venv`
- Install dependencies: `/tmp/ha-test-venv/bin/pip install -r requirements_test.txt`
- Run tests: `/tmp/ha-test-venv/bin/pytest tests/ -q`

---

## Linting & Formatting

- Run `pre-commit` to execute all lint and format checks
- Max McCabe complexity is **15** — nested functions inside `async_setup_entry` count
  toward its score; extract branch-heavy logic into module-level helpers

---

## Versioning

Version lives in **two places** — always bump both together:
- `custom_components/chargepoint/const.py` → `VERSION = "x.y.z"`
- `custom_components/chargepoint/manifest.json` → `"version": "x.y.z"`

---

## Git

- Commit as the user, not as Claude
- Reference the relevant issue URL in commit messages
