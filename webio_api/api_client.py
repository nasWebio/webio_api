import aiohttp
import hashlib
import json
import logging
from typing import Optional, Any


from .const import (
    EP_CHECK_CONNECTION,
    EP_DEVICE_INFO,
    EP_SET_OUTPUT,
    EP_STATUS_SUBSCRIPTION,
    KEY_ADDRESS,
    KEY_ANSWER,
    KEY_INDEX,
    KEY_LOGIN,
    KEY_PASSWORD,
    KEY_STATUS,
    KEY_SUBSCRIBE,
    NOT_AUTHORIZED,
)

_LOGGER = logging.getLogger(__name__)


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
        if response is None:
            return False
        try:
            response_dict: dict = json.loads(response)
            return response_dict.get(KEY_ANSWER, "") == "OK"
        except json.JSONDecodeError as e:
            _LOGGER.warning("set_output: invalid json in response -> %s", e.msg)
        return False

    async def status_subscription(self, address: str, subscribe: bool) -> bool:
        data = {
            KEY_LOGIN: self._login,
            KEY_PASSWORD: self._password,
            KEY_ADDRESS: address,
            KEY_SUBSCRIBE: subscribe,
        }
        response = await self._send_request(EP_STATUS_SUBSCRIPTION, data)
        _LOGGER.debug("status_subscription(%s, %s): %s", address, subscribe, response)
        if response is None:
            return False
        try:
            response_dict: dict = json.loads(response)
            return response_dict.get(KEY_ANSWER, "") == "OK"
        except json.JSONDecodeError as e:
            _LOGGER.warning("set_output: invalid json in response -> %s", e.msg)
        return False

    async def _send_request(
        self, ep: str, data: Optional[dict] = None
    ) -> Optional[str]:
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
