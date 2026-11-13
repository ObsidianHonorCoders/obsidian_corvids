import unittest
from datetime import UTC, datetime, timedelta
from importlib.util import find_spec
from tempfile import TemporaryDirectory
from unittest.mock import Mock, patch

from runtime import (
    AccessDenied,
    AccessVerifier,
    Admission,
    CapacityError,
    Settings,
    access_token,
)


class RuntimeTests(unittest.TestCase):
    def test_production_requires_access_configuration(self):
        with patch.dict("os.environ", {"APP_ENV": "production"}, clear=True), self.assertRaises(ValueError):
            Settings.load()

    def test_configuration_rejects_invalid_mode_and_credentials(self):
        for environment in (
            {"APP_ENV": "prod"},
            {"OLLAMA_HOST": "http://user:secret@localhost"},
            {"OLLAMA_HOST": "http://localhost:11434/api?token=secret"},
            {"OLLAMA_MODEL": "-malformed"},
        ):
            with patch.dict("os.environ", environment, clear=True), self.assertRaises(ValueError):
                Settings.load()

    def test_development_identity(self):
        with patch.dict("os.environ", {"APP_ENV": "development"}, clear=True):
            self.assertEqual(AccessVerifier(Settings.load()).identity(None), "local-development")

    def test_missing_environment_defaults_to_production(self):
        with patch.dict("os.environ", {}, clear=True), self.assertRaisesRegex(ValueError, "CF_ACCESS_TEAM"):
            Settings.load()

    def test_access_header_lookup_is_case_insensitive_and_rejects_duplicates(self):
        self.assertEqual(access_token({"cf-access-jwt-assertion": "token"}), "token")
        self.assertEqual(access_token({"CF-ACCESS-JWT-ASSERTION": "token"}), "token")
        self.assertIsNone(access_token({"other": "value"}))
        with self.assertRaises(AccessDenied):
            access_token({"Cf-Access-Jwt-Assertion": "one", "cf-access-jwt-assertion": "two"})

    def test_access_checks_claims_and_rejects_missing_token(self):
        jwt = Mock()
        jwt.decode.return_value = {"sub": "user-123"}
        settings = Settings("production", "http://localhost:11434", "test", "team", "audience")
        with patch.dict("sys.modules", {"jwt": jwt}):
            verifier = AccessVerifier(settings)
            with self.assertRaises(AccessDenied):
                verifier.identity(None)
            self.assertEqual(verifier.identity("signed-token"), "user-123")
            kwargs = jwt.decode.call_args.kwargs
            self.assertEqual(kwargs["algorithms"], ["RS256"])
            self.assertEqual(kwargs["audience"], "audience")
            self.assertIn("exp", kwargs["options"]["require"])
            jwt.decode.side_effect = ValueError("private authentication detail")
            with self.assertRaises(AccessDenied) as caught:
                verifier.identity("expired-token")
            self.assertNotIn("private", str(caught.exception))

    @unittest.skipUnless(find_spec("jwt") and find_spec("cryptography"), "Install runtime authentication dependencies")
    def test_access_verifier_checks_real_signature_and_claims(self):
        import jwt
        from cryptography.hazmat.primitives.asymmetric import rsa

        private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        settings = Settings("production", "http://localhost:11434", "test", "team", "audience")
        key_client = Mock()
        key_client.get_signing_key_from_jwt.return_value.key = private_key.public_key()
        with patch("jwt.PyJWKClient", return_value=key_client):
            verifier = AccessVerifier(settings)
            claims = {
                "sub": "user-123",
                "iss": "https://team.cloudflareaccess.com",
                "aud": "audience",
                "iat": datetime.now(UTC),
                "exp": datetime.now(UTC) + timedelta(minutes=5),
            }
            valid_token = jwt.encode(claims, private_key, algorithm="RS256", headers={"kid": "test-key"})
            self.assertEqual(verifier.identity(valid_token), "user-123")

            invalid_signature = jwt.encode(claims, rsa.generate_private_key(
                public_exponent=65537, key_size=2048,
            ), algorithm="RS256", headers={"kid": "test-key"})
            with self.assertRaises(AccessDenied):
                verifier.identity(invalid_signature)

            wrong_audience = {**claims, "aud": "other-app"}
            wrong_audience_token = jwt.encode(wrong_audience, private_key, algorithm="RS256")
            with self.assertRaises(AccessDenied):
                verifier.identity(wrong_audience_token)

    def test_capacity_releases_after_failure_and_limits_users(self):
        admission = Admission(requests=2)
        with admission.admit("alice"), self.assertRaises(CapacityError), admission.admit("bob"):
            pass
        with self.assertRaises(RuntimeError), admission.admit("alice"):
            raise RuntimeError()
        with self.assertRaises(CapacityError), admission.admit("alice"):
            pass
        with admission.admit("bob"):
            pass

    def test_quota_expires_and_identity_memory_is_bounded(self):
        now = [0]
        admission = Admission(requests=1, max_identities=1, clock=lambda: now[0])
        with admission.admit("alice"):
            pass
        with self.assertRaises(CapacityError), admission.admit("bob"):
            pass
        now[0] = 61
        with admission.admit("bob"):
            pass
        self.assertEqual(
            admission.database.execute("SELECT COUNT(DISTINCT identity_hash) FROM requests").fetchone()[0],
            1,
        )

    def test_limit_is_shared_between_instances_and_survives_reopen(self):
        with TemporaryDirectory() as directory:
            database = f"{directory}/admission.sqlite3"
            first = Admission(concurrent=1, requests=1, database_path=database)
            second = Admission(concurrent=1, requests=1, database_path=database)
            with first.admit("alice"), self.assertRaises(CapacityError), second.admit("bob"):
                pass
            with self.assertRaises(CapacityError), second.admit("alice"):
                pass
            first.close()
            second.close()
            restarted = Admission(concurrent=1, requests=1, database_path=database)
            with self.assertRaises(CapacityError), restarted.admit("alice"):
                pass
            with restarted.admit("bob"):
                pass
            restarted.close()

    def test_expired_concurrency_lease_releases_capacity(self):
        now = [100]
        admission = Admission(concurrent=1, lease=5, clock=lambda: now[0])
        first = admission.admit("alice")
        first.__enter__()
        now[0] = 106
        with admission.admit("bob"):
            pass
        first.__exit__(None, None, None)