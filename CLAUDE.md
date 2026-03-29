# CLAUDE.md

## Project
Home Assistant custom integration for ChargePoint EV chargers. Uses the `python-chargepoint` library to poll the ChargePoint cloud API and expose data as HA entities (sensors, buttons, switches, etc.) for home chargers and public stations.

## Rules

### Library
- Never pass `session=` to `ChargePoint.create()` — the library must own its aiohttp session and cookie jar to manage the `coulomb_sess` auth cookie correctly
- `client.coulomb_token` reads live from the cookie jar; returns `None` when expired
- `RuntimeError("Must login to use ChargePoint API")` means the session cookie expired — handle it with automatic re-login, not as a crash

### Exception Handling
- `RuntimeError` → attempt re-login via `_async_recreate_client()`; fall back to `ConfigEntryAuthFailed`
- `InvalidSession` / `DatadomeCaptcha` → `ConfigEntryAuthFailed` (triggers reauth flow)
- `CommunicationError` → `UpdateFailed` (coordinator retries silently)
- Never let exceptions from the library surface as unhandled "unexpected errors"

### Architecture
- One `DataUpdateCoordinator` per config entry; all entities share it
- Coordinator data is a single dict keyed by `ACCT_*` constants from `const.py`
- Entity platforms (`sensor`, `button`, etc.) register entities in their own `async_setup_entry()`, pulling `client` and `coordinator` from `hass.data[DOMAIN][entry.entry_id]`
- `ChargePointEntity` = account-level; `ChargePointChargerEntity` = per home charger (keyed by `charger_id`); public station entities subclass `CoordinatorEntity` directly

### Versioning
- Always bump version in **both** `const.py` (`VERSION`) and `manifest.json` (`"version"`) together

### Complexity
- Max McCabe complexity is **15** — nested functions inside `async_setup_entry` count toward its score; extract branch-heavy logic into module-level helpers

### Testing
- Use Python 3.13: `python3.13 -m venv /tmp/ha-test-venv`
- Install deps: `pip install -r requirements_test.txt`
- Run tests: `pytest tests/ -q`
- Run checks: `pre-commit`

### Git
- Commit as the user, not as Claude
- Reference the relevant GitHub issue URL in commit messages
