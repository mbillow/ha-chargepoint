# Frequently Asked Questions

## Authentication

### Why am I seeing "Bot Protection Detected" during setup?

ChargePoint uses a bot protection service called Datadome that can block automated logins, including the ones this integration uses. When this happens, you can bypass it by providing a session token directly instead of your password. This method is also more reliable long-term since session tokens are less likely to be challenged.

### How do I get my `coulomb_sess` session token?

You need to log into ChargePoint in a browser and copy the session cookie from Developer Tools. The steps vary slightly by browser.

#### Google Chrome / Microsoft Edge

1. Open [driver.chargepoint.com](https://driver.chargepoint.com) and log in.
2. Press `F12` (Windows/Linux) or `Cmd+Option+I` (Mac) to open Developer Tools.
3. Click the **Application** tab.
4. In the left sidebar, expand **Cookies** and click on `https://driver.chargepoint.com`.
5. Find the row named `coulomb_sess` and copy the value from the **Value** column.

#### Mozilla Firefox

1. Open [driver.chargepoint.com](https://driver.chargepoint.com) and log in.
2. Press `F12` (Windows/Linux) or `Cmd+Option+I` (Mac) to open Developer Tools.
3. Click the **Storage** tab.
4. In the left sidebar, expand **Cookies** and click on `https://driver.chargepoint.com`.
5. Find the row named `coulomb_sess` and copy the value from the **Value** column.

#### Safari

1. Open [driver.chargepoint.com](https://driver.chargepoint.com) and log in.
2. First enable the Develop menu: open **Safari > Settings > Advanced** and check **Show features for web developers**.
3. Press `Cmd+Option+I` to open Web Inspector.
4. Click the **Storage** tab.
5. In the left sidebar, expand **Cookies** and click on `driver.chargepoint.com`.
6. Find the row named `coulomb_sess` and copy the value from the **Value** column.

#### Tips

- The token expires when your ChargePoint session ends. If you log out of ChargePoint or the token expires, you'll need to reauthenticate in Home Assistant.
- If you can't find `coulomb_sess`, make sure you are fully logged in before looking. The cookie is only set after a successful login.

---

## Public Stations

### Why didn't my station appear in the search results?

The map search uses ChargePoint's API which clusters nearby stations at lower zoom levels. Try these steps:

- Move the pin closer to the exact location of the station.
- Reduce the search radius — a smaller radius forces the API to return individual stations instead of clusters.
- Zoom into the map before dropping the pin to improve accuracy.

### How do I report a problem or request a feature?

Open an issue at [github.com/mbillow/ha-chargepoint/issues](https://github.com/mbillow/ha-chargepoint/issues). If reporting a bug, please include a diagnostics dump from **Settings > Devices & Services > ChargePoint > (three dots) > Download Diagnostics**.
