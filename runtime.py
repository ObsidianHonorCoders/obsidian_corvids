import hashlib
import os
import sqlite3
import threading
import time
import uuid
from contextlib import contextmanager
from dataclasses import dataclass
from urllib.parse import urlsplit


class AccessDenied(Exception):
    pass


class CapacityError(Exception):
    pass


@dataclass(frozen=True)
class Settings:
    environment: str
    ollama_host: str
    model: str
    access_team: str
    access_audience: str

    @classmethod
    def load(cls):
        environment = os.getenv("APP_ENV", "production")
        if environment not in {"development", "production"}:
            raise ValueError("APP_ENV must be development or production")
        team = os.getenv("CF_ACCESS_TEAM", "")
        audience = os.getenv("CF_ACCESS_AUD", "")
        if environment == "production" and (
            not team or not audience or len(team) > 63
            or any(character not in "abcdefghijklmnopqrstuvwxyz0123456789-" for character in team)
            or team.startswith("-") or team.endswith("-")
        ):
            raise ValueError("Production requires a valid CF_ACCESS_TEAM and CF_ACCESS_AUD")
        host = os.getenv("OLLAMA_HOST", "http://127.0.0.1:11434")
        parsed = urlsplit(host)
        if (
            parsed.scheme not in {"http", "https"}
            or not parsed.hostname
            or parsed.username
            or parsed.password
            or parsed.query
            or parsed.fragment
            or parsed.path not in {"", "/"}
        ):
            raise ValueError("OLLAMA_HOST must be an HTTP(S) URL without credentials")
        model = os.getenv("OLLAMA_MODEL", "llama3.2")
        if (
            not model.strip()
            or len(model) > 200
            or model.startswith("-")
            or any(character not in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789._:/-" for character in model)
        ):
            raise ValueError("OLLAMA_MODEL is invalid")
        return cls(environment, host, model, team, audience)


def access_token(headers) -> str | None:
    values = [
        value for name, value in headers.items()
        if name.casefold() == "cf-access-jwt-assertion"
    ]
    if len(values) > 1:
        raise AccessDenied("Authentication could not be verified. Reconnect through Cloudflare Access.")
    return values[0] if values else None


class AccessVerifier:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.keys = None
        if settings.environment == "production":
            import jwt

            self.keys = jwt.PyJWKClient(
                f"https://{settings.access_team}.cloudflareaccess.com/cdn-cgi/access/certs",
                timeout=5,
            )

    def identity(self, token: str | None) -> str:
        if self.settings.environment == "development":
            return "local-development"
        if not isinstance(token, str) or not token or len(token) > 16384:
            raise AccessDenied("Authentication required. Reconnect through Cloudflare Access.")
        import jwt

        try:
            key = self.keys.get_signing_key_from_jwt(token)
            claims = jwt.decode(
                token,
                key.key,
                algorithms=["RS256"],
                audience=self.settings.access_audience,
                issuer=f"https://{self.settings.access_team}.cloudflareaccess.com",
                options={"require": ["exp", "iat", "sub", "aud", "iss"]},
            )
            subject = claims["sub"]
            if not isinstance(subject, str) or not subject or len(subject) > 256:
                raise AccessDenied("Invalid identity.")
            return subject
        except AccessDenied:
            raise
        except Exception:
            raise AccessDenied("Authentication could not be verified. Reconnect through Cloudflare Access.") from None


class Admission:
    def __init__(
        self,
        concurrent=1,
        requests=10,
        window=60,
        max_identities=1024,
        lease=300,
        database_path=":memory:",
        clock=time.time,
    ):
        if min(concurrent, requests, window, max_identities, lease) < 1:
            raise ValueError("Admission limits must be positive")
        self.lock = threading.RLock()
        self.requests = requests
        self.window = window
        self.max_identities = max_identities
        self.concurrent = concurrent
        self.lease = lease
        self.clock = clock
        if database_path != ":memory:":
            os.makedirs(os.path.dirname(os.path.abspath(database_path)), exist_ok=True)
        self.database = sqlite3.connect(database_path, timeout=10, isolation_level=None, check_same_thread=False)
        self.database.execute("PRAGMA busy_timeout = 10000")
        if database_path != ":memory:":
            self.database.execute("PRAGMA journal_mode = WAL")
        self.database.executescript(
            "CREATE TABLE IF NOT EXISTS requests ("
            "identity_hash TEXT NOT NULL, created_at REAL NOT NULL);"
            "CREATE INDEX IF NOT EXISTS requests_identity_time "
            "ON requests(identity_hash, created_at);"
            "CREATE TABLE IF NOT EXISTS inflight ("
            "request_id TEXT PRIMARY KEY, identity_hash TEXT NOT NULL, expires_at REAL NOT NULL);"
            "CREATE INDEX IF NOT EXISTS inflight_expiry ON inflight(expires_at);"
        )

    @contextmanager
    def admit(self, identity: str):
        identity_hash = hashlib.sha256(identity.encode("utf-8")).hexdigest()
        request_id = uuid.uuid4().hex
        with self.lock:
            now = self.clock()
            self.database.execute("BEGIN IMMEDIATE")
            try:
                self.database.execute("DELETE FROM requests WHERE created_at <= ?", (now - self.window,))
                self.database.execute("DELETE FROM inflight WHERE expires_at <= ?", (now,))
                identities = self.database.execute(
                    "SELECT COUNT(DISTINCT identity_hash) FROM requests"
                ).fetchone()[0]
                known_identity = self.database.execute(
                    "SELECT 1 FROM requests WHERE identity_hash = ? LIMIT 1", (identity_hash,)
                ).fetchone()
                if not known_identity and identities >= self.max_identities:
                    raise CapacityError("Service capacity reached. Please try again later.")
                user_requests = self.database.execute(
                    "SELECT COUNT(*) FROM requests WHERE identity_hash = ?", (identity_hash,)
                ).fetchone()[0]
                if user_requests >= self.requests:
                    raise CapacityError("Request limit reached. Please try again in a minute.")
                active_requests = self.database.execute("SELECT COUNT(*) FROM inflight").fetchone()[0]
                if active_requests >= self.concurrent:
                    raise CapacityError("The model is busy. Please try again shortly.")
                self.database.execute(
                    "INSERT INTO requests(identity_hash, created_at) VALUES (?, ?)",
                    (identity_hash, now),
                )
                self.database.execute(
                    "INSERT INTO inflight(request_id, identity_hash, expires_at) VALUES (?, ?, ?)",
                    (request_id, identity_hash, now + self.lease),
                )
                self.database.execute("COMMIT")
            except Exception:
                self.database.execute("ROLLBACK")
                raise
        try:
            yield
        finally:
            with self.lock:
                self.database.execute("BEGIN IMMEDIATE")
                self.database.execute("DELETE FROM inflight WHERE request_id = ?", (request_id,))
                self.database.execute("COMMIT")

    def close(self):
        with self.lock:
            self.database.close()