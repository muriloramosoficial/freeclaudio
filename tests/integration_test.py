"""Teste determinístico: provider fake síncrono + proxy + cliente que lê o stream."""
import json
import threading
import time
from http.server import BaseHTTPRequestHandler, HTTPServer

import httpx
import uvicorn

from freeclaudio.config import load_config
from freeclaudio.proxy import build_app


class FakeProvider(BaseHTTPRequestHandler):
    def do_POST(self):
        length = int(self.headers.get("Content-Length", 0))
        self.rfile.read(length)
        chunks = [
            'data: {"choices":[{"delta":{"content":"Ola"},"finish_reason":null}]}\n\n',
            'data: {"choices":[{"delta":{"content":" mundo"},"finish_reason":null}]}\n\n',
            'data: {"choices":[{"delta":{},"finish_reason":"stop"}]}\n\n',
            "data: [DONE]\n\n",
        ]
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.end_headers()
        for c in chunks:
            self.wfile.write(c.encode())
            self.wfile.flush()
            time.sleep(0.2)

    def log_message(self, *args):
        pass


def main():
    provider_server = HTTPServer(("127.0.0.1", 9998), FakeProvider)
    threading.Thread(target=provider_server.serve_forever, daemon=True).start()

    cfg = {
        "proxy": {"host": "127.0.0.1", "port": 8099, "auth_token": "tok", "auth_enabled": False},
        "providers": {
            "mock": {
                "enabled": True,
                "type": "openai",
                "base_url": "http://127.0.0.1:9998/v1",
                "api_key": "",
                "default_model": "mock-model",
            }
        },
        "default_provider": "mock",
    }
    tmp = tempfile = __import__("tempfile").NamedTemporaryFile("w", delete=False, suffix=".json")
    json.dump(cfg, tmp)
    tmp.close()

    config = load_config(tmp.name)
    app = build_app(config)
    threading.Thread(
        target=lambda: uvicorn.run(app, host="127.0.0.1", port=8099, log_level="warning"),
        daemon=True,
    ).start()
    time.sleep(1.5)

    body = {
        "model": "default",
        "stream": True,
        "max_tokens": 50,
        "messages": [{"role": "user", "content": "oi"}],
    }
    collected = []
    with httpx.Client(timeout=10.0) as client:
        with client.stream("POST", "http://127.0.0.1:8099/v1/messages", json=body) as r:
            assert r.status_code == 200, r.status_code
            for line in r.iter_lines():
                collected.append(line)

    text = "\n".join(collected)
    found = ""
    for line in collected:
        if "text_delta" in line:
            try:
                data = json.loads(line.split("data: ", 1)[1])
                found += data.get("delta", {}).get("text", "")
            except Exception:
                pass
    print("### STATUS: 200")
    print("### TEXTO CONCATENADO:", repr(found))
    print("### TEM TEXT_DELTA:", "text_delta" in text, "| TEM 'Ola mundo':", "Ola mundo" in found)
    print("### TEM message_stop:", "message_stop" in text)
    print("### TEM message_start:", "message_start" in text)

    assert found == "Ola mundo", f"texto nao veio: {found!r}"
    assert "message_start" in text
    assert "message_stop" in text
    print("### OK!")

    provider_server.shutdown()


if __name__ == "__main__":
    main()
