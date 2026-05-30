"""Local OAuth callback catcher for Oura development auth."""
from __future__ import annotations

import threading
import time
import urllib.parse
from http.server import BaseHTTPRequestHandler, HTTPServer


class OAuthCallbackError(RuntimeError):
    pass


def catch_oauth_callback(
    redirect_uri: str,
    *,
    expected_state: str,
    bind_host: str | None = None,
    bind_port: int | None = None,
    timeout: int | None = None,
) -> dict[str, str]:
    parsed = urllib.parse.urlparse(redirect_uri)
    if parsed.scheme not in {"http", "https"}:
        raise OAuthCallbackError("Oura redirect URI must be http:// or https://")

    is_local_redirect = parsed.hostname in {"localhost", "127.0.0.1", "::1"}
    host = bind_host or (parsed.hostname if is_local_redirect else "127.0.0.1") or "127.0.0.1"
    port = int(bind_port or (parsed.port if is_local_redirect and parsed.port else 8765))
    expected_path = parsed.path or "/"
    result: dict[str, str] = {}
    done = threading.Event()

    class CallbackHandler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:
            request_url = urllib.parse.urlparse(self.path)
            params = urllib.parse.parse_qs(request_url.query)
            if request_url.path != expected_path:
                self._respond(404, "Unknown callback path.")
                return
            if params.get("state", [""])[0] != expected_state:
                self._respond(400, "State mismatch. Authorization was not accepted.")
                return
            if "error" in params:
                error = params.get("error", ["unknown error"])[0]
                self._respond(400, f"Oura returned an error: {error}")
                result["error"] = error
                done.set()
                return
            code = params.get("code", [""])[0]
            if not code:
                self._respond(400, "Missing authorization code.")
                result["error"] = "missing code"
                done.set()
                return
            result["code"] = code
            result["scope"] = params.get("scope", [""])[0]
            self._respond(200, "Oura authorization complete. You can close this tab.")
            done.set()

        def log_message(self, format: str, *args) -> None:
            return

        def _respond(self, status: int, message: str) -> None:
            body = message.encode()
            self.send_response(status)
            self.send_header("Content-Type", "text/plain; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

    server = HTTPServer((host, port), CallbackHandler)
    server.timeout = 1
    print(f"Waiting for Oura redirect at {redirect_uri}")
    print(f"Listening locally on http://{host}:{port}{expected_path}")
    if timeout is None:
        print("No timeout configured; press Ctrl-C to stop waiting.")
        deadline = None
    else:
        deadline = time.monotonic() + timeout
    try:
        while not done.is_set():
            if deadline is not None and time.monotonic() >= deadline:
                raise OAuthCallbackError("Timed out waiting for Oura OAuth callback")
            server.handle_request()
    finally:
        server.server_close()

    if "code" not in result:
        raise OAuthCallbackError(result.get("error") or "Oura OAuth callback failed")
    return result
