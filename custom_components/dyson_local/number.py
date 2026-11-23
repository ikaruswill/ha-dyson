"""Number platform for dyson."""

from typing import Callable

from homeassistant.components.number import NumberEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_NAME, UnitOfTime
from homeassistant.core import HomeAssistant

from . import DysonEntity
from .const import DATA_DEVICES, DOMAIN
from .devices import DysonHushJet


async def async_setup_entry(
    hass: HomeAssistant, config_entry: ConfigEntry, async_add_entities: Callable
) -> None:
    """Set up Dyson numbers from a config entry."""
    device = hass.data[DOMAIN][DATA_DEVICES][config_entry.entry_id]
    name = config_entry.data[CONF_NAME]
    entities = []
    if isinstance(device, DysonHushJet):
        entities.append(DysonSleepTimerNumber(device, name))
    async_add_entities(entities)


class DysonSleepTimerNumber(DysonEntity, NumberEntity):
    """Minutes until the device turns itself off; 0 turns the timer off."""

    _attr_icon = "mdi:timer-outline"
    _attr_native_min_value = 0
    _attr_native_max_value = 540
    _attr_native_step = 15
    _attr_native_unit_of_measurement = UnitOfTime.MINUTES

    @property
    def sub_name(self) -> str:
        """Return the name of the entity."""
        return "Sleep Timer"

    @property
    def sub_unique_id(self) -> str:
        """Return the entity sub unique id."""
        return "sleep_timer"

    @property
    def native_value(self) -> int:
        """Return the minutes left on the timer."""
        return self._device.sleep_timer

    def set_native_value(self, value: float) -> None:
        """Start the timer, or turn it off at 0."""
        minutes = int(value)
        if minutes == 0:
            self._device.disable_sleep_timer()
        else:
            self._device.set_sleep_timer(minutes)
