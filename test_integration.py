"""Exercise BLE initialization and light service calls in Home Assistant Core."""

import asyncio
import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from homeassistant.core import HomeAssistant, callback

from custom_components import pawprint_light

LIGHT = "light.example_lamp"


class SimulatedPawprint:
    """Model the two GATT characteristics used by the V1.1 bridge."""

    def __init__(self):
        self.is_connected = True
        self.initialized = asyncio.Event()
        self.notify = None

    async def start_notify(self, uuid, callback):
        if uuid != "0000150b-0000-1000-8000-00805f9b34fb":
            raise ValueError("Unexpected notification characteristic")
        self.notify = callback

    async def write_gatt_char(self, uuid, command, *, response):
        if uuid != "0000150a-0000-1000-8000-00805f9b34fb":
            raise ValueError("Unexpected command characteristic")
        if response:
            raise ValueError("V1.1 only supports write without response")
        if command != bytes.fromhex("50 01 D0 01") + bytes(13) or self.notify is None:
            raise ValueError("Unexpected initialization sequence")
        self.initialized.set()

    async def disconnect(self):
        self.is_connected = False

    async def sample(self, pressed, angle=0, delay=0.12):
        await asyncio.sleep(delay)
        self.notify(None, bytes((0xD0, 1, 2, pressed, 0, angle % 256, 0, 0, 0)))


class BridgeTests(unittest.IsolatedAsyncioTestCase):
    async def test_v11_notifications_become_light_service_calls(self):
        with tempfile.TemporaryDirectory() as config_dir:
            hass = HomeAssistant(config_dir)
            button = SimulatedPawprint()
            device = SimpleNamespace(address="AA:BB:CC:DD:EE:FF", name="47L120300")
            calls = []
            events = []

            @callback
            def record_call(call):
                calls.append((call.service, dict(call.data)))

            @callback
            def record_event(event):
                events.append(dict(event.data))

            hass.services.async_register("light", "turn_on", record_call)
            hass.services.async_register("light", "turn_off", record_call)
            hass.bus.async_listen("pawprint_light_gesture", record_event)
            hass.states.async_set(LIGHT, "off")
            config = pawprint_light.CONFIG_SCHEMA({"pawprint_light": {"light": LIGHT}})

            with (
                patch.object(
                    pawprint_light.bluetooth, "async_discovered_service_info", return_value=[device]
                ),
                patch.object(
                    pawprint_light.bluetooth, "async_ble_device_from_address", return_value=device
                ),
                patch.object(pawprint_light, "establish_connection", return_value=button),
            ):
                try:
                    self.assertTrue(await pawprint_light.async_setup(hass, config))
                    await asyncio.wait_for(button.initialized.wait(), timeout=2)
                    await asyncio.wait_for(self.send_gestures(button), timeout=10)
                    await hass.async_block_till_done()
                finally:
                    await hass.async_stop(force=True)

            self.assertFalse(button.is_connected)
            self.assertEqual(
                [(event["gesture"], event["brightness_pct"]) for event in events],
                [("color", None), ("off", None), ("brightness", 0),
                 ("brightness", 50), ("brightness", 100)],
            )
            self.assertEqual(
                calls,
                [
                    ("turn_on", {"entity_id": LIGHT, "rgb_color": [255, 255, 255]}),
                    ("turn_off", {"entity_id": LIGHT}),
                    ("turn_off", {"entity_id": LIGHT}),
                    ("turn_on", {"entity_id": LIGHT, "brightness_pct": 50}),
                    ("turn_on", {"entity_id": LIGHT, "brightness_pct": 100}),
                ],
            )

    async def send_gestures(self, button):
        await button.sample(0)
        await button.sample(1)
        await button.sample(0)

        await button.sample(1)
        for _ in range(5):
            await button.sample(1)
        await button.sample(0)

        await button.sample(1)
        for _ in range(5):
            await button.sample(1, -60)
        await button.sample(1, 0, delay=0.24)
        await button.sample(1, 60, delay=0.24)
        await button.sample(0, 60)
