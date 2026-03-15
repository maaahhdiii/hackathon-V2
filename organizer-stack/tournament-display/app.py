import os

import requests
from flask import Flask, Response, render_template
from flask_cors import CORS

app = Flask(__name__)
CORS(app)

ORCHESTRATOR_URL = os.getenv("ORCHESTRATOR_URL", "http://127.0.0.1:9000").rstrip("/")


@app.get("/")
def index():
    return render_template("display.html")


@app.get("/stream")
def stream_proxy():
    def generate():
        while True:
            try:
                with requests.get(f"{ORCHESTRATOR_URL}/stream", stream=True, timeout=65) as upstream:
                    for line in upstream.iter_lines(decode_unicode=True):
                        if line is None:
                            continue
                        if line:
                            yield f"{line}\n"
                        else:
                            yield "\n"
            except Exception:
                yield "event: ping\ndata: {\"ok\": false}\n\n"

    return Response(generate(), mimetype="text/event-stream")


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, threaded=True)
