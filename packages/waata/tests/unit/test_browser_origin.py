"""WebSocket routing uses the same origin and the caller's exact path allowlist."""

from unittest import TestCase

from waata.browser.policy import Origin


class BrowserOriginTests(TestCase):
    def test_websocket_requires_explicit_path_on_the_case_origin(self):
        origin = Origin.from_url("http://127.0.0.1:13037")
        paths = frozenset({"/socket.io/"})
        allowed = "ws://127.0.0.1:13037/socket.io/?transport=websocket"
        self.assertTrue(origin.permits_websocket(allowed, paths))
        self.assertFalse(origin.permits_websocket(allowed, frozenset()))
        for url in (
            "wss://127.0.0.1:13037/socket.io/",
            "ws://127.0.0.1:13038/socket.io/",
            "ws://127.0.0.1:13037/socket.io/extra",
            "ws://localhost:13037/socket.io/",
        ):
            self.assertFalse(origin.permits_websocket(url, paths), url)
