import aiohttp
import hashlib
import json
import logging
from typing import Optional, Any


from .const import (
    EP_CHECK_CONNECTION,
    EP_DEVICE_INFO,
    EP_SET_OUTPUT,
    EP_ARM_ZONE,
    EP_THERMOSTAT,
    EP_STATUS_SUBSCRIPTION,
    KEY_ABOVE,
    KEY_ACTION,
    KEY_ADDRESS,
    KEY_ANSWER,
    KEY_BELOW,
    KEY_INDEX,
    KEY_LOGIN,
    KEY_PASSWORD,
    KEY_PASSCODE,
    KEY_STATUS,
    KEY_SUBSCRIBE,
    KEY_TEMP_MIN,
    KEY_TEMP_MAX,
    NOT_AUTHORIZED,
    REQUEST_TIMEOUT,
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
        result = await self._send_regular_request(EP_SET_OUTPUT, data)
        _LOGGER.debug("set_output(%s, %s): %s", index, new_state, result)
        return result

    async def arm_zone(self, index: int, arm: bool, passcode: Optional[str]) -> bool:
        passcode_sha = ""
        if passcode:
            hash_object = hashlib.sha1(passcode.encode("utf-8"))
            passcode_sha = hash_object.hexdigest().upper()
        data = {
            KEY_LOGIN: self._login,
            KEY_PASSWORD: self._password,
            KEY_INDEX: f"{index}",
            KEY_STATUS: arm,
            KEY_PASSCODE: passcode_sha
        }
        result = await self._send_regular_request(EP_ARM_ZONE, data)
        _LOGGER.debug("arm_zone(%s, %s, [password]): %s", index, arm, result)
        return result

    async def set_hvac_mode(self, hvac_mode: str) -> bool:
        have_cooling = "cool" in hvac_mode
        have_heating = "heat" in hvac_mode
        data = {
            KEY_LOGIN: self._login,
            KEY_PASSWORD: self._password,
            KEY_ACTION: "set_hvac_mode",
            KEY_BELOW: have_heating,
            KEY_ABOVE: have_cooling,
        }
        result = await self._send_regular_request(EP_THERMOSTAT, data)
        _LOGGER.debug("set_hvac_mode(%s): %s", hvac_mode, result)
        return result

    async def set_temperature(self, temp_min: int, temp_max: int) -> bool:
        data = {
            KEY_LOGIN: self._login,
            KEY_PASSWORD: self._password,
            KEY_ACTION: "set_temp_range",
            KEY_TEMP_MIN: temp_min,
            KEY_TEMP_MAX: temp_max,
        }
        result = await self._send_regular_request(EP_THERMOSTAT, data)
        _LOGGER.debug("set_temperature(%s, %s): %s", temp_min, temp_max, result)
        return result

    async def status_subscription(self, address: str, subscribe: bool) -> bool:
        data = {
            KEY_LOGIN: self._login,
            KEY_PASSWORD: self._password,
            KEY_ADDRESS: address,
            KEY_SUBSCRIBE: subscribe,
        }
        result = await self._send_regular_request(EP_STATUS_SUBSCRIPTION, data)
        _LOGGER.debug("status_subscription(%s, %s): %s", address, subscribe, result)
        return result

    async def _send_regular_request(self, ep: str, data: dict) -> bool:
        response = await self._send_request(ep, data)
        if response is None:
            return False
        try:
            response_dict: dict = json.loads(response)
            return response_dict.get(KEY_ANSWER, "") == "OK"
        except json.JSONDecodeError as e:
            _LOGGER.warning("regular_request: invalid json in response -> %s", e.msg)
        return False

    async def _send_request(
        self, ep: str, data: Optional[dict] = None
    ) -> Optional[str]:
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=REQUEST_TIMEOUT)) as session:
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
