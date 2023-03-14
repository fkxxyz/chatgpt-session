import http


class ChatGPTSessionError(Exception):
    HttpStatus: int = 0

    def __init__(self, *args, **kwargs):
        pass


class AlreadyExistsError(ChatGPTSessionError):
    HttpStatus = http.HTTPStatus.CONFLICT

    def __init__(self, *args, **kwargs):
        pass


class NotFoundError(ChatGPTSessionError):
    HttpStatus = http.HTTPStatus.NOT_FOUND

    def __init__(self, *args, **kwargs):
        pass


class InvalidParamError(ChatGPTSessionError):
    HttpStatus = http.HTTPStatus.BAD_REQUEST

    def __init__(self, *args, **kwargs):
        pass


class InternalError(ChatGPTSessionError):
    HttpStatus = http.HTTPStatus.INTERNAL_SERVER_ERROR

    def __init__(self, *args, **kwargs):
        pass


class ServerIsBusy(ChatGPTSessionError):
    HttpStatus = http.HTTPStatus.SERVICE_UNAVAILABLE

    def __init__(self, *args, **kwargs):
        pass


class Unauthorized(ChatGPTSessionError):
    HttpStatus = http.HTTPStatus.UNAUTHORIZED

    def __init__(self, *args, **kwargs):
        pass


class NoResource(ChatGPTSessionError):
    HttpStatus = http.HTTPStatus.PAYMENT_REQUIRED

    def __init__(self, *args, **kwargs):
        pass


class NotImplementedError1(ChatGPTSessionError):
    HttpStatus = http.HTTPStatus.NOT_IMPLEMENTED

    def __init__(self, *args, **kwargs):
        pass
