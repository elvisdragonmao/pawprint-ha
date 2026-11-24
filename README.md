# PawPrint Light Controller

[繁體中文](README.zh-TW.md) · [MIT License](LICENSE)

A Home Assistant custom integration that uses the DG-LAB Pawprint V1.1 as a local Bluetooth LE controller for one light. Home Assistant receives the button's sensor reports and calls its own light services. The integration needs no separate server, MQTT broker, or Home Assistant access token.

| Gesture | Light action |
| --- | --- |
| Short press | If the light is on, advance through white, red, amber, green, cyan, blue, and violet. If the light is off, turn it on in the last selected color, or white on first use. |
| Hold still and release | Turn the light off. |
| Hold and tilt | Adjust brightness. At 0% the light turns off. Tilting back above 0% turns it on again. Release to end dimming. |

## What you need

- A first-generation **Pawprint V1.1** that advertises as `47L120300`. If it advertises as `47L120100`, see the firmware update instructions in the [DG-LAB Pawprint protocol](https://github.com/dungeonlab-open/dglab-bluetooth-protocol/blob/main/paw-prints/README.md#bluetooth-name).
- Home Assistant with the [Bluetooth integration](https://www.home-assistant.io/integrations/bluetooth/) active and a connectable BLE adapter within range. For Home Assistant Container with a local adapter, follow the official instructions for the host D-Bus mount and adapter permissions.
- A Home Assistant `light.*` entity that supports color and brightness for all three gestures.

Verified with a physical Pawprint V1.1, Home Assistant Container 2026.10.1 on a Raspberry Pi with built-in Bluetooth, and a Matter color light.

## Install and pair

1. Download or clone this repository. Copy `custom_components/pawprint_light/` into the `custom_components/` directory under your Home Assistant configuration directory. Create that directory if necessary. The resulting path should look like `/config/custom_components/pawprint_light/manifest.json` inside Home Assistant.
2. Add the `pawprint_light:` and logging settings from [sample.yaml](sample.yaml) to `configuration.yaml`. Replace `light.example_lamp` with your light's entity ID. If you already have a `logger:` block, add the component's log level under its existing `logs:` key. The sample starts with `dry_run: true`, so you can observe gestures before they control the light.
3. Run Home Assistant's configuration check and restart it. Close any app or browser tab already connected to the Pawprint. Turn the Pawprint on and hold the button until the shoulder LEDs alternate white and blue. It connects automatically when only one matching button is visible.
4. Wait for `Pawprint connected and reporting sensor data` in **Settings → System → Logs**, then release the button. In **Developer Tools → Events**, listen for `pawprint_light_gesture` and try the gestures. The event contains `gesture` (`color`, `off`, or `brightness`) and `brightness_pct` (0–100 for dimming and `null` for other gestures).
5. Copy the Bluetooth address shown in the logs to `address` to bind the integration to this button across restarts. Set `dry_run: false` to enable real control. Once you finish calibrating, set `debug: false` and lower the component's logger level to `info`. Check the configuration and restart to apply your changes.

## Calibrate dimming

With `debug: true` and the component log level set to `debug`, watch the `XYZ` values in the logs while tilting the button between the two positions you want to use. Set `axis` to the axis with the clearest change. Set `left` to the reading for 0% and `right` to the reading for 100%. Swapping the readings reverses the direction. These are signed sensor counts. Tilting the button may give a clearer signal than rotating it flat on a desk.

| Option | Default | Meaning |
| --- | --- | --- |
| `light` | Required | Target Home Assistant light entity |
| `address` | Auto-discovery | Bluetooth address. Set it when more than one Pawprint is in range |
| `axis` | `x` | Sensor axis used for dimming, one of `x`, `y`, or `z` |
| `left`, `right` | `-60`, `60` | Raw readings for 0% and 100%, within −128 to 127 and distinct |
| `hold_seconds` | `0.5` | Hold threshold in seconds |
| `motion_threshold` | `12` | Movement threshold in sensor counts |
| `speed_threshold` | `35` | Movement speed threshold in sensor counts per second |
| `debug` | `false` | Log raw sensor reports at debug level |
| `dry_run` | `false` | Emit gesture events without calling light services |

The button reports approximately every 100 ms, so an especially fast tap can fall between samples. If it stops sending, the bridge discards the unfinished gesture and retries the connection. Wake the button or put it back into pairing mode if it has stopped advertising. Dimming maps the current tilt to an absolute brightness, so the first adjustment can jump to that position's value.

## Development

Run the gesture tests with Python 3.9 or later.

```sh
python3 -m unittest -v test_gesture
```

Run the full suite in the same Home Assistant Core image used by GitHub Actions. The integration test simulates BLE notifications and checks the events and light service calls in Core. It also verifies the write-without-response initialization required by the tested button.

```sh
docker run --rm --entrypoint python \
  --volume "$PWD:/workspace:ro" --workdir /workspace \
  --env PYTHONDONTWRITEBYTECODE=1 \
  ghcr.io/home-assistant/home-assistant:2026.10.1 -m unittest -v
```

The code is released under the [MIT License](LICENSE). The BLE implementation follows the [DG-LAB Pawprint V1.1 protocol](https://github.com/dungeonlab-open/dglab-bluetooth-protocol/blob/main/paw-prints/README.md).
