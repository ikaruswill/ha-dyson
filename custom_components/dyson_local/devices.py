"""Devices this integration supports that libdyson-neon does not know about.

libdyson-neon is unmaintained, so new models are added here instead of
upstream. Everything that creates a device or maps a cloud product type
goes through this module so the integration sees one combined list.
"""

from typing import Optional

from libdyson import DEVICE_TYPE_NAMES as LIBDYSON_DEVICE_TYPE_NAMES
from libdyson import get_device as libdyson_get_device
from libdyson.cloud import DysonDeviceInfo
from libdyson.dyson_device import DysonDevice
from libdyson.dyson_pure_cool import DysonPureCoolBase

# Cloud ProductType and MQTT topic prefix of the HushJet Purifier Compact.
DEVICE_TYPE_HUSHJET = "897"


class DysonHushJet(DysonPureCoolBase):
    """Dyson HushJet Purifier Compact (HJ10).

    Speaks the Pure Cool protocol for power, speed, auto, night mode,
    continuous monitoring, sleep timer, filter life and particulate matter,
    but has no oscillation or airflow direction. The state never carries the
    oscillation fields, so this deliberately does not subclass DysonPureCool,
    whose angle properties would raise on the missing values.
    """

    @property
    def oscillation(self) -> bool:
        """Return oscillation status; the HushJet cannot oscillate."""
        return False

    def enable_oscillation(self) -> None:
        """Reject oscillation; the HushJet cannot oscillate."""
        raise NotImplementedError("HushJet has no oscillation")

    def disable_oscillation(self) -> None:
        """Reject oscillation; the HushJet cannot oscillate."""
        raise NotImplementedError("HushJet has no oscillation")

    @property
    def sleep_timer(self) -> int:
        """Return the sleep timer in minutes, or 0 when it is off.

        Read from the product state, which the HushJet pushes as soon as the
        timer changes, rather than from the polled environmental data.
        """
        value = self._get_field_value(self._status, "sltm")
        if value is None or value == "OFF":
            return 0
        return int(value)

    def _set_speed(self, speed: int) -> None:
        # Leave auto mode in the same message. A separate auto=OFF command
        # after the speed resets the speed on the HushJet.
        self._set_configuration(fpwr="ON", fnsp=f"{speed:04d}", auto="OFF")


_DEVICE_CLASSES = {
    DEVICE_TYPE_HUSHJET: DysonHushJet,
}

DEVICE_TYPE_NAMES = {
    **LIBDYSON_DEVICE_TYPE_NAMES,
    DEVICE_TYPE_HUSHJET: "HushJet Purifier Compact (HJ10)",
}


def get_device(serial: str, credential: str, device_type: str) -> Optional[DysonDevice]:
    """Create a device, preferring this integration's own device classes."""
    device_class = _DEVICE_CLASSES.get(device_type)
    if device_class is not None:
        return device_class(serial, credential, device_type)
    return libdyson_get_device(serial, credential, device_type)


def get_device_type(device_info: DysonDeviceInfo) -> Optional[str]:
    """Map a MyDyson cloud device to a device type."""
    if device_info.product_type in _DEVICE_CLASSES:
        return device_info.product_type
    return device_info.get_device_type()
