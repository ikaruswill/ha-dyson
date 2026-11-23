"""Tests for the HushJet Purifier Compact (HJ10)."""

import asyncio
import json
from unittest.mock import MagicMock

from homeassistant.components.fan import FanEntityFeature
from homeassistant.const import CONF_NAME
from libdyson import DysonPureCool
from libdyson.cloud import DysonDeviceInfo
import pytest

from custom_components.dyson_local import _async_get_platforms, sensor
from custom_components.dyson_local.binary_sensor import DysonFanRunningSensor
from custom_components.dyson_local.const import DATA_COORDINATORS, DATA_DEVICES, DOMAIN
from custom_components.dyson_local.devices import (
    DEVICE_TYPE_HUSHJET,
    DEVICE_TYPE_NAMES,
    DysonHushJet,
    get_device,
    get_device_type,
)
from custom_components.dyson_local.fan import DysonHushJetEntity
from custom_components.dyson_local.number import DysonSleepTimerNumber

SERIAL = "M4P-SG-ABC1234A"

# Product state as an HJ10 reports it (captured 2026-11-23): Pure Cool
# fields, no oscillation.
STATUS = {
    "auto": "OFF",
    "cflr": "0088",
    "cflt": "CARF",
    "fnsp": "0004",
    "fnst": "FAN",
    "fpwr": "ON",
    "hflr": "0093",
    "hflt": "HSCO",
    "nmdv": "0000",
    "nmod": "OFF",
    "rhtm": "ON",
    "sltm": "OFF",
}


@pytest.fixture
def hushjet() -> DysonHushJet:
    """Return a connected HushJet with a recorded MQTT client."""
    device = DysonHushJet(SERIAL, "credential", DEVICE_TYPE_HUSHJET)
    device._status = dict(STATUS)
    device._mqtt_client = MagicMock()
    device._connected.set()
    return device


def published(device: DysonHushJet) -> list:
    """Return the data of every command the device published."""
    return [
        json.loads(call.args[1])["data"]
        for call in device._mqtt_client.publish.call_args_list
    ]


def device_info(product_type: str) -> DysonDeviceInfo:
    """Return MyDyson cloud info for a device of the given product type."""
    return DysonDeviceInfo(
        active=True,
        serial=SERIAL,
        name="Bedroom",
        version="",
        credential="credential",
        auto_update=True,
        new_version_available=False,
        product_type=product_type,
    )


def test_get_device_creates_hushjet():
    device = get_device(SERIAL, "credential", DEVICE_TYPE_HUSHJET)
    assert isinstance(device, DysonHushJet)
    assert device.device_type == DEVICE_TYPE_HUSHJET


def test_get_device_delegates_other_types():
    assert isinstance(get_device(SERIAL, "credential", "438"), DysonPureCool)
    assert get_device(SERIAL, "credential", "999") is None


def test_hushjet_is_not_pure_cool():
    # DysonPureCool's oscillation angle properties raise without osal/osau.
    assert not issubclass(DysonHushJet, DysonPureCool)


def test_cloud_product_type_maps_to_hushjet():
    assert get_device_type(device_info("897")) == DEVICE_TYPE_HUSHJET


def test_cloud_product_type_falls_back_to_libdyson():
    assert get_device_type(device_info("TP04")) == "438"
    assert get_device_type(device_info("999")) is None


def test_hushjet_has_a_name():
    assert "HushJet" in DEVICE_TYPE_NAMES[DEVICE_TYPE_HUSHJET]
    assert DEVICE_TYPE_NAMES["438"]


def test_hushjet_reads_state_without_oscillation_fields(hushjet):
    assert hushjet.is_on
    assert hushjet.speed == 4
    assert not hushjet.auto_mode
    assert not hushjet.oscillation
    assert hushjet.continuous_monitoring
    assert hushjet.hepa_filter_life == 93
    assert hushjet.carbon_filter_life == 88


def test_hushjet_rejects_oscillation(hushjet):
    with pytest.raises(NotImplementedError):
        hushjet.enable_oscillation()
    with pytest.raises(NotImplementedError):
        hushjet.disable_oscillation()
    assert published(hushjet) == []


def test_hushjet_sets_speed_and_leaves_auto_in_one_command(hushjet):
    hushjet.set_speed(7)
    assert published(hushjet) == [{"fpwr": "ON", "fnsp": "0007", "auto": "OFF"}]


def test_fan_entity_does_not_offer_oscillation(hushjet):
    entity = DysonHushJetEntity(hushjet, "Bedroom")
    assert not entity.supported_features & FanEntityFeature.OSCILLATE
    assert not entity.supported_features & FanEntityFeature.DIRECTION
    assert entity.supported_features & FanEntityFeature.SET_SPEED
    assert entity.supported_features & FanEntityFeature.PRESET_MODE


def test_fan_entity_sets_percentage_in_one_command(hushjet):
    DysonHushJetEntity(hushjet, "Bedroom").set_percentage(70)
    assert published(hushjet) == [{"fpwr": "ON", "fnsp": "0007", "auto": "OFF"}]


def test_fan_entity_turns_off_at_zero_percent(hushjet):
    DysonHushJetEntity(hushjet, "Bedroom").set_percentage(0)
    assert published(hushjet) == [{"fpwr": "OFF"}]


def test_sensors_are_particulates_and_filters(hushjet):
    entry = MagicMock(entry_id="entry", data={CONF_NAME: "Bedroom"})
    hass = MagicMock()
    hass.data = {
        DOMAIN: {
            DATA_DEVICES: {"entry": hushjet},
            DATA_COORDINATORS: {"entry": MagicMock()},
        }
    }
    added = []
    asyncio.run(sensor.async_setup_entry(hass, entry, added.extend))
    assert sorted(type(entity).__name__ for entity in added) == [
        "DysonCarbonFilterLifeSensor",
        "DysonHEPAFilterLifeSensor",
        "DysonPM10Sensor",
        "DysonPM25Sensor",
    ]


def test_sleep_timer_reads_the_product_state(hushjet):
    assert hushjet.sleep_timer == 0
    hushjet._handle_message(
        {
            "msg": "STATE-CHANGE",
            "product-state": {
                **{key: [value, value] for key, value in STATUS.items()},
                "sltm": ["OFF", "0015"],
            },
        }
    )
    assert hushjet.sleep_timer == 15


def test_sleep_timer_number_sets_and_clears(hushjet):
    entity = DysonSleepTimerNumber(hushjet, "Bedroom")
    entity.set_native_value(30.0)
    entity.set_native_value(0.0)
    assert published(hushjet) == [{"sltm": "0030"}, {"sltm": "OFF"}]
    assert entity.unique_id == f"{SERIAL}-sleep_timer"


def test_fan_running_follows_fnst(hushjet):
    entity = DysonFanRunningSensor(hushjet, "Bedroom")
    assert entity.is_on
    hushjet._status["fnst"] = "OFF"
    assert not entity.is_on


def test_hushjet_sets_up_timer_and_fan_running_platforms(hushjet):
    platforms = _async_get_platforms(hushjet)
    assert {"binary_sensor", "number"} <= set(platforms)
    assert "climate" not in platforms
