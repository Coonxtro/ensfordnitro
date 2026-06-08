# keep_alive.py
from flask import Flask

app = Flask(__name__)


@app.route('/')
def main():
    return '<meta http-equiv="refresh" content="0; URL=https://google.com/"/>'
