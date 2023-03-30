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


@app.route('/api/info')
def handle_info():
    id_ = flask.request.args.get('id')
    session, r = get_session_query(id_)
    if r is not None:
        return r

    info = session.asdict()
    return flask.jsonify(info)


@app.route('/api/params', methods=['POST'])
def handle_params():
    id_ = flask.request.args.get('id')
    session, r = get_session_query(id_)
    if r is not None:
        return r
    params = flask.request.get_json()
    try:
        session.set_params(params)
    except error.ChatGPTSessionError as e:
        return flask.make_response(str(e), e.HttpStatus)
    info = session.asdict()
    return flask.jsonify(info)


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


@app.route('/api/inherit', methods=['PUT'])
def handle_inherit():
    id_ = flask.request.args.get('id')
    if id_ is None or len(id_) == 0:
        return flask.make_response('error: missing id query', http.HTTPStatus.BAD_REQUEST)
    type_ = flask.request.args.get('type')
    if type_ is None or len(type_) == 0:
        return flask.make_response('error: missing type query', http.HTTPStatus.BAD_REQUEST)

    data = flask.request.get_json()
    params = data.get('params')
    if params is None:
        return flask.make_response('error: missing params', http.HTTPStatus.BAD_REQUEST)
    memo = data.get('memo')
    if memo is None:
        return flask.make_response('error: missing memo', http.HTTPStatus.BAD_REQUEST)
    history = data.get('history')
    if history is None:
        return flask.make_response('error: missing history', http.HTTPStatus.BAD_REQUEST)

    try:
        s = globalObject.session_manager.add_exists(id_, type_, params, memo, history)
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
    message_info = flask.request.get_json()
    msg_str = message_info.get('message')
    if msg_str is None or len(msg_str) == 0:
        return flask.make_response('error: missing message', http.HTTPStatus.BAD_REQUEST)
    remark = message_info.get('remark')
    if remark is None:
        remark = {}

    try:
        session.append_msg(msg_str, remark)
    except error.ChatGPTSessionError as e:
        return flask.make_response(str(e), e.HttpStatus)

    return flask.jsonify({})


def get_session_query(id_: str) -> (Session, flask.Response | None):
    if id_ is None or len(id_) == 0:
        session = globalObject.session_manager.get_default()
        if session is None:
            return None, flask.make_response('error: no sessions', http.HTTPStatus.BAD_REQUEST)
        return session, None
    try:
        session = globalObject.session_manager.get(id_)
    except error.ChatGPTSessionError as err:
        return None, flask.make_response(f'error: get session: {id_}: {str(err)}', http.HTTPStatus.BAD_REQUEST)
    if session is None:
        return None, flask.make_response(f'error: no such session: {id_}', http.HTTPStatus.BAD_REQUEST)
    return session, None


@app.route('/api/get', methods=['GET', 'PATCH'])
def handle_get():
    id_ = flask.request.args.get('id')
    session, r = get_session_query(id_)
    if r is not None:
        return r

    stop = flask.request.method == 'PATCH'
    try:
        m = session.get(stop)
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


@app.route('/api/status_all')
def handle_status_all():
    statuses = []
    for session in globalObject.session_manager.list():
        try:
            status, tokens = session.status()
        except error.ChatGPTSessionError as e:
            return flask.make_response(str(e), e.HttpStatus)
        statuses.append({
            "id": session.asdict()['id'],
            "status": status,
            "tokens": tokens,
        })

    return flask.jsonify(statuses)


@app.route('/api/memo')
def handle_memo():
    id_ = flask.request.args.get('id')
    session, r = get_session_query(id_)
    if r is not None:
        return r

    try:
        memo = session.memo()
    except error.ChatGPTSessionError as e:
        return flask.make_response(str(e), e.HttpStatus)

    return memo


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


@app.route('/api/remark', methods=['GET', 'PUT'])
def handle_remark():
    id_ = flask.request.args.get('id')
    session, r = get_session_query(id_)
    if r is not None:
        return r

    if flask.request.method == 'GET':
        remark = session.get_remark()
    else:
        remark = flask.request.get_json()
        try:
            session.set_remark(remark)
        except error.ChatGPTSessionError as e:
            return flask.make_response(str(e), e.HttpStatus)
    return flask.jsonify(remark)


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


@app.route('/api/once', methods=['POST'])
def handle_send_once():
    message_info = flask.request.get_json()
    msg_str = message_info.get('message')
    if msg_str is None or len(msg_str) == 0:
        return flask.make_response('error: missing message', http.HTTPStatus.BAD_REQUEST)
    try:
        reply = globalObject.scheduler.send_away(msg_str)
    except error.ChatGPTSessionError as e:
        return flask.make_response(str(e), e.HttpStatus)
    return reply
