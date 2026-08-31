"""Teste do fluxo de erro do proxy: provider retorna 401, deve emitir event:error limpo."""
import json
import threading
import time
from http.server import BaseHTTPRequestHandler, HTTPServer

import httpx
import uvicorn

from freeclaudio.config import load_config
from freeclaudio.proxy import build_app


class Fake401(BaseHTTPRequestHandler):
    def do_POST(self):
        length = int(self.headers.get("Content-Length", 0))
        self.rfile.read(length)
        body = json.dumps({"error": {"message": "No cookie auth credentials found", "code": 401}}).encode()
        self.send_response(401)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args):
        pass


def main():
    provider_server = HTTPServer(("127.0.0.1", 9997), Fake401)
    threading.Thread(target=provider_server.serve_forever, daemon=True).start()

    cfg = {
        "proxy": {"host": "127.0.0.1", "port": 8096, "auth_token": "tok", "auth_enabled": False},
        "providers": {
            "mock": {
                "enabled": True,
                "type": "openai",
                "base_url": "http://127.0.0.1:9997/v1",
                "api_key": "",
                "default_model": "mock-model",
            }
        },
        "default_provider": "mock",
    }
    import tempfile
    tmp = tempfile.NamedTemporaryFile("w", delete=False, suffix=".json")
    json.dump(cfg, tmp)
    tmp.close()

    config = load_config(tmp.name)
    app = build_app(config)
    threading.Thread(
        target=lambda: uvicorn.run(app, host="127.0.0.1", port=8096, log_level="warning"),
        daemon=True,
    ).start()
    time.sleep(1.5)

    body = {
        "model": "default",
        "stream": True,
        "max_tokens": 50,
        "messages": [{"role": "user", "content": "oi"}],
    }
    with httpx.Client(timeout=10.0) as client:
        with client.stream("POST", "http://127.0.0.1:8096/v1/messages", json=body) as r:
            print("STATUS:", r.status_code)
            content = "".join(r.iter_text())

    print("### CONTEUDO INICIA COM event:error:", content.strip().startswith("event:"))
    print("### CONTEM event:error:", "type_error" in content or '"type": "error"' in content or "auth-enticacao" in content or "autenticacao" in content)
    print("### CONTEM HINT auth:", "autenticacao" in content or "auth" in content)
    print("### TEM message_stop:", "message_stop" in content)
    print("### NAO TEM STACK TRACE (RuntimeError):", "RuntimeError" not in content)

    assert "RuntimeError" not in content, "ainda gera stack trace"
    assert "message_stop" in content

    # Verificar que o erro gerado inclui a dica de auth
    if "autenticacao" in content or "auth" in content.lower():
        print("### DICA DE AUTENTICACAO PRESENTE: OK")

    print("### OK!")
    provider_server.shutdown()


if __name__ == "__main__":
    main()
