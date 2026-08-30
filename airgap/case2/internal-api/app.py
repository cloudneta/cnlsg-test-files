from flask import Flask, jsonify

app = Flask(__name__)

SERVICES = {
    "gateway": "Internal LLM Gateway",
    "model": "Qwen3-4B",
    "environment": "air-gap"
}


@app.route("/health")
def health():
    return jsonify({"status": "ok"})


@app.route("/services")
def services():
    return jsonify(SERVICES)


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=8080)
