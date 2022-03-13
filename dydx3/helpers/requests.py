import json, aiohttp
from dydx3.errors import DydxApiError
from dydx3.helpers.request_helpers import remove_nones


class Response(object):
    def __init__(self, data={}, headers=None):
        self.data = data
        self.headers = headers


async def request(uri, method, session=None, headers=None, data_values={}):
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

        response = send_request(
            uri,
            method,
            headers,
            data=json.dumps(
                remove_nones(data_values)
            )
        )

        if not str(response.status_code).startswith('2'):
            raise DydxApiError(response)

        if response.content:
            return Response(response.json(), response.headers)
        else:
            return Response('{}', response.headers)

    finally:
        # close temp session
        if temp_session:
            temp_session.close()


async def send_request(session, uri, method, headers=None, **kwargs):
    return await getattr(session, method)(uri, headers=headers, **kwargs)
