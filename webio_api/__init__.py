""""API Library for WebIO devices"""

import logging
import time
from typing import Any, Optional

from .api_client import ApiClient
from .const import (
    KEY_DEVICE_NAME,
    KEY_DEVICE_SERIAL,
    KEY_DEVICE_TEMP_ENV,
    KEY_INDEX,
    KEY_NAME,
    KEY_OUTPUTS,
    KEY_INPUTS,
    KEY_STATUS,
    KEY_WEBIO_NAME,
    KEY_WEBIO_SERIAL,
    KEY_ZONES,
    KEY_PASS_TYPE,
    KEY_THERMOSTAT,
    KEY_RANGE_FROM,
    KEY_RANGE_TO,
    KEY_IDLE_OUTPUT,
    KEY_BELOW_CHECK,
    KEY_ABOVE_CHECK,
    KEY_TEMP_ENV,
)

_LOGGER = logging.getLogger(__name__)
_LOGGER.setLevel(logging.INFO)


class BaseEntity:
    def __init__(self, serial: str) -> None:
        self.last_update: float = time.time()
        self.available: Optional[bool] = True
        self.webio_serial: str = serial


class Output(BaseEntity):
    """Class representing WebIO output"""

    def __init__(
        self,
        serial: str,
        api_client: ApiClient,
        index: int,
        state: Optional[bool] = None,
    ):
        super().__init__(serial)
        self._api_client: ApiClient = api_client
        self.index: int = index
        self.state: Optional[bool] = state

    async def turn_on(self) -> None:
        await self._api_client.set_output(self.index, True)

    async def turn_off(self) -> None:
        await self._api_client.set_output(self.index, False)

    def __str__(self) -> str:
        return f"Output[index: {self.index}, state: {self.state}, available: {self.available}]"


class Input(BaseEntity):
    """Class representing WebIO input"""

    def __init__(
        self,
        serial: str,
        index: int,
        state: Optional[str] = None,
    ):
        super().__init__(serial)
        self.index: int = index
        self.state: Optional[str] = state
        self.available = self.state is not None

    def __str__(self) -> str:
        return f"Input[index: {self.index}, state: {self.state}, available: {self.available}]"


class Zone(BaseEntity):
    """Class representing WebIO zone"""

    def __init__(
        self,
        serial: str,
        api_client: ApiClient,
        index: int,
        state: Optional[str] = None,
    ):
        super().__init__(serial)
        self._api_client: ApiClient = api_client
        self.index: int = index
        self.name: Optional[str] = None
        self.state: Optional[str] = state
        self.pass_type: int = 2
        self.available: bool = self.state is not None

    async def arm(self, passcode: Optional[str]) -> None:
        await self._api_client.arm_zone(self.index, True, passcode)

    async def disarm(self, passcode: Optional[str]) -> None:
        await self._api_client.arm_zone(self.index, False, passcode)

    def __str__(self) -> str:
        return (
            f"Zone[name: {self.name}, state: {self.state}, available: {self.available}]"
        )


class TempSensor(BaseEntity):
    """Class representing WebIO temperature sensor"""

    def __init__(self, serial: str, value: Optional[int]):
        super().__init__(serial)
        self.value = value
        self.available = self.value is not None

    def __str__(self) -> str:
        return f"TempSensor[value: {self.value}, available: {self.available}]"


class Thermostat(BaseEntity):
    """Class representing WebIO climate entity"""

    def __init__(
        self,
        serial: str,
        api_client: ApiClient,
    ) -> None:
        super().__init__(serial)
        self._api_client: ApiClient = api_client
        self.name: Optional[str]
        self.temp_target_min: Optional[int]
        self.temp_target_max: Optional[int]
        self.enabled_below_output: bool
        self.enabled_inrange_output: bool
        self.enabled_above_output: bool
        self.current_temp: Optional[int]
        self.available = False

    async def set_hvac_mode(self, hvac_mode: str) -> None:
        await self._api_client.set_hvac_mode(hvac_mode)

    async def set_temperature(self, temp_min: int, temp_max: int) -> None:
        await self._api_client.set_temperature(temp_min, temp_max)


class WebioAPI:
    def __init__(self, host: str, login: str, password: str):
        self._api_client = ApiClient(host, login, password)
        self._info: dict[str, Any] = {}
        self.outputs: list[Output] = []
        self.inputs: list[Input] = []
        self.zones: list[Zone] = []
        self.temp_sensor: Optional[TempSensor] = None
        self.thermostat: Optional[Thermostat] = None

    async def check_connection(self) -> bool:
        return await self._api_client.check_connection()

    async def refresh_device_info(self) -> bool:
        info = await self._api_client.get_info()
        try:
            serial: str = info[KEY_WEBIO_SERIAL]
            self._info[KEY_DEVICE_SERIAL] = serial.replace("-", "")
            self._info[KEY_DEVICE_NAME] = info[KEY_WEBIO_NAME]
        except (KeyError, AttributeError):
            _LOGGER.warning("get_info: response has missing/invalid values")
            return False
        self.temp_sensor = TempSensor(self._info[KEY_DEVICE_SERIAL], None)
        self.thermostat = Thermostat(self._info[KEY_DEVICE_SERIAL], self._api_client)
        return True

    async def status_subscription(self, address: str, subscribe: bool) -> bool:
        return await self._api_client.status_subscription(address, subscribe)

    def update_device_status(self, new_status: dict[str, Any]) -> dict[str, list]:
        webio_outputs: Optional[list[dict[str, Any]]] = new_status.get(KEY_OUTPUTS)
        new_outputs: list[Output] = []
        if webio_outputs is None:
            _LOGGER.error("No outputs data in status update")
        else:
            new_outputs = self._update_outputs(webio_outputs)

        webio_inputs: Optional[list[dict[str, Any]]] = new_status.get(KEY_INPUTS)
        new_inputs: list[Input] = []
        if webio_inputs is None:
            _LOGGER.error("No inputs data in status update")
        else:
            new_inputs = self._update_inputs(webio_inputs)

        webio_zones: Optional[list[dict[str, Any]]] = new_status.get(KEY_ZONES)
        new_zones: list[Zone] = []
        if webio_zones is None:
            _LOGGER.error("No zones data in status update")
        else:
            new_zones = self._update_zones(webio_zones)

        self._update_temp_sensor(new_status.get(KEY_DEVICE_TEMP_ENV, "N/A"))

        webio_thermostat: dict[str, Any] = new_status.get(KEY_THERMOSTAT, {})
        self._update_thermostat(webio_thermostat)

        return {
            KEY_OUTPUTS: new_outputs,
            KEY_INPUTS: new_inputs,
            KEY_ZONES: new_zones,
        }

    def get_serial_number(self) -> Optional[str]:
        if self._info is None:
            return None
        return self._info.get(KEY_DEVICE_SERIAL)

    def get_name(self) -> str:
        if self._info is None:
            return self._api_client._host
        name = self._info.get(KEY_DEVICE_NAME)
        return name if name is not None else self._api_client._host

    @staticmethod
    def get_int_or_none(int_str: Optional[str]) -> Optional[int]:
        try:
            return int(int_str) if int_str else None
        except ValueError:
            return None

    def _update_outputs(self, outputs: list[dict[str, Any]]) -> list[Output]:
        current_indexes: list[int] = []
        new_outputs: list[Output] = []
        # preemptively set unavailable to None (for entity removal) for all inputs then change it to available
        for out in self.outputs:
            out.state = None
            out.available = None

        for o in outputs:
            index: int = o.get(KEY_INDEX, -1)
            if index < 0:
                _LOGGER.error("WebIO output has no index")
                continue
            current_indexes.append(index)
            webio_output: Optional[Output] = self._get_output(index)
            if webio_output is None:
                webio_output = Output(
                    self._info[KEY_DEVICE_SERIAL], self._api_client, index
                )
                self.outputs.append(webio_output)
                new_outputs.append(webio_output)
            webio_output.last_update = time.time()
            webio_output.state = self._convert_outputs_status(o.get(KEY_STATUS))
            webio_output.available = webio_output.state is not None
        if len(current_indexes) > 0:
            self.outputs = [
                webio_output
                for webio_output in self.outputs
                if webio_output.index in current_indexes
            ]
        return new_outputs

    def _update_inputs(self, inputs: list[dict[str, Any]]) -> list[Input]:
        current_indexes: list[int] = []
        new_inputs: list[Input] = []
        # preemptively set unavailable for all then change it to available
        for webio_input in self.inputs:
            webio_input.state = None
            webio_input.available = False

        for i in inputs:
            index: int = i.get(KEY_INDEX, -1)
            if index < 0:
                _LOGGER.error("WebIO input has no index")
                continue
            current_indexes.append(index)
            webio_input: Optional[Input] = self._get_input(index)
            if webio_input is None:
                webio_input = Input(
                    self._info[KEY_DEVICE_SERIAL], index
                )
                self.inputs.append(webio_input)
                new_inputs.append(webio_input)
            webio_input.last_update = time.time()
            webio_input.state = i.get(KEY_STATUS)
            webio_input.available = webio_input.state is not None
        if len(current_indexes) > 0:
            self.inputs = [
                webio_input
                for webio_input in self.inputs
                if webio_input.index in current_indexes
            ]
        return new_inputs

    def _update_zones(self, zones: list[dict[str, Any]]) -> list[Zone]:
        current_indexes: list[int] = []
        new_zones: list[Zone] = []
        # preemptively set unavailable for all zones then change it to available
        for zone in self.zones:
            zone.state = None
            zone.available = False

        for z in zones:
            index: int = z.get(KEY_INDEX, -1)
            if index < 0:
                _LOGGER.error("WebIO zone has no index")
                continue
            current_indexes.append(index)
            name: Optional[str] = z.get(KEY_NAME)
            state: Optional[str] = z.get(KEY_STATUS)
            webio_zone: Optional[Zone] = self._get_zone(index)
            if webio_zone is None:
                webio_zone = Zone(
                    self._info[KEY_DEVICE_SERIAL], self._api_client, index
                )
                self.zones.append(webio_zone)
                new_zones.append(webio_zone)
            webio_zone.last_update = time.time()
            webio_zone.name = name
            webio_zone.state = self._convert_zone_status(state)
            webio_zone.available = webio_zone.state is not None
            webio_zone.pass_type = z.get(KEY_PASS_TYPE, 2)
        # delete zones with old indexes - they are already set to unavailable
        if len(current_indexes) > 0:
            self.zones = [zone for zone in self.zones if zone.index in current_indexes]
        return new_zones

    def _update_temp_sensor(self, temp_value: str) -> None:
        try:
            new_value = None if temp_value == "N/A" else int(temp_value)
        except ValueError:
            new_value = None
        if self.temp_sensor is None:
            _LOGGER.error("TempSensor is None, cannot update status")
            return
        self.temp_sensor.last_update = time.time()
        self.temp_sensor.value = new_value
        self.temp_sensor.available = self.temp_sensor.value is not None

    def _update_thermostat(self, thermostat: dict[str, Any]) -> None:
        if self.thermostat is None:
            _LOGGER.warning("Cannot update Thermostat status. Thermostat is None")
            return
        if len(thermostat) <= 6:
            self.thermostat.available = False
            return
        self.thermostat.name = thermostat.get(KEY_NAME)
        self.thermostat.temp_target_min = WebioAPI.get_int_or_none(
            thermostat.get(KEY_RANGE_FROM)
        )
        self.thermostat.temp_target_max = WebioAPI.get_int_or_none(
            thermostat.get(KEY_RANGE_TO)
        )
        self.thermostat.enabled_below_output = (
            WebioAPI.get_int_or_none(thermostat.get(KEY_BELOW_CHECK)) == 1
        )
        self.thermostat.enabled_inrange_output = (
            WebioAPI.get_int_or_none(thermostat.get(KEY_IDLE_OUTPUT)) is not None
        )
        self.thermostat.enabled_above_output = (
            WebioAPI.get_int_or_none(thermostat.get(KEY_ABOVE_CHECK)) == 1
        )
        self.thermostat.current_temp = WebioAPI.get_int_or_none(
            thermostat.get(KEY_TEMP_ENV)
        )
        self.thermostat.last_update = time.time()
        self.thermostat.available = True

    def _get_output(self, index: int) -> Optional[Output]:
        for o in self.outputs:
            if o.index == index:
                return o
        return None

    def _convert_outputs_status(self, output_status: Optional[str]) -> Optional[bool]:
        if output_status is None:
            return None
        if output_status == "true":
            return True
        if output_status == "false":
            return False
        return None

    def _get_input(self, index: int) -> Optional[Input]:
        for i in self.inputs:
            if i.index == index:
                return i
        return None

    def _get_zone(self, index: int) -> Optional[Zone]:
        for z in self.zones:
            if z.index == index:
                return z
        return None

    def _convert_zone_status(self, zone_status: Optional[str]) -> Optional[str]:
        if zone_status is None:
            return None
        if zone_status == "alarm":
            return "triggered"
        if zone_status == "armed":
            return "armed_away"
        if zone_status == "disarmed":
            return "disarmed"
        return None
