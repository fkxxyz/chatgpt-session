import flask

app = flask.Flask(__name__)

from server.index import *
from server.session import *
