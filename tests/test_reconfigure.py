"""Tests for reconfiguring how a device is reached."""

import asyncio
import threading
from unittest.mock import AsyncMock, MagicMock, patch

from homeassistant.const import CONF_HOST, CONF_NAME

from custom_components.dyson_local import async_unload_entry
from custom_components.dyson_local.cloud.const import CONF_AUTH, CONF_REGION
from custom_components.dyson_local.config_flow import (
    CannotFind,
    DysonLocalConfigFlow,
)
from custom_components.dyson_local.const import (
    CONF_CREDENTIAL,
    CONF_DEVICE_TYPE,
    CONF_SERIAL,
    DATA_COORDINATORS,
    DATA_DEVICES,
    DATA_DISCOVERY,
    DATA_DISCOVERY_ENTRIES,
    DOMAIN,
)

SERIAL = "M4P-SG-ABC1234A"
DEVICE_DATA = {
    CONF_SERIAL: SERIAL,
    CONF_CREDENTIAL: "credential",
    CONF_DEVICE_TYPE: "897",
    CONF_NAME: "Bedroom",
    CONF_HOST: "",
}


def flow_for(entry_data: dict) -> DysonLocalConfigFlow:
    """Return a reconfigure flow for an entry with the given data."""
    flow = DysonLocalConfigFlow()
    flow.hass = MagicMock()
    flow.hass.async_add_executor_job = AsyncMock(
        side_effect=lambda func, *args: func(*args)
    )
    flow.flow_id = "flow"
    flow.handler = DOMAIN
    flow.context = {}
    entry = MagicMock(entry_id="entry", data=entry_data)
    flow._get_reconfigure_entry = MagicMock(return_value=entry)
    flow.async_update_reload_and_abort = MagicMock(
        return_value={"type": "abort", "reason": "reconfigure_successful"}
    )
    return flow


def run(coro):
    return asyncio.run(coro)


def test_account_entry_has_nothing_to_reconfigure():
    flow = flow_for({CONF_REGION: "GB", CONF_AUTH: {}})
    result = run(flow.async_step_reconfigure())
    assert result["type"] == "abort"
    assert result["reason"] == "reconfigure_account"


def test_form_suggests_current_host():
    flow = flow_for({**DEVICE_DATA, CONF_HOST: "192.0.2.10"})
    result = run(flow.async_step_reconfigure())
    assert result["step_id"] == "reconfigure"
    (key,) = result["data_schema"].schema
    assert key.description == {"suggested_value": "192.0.2.10"}


def test_new_host_is_checked_then_saved():
    flow = flow_for(DEVICE_DATA)
    flow._async_try_connect = AsyncMock()
    run(flow.async_step_reconfigure({CONF_HOST: " 192.0.2.10 "}))
    flow._async_try_connect.assert_awaited_once_with(
        SERIAL, "credential", "897", "192.0.2.10"
    )
    flow.async_update_reload_and_abort.assert_called_once_with(
        flow._get_reconfigure_entry(), data_updates={CONF_HOST: "192.0.2.10"}
    )


def test_blank_host_switches_to_discovery():
    flow = flow_for({**DEVICE_DATA, CONF_HOST: "192.0.2.10"})
    flow._async_try_connect = AsyncMock()
    run(flow.async_step_reconfigure({CONF_HOST: ""}))
    flow._async_try_connect.assert_awaited_once_with(
        SERIAL, "credential", "897", None
    )
    flow.async_update_reload_and_abort.assert_called_once_with(
        flow._get_reconfigure_entry(), data_updates={CONF_HOST: None}
    )


def test_unreachable_device_keeps_the_old_host():
    flow = flow_for(DEVICE_DATA)
    flow._async_try_connect = AsyncMock(side_effect=CannotFind)
    result = run(flow.async_step_reconfigure({CONF_HOST: ""}))
    assert result["errors"] == {"base": "cannot_find"}
    flow.async_update_reload_and_abort.assert_not_called()


def test_connection_check_does_not_hold_the_connection():
    flow = flow_for(DEVICE_DATA)
    device = MagicMock()
    with patch(
        "custom_components.dyson_local.config_flow.get_device", return_value=device
    ):
        run(flow._async_try_connect(SERIAL, "credential", "897", "192.0.2.10"))
    device.connect.assert_called_once_with("192.0.2.10")
    device.disconnect.assert_called_once()


def test_unload_stops_waiting_for_an_undiscovered_device():
    discovery = MagicMock()
    discovery._lock = threading.Lock()
    discovery._discovered = {}
    discovery._registered = {SERIAL: MagicMock()}
    hass = MagicMock()
    hass.async_add_executor_job = AsyncMock(
        side_effect=lambda func, *args: func(*args)
    )
    hass.data = {
        DOMAIN: {
            DATA_DEVICES: {},
            DATA_COORDINATORS: {},
            DATA_DISCOVERY: discovery,
            DATA_DISCOVERY_ENTRIES: {"entry"},
            "discovery_count": 1,
        }
    }
    # Reconfigure saves the new host before the entry is unloaded.
    entry = MagicMock(entry_id="entry", data={**DEVICE_DATA, CONF_HOST: "192.0.2.10"})

    assert run(async_unload_entry(hass, entry))

    assert SERIAL not in discovery._registered
    assert hass.data[DOMAIN][DATA_DISCOVERY_ENTRIES] == set()
    assert hass.data[DOMAIN]["discovery_count"] == 0
    discovery.stop_discovery.assert_called_once()
    assert hass.data[DOMAIN][DATA_DISCOVERY] is None
