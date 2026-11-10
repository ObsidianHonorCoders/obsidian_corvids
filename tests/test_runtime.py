import unittest
from unittest.mock import Mock, patch

from runtime import AccessDenied, AccessVerifier, Admission, CapacityError, Settings


class RuntimeTests(unittest.TestCase):
    def test_production_requires_access_configuration(self):
        with patch.dict("os.environ", {"APP_ENV": "production"}, clear=True):
            with self.assertRaises(ValueError):
                Settings.load()

    def test_configuration_rejects_invalid_mode_and_credentials(self):
        for environment in ({"APP_ENV": "prod"}, {"OLLAMA_HOST": "http://user:secret@localhost"}):
            with patch.dict("os.environ", environment, clear=True):
                with self.assertRaises(ValueError):
                    Settings.load()

    def test_development_identity(self):
        with patch.dict("os.environ", {}, clear=True):
            self.assertEqual(AccessVerifier(Settings.load()).identity(None), "local-development")

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

    def test_capacity_releases_after_failure_and_limits_users(self):
        admission = Admission(requests=2)
        with admission.admit("alice"):
            with self.assertRaises(CapacityError):
                with admission.admit("bob"):
                    pass
        with self.assertRaises(RuntimeError):
            with admission.admit("alice"):
                raise RuntimeError()
        with self.assertRaises(CapacityError):
            with admission.admit("alice"):
                pass
        with admission.admit("bob"):
            pass

    def test_quota_expires_and_identity_memory_is_bounded(self):
        now = [0]
        admission = Admission(requests=1, max_identities=1, clock=lambda: now[0])
        with admission.admit("alice"):
            pass
        with self.assertRaises(CapacityError):
            with admission.admit("bob"):
                pass
        now[0] = 61
        with admission.admit("bob"):
            pass
        self.assertEqual(list(admission.recent), ["bob"])