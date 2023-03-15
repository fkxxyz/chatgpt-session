import http
from dataclasses import asdict

import flask

import error
from server import app
from server.common import globalObject
from session.session import Session


@app.route('/api/ping')
def handle_api():
    return 'hello fkxxyz!'


@app.route('/api/list')
def handle_list():
    try:
        sessions = globalObject.session_manager.list()
    except error.ChatGPTSessionError as e:
        return flask.make_response(str(e), e.HttpStatus)

    result = []
    for s in sessions:
        result.append(s.asdict())
    return flask.jsonify(result)


@app.route('/api/create', methods=['PUT'])
def handle_create():
    id_ = flask.request.args.get('id')
    if id_ is None or len(id_) == 0:
        return flask.make_response('error: missing id query', http.HTTPStatus.BAD_REQUEST)
    type_ = flask.request.args.get('type')
    if type_ is None or len(type_) == 0:
        return flask.make_response('error: missing type query', http.HTTPStatus.BAD_REQUEST)
    params = flask.request.get_json()
    try:
        s = globalObject.session_manager.add(id_, type_, params)
    except error.ChatGPTSessionError as e:
        return flask.make_response(str(e), e.HttpStatus)

    return flask.jsonify(s.asdict())


@app.route('/api/delete', methods=['DELETE'])
def handle_delete():
    id_ = flask.request.args.get('id')
    if id_ is None or len(id_) == 0:
        return flask.make_response('error: missing id query', http.HTTPStatus.BAD_REQUEST)

    try:
        globalObject.session_manager.remove(id_)
    except error.ChatGPTSessionError as e:
        return flask.make_response(str(e), e.HttpStatus)

    return flask.jsonify({})


@app.route('/api/send', methods=['POST'])
def handle_send():
    id_ = flask.request.args.get('id')
    session, r = get_session_query(id_)
    if r is not None:
        return r
    msg_bytes = flask.request.get_data()
    msg_str = msg_bytes.decode()

    try:
        session.append_msg(msg_str)
    except error.ChatGPTSessionError as e:
        return flask.make_response(str(e), e.HttpStatus)

    return flask.jsonify({})


def get_session_query(id_: str) -> (Session, flask.Response | None):
    if id_ is None or len(id_) == 0:
        session = globalObject.session_manager.get_default()
        if session is None:
            return None, flask.make_response('error: no sessions', http.HTTPStatus.BAD_REQUEST)
        return session, None
    session = globalObject.session_manager.get(id_)
    if session is None:
        return None, flask.make_response(f'error: no such session: {session}', http.HTTPStatus.BAD_REQUEST)
    return session, None


@app.route('/api/get')
def handle_get():
    id_ = flask.request.args.get('id')
    session, r = get_session_query(id_)
    if r is not None:
        return r

    try:
        m = session.get()
    except error.ChatGPTSessionError as e:
        return flask.make_response(str(e), e.HttpStatus)

    return flask.jsonify(asdict(m))


@app.route('/api/status')
def handle_status():
    id_ = flask.request.args.get('id')
    session, r = get_session_query(id_)
    if r is not None:
        return r

    try:
        status, tokens = session.status()
    except error.ChatGPTSessionError as e:
        return flask.make_response(str(e), e.HttpStatus)

    return flask.jsonify({
        "status": status,
        "tokens": tokens,
    })


@app.route('/api/history')
def handle_history():
    id_ = flask.request.args.get('id')
    session, r = get_session_query(id_)
    if r is not None:
        return r

    try:
        messages = session.history()
    except error.ChatGPTSessionError as e:
        return flask.make_response(str(e), e.HttpStatus)

    messages_ = []
    for message in messages:
        messages_.append(asdict(message))

    return flask.jsonify(messages_)


@app.route('/api/compress', methods=['PATCH'])
def handle_compress():
    id_ = flask.request.args.get('id')
    session, r = get_session_query(id_)
    if r is not None:
        return r

    try:
        session.force_compress()
    except error.ChatGPTSessionError as e:
        return flask.make_response(str(e), e.HttpStatus)

    return flask.jsonify({})
