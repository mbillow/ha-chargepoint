# CLAUDE.md

This file provides guidance for AI assistants working on the `ha-chargepoint` repository.

## What This Is

A Home Assistant custom component integration for ChargePoint EV charging stations. It is a cloud-polling integration (`iot_class: cloud_polling`) distributed via HACS. The integration wraps the [`python-chargepoint`](https://github.com/mbillow/python-chargepoint) library, which is **maintained by the same author as this repo**.

Domain: `chargepoint`.

## Repository Layout

```
custom_components/chargepoint/   # All integration source code
    __init__.py                  # setup, DataUpdateCoordinator, base entity classes
    const.py                     # all constants and coordinator data keys
    config_flow.py               # config + options UI flows
    manifest.json                # HA integration metadata, dependency declarations
    binary_sensor.py             # public station availability
    button.py                    # start/stop charging, restart charger
    number.py                    # LED brightness
    select.py                    # amperage limit
    sensor.py                    # account balance, session metrics
    switch.py                    # charging schedule enable/disable
    time.py                      # schedule start/end times
    diagnostics.py               # anonymized debug data export
    translations/en.json         # UI strings
tests/
    conftest.py                  # all shared fixtures and mock factories
    test_init.py
    test_binary_sensor.py
    test_button.py
    test_config_flow.py
    test_number.py
    test_select.py
    test_sensor.py
```

## Development Workflow

### Python Version

Check `.github/workflows/combined.yaml` for the canonical Python version (`python-version:` under the `lint-and-test` job). There is no `.python-version` file.

### Installing Dependencies

Create a virtual environment first, then install dependencies:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements_test.txt
```

This installs all test, lint, type-check, and formatting tools plus `python-chargepoint`.

### Running Checks

**All checks are run via pre-commit. This is the single source of truth.**

```bash
pre-commit run --all-files
```

This runs in order: `trailing-whitespace`, `end-of-file-fixer`, `check-yaml`, `check-added-large-files`, `black`, `flake8`, `isort`, `mypy`, `pyright`, `pytest`.

Do not run tools individually — always use `pre-commit run --all-files`. **Do not commit unless this passes cleanly.**

### Local HA Instance (Optional)

A `docker-compose.yaml` is provided for running a local Home Assistant instance with the integration mounted live:

```bash
docker compose up
```

HA will be available at `http://127.0.0.1:8123`. The integration source is bind-mounted from `./custom_components/chargepoint`.

## Code Patterns

### Base Classes

Every entity inherits from one of two base classes defined in `__init__.py`:

- `ChargePointEntity(CoordinatorEntity)` — for account-level entities (e.g. account balance)
- `ChargePointChargerEntity(CoordinatorEntity)` — for per-charger entities

Platform entities then mix in the HA platform base, e.g.:

```python
class ChargePointChargerSensorEntity(SensorEntity, ChargePointChargerEntity):
    ...
```

### Entity Descriptions

Use frozen dataclasses extending the platform's `*EntityDescription`:

```python
@dataclass(frozen=True)
class ChargePointSensorEntityDescription(SensorEntityDescription):
    name_suffix: str = ""
    value: Callable[..., StateType] = field(default=lambda _: None)
```

### Unique IDs

- Account-level: `{user_id}_{description.key}`
- Charger-level: `{charger_id}_{description.key}`
- Public station: `public_{station_id}_{description.key}` — the `public_` prefix is significant; it drives entity ID migration logic in `_migrate_public_entity_ids()`.

Do not change the unique ID format for existing entities — it will break entity registry entries for existing users.

### Coordinator Data Keys

All coordinator data keys are constants in `const.py`:

- `ACCT_INFO` — account object
- `ACCT_CRG_STATUS` — user charging status
- `ACCT_SESSION` — active charging session (may be `None`)
- `ACCT_HOME_CRGS` — `dict[charger_id, dict]` with sub-keys: `ACCT_CHARGER_STATUS`, `ACCT_CHARGER_TECH_INFO`, `ACCT_CHARGER_CONFIG`, `ACCT_CHARGER_SCHEDULE`
- `ACCT_PUBLIC_STATIONS` — `dict[station_id, StationInfo]`

### Adding a New Entity or Platform

1. Add the platform to `PLATFORMS` in `const.py` and add the file.
2. Define an entity description dataclass and a list of descriptions.
3. Inherit from the correct base class (`ChargePointEntity` or `ChargePointChargerEntity`) and the HA platform mixin.
4. Implement `async_setup_entry` to create and register entities via `async_add_entities`.
5. Add tests in `tests/test_<platform>.py` using the fixtures from `tests/conftest.py`.
6. If the entity is for a new charger feature, ensure the coordinator fetches it in `__init__.py`.

## Testing

Tests use `pytest-homeassistant-custom-component`. Key things to know:

- **`auto_enable_custom_integrations` fixture is `autouse=True`** in `tests/conftest.py`. Without this, HA will not load from `custom_components/`. Never remove it.
- **Always patch `ChargePoint.create`**, not the constructor. The integration uses `await ChargePoint.create(...)` to build the client. The patch target is `custom_components.chargepoint.ChargePoint.create`.
- **Use `await hass.async_block_till_done()`** after setup to flush all async tasks before asserting state.
- **Mock factories** in `conftest.py` (`make_mock_client()`, `make_mock_charger_status()`, etc.) are plain functions, not fixtures, so tests can call them directly to build modified variants without re-using a fixture.
- **Look up entities by unique ID**, not by assumed entity ID, using the `get_entity_id(hass, platform, unique_id)` helper in `conftest.py`. Entity IDs can change; unique IDs are stable.
- **Exception constructors** in `python-chargepoint` require a mock request object as the first argument. Use the factory functions (`make_communication_error()`, `make_login_error()`, etc.) from `conftest.py`.

## python-chargepoint Library

This integration depends on the `python-chargepoint` library. **The same author maintains both repositories.**

If a required capability doesn't exist in the library (e.g. a new API method, a missing field on a model, a new exception type), the change belongs in `python-chargepoint`, not in this integration.

When flagging that a change belongs in `python-chargepoint`, provide:
1. **What interface is needed** — the exact method signature, model field, or exception type the integration expects.
2. **Why it's needed** — the HA feature or entity this will enable.
3. **How it should behave** — expected inputs, return type, error cases.

This gives a `python-chargepoint`-focused agent enough context to implement the change without needing to read this repo.

## Version Bumping

### Integration version

Update in **two places**:
1. `custom_components/chargepoint/const.py` — `VERSION`
2. `custom_components/chargepoint/manifest.json` — `"version"`

### python-chargepoint library version

Update in **three places**:
1. `custom_components/chargepoint/manifest.json` — `"requirements"`
2. `requirements_test.txt`
3. `.docker/services/run` — pinned with `==`, not a range like the others

### Python version

Defined in one place: `.github/workflows/combined.yaml` (`python-version:` under the `lint-and-test` job). There is no `.python-version` file; always check the workflow for the current value.

## Key Guard Rails

- Do not change unique ID formats for existing entities — it breaks existing HA installations.
- Do not add platforms to `PLATFORMS` without a corresponding platform file and tests.
- All new code must pass `pre-commit run --all-files` cleanly (type hints, formatting, lint, tests).
