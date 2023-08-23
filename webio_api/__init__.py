""""API Library for WebIO devices"""

import logging
from typing import Any, Optional

from .api_client import ApiClient
from .const import (
    KEY_DEVICE_NAME,
    KEY_DEVICE_SERIAL,
    KEY_INDEX,
    KEY_OUTPUT_COUNT,
    KEY_OUTPUTS,
    KEY_STATUS,
    KEY_WEBIO_NAME,
    KEY_WEBIO_SERIAL,
)

_LOGGER = logging.getLogger(__name__)
_LOGGER.setLevel(logging.INFO)


class Output:
    """Class representing WebIO output"""

    def __init__(
        self,
        api_client: ApiClient,
        index: int,
        serial: str,
        state: Optional[bool] = None,
    ):
        self._api_client: ApiClient = api_client
        self.index: int = index
        self.state: Optional[bool] = state
        self.available: bool = self.state is not None
        self.webio_serial = serial

    async def turn_on(self) -> None:
        await self._api_client.set_output(self.index, True)

    async def turn_off(self) -> None:
        await self._api_client.set_output(self.index, False)

    def __str__(self) -> str:
        return f"Output[index: {self.index}, state: {self.state}, available: {self.available}]"


class WebioAPI:
    def __init__(self, host: str, login: str, password: str):
        self._api_client = ApiClient(host, login, password)
        self._info: dict[str, Any] = {}
        self.outputs: list[Output] = []

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
        self._info[KEY_OUTPUT_COUNT] = 16
        if not self.outputs:
            self.outputs: list[Output] = [
                Output(self._api_client, i, self._info[KEY_DEVICE_SERIAL], False)
                for i in range(1, self.get_output_count() + 1)
            ]
        return True

    async def status_subscription(self, address: str, subscribe: bool) -> bool:
        return await self._api_client.status_subscription(address, subscribe)

    def update_device_status(self, new_status: dict[str, Any]) -> None:
        webio_outputs: Optional[list[dict[str, Any]]] = new_status.get(KEY_OUTPUTS)
        if webio_outputs is None:
            _LOGGER.error("No outputs data in status update")
        else:
            self._update_outputs(webio_outputs)

    def _update_outputs(self, outputs: list[dict[str, Any]]) -> None:
        output_states: list[Optional[bool]] = [None for i in range(0, len(outputs) + 1)]
        for out in outputs:
            try:
                index: int = out[KEY_INDEX]
                state_str = out[KEY_STATUS]
                state: Optional[bool] = None
                if state_str == "true":
                    state = True
                elif state_str == "false":
                    state = False
            except KeyError as e:
                _LOGGER.warning("Output dictionary missing key: %s", e)
                continue
            output_states[index] = state
        _LOGGER.debug("Output states for update: %s", output_states)
        for out in self.outputs:
            if not isinstance(out, Output):
                _LOGGER.error(
                    "Cannot update status: incorrect type: %s != %s",
                    type(Output),
                    type(out),
                )
                continue
            applicable_state = output_states[out.index]
            out.available = applicable_state is not None
            out.state = False if applicable_state is None else applicable_state

    def get_serial_number(self) -> Optional[str]:
        if self._info is None:
            return None
        return self._info.get(KEY_DEVICE_SERIAL)

    def get_output_count(self) -> int:
        if self._info is None:
            return 0
        return self._info.get(KEY_OUTPUT_COUNT, 0)

    def get_name(self) -> str:
        if self._info is None:
            return self._api_client._host
        name = self._info.get(KEY_DEVICE_NAME)
        return name if name is not None else self._api_client._host
