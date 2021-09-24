import json, aiohttp
from dydx3.errors import DydxApiError, response_to_error
from dydx3.helpers.request_helpers import remove_nones


async def request(uri, method, session=None, headers=None, data_values={}):
    temp_session = None
    if session is None:
        temp_session = aiohttp.ClientSession()
        session = temp_session
    try:
        data = json.dumps(remove_nones(data_values))

        response = await send_request(
            session,
            uri,
            method,
            headers,
            data=data
        )
        if not str(response.status).startswith('2'):
            err = await response_to_error(response)
            raise err

        res = (await response.json()) if response.content else '{}'

    finally:
        # close temp session
        if temp_session:
            temp_session.close()

    return res


async def send_request(session, uri, method, headers=None, **kwargs):
    return await getattr(session, method)(uri, headers=headers, **kwargs)
