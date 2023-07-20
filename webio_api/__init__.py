""""API Library for WebIO devices"""

import aiohttp
import hashlib
import json
import logging
from typing import Any, Optional

from .const import (
    EP_CHECK_CONNECTION,
    EP_DEVICE_INFO,
    EP_SET_OUTPUT,
    KEY_LOGIN,
    KEY_PASSWORD,
    KEY_SERIAL_NUMBER,
    KEY_WEBIO_NAME,
    KEY_OUTPUT_COUNT,
    KEY_OUTPUTS,
    KEY_INDEX,
    KEY_STATUS,
    KEY_ANSWER,
    NOT_AUTHORIZED,
)

_LOGGER = logging.getLogger(__name__)
_LOGGER.setLevel(logging.INFO)


class AuthError(Exception):
    """Error to indicate there is invalid login/passowrd"""


class ApiClient:
    """Class used for communication with WebIO REST API"""

    def __init__(self, host: str, login: str, password: str):
        self._host = host
        self._login = login
        if password is None:
            self._password = None
        else:
            hash_object = hashlib.sha1(password.encode("utf-8"))
            self._password = hash_object.hexdigest().upper()

    async def check_connection(self) -> bool:
        response = await self._send_request(EP_CHECK_CONNECTION)
        return response == "restAPI" if response is not None else False

    async def get_info(self) -> dict[str, Any]:
        data = {KEY_LOGIN: self._login, KEY_PASSWORD: self._password}
        response = await self._send_request(EP_DEVICE_INFO, data)
        if response is None:
            return {}
        try:
            info = json.loads(response)
            return info
        except json.JSONDecodeError as e:
            _LOGGER.warning("get_info: received invalid json: %s", e.msg)
        return {}

    async def set_output(self, index: int, new_state: bool) -> bool:
        data = {
            KEY_LOGIN: self._login,
            KEY_PASSWORD: self._password,
            KEY_INDEX: index,
            KEY_STATUS: new_state,
        }
        response = await self._send_request(EP_SET_OUTPUT, data)
        _LOGGER.debug("set_output(%s, %s): %s", index, new_state, response)
        try:
            response_dict: dict = json.loads(response)
            return response_dict.get(KEY_ANSWER, "") == "OK"
        except json.JSONDecodeError as e:
            _LOGGER.warning("set_output: invalid json in response -> %s", e.msg)
        return False

    async def _send_request(
        self, ep: str, data: Optional[dict] = None
    ) -> Optional[dict]:
        async with aiohttp.ClientSession() as session:
            full_request = f"https://{self._host}/{ep}"
            data_json = json.dumps(data) if data is not None else None
            _LOGGER.debug("REST API endpoint: %s, data: %s", full_request, data_json)
            async with session.post(
                full_request, json=data, verify_ssl=False
            ) as response:
                response_text = await response.text()
                _LOGGER.debug(
                    "REST API http_code: %s, response: %s",
                    response.status,
                    response_text,
                )
                if response.status == 401 or response_text == NOT_AUTHORIZED:
                    raise AuthError
                if response.status != 200:
                    _LOGGER.error("Request error: http_code -> %s", response.status)
                    return None
                return response_text


class Output:
    """Class representing WebIO output"""

    def __init__(
        self,
        api_client: ApiClient,
        index: int,
        state: Optional[bool] = None,
    ):
        self._api_client: ApiClient = api_client
        self.index: int = index
        self.state: Optional[bool] = state
        self.available: bool = self.state is not None

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
        self.outputs: list[Output] = {}

    async def check_connection(self) -> bool:
        return await self._api_client.check_connection()

    async def refresh_device_info(self) -> bool:
        info = await self._api_client.get_info()
        try:
            serial: str = info[KEY_SERIAL_NUMBER]
            self._info[KEY_SERIAL_NUMBER] = serial.replace("-", "")
        except (KeyError, AttributeError):
            _LOGGER.warning("get_info: response has missing/invalid values")
            return False
        self._info[KEY_OUTPUT_COUNT] = 16
        if not self.outputs:
            self.outputs: list[Output] = {
                Output(self._api_client, i, False)
                for i in range(1, self.get_output_count() + 1)
            }
        return True

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
        return self._info.get(KEY_SERIAL_NUMBER)

    def get_output_count(self) -> int:
        if self._info is None:
            return 0
        return self._info.get(KEY_OUTPUT_COUNT, 0)

    def get_name(self) -> str:
        if self._info is None:
            return self._api_client._host
        name = self._info.get(KEY_WEBIO_NAME)
        return name if name is not None else self._api_client._host
