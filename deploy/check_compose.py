import json
import os
import re
import subprocess
import sys
from pathlib import Path
from typing import Any


REQUIRED_SERVICES = {"app", "ollama", "model-init", "egress-proxy", "cloudflared"}
REQUIRED_NETWORKS = {
    "app": {"backend", "ingress", "proxy"},
    "ollama": {"backend", "model-egress"},
    "model-init": {"backend"},
    "egress-proxy": {"proxy", "egress"},
    "cloudflared": {"ingress", "egress"},
}
INTERNAL_NETWORKS = {"backend", "ingress", "proxy"}
IMAGE_DIGEST = re.compile(r".+@sha256:[0-9a-f]{64}$")
TEAM_SLUG = re.compile(r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?$")
REPOSITORY_ROOT = Path(__file__).resolve().parents[1]


def _fail(message: str) -> None:
    raise ValueError(message)


def validate_config(config: dict[str, Any]) -> None:
    services = config.get("services")
    if not isinstance(services, dict) or not REQUIRED_SERVICES <= services.keys():
        _fail("Compose is missing one or more required services.")
    networks = config.get("networks")
    if not isinstance(networks, dict) or not set().union(*REQUIRED_NETWORKS.values()) <= networks.keys():
        _fail("Compose is missing one or more required networks.")

    for network_name in INTERNAL_NETWORKS:
        if networks[network_name].get("internal") is not True:
            _fail(f"The {network_name} network must be internal.")
    for network_name, expected in REQUIRED_NETWORKS.items():
        actual = set(services[network_name].get("networks", {}))
        if actual != expected:
            _fail(f"{network_name} has an unexpected Docker network attachment.")

    app = services["app"]
    build_args = app.get("build", {}).get("args", {})
    image_refs = [build_args.get("PYTHON_BASE_IMAGE")]
    image_refs.extend(service["image"] for service in services.values() if "image" in service)
    if any(
        not isinstance(image, str)
        or not IMAGE_DIGEST.fullmatch(image)
        or image.endswith("0" * 64)
        for image in image_refs
    ):
        _fail("Every deployment image must use a verified @sha256:<64 lowercase hex> digest.")
    environment = app.get("environment", {})
    team = environment.get("CF_ACCESS_TEAM")
    audience = environment.get("CF_ACCESS_AUD")
    if (
        not isinstance(team, str)
        or not TEAM_SLUG.fullmatch(team)
        or team in {"your-team-name", "ci-test"}
    ):
        _fail("CF_ACCESS_TEAM must be the configured Cloudflare team slug, not an example value.")
    if (
        not isinstance(audience, str)
        or not audience.strip()
        or audience.casefold().startswith("your-")
        or audience.casefold() == "ci-test-audience"
        or "placeholder" in audience.casefold()
        or "replace_with" in audience.casefold()
    ):
        _fail("CF_ACCESS_AUD must be the configured Cloudflare application audience.")

    if any(service.get("ports") for service in services.values()):
        _fail("No service may publish a host port.")
    for service_name in ("app", "egress-proxy", "cloudflared"):
        service = services[service_name]
        if service.get("read_only") is not True:
            _fail(f"{service_name} must use a read-only root filesystem.")
        if "ALL" not in service.get("cap_drop", []):
            _fail(f"{service_name} must drop all Linux capabilities.")
        if "no-new-privileges:true" not in service.get("security_opt", []):
            _fail(f"{service_name} must disallow privilege escalation.")

    for service_name, service in services.items():
        logging = service.get("logging", {})
        options = logging.get("options", {})
        if logging.get("driver") != "json-file" or not options.get("max-size") or not options.get("max-file"):
            _fail(f"{service_name} must have bounded JSON log rotation.")


def main(repository_root: Path = REPOSITORY_ROOT) -> int:
    secret_path = repository_root / "secrets" / "cloudflared-token"
    if not secret_path.is_file() or not secret_path.read_bytes().strip():
        print("Missing non-empty secrets/cloudflared-token file.", file=sys.stderr)
        return 1
    try:
        result = subprocess.run(
            ["docker", "compose", "config", "--format", "json"],
            check=True,
            capture_output=True,
            text=True,
            env=os.environ.copy(),
            cwd=repository_root,
        )
        validate_config(json.loads(result.stdout))
    except FileNotFoundError:
        print("Docker Compose v2 is required for deployment validation.", file=sys.stderr)
        return 1
    except (subprocess.CalledProcessError, json.JSONDecodeError, ValueError) as error:
        print(f"Deployment configuration check failed: {error}", file=sys.stderr)
        return 1
    print("Deployment configuration passed production policy checks.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())