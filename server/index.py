from server import app


@app.route('/api/ping')
def handle_api():
    return 'hello fkxxyz!'
