"""A local stand-in for the parts of the Zulip REST API that the adapter uses
(zulip.com/api: send-message, get-messages, get-stream-id, get-stream-topics, get-own-user).
"""

import base64
import json
import threading
import time
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

STREAM, STREAM_ID = "runs", 7


class FakeZulip:
    def __init__(self) -> None:
        self.messages: list[dict] = []
        self.lock = threading.Lock()
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), self._handler())
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        self.site = f"http://127.0.0.1:{self.server.server_address[1]}"

    def close(self) -> None:
        self.server.shutdown()

    def _handler(self):
        fake = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass

            def do_GET(self):
                url = urllib.parse.urlparse(self.path)
                self._answer(*fake.get(url.path, dict(urllib.parse.parse_qsl(url.query)), self._who()))

            def do_POST(self):
                length = int(self.headers["Content-Length"])
                params = dict(urllib.parse.parse_qsl(self.rfile.read(length).decode()))
                self._answer(*fake.post(self.path, params, self._who()))

            def _who(self) -> str:
                encoded = self.headers["Authorization"].removeprefix("Basic ")
                return base64.b64decode(encoded).decode().split(":")[0].split("@")[0]

            def _answer(self, status: int, payload: dict) -> None:
                body = json.dumps(payload).encode()
                self.send_response(status)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

        return Handler

    def post(self, path: str, params: dict, who: str) -> tuple[int, dict]:
        if path != "/api/v1/messages" or params.get("to") != STREAM:
            return 400, {"result": "error", "msg": "Invalid channel name", "code": "BAD_REQUEST"}
        with self.lock:
            id = 100 + len(self.messages)
            self.messages.append(
                {
                    "id": id,
                    "subject": params["topic"],
                    "sender_full_name": who,
                    "content": params["content"],
                    "timestamp": int(time.time()),
                }
            )
        return 200, {"result": "success", "msg": "", "id": id}

    def get(self, path: str, params: dict, who: str) -> tuple[int, dict]:
        if path == "/api/v1/users/me":
            return 200, {"result": "success", "full_name": who}
        if path == "/api/v1/get_stream_id":
            if params["stream"] != STREAM:
                return 400, {"result": "error", "msg": f"Invalid channel name '{params['stream']}'"}
            return 200, {"result": "success", "stream_id": STREAM_ID}
        if path == f"/api/v1/users/me/{STREAM_ID}/topics":
            latest: dict[str, int] = {}
            for m in self.messages:
                latest[m["subject"]] = m["id"]
            topics = sorted(({"name": n, "max_id": i} for n, i in latest.items()), key=lambda t: -t["max_id"])
            return 200, {"result": "success", "topics": topics}
        if path == "/api/v1/messages":
            return 200, {"result": "success", "messages": self._narrowed(params)}
        return 404, {"result": "error", "msg": "Not found"}

    def _narrowed(self, params: dict) -> list[dict]:
        assert params["apply_markdown"] == "false"
        found = list(self.messages)
        for term in json.loads(params["narrow"]):
            if term["operator"] == "topic":
                found = [m for m in found if m["subject"] == term["operand"]]
        anchor, before, after = params["anchor"], int(params["num_before"]), int(params["num_after"])
        if anchor == "newest":
            return found[-before:] if before else []
        if anchor == "oldest":
            return found[:after]
        older = [m for m in found if m["id"] < int(anchor)][-before:] if before else []
        return older + [m for m in found if m["id"] >= int(anchor)][: after + 1]
