# ChargePoint for Home Assistant

A cloud-polling Home Assistant component to expose ChargePoint Home Charger and Account information.

![home assistant entities](https://github.com/mbillow/ha-chargepoint/raw/main/.github/images/ha_chargepoint_sensor_card.png)

## Installation

1. If you haven't already installed HACS, follow [their instructions](https://hacs.xyz/docs/setup/prerequisites).
2. Navigate to HACS.
3. Choose "Integrations"
4. Install the integration like you would [any other HACS addon](https://hacs.xyz/docs/navigation/overview).

## Usage

Once you have installed the component, you'll need to add and configure it. From the
`Configuration > Devices & Services` page, click `+ Add Integration` in the bottom
right.

Search for ChargePoint and select the integration. You will be prompted for your
ChargePoint credentials.

Once you are logged in, if you have any home chargers, you will be asked which zones/rooms
to assign each device to. Otherwise, you will just see a sensor exposing your account
balance.


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
pip install pre-commit
pre-commit install
```

### Running the Integration

I've included a simple Docker Compose file that will launch a new Home Assistant instance
with the integration and its dependencies pre-installed. Simply run:

```shell
docker-compose up -d
```

Then navigate to `http://127.0.0.1:8123` in your browser.
