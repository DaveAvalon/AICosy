"""AICosy HTTP adapter; the service owns every game operation."""
from __future__ import annotations

import argparse
import errno
from collections import defaultdict, deque
import hmac
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import ipaddress
import json
import os
from pathlib import Path
import re
import socket
import sys
import threading
import time
from urllib.parse import parse_qs, unquote, urlsplit

from .schemas import json_schema, openapi
from aicosy.errors import GameError

MAX_BODY_BYTES = 65536
WEB_ROOT = Path(__file__).resolve().parent.parent / "aicosy" / "web"
STATUS_HTML = WEB_ROOT / "status.html"


def _loopback(host):
    """Accept literal loopback or localhost; never infer trust from an arbitrary DNS name."""
    if host == "localhost":
        return True
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return False


class GameHTTPServer(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = True

    def __init__(self, address, handler, *, service, token, rate_limit):
        self.service = service
        self.token = token
        self.rate_limit = rate_limit
        self.rate_lock = threading.Lock()
        self.requests = defaultdict(deque)
        super().__init__(address, handler)

    def allowed(self, peer):
        now = time.monotonic()
        with self.rate_lock:
            # Prune idle peers so the limiter itself has a bounded lifetime.
            if len(self.requests) > 1024:
                self.requests = defaultdict(deque, {key: values for key, values in self.requests.items()
                                                   if values and values[-1] > now-60})
            history = self.requests[peer]
            while history and history[0] <= now-60:
                history.popleft()
            if len(history) >= self.rate_limit:
                return False
            history.append(now)
            return True


class Handler(BaseHTTPRequestHandler):
    server_version = "AICosy/0.4"
    sys_version = ""
    # Closing each connection simplifies body limits and prevents request smuggling.
    protocol_version = "HTTP/1.0"

    def setup(self):
        super().setup()
        self.connection.settimeout(5)

    def log_message(self, format, *args):
        # Paths can contain researcher identifiers; bearer tokens are never logged.
        return

    def _reply(self, status, value, *, content_type="application/json; charset=utf-8"):
        body = value if isinstance(value, bytes) else json.dumps(value, ensure_ascii=False, allow_nan=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("X-Frame-Options", "DENY")
        if status == 401:
            self.send_header("WWW-Authenticate", 'Bearer realm="AICosy"')
        if status == 429:
            self.send_header("Retry-After", "60")
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(body)

    def _error(self, code, message, status=400, details=None):
        self._reply(status, {"error": {"code": code, "message": message, "details": details}})

    def send_error(self, code, message=None, explain=None):
        self._error("HTTP_ERROR", message or "HTTP request rejected", code)

    def _authenticate(self):
        if not self.server.token:
            return
        expected = "Bearer " + self.server.token
        value = self.headers.get("Authorization", "")
        if not hmac.compare_digest(value.encode("utf-8"), expected.encode("utf-8")):
            raise GameError("UNAUTHORIZED", "A valid bearer access token is required", status=401)

    def _check_origin(self):
        """Reject browser cross-origin writes and loopback DNS-rebinding hosts."""
        host_header = self.headers.get("Host", "")
        try:
            host = urlsplit("//" + host_header).hostname
        except ValueError:
            host = None
        if not self.server.token and (host is None or not _loopback(host)):
            raise GameError("INVALID_HOST", "Use localhost or a literal loopback address", status=403)
        origin = self.headers.get("Origin")
        if origin is not None:
            try:
                parsed = urlsplit(origin)
            except ValueError:
                raise GameError("CROSS_ORIGIN_DENIED", "Malformed request origin", status=403) from None
            if parsed.scheme not in ("http", "https") or parsed.netloc != host_header:
                raise GameError("CROSS_ORIGIN_DENIED", "Cross-origin API requests are not permitted", status=403)

    def _body(self, *, optional=False):
        if self.headers.get("Transfer-Encoding") is not None:
            raise GameError("INVALID_REQUEST", "Transfer-Encoding is not supported", status=400)
        lengths = self.headers.get_all("Content-Length", [])
        if len(lengths) > 1:
            raise GameError("INVALID_REQUEST", "Duplicate Content-Length headers are not supported", status=400)
        length_text = lengths[0] if lengths else "0"
        if not re.fullmatch(r"\d{1,10}", length_text):
            raise GameError("INVALID_REQUEST", "Content-Length must be a nonnegative integer", status=400)
        length = int(length_text)
        if length > MAX_BODY_BYTES:
            raise GameError("BODY_TOO_LARGE", f"JSON body exceeds {MAX_BODY_BYTES} bytes", status=413)
        if length == 0 and optional:
            return {}
        if self.headers.get_content_type() != "application/json":
            raise GameError("UNSUPPORTED_MEDIA_TYPE", "Use Content-Type: application/json", status=415)
        if length == 0:
            raise GameError("INVALID_JSON", "A JSON object is required", status=400)
        raw = self.rfile.read(length)
        if len(raw) != length:
            raise GameError("INVALID_REQUEST", "Request body is shorter than Content-Length", status=400)
        try:
            def pairs(items):
                result = {}
                for key, value in items:
                    if key in result:
                        raise ValueError("duplicate object key")
                    result[key] = value
                return result
            value = json.loads(raw.decode("utf-8"), object_pairs_hook=pairs,
                               parse_constant=lambda value: (_ for _ in ()).throw(ValueError(value)))
        except (UnicodeError, ValueError, RecursionError):
            raise GameError("INVALID_JSON", "Body must be finite UTF-8 JSON", status=400) from None
        if not isinstance(value, dict):
            raise GameError("INVALID_REQUEST", "A JSON object is required", status=400)
        return value

    @staticmethod
    def _query(parsed, allowed=()):
        try:
            values = parse_qs(parsed.query, keep_blank_values=True, max_num_fields=8, strict_parsing=True)
        except ValueError:
            raise GameError("INVALID_QUERY", "Malformed query parameters", status=400) from None
        if any(key not in allowed or len(value) != 1 for key, value in values.items()):
            raise GameError("INVALID_QUERY", "Unknown or repeated query parameter", status=400)
        return {key: value[0] for key, value in values.items()}

    @staticmethod
    def _number(value, name):
        if not re.fullmatch(r"-?\d{1,11}", value):
            raise GameError("INVALID_QUERY", f"{name} must be an integer", status=400)
        return int(value)

    def _dispatch(self):
        if not self.server.allowed(self.client_address[0]):
            raise GameError("RATE_LIMITED", "Request limit exceeded; retry after 60 seconds", status=429)
        parsed = urlsplit(self.path)
        path = parsed.path
        method = self.command
        service = self.server.service
        if method == "GET" and path in ("/", "/observer", "/status"):
            self._query(parsed, ("session",) if path != "/status" else ())
            page = STATUS_HTML if path == "/status" else WEB_ROOT / "observer.html"
            self._reply(200, page.read_bytes(), content_type="text/html; charset=utf-8")
            return
        assets = {"/assets/observer.css": ("observer.css", "text/css; charset=utf-8"),
                  "/assets/observer.js": ("observer.js", "text/javascript; charset=utf-8")}
        if method == "GET" and path in assets:
            self._query(parsed)
            name, content_type = assets[path]
            self._reply(200, (WEB_ROOT/name).read_bytes(), content_type=content_type)
            return
        if method == "GET" and path == "/openapi.json":
            self._query(parsed)
            self._reply(200, openapi())
            return
        schema_match = re.fullmatch(r"/schemas/([a-z_]+)\.json", path)
        if method == "GET" and schema_match:
            self._query(parsed)
            schema = json_schema(schema_match[1])
            if schema is None:
                raise GameError("NOT_FOUND", "Schema not found", status=404)
            self._reply(200, schema)
            return
        if path.startswith("/v1/"):
            self._check_origin()
            self._authenticate()
        simple_get = {"/v1/manifest": service.manifest, "/v1/status": service.status}
        if method == "GET" and path in simple_get:
            self._query(parsed)
            result = simple_get[path]()
        elif method == "GET" and path == "/v1/rules":
            query = self._query(parsed, ("engine_version",))
            result = service.rules(self._number(query.get("engine_version", "4"), "engine_version"))
        elif method == "GET" and path == "/v1/observer/sessions":
            query = self._query(parsed, ("limit",))
            result = service.list_sessions(limit=self._number(query.get("limit", "30"), "limit"))
        elif method == "GET" and re.fullmatch(r"/v1/observer/sessions/[^/]+", path):
            self._query(parsed)
            result = service.observer(unquote(path.rsplit("/", 1)[1]))
        elif method == "POST" and path == "/v1/sessions":
            self._query(parsed)
            result = service.start(self._body())
        else:
            session_match = re.fullmatch(r"/v1/sessions/([^/]+)/(observation|action|events|heartbeat|result|debug|replay|leave)", path)
            player_match = re.fullmatch(r"/v1/players/([^/]+)/(profile(?:/reset)?|export|comparison)", path)
            if session_match:
                sid, operation = unquote(session_match[1]), session_match[2]
                query = self._query(parsed, ("after", "limit") if operation == "events" else ())
                if method == "GET" and operation in ("observation", "result", "debug", "replay"):
                    name = "observe" if operation == "observation" else operation
                    result = getattr(service, name)(sid)
                elif method == "GET" and operation == "events":
                    result = service.events(sid, after=self._number(query.get("after", "-1"), "after"),
                                            limit=self._number(query.get("limit", "100"), "limit"))
                elif method == "POST" and operation in ("action", "leave"):
                    result = getattr(service, "act" if operation == "action" else "leave")(sid, self._body())
                elif method == "POST" and operation == "heartbeat":
                    if self._body(optional=True):
                        raise GameError("INVALID_FIELDS", "Heartbeat accepts only an empty JSON object", status=400)
                    result = service.heartbeat(sid)
                else:
                    raise GameError("METHOD_NOT_ALLOWED", "Method not allowed for this endpoint", status=405)
            elif player_match:
                pid, operation = unquote(player_match[1]), player_match[2]
                query = self._query(parsed, ("mode", "engine_version") if operation.startswith("profile") else ())
                if method == "GET" and operation == "profile":
                    result = service.profile(pid, mode=query.get("mode", "normal"), engine_version=self._number(query.get("engine_version", "4"), "engine_version"))
                elif method == "POST" and operation == "profile/reset":
                    if self._body(optional=True):
                        raise GameError("INVALID_FIELDS", "Profile reset accepts only an empty JSON object", status=400)
                    result = service.reset_profile(pid, mode=query.get("mode", "normal"), engine_version=self._number(query.get("engine_version", "4"), "engine_version"))
                elif method == "GET" and operation in ("export", "comparison"):
                    result = getattr(service, "export_player" if operation == "export" else "compare")(pid)
                else:
                    raise GameError("METHOD_NOT_ALLOWED", "Method not allowed for this endpoint", status=405)
            else:
                raise GameError("NOT_FOUND", "Endpoint not found; read /v1/manifest", status=404)
        self._reply(200, result)

    def _handle(self):
        try:
            self._dispatch()
        except GameError as exc:
            self._reply(exc.status, exc.as_dict())
        except (TimeoutError, socket.timeout):
            self._error("REQUEST_TIMEOUT", "Request timed out", 408)
        except (BrokenPipeError, ConnectionResetError):
            pass
        except Exception:
            # No input, identifiers, database paths, secrets or traceback exposed.
            self._error("INTERNAL_ERROR", "The server could not complete this request", 500)

    do_GET = _handle
    do_POST = _handle
    do_HEAD = _handle
    do_PUT = _handle
    do_DELETE = _handle
    do_PATCH = _handle
    do_OPTIONS = _handle


def make_server(service, host="127.0.0.1", port=8765, token=None, rate_limit=120):
    if not isinstance(host, str) or not host:
        raise ValueError("A listening host is required")
    if token is not None and (not isinstance(token, str) or not token or any(ord(c) < 33 or ord(c) > 126 for c in token)):
        raise ValueError("Access token must be a nonempty printable ASCII string without spaces")
    if not _loopback(host) and not token:
        raise ValueError("Non-loopback listening requires an explicit bearer token")
    if type(port) is not int or not 0 <= port <= 65535:
        raise ValueError("Port must be in 0..65535")
    if type(rate_limit) is not int or rate_limit < 1:
        raise ValueError("Rate limit must be a positive request count per minute")
    server_type = GameHTTPServer
    try:
        if ipaddress.ip_address(host).version == 6:
            class IPv6GameHTTPServer(GameHTTPServer):
                address_family = socket.AF_INET6
            server_type = IPv6GameHTTPServer
    except ValueError:
        pass
    return server_type((host, port), Handler, service=service, token=token, rate_limit=rate_limit)


def main(argv=None):
    from aicosy.service import GameService
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--db", default="data/porn.sqlite3")
    parser.add_argument("--token-env", default="AICOSY_ACCESS_TOKEN", help="Environment variable holding an optional bearer access token (defaults to AICOSY_ACCESS_TOKEN, with legacy fallback)")
    parser.add_argument("--rate-limit", type=int, default=120, help="Maximum requests per peer per minute")
    args = parser.parse_args(argv)
    service = GameService(args.db)
    server = None
    try:
        token_names = {
            "AICOSY_ACCESS_TOKEN": ("AICOSY_ACCESS_TOKEN", "AIRPORN_ACCESS_TOKEN", "PORN_ACCESS_TOKEN"),
            "AIRPORN_ACCESS_TOKEN": ("AIRPORN_ACCESS_TOKEN", "PORN_ACCESS_TOKEN"),
        }.get(args.token_env, (args.token_env,))
        token = next((os.environ[name] for name in token_names if name in os.environ), None)
        server = make_server(service, args.host, args.port, token, args.rate_limit)
        print(f"AICosy listening on {args.host}:{server.server_port}; status page and API share this port", file=sys.stderr)
        server.serve_forever(poll_interval=.2)
    except KeyboardInterrupt:
        pass
    except OSError as exc:
        if exc.errno == errno.EADDRINUSE:
            parser.error(f"Port {args.port} is already in use; choose another with --port 8766 and use that port in the observer URL and client --server.")
        parser.error(str(exc))
    except ValueError as exc:
        parser.error(str(exc))
    finally:
        if server:
            server.server_close()
        service.close()


if __name__ == "__main__":
    main()
