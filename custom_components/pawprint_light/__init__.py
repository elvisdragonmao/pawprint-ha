"""Bridge a Pawprint V1.1 button to a Home Assistant light."""

import asyncio
import logging
import time

import voluptuous as vol
from bleak_retry_connector import BleakClientWithServiceCache, establish_connection
from homeassistant.components import bluetooth
from homeassistant.const import EVENT_HOMEASSISTANT_STOP
from homeassistant.helpers import config_validation as cv

from .gesture import MAX_SAMPLE_GAP, Gesture, decode

DOMAIN = "pawprint_light"
EVENT_GESTURE = "pawprint_light_gesture"
ADVERTISED_NAME = "47L120300"
WRITE = "0000150a-0000-1000-8000-00805f9b34fb"
NOTIFY = "0000150b-0000-1000-8000-00805f9b34fb"
ENABLE_SENSOR_REPORTS = bytes.fromhex("50 01 D0 01") + bytes(13)
PALETTE = [
    [255, 255, 255],
    [255, 0, 0],
    [255, 160, 0],
    [0, 255, 0],
    [0, 255, 255],
    [0, 0, 255],
    [160, 0, 255],
]

_LOGGER = logging.getLogger(__name__)

PAWPRINT_SCHEMA = vol.Schema(
    {
        vol.Required("light"): cv.entity_id,
        vol.Optional("address"): cv.string,
        vol.Optional("axis", default="x"): vol.In(["x", "y", "z"]),
        vol.Optional("left", default=-60): vol.All(
            vol.Coerce(int), vol.Range(min=-128, max=127)
        ),
        vol.Optional("right", default=60): vol.All(
            vol.Coerce(int), vol.Range(min=-128, max=127)
        ),
        vol.Optional("hold_seconds", default=0.5): vol.All(
            vol.Coerce(float), vol.Range(min=0.3, max=3)
        ),
        vol.Optional("motion_threshold", default=12): vol.All(
            vol.Coerce(int), vol.Range(min=2, max=100)
        ),
        vol.Optional("speed_threshold", default=35): vol.All(
            vol.Coerce(float), vol.Range(min=1)
        ),
        vol.Optional("debug", default=False): cv.boolean,
        vol.Optional("dry_run", default=False): cv.boolean,
    }
)
CONFIG_SCHEMA = vol.Schema({DOMAIN: PAWPRINT_SCHEMA}, extra=vol.ALLOW_EXTRA)


async def async_setup(hass, config):
    """Start the bridge and tie its lifetime to Home Assistant."""
    if DOMAIN not in config:
        return True
    cfg = config[DOMAIN]
    if not cfg["light"].startswith("light.") or cfg["left"] == cfg["right"]:
        _LOGGER.error("Expected a light entity and distinct left/right endpoints")
        return False

    bridge = Bridge(hass, cfg)
    task = hass.async_create_background_task(bridge.run(), "pawprint_light bridge")
    _LOGGER.info("Pawprint bridge ready for %s (dry_run=%s)", cfg["light"], cfg["dry_run"])

    async def stop(_event):
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)

    hass.bus.async_listen_once(EVENT_HOMEASSISTANT_STOP, stop)
    return True


class Bridge:
    """Manage the BLE connection and map gestures to light services."""

    def __init__(self, hass, cfg):
        self.hass = hass
        self.cfg = cfg
        self.gesture = Gesture(
            axis="xyz".index(cfg["axis"]),
            left=cfg["left"],
            right=cfg["right"],
            hold=cfg["hold_seconds"],
            motion=cfg["motion_threshold"],
            speed=cfg["speed_threshold"],
        )
        self.color = -1
        self.address = cfg.get("address")

    async def action(self, action):
        kind, value = action
        self.hass.bus.async_fire(EVENT_GESTURE, {"gesture": kind, "brightness_pct": value})
        _LOGGER.debug("Gesture: %s", action)
        if self.cfg["dry_run"]:
            return

        entity = self.cfg["light"]
        data = {"entity_id": entity}
        service = "turn_on"
        if kind == "off" or (kind == "brightness" and value == 0):
            service = "turn_off"
        elif kind == "brightness":
            data["brightness_pct"] = value
        elif kind == "color":
            state = self.hass.states.get(entity)
            if state is None or state.state in ("unknown", "unavailable"):
                return
            if state.state == "on":
                self.color = (self.color + 1) % len(PALETTE)
            elif self.color < 0:
                self.color = 0
            data["rgb_color"] = PALETTE[self.color]

        try:
            await asyncio.wait_for(
                self.hass.services.async_call("light", service, data, blocking=True),
                timeout=5,
            )
        except Exception:
            _LOGGER.exception("Light service failed")

    async def run(self):
        """Find the configured button and reconnect when a session ends."""
        while True:
            try:
                if not self.address:
                    found = {
                        info.address
                        for info in bluetooth.async_discovered_service_info(
                            self.hass, connectable=True
                        )
                        if info.name == ADVERTISED_NAME
                    }
                    if len(found) == 1:
                        self.address = found.pop()
                        _LOGGER.info("Pawprint found: %s", self.address)
                    elif len(found) > 1:
                        _LOGGER.warning("Multiple Pawprints found; configure an address in YAML")

                device = (
                    bluetooth.async_ble_device_from_address(
                        self.hass, self.address, connectable=True
                    )
                    if self.address
                    else None
                )
                if device is None:
                    await asyncio.sleep(5)
                    continue
                await self.session(device)
            except Exception as err:
                _LOGGER.warning("Pawprint session ended, retrying: %r", err)
            await asyncio.sleep(3)

    async def session(self, device):
        client = await establish_connection(BleakClientWithServiceCache, device, "Pawprint")
        self.gesture.reset()
        queue = asyncio.Queue(maxsize=32)

        def notify(_sender, data):
            sample = decode(data)
            if sample is None:
                return
            if self.cfg["debug"]:
                _LOGGER.debug("D0 %s pressed=%s XYZ=%s", data.hex(), *sample)
            if queue.full():
                while not queue.empty():
                    queue.get_nowait()
                self.gesture.reset()
            queue.put_nowait((time.monotonic(), *sample))

        try:
            await client.start_notify(NOTIFY, notify)
            # The V1.1 command characteristic advertises write-without-response.
            await client.write_gatt_char(WRITE, ENABLE_SENSOR_REPORTS, response=False)
            first_sample = await asyncio.wait_for(queue.get(), timeout=2)
            self.gesture.feed(*first_sample)
            _LOGGER.info("Pawprint connected and reporting sensor data: %s", device.address)

            while client.is_connected:
                sample = await asyncio.wait_for(queue.get(), timeout=2)
                if time.monotonic() - sample[0] > MAX_SAMPLE_GAP:
                    self.gesture.reset()
                    continue
                action = self.gesture.feed(*sample)
                if action:
                    await self.action(action)
        finally:
            self.gesture.reset()
            if client.is_connected:
                await client.disconnect()
