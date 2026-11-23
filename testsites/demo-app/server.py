"""Resettable loopback login fixture for WAATA AC-01–AC-06."""

import argparse
import hmac
import os
from html import escape
from http.cookies import CookieError, SimpleCookie
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from secrets import token_urlsafe
from urllib.parse import parse_qs, urlsplit

LOGIN_ERROR = "Wrong password"
REGRESSION_ERROR = "Service temporarily unavailable"


class DemoServer(ThreadingHTTPServer):
    def __init__(self, port: int, password: str, *, regression: bool = False):
        self.password = password.encode()
        self.session = token_urlsafe(24)
        self.error = REGRESSION_ERROR if regression else LOGIN_ERROR
        super().__init__(("127.0.0.1", port), LoginHandler)

    @property
    def origin(self) -> str:
        return f"http://127.0.0.1:{self.server_port}"


class LoginHandler(BaseHTTPRequestHandler):
    server: DemoServer

    def log_message(self, format, *args):
        pass

    def _html(self, title: str, body: str) -> None:
        content = (
            f'<!doctype html><html lang="en"><meta charset="utf-8">'
            f"<title>{title}</title><main>{body}</main></html>"
        ).encode()
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(content)))
        self.end_headers()
        self.wfile.write(content)

    def _login(self, error: str = "") -> None:
        alert = f'<p role="alert" data-testid="login-error">{escape(error)}</p>'
        self._html(
            "Demo login",
            "<h1>Demo login</h1>"
            '<form method="post" action="/login">'
            '<label for="password">Password</label>'
            '<input type="password" id="password" name="password" required>'
            '<button type="submit">Sign in</button></form>'
            f"{alert if error else ''}",
        )

    def do_GET(self):
        path = urlsplit(self.path).path
        if path == "/login":
            self._login()
            return
        if path == "/dashboard":
            try:
                cookies = SimpleCookie(self.headers.get("Cookie", ""))
            except CookieError:
                cookies = {}
            session = cookies.get("demo_session")
            if session and hmac.compare_digest(
                session.value.encode(), self.server.session.encode()
            ):
                self._html("Dashboard", '<h1 data-testid="signed-in">Signed in</h1>')
                return
        self.send_error(404)

    def do_POST(self):
        if self.path != "/login":
            self.send_error(404)
            return
        length = int(self.headers.get("Content-Length", "0"))
        if not 0 < length <= 4096:
            self.send_error(400)
            return
        password = parse_qs(self.rfile.read(length).decode("utf-8", "replace")).get(
            "password", [""]
        )[0]
        if not hmac.compare_digest(password.encode(), self.server.password):
            self._login(self.server.error)
            return
        self.send_response(303)
        self.send_header("Location", "/dashboard")
        self.send_header(
            "Set-Cookie",
            f"demo_session={self.server.session}; Path=/; HttpOnly; SameSite=Strict",
        )
        self.send_header("Content-Length", "0")
        self.end_headers()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=3010)
    parser.add_argument("--regression", action="store_true")
    args = parser.parse_args()
    if not (password := os.environ.get("WAATA_DEMO_PASSWORD")):
        parser.error("Set WAATA_DEMO_PASSWORD to a dedicated fixture value")
    with DemoServer(args.port, password, regression=args.regression) as server:
        print(f"Login fixture at {server.origin}/login", flush=True)
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            pass


if __name__ == "__main__":
    main()
