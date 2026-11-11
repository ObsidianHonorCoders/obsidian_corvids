# Obsidian Corvids

A Streamlit chat interface with one Ollama-powered orchestrator and four fixed demonstration-data tools (CFO, CISO, CMO, COO). It is not a multi-agent system and does not connect to live business or security systems. All tool output is simulated and must not be used for business or compliance decisions.

## Local Development

Requirements: Python 3.12, Ollama, and the `llama3.2` model.

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
ollama pull llama3.2
python -m streamlit run app.py
```

Local mode has no authentication and is for loopback development only. Do not publish it. Ollama defaults to `http://127.0.0.1:11434`; set `OLLAMA_HOST` and `OLLAMA_MODEL` to override the local defaults.

## Tests And Checks

```powershell
python -m unittest discover -s tests -v
python -m pip install -r requirements-dev.txt
ruff check app.py orchestrator.py runtime.py tools.py tests
pip-audit -r requirements.txt
```

The CI workflow runs these tests, lint, and dependency auditing on Python 3.12.

## Cloudflare Tunnel Deployment

The included Compose stack runs the app, Ollama, a model-pull initialization job, and `cloudflared`. The app starts only after Ollama is healthy and the configured model pull succeeds. It publishes no host ports. The app and Ollama communicate over an internal Docker network; Ollama's API is never routed through the tunnel. A separate internal network connects the app to `cloudflared`. An egress-enabled network allows Ollama to download models, `cloudflared` to connect to Cloudflare, and the app to retrieve Cloudflare Access signing keys. Restrict host egress for the app to DNS and `https://<team>.cloudflareaccess.com/cdn-cgi/access/certs`; the Compose bridge itself does not enforce destination allowlists. The app and tunnel containers use read-only root filesystems, drop Linux capabilities, and disallow privilege escalation. Use one app replica: concurrency and per-user quotas are process-local.

1. Create a remotely managed Cloudflare Tunnel. Create a Cloudflare Access self-hosted application and a deny-by-default Allow policy for the intended users **before** publishing a public hostname.
2. Add a public hostname route targeting `http://app:8501` from the tunnel connector. Enable Access JWT validation with the tunnel's **Protect with Access** setting and configure the Access policy and session duration.
3. Obtain the Access team slug and the application's AUD tag. Get the Python base image digest and versioned Ollama and cloudflared images from trusted registries.
4. Copy `.env.example` to `.env` and replace the image and Access placeholders. Use a cloudflared image version 2025.4.0 or later (required for token-file support). Create `secrets/cloudflared-token` containing only the tunnel token, with filesystem access restricted to deployment administrators. This path is ignored by Git and excluded from the app build context.
5. Start the stack. Compose waits for the configured model pull to finish before starting the app:

```powershell
Copy-Item .env.example .env
# Edit .env and create secrets/cloudflared-token before continuing.
docker compose config --quiet
docker compose up --build -d
```

6. In Cloudflare, confirm the hostname has the intended Access application and policy. Test that an unauthenticated browser is denied, an authorized browser can use chat, the origin has no published host port, and the public hostname cannot access Ollama. Test expiration and reauthentication as well.

Production startup requires `APP_ENV=production`, `CF_ACCESS_TEAM`, and `CF_ACCESS_AUD`; Compose sets production mode and fails if required deployment settings are missing. Every app request validates the Cloudflare Access JWT's signature, issuer, audience, and required claims. Requests are limited to 10 per identity per minute and one concurrent model request per process. Chat input is limited to 1,500 characters, history to 5,000 serialized characters, tool output to 2,000 characters per call, and generated output to 512 tokens.

Do not set `APP_ENV=development` on a published service. The development mode intentionally bypasses authentication. If Cloudflare Access is not validating the origin token at the tunnel, the app still validates it itself, but the tunnel-side validation is defense in depth and should be enabled.

## Operational Limitations

- This is a single-host demo deployment, not a highly available production architecture. Ollama needs sufficient RAM/VRAM; model inference capacity has not been load-tested.
- The in-process limiter does not coordinate across replicas or restarts. Add a shared rate-limit store before scaling out.
- Dependency ranges are not a lockfile. Resolve and commit a reviewed, hash-pinned lock and pin container images by digest before a production release. The current environment could not reach its configured package index, so dependencies and image compatibility were not verified here.
- Configure host backups for the `ollama_models` volume, service monitoring, disk and GPU alerts, incident response, and an update/rollback schedule. Avoid collecting prompts or tokens in logs.
- Real data requires separate least-privilege connectors, authorization by authenticated user and tenant, provenance and freshness metadata, audit logging, privacy/retention rules, and security testing. The current tools must remain demo-only.

## Architecture

```text
Browser
  -> Cloudflare Access
  -> Cloudflare Tunnel
  -> Streamlit app (JWT validation, request limits, session UI)
  -> Ollama on private Docker network
  -> fixed, read-only demonstration tools
```
