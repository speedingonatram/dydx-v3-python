class DydxError(Exception):
    """Base error class for all exceptions raised in this library.
    Will never be raised naked; more specific subclasses of this exception will
    be raised when appropriate."""


class DydxApiError(DydxError):

    def __init__(self, response, status, msg):
        self.response = response
        self.status = status
        self.msg = msg
        self.request_info = getattr(response, 'request_info', None)

    def __str__(self):
        return self.__repr__()

    def __repr__(self):
        return 'DydxApiError(status={}, response={})'.format(
            self.status,
            self.msg,
        )


class TransactionReverted(DydxError):

    def __init__(self, tx_receipt):
        self.tx_receipt = tx_receipt


async def response_to_error(response):
    status = response.status
    try:
        msg = await response.json(content_type=None)  # do not check content_type
    except ValueError:
        msg = await response.text()
    return DydxApiError(response, status, msg)