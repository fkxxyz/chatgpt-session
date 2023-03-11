import http

import flask

import error
from server import app
from server.common import globalObject


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
        result.append(s.__dict__())
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

    return flask.jsonify(s.__dict__())


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
    return ''
