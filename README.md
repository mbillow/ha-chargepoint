# ChargePoint for Home Assistant

A cloud-polling Home Assistant component to expose ChargePoint Home Charger, Account, and Public Station information.

![home assistant entities](https://github.com/mbillow/ha-chargepoint/raw/main/.github/images/ha_chargepoint_sensor_card.png)

## Installation

1. If you haven't already installed HACS, follow [their instructions](https://hacs.xyz/docs/use/#getting-started-with-hacs).
2. Navigate to HACS.
3. Choose "Integrations"
4. Install the integration like you would [any other HACS addon](https://hacs.xyz/docs/navigation/overview).

## Usage

Once you have installed the component, you'll need to add and configure it. From the
`Configuration > Devices & Services` page, click `+ Add Integration` in the bottom
right.

Search for ChargePoint and select the integration. You will be prompted for your
ChargePoint credentials. If ChargePoint's bot protection blocks the login, see the
[FAQ](FAQ.md#why-am-i-seeing-bot-protection-detected-during-setup) for how to
authenticate using a session token instead.

Once you are logged in, if you have any home chargers, you will be asked which zones/rooms
to assign each device to.

The integration exposes the following:

**Account-level sensors** (always present):

- Account balance
- Active session state, power output, energy delivered, and running cost. These update
  on every poll and work whether you are charging at home or at a public station.

**Home charger controls and sensors** (one set per charger):

- **Controls:** Start and stop charging sessions, restart the charger, adjust the charging
  amperage limit, and tune LED brightness.
- **Sensors:** Charging status, cable state, network connectivity, active session data
  (power output, energy delivered, miles added, charge cost), and charging time.



## Monitoring Public Stations

![public station device page](https://github.com/mbillow/ha-chargepoint/raw/main/.github/images/ha_chargepoint_public_station.png)

You can monitor public or shared ChargePoint stations (such as apartment parking garages
or office charging). This is useful for automations that alert you when a specific station
becomes available.

To add public stations, open the integration options from `Settings > Devices & Services > ChargePoint`,
then choose `Configure > Manage Public Chargers > Add chargers`. Drop a pin on the map near the
stations you want to track and adjust the radius. Select the stations from the results and
save.

Each tracked station creates:

**Station availability** (`binary_sensor`) — on when the station has at least one available port.

| Attribute | Description |
|---|---|
| `available_ports` | Number of ports currently available |
| `total_ports` | Total number of ports on the station |
| `address` | Street address of the station |

**Per-port availability** (`binary_sensor`) — one per port, named by connector type (e.g. "Port 1 (J1772)"), with an icon matching the plug standard. On when that specific port is available.

| Attribute | Description |
|---|---|
| `status` | Raw port status: `available`, `in_use`, `maintenance_required`, `unreachable` |
| `level` | Charging level: `L1`, `L2`, or `DC` |
| `connectors` | List of connector types on this port |
| `max_power_kw` | Maximum power output in kW |
| `estimated_shared_power_kw` | Estimated available power when the station shares power across ports (only present on shared-power stations) |

**Full Power Available** (`binary_sensor`) — on when every port on the station is available simultaneously. Useful for triggering automations that need the full station capacity.

**Diagnostic sensors** (disabled by default in the entity registry):

| Entity | Description |
|---|---|
| Max Power | Station's maximum charge rate in kW |
| Hours | Whether the station is currently open or closed |
| Shared Power | Whether the station shares power across its ports |
| Reduced Power | Whether the station is operating at reduced power |

To remove a station, go to `Settings > Devices & Services > ChargePoint` and choose `Configure > Manage Public Chargers > Remove charger(s)`.


## Energy Tracking

**Must be using `v0.1.2` or higher for proper sensor classification.**

For users that have one or more ChargePoint Home Flex(es), you can add your chargers as
sources of grid consumption in Home Assistant's energy tracking system. Simply add the
`Energy Output` output sensor of your device and add the `Charge Cost` sensor an "entity
tracking the total costs."

## Using with Third-Party Cards

The sensors created by this component can be used with third-party EV charging
cards like [tmjo/charger-card](https://github.com/tmjo/charger-card).

Feel free to create Pull Requests adding demo configurations to this section of
the README if you end up building something you'd like to share.


## Development and Contributing

If you notice any issues, please create a GitHub issue describing the error and include
any error messages or stack traces.

### Developing

Please ensure that you have the pre-commit hooks enabled. This will ensure that your
contributions are formatted and styled correctly.

```bash
pip install -r requirements_test.txt
pre-commit install
```

### Running the Integration

I've included a simple Docker Compose file that will launch a new Home Assistant instance
with the integration and its dependencies pre-installed. Simply run:

```shell
docker-compose up -d
```

Then navigate to `http://127.0.0.1:8123` in your browser.
