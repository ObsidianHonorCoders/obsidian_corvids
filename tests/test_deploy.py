import unittest

from deploy.check_compose import validate_config


IMAGE = "example/service@sha256:" + "a" * 64


def service(networks=(), **overrides):
    value = {
        "image": IMAGE,
        "networks": {network: {} for network in networks},
        "logging": {"driver": "json-file", "options": {"max-size": "10m", "max-file": "3"}},
    }
    value.update(overrides)
    return value


def valid_config():
    return {
        "services": {
            "app": service(
                ("backend", "ingress", "proxy"),
                build={"args": {"PYTHON_BASE_IMAGE": IMAGE}},
                environment={"CF_ACCESS_TEAM": "ci-test", "CF_ACCESS_AUD": "ci-test-audience"},
                read_only=True,
                cap_drop=["ALL"],
                security_opt=["no-new-privileges:true"],
            ),
            "ollama": service(("backend", "model-egress")),
            "model-init": service(("backend",)),
            "egress-proxy": service(
                ("proxy", "egress"),
                read_only=True,
                cap_drop=["ALL"],
                security_opt=["no-new-privileges:true"],
            ),
            "cloudflared": service(
                ("ingress", "egress"),
                read_only=True,
                cap_drop=["ALL"],
                security_opt=["no-new-privileges:true"],
            ),
        }
    }


class DeploymentPolicyTests(unittest.TestCase):
    def test_accepts_hardened_digest_pinned_topology(self):
        validate_config(valid_config())

    def test_rejects_mutable_image_reference(self):
        config = valid_config()
        config["services"]["ollama"]["image"] = "ollama/ollama:latest"
        with self.assertRaisesRegex(ValueError, "digest"):
            validate_config(config)

    def test_rejects_example_access_configuration(self):
        config = valid_config()
        config["services"]["app"]["environment"] = {
            "CF_ACCESS_TEAM": "your-team-name",
            "CF_ACCESS_AUD": "your-access-application-audience",
        }
        with self.assertRaisesRegex(ValueError, "team slug"):
            validate_config(config)

    def test_rejects_example_access_audience(self):
        config = valid_config()
        config["services"]["app"]["environment"]["CF_ACCESS_AUD"] = (
            "your-access-application-audience"
        )
        with self.assertRaisesRegex(ValueError, "application audience"):
            validate_config(config)

    def test_rejects_shared_tunnel_and_ollama_network(self):
        config = valid_config()
        config["services"]["ollama"]["networks"]["egress"] = {}
        with self.assertRaisesRegex(ValueError, "must not share"):
            validate_config(config)

    def test_rejects_publicly_published_service_ports(self):
        config = valid_config()
        config["services"]["ollama"]["ports"] = ["11434:11434"]
        with self.assertRaisesRegex(ValueError, "host ports"):
            validate_config(config)

    def test_rejects_unbounded_container_logs(self):
        config = valid_config()
        config["services"]["app"]["logging"]["options"].pop("max-size")
        with self.assertRaisesRegex(ValueError, "log rotation"):
            validate_config(config)


if __name__ == "__main__":
    unittest.main()