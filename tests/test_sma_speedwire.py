"""Unit tests for the local Speedwire response decoder."""

from __future__ import annotations

import unittest
from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path

MODULE_PATH = (
    Path(__file__).parents[1]
    / "custom_components"
    / "sma_speedwire"
    / "sma_speedwire.py"
)
SPEC = spec_from_file_location("sma_speedwire_protocol", MODULE_PATH)
PROTOCOL = module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(PROTOCOL)
SMA_SPEEDWIRE = PROTOCOL.SMA_SPEEDWIRE
smaError = PROTOCOL.smaError


def register_response(register_id: int, values: list[int], register_size: int = 16):
    """Build the relevant part of a synthetic 6065 register response."""
    data = bytearray(54 + register_size + 4)
    data[46:50] = (1).to_bytes(4, "little")
    data[50:54] = (1).to_bytes(4, "little")
    data[54:58] = register_id.to_bytes(4, "little")
    for index, value in enumerate(values):
        offset = 62 + index * 4
        data[offset : offset + 4] = value.to_bytes(4, "little", signed=False)
    return bytes(data)


def multi_register_response(
    registers: list[tuple[int, list[int]]], register_size: int = 16
):
    """Build a synthetic response containing multiple consecutive registers."""
    data = bytearray(54 + register_size * len(registers) + 4)
    data[46:50] = (1).to_bytes(4, "little")
    data[50:54] = len(registers).to_bytes(4, "little")
    for register_index, (register_id, values) in enumerate(registers):
        start = 54 + register_index * register_size
        data[start : start + 4] = register_id.to_bytes(4, "little")
        for value_index, value in enumerate(values):
            offset = start + 8 + value_index * 4
            data[offset : offset + 4] = value.to_bytes(
                4, "little", signed=False
            )
    return bytes(data)


class RegisterDecoderTest(unittest.TestCase):
    """Verify scaling, signed values and SMA status tags."""

    def setUp(self):
        self.api = SMA_SPEEDWIRE("127.0.0.1")

    def tearDown(self):
        self.api.close()

    def test_original_sensor_keys_and_names_are_unchanged(self):
        """Protect the entity registry identities used by existing installs."""
        self.assertEqual(
            list(self.api.sensors)[:3],
            ["energy_total", "energy_today", "power_ac_total"],
        )
        self.assertEqual(
            [self.api.sensors[key]["name"] for key in list(self.api.sensors)[:3]],
            [
                "Energy Production Total",
                "Energy Production Today",
                "Power Production Now",
            ],
        )

    def test_voltage_scaling(self):
        self.api._decode_register_response(
            register_response(0x00464801, [23012])
        )
        self.assertEqual(self.api.sensors["voltage_ac_l1"]["value"], 230.12)

    def test_signed_temperature_scaling(self):
        self.api._decode_register_response(
            register_response(0x40237701, [0xFFFFF9C0])
        )
        self.assertEqual(self.api.sensors["inverter_temperature"]["value"], -16.0)

    def test_status_mapping(self):
        self.api._decode_register_response(
            register_response(0x08416401, [0x01000033], register_size=28)
        )
        self.assertEqual(self.api.sensors["grid_relay_status"]["value"], "Closed")

    def test_invalid_value_is_ignored(self):
        self.api._decode_register_response(
            register_response(0x00465701, [0xFFFFFFFF])
        )
        self.assertIsNone(self.api.sensors["grid_frequency"]["value"])

    def test_multiple_registers_are_decoded(self):
        decoded = self.api._decode_register_response(
            multi_register_response(
                [
                    (0x40464001, [1234]),
                    (0x40464101, [2345]),
                    (0x40464201, [3456]),
                ]
            )
        )
        self.assertEqual(decoded, 3)
        self.assertEqual(self.api.sensors["power_ac_l1"]["value"], 1234)
        self.assertEqual(self.api.sensors["power_ac_l2"]["value"], 2345)
        self.assertEqual(self.api.sensors["power_ac_l3"]["value"], 3456)

    def test_low_identifier_nibble_is_tolerated(self):
        decoded = self.api._decode_register_response(
            register_response(0x00464802, [23123])
        )
        self.assertEqual(decoded, 1)
        self.assertEqual(self.api.sensors["voltage_ac_l1"]["value"], 231.23)

    def test_repeated_unsupported_command_enters_backoff(self):
        def unavailable(_command, **_kwargs):
            raise smaError("unsupported")

        self.api._send_recieve = unavailable
        for now in (10.0, 20.0, 30.0):
            self.assertFalse(
                self.api._fetch_diagnostics("grid_frequency", now=now)
            )

        retry_after = self.api._diagnostic_retry_after["grid_frequency"]
        self.assertEqual(retry_after, 30.0 + PROTOCOL.DIAGNOSTIC_RETRY_DELAY)

        # During backoff no new network request is made.
        self.api._send_recieve = (
            lambda _command, **_kwargs: self.fail("unexpected request")
        )
        self.assertFalse(
            self.api._fetch_diagnostics("grid_frequency", now=retry_after - 1)
        )

    def test_diagnostic_tier_is_staggered_across_updates(self):
        calls = []

        def record(command, now=None):
            calls.append((command, now))
            return True

        self.api._fetch_diagnostics = record
        commands = PROTOCOL.FAST_DIAGNOSTIC_COMMANDS
        self.api._poll_next_diagnostic(commands, 30, 0.0)
        self.api._poll_next_diagnostic(commands, 30, 10.0)
        self.api._poll_next_diagnostic(commands, 30, 20.0)
        self.api._poll_next_diagnostic(commands, 30, 30.0)

        self.assertEqual(
            calls,
            [
                ("power_ac_phases", 0.0),
                ("power_dc_strings", 10.0),
                ("power_ac_phases", 30.0),
            ],
        )


if __name__ == "__main__":
    unittest.main()
