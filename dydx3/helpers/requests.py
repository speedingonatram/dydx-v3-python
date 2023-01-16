import json
import aiohttp
from dydx3.errors import DydxApiError
from dydx3.helpers.request_helpers import remove_nones


class Response(object):

    def __init__(self, data={}, headers=None):
        self.data = data
        self.headers = headers


async def request(uri, method, session=None, headers=None, data_values={}, api_timeout=None):
    """_summary_

    Args:
        uri (_type_): _description_
        method (_type_): _description_
        session (_type_, optional): _description_. Defaults to None.
        headers (_type_, optional): _description_. Defaults to None.
        data_values (dict, optional): _description_. Defaults to {}.
        api_timeout (_type_, optional): _description_. Defaults to None.

    Raises:
        err: _description_

    Returns:
        _type_: _description_
    """
    temp_session = None
    if session is None:
        temp_session = aiohttp.ClientSession()
        temp_session.headers.update({
            'Accept': 'application/json',
            'Content-Type': 'application/json',
            'User-Agent': 'dydx/python',
        })
        session = temp_session
    try:

        response = await send_request(
            session,
            uri,
            method,
            headers,
            data=json.dumps(
                remove_nones(data_values)
            ),
            timeout=api_timeout
        )

        if not str(response.status).startswith('2'):
            err = await response_to_error(response)
            raise err

        if response.content:
            return Response(await response.json(), response.headers).data

        return Response('{}', response.headers).data

    finally:
        # close temp session
        if temp_session:
            temp_session.close()


async def send_request(session, uri, method, headers=None, **kwargs):
    """_summary_

    Args:
        session (_type_): _description_
        uri (_type_): _description_
        method (_type_): _description_
        headers (_type_, optional): _description_. Defaults to None.

    Returns:
        _type_: _description_
    """
    return await getattr(session, method)(uri, headers=headers, **kwargs)


async def response_to_error(response):
    """_summary_

    Args:
        response (_type_): _description_

    Returns:
        _type_: _description_
    """
    status = response.status
    try:
        msg = await response.json(content_type=None)  # do not check content_type
    except ValueError:
        msg = await response.text()

    return DydxApiError(response, status, msg)
