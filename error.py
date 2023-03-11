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
