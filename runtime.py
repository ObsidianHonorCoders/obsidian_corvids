import os
import threading
import time
from collections import deque
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
        environment = os.getenv("APP_ENV", "development")
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
    def __init__(self, concurrent=1, requests=10, window=60, max_identities=1024, clock=time.monotonic):
        self.slots = threading.BoundedSemaphore(concurrent)
        self.lock = threading.Lock()
        self.recent = {}
        self.requests = requests
        self.window = window
        self.max_identities = max_identities
        self.clock = clock

    @contextmanager
    def admit(self, identity: str):
        with self.lock:
            now = self.clock()
            for subject in list(self.recent):
                timestamps = self.recent[subject]
                while timestamps and timestamps[0] <= now - self.window:
                    timestamps.popleft()
                if not timestamps:
                    del self.recent[subject]
            if identity not in self.recent and len(self.recent) >= self.max_identities:
                raise CapacityError("Service capacity reached. Please try again later.")
            timestamps = self.recent.setdefault(identity, deque())
            if len(timestamps) >= self.requests:
                raise CapacityError("Request limit reached. Please try again in a minute.")
            if not self.slots.acquire(blocking=False):
                raise CapacityError("The model is busy. Please try again shortly.")
            timestamps.append(now)
        try:
            yield
        finally:
            self.slots.release()