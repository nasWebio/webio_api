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
        return {KEY_OUTPUTS: new_outputs}

    def _update_outputs(self, outputs: list[dict[str, Any]]) -> list[Output]:
        current_indexes: list[int] = []
        new_outputs: list[Output] = []
        # preemptively set unavailable for all inputs then change it to available
        for out in self.outputs:
            out.state = None
            out.available = False

        for o in outputs:
            index: int = o.get(KEY_INDEX, -1)
            if index < 0:
                _LOGGER.error("WebIO output has no index")
                continue
            current_indexes.append(index)
            webio_output: Optional[Output] = self._get_output(index)
            if webio_output is None:
                webio_output = Output(
                    self._api_client, index, self._info[KEY_DEVICE_SERIAL]
                )
                self.outputs.append(webio_output)
                new_outputs.append(webio_output)
            webio_output.state = self._convert_outputs_status(o.get(KEY_STATUS))
            webio_output.available = webio_output.state is not None
        if len(current_indexes) > 0:
            self.outputs = [
                webio_output
                for webio_output in self.outputs
                if webio_output.index in current_indexes
            ]
        return new_outputs

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
