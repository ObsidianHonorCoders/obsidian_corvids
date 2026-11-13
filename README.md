# Obsidian Corvids

A Streamlit chat interface with one Ollama-powered orchestrator and four fixed demonstration-data tools (CFO, CISO, CMO, COO). It is not a multi-agent system and does not connect to live business or security systems. All tool output is simulated and must not be used for business or compliance decisions.

## Local Development

Requirements: Python 3.12, Ollama, and the `llama3.2` model.

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --require-hashes -r requirements.lock
ollama pull llama3.2
$env:APP_ENV = "development"
python -m streamlit run app.py
```

Local mode must be explicitly enabled and has no authentication; it is for loopback development only. Do not publish it. Unset `APP_ENV` defaults to authenticated production mode and requires Cloudflare Access configuration. Ollama defaults to `http://127.0.0.1:11434`; set `OLLAMA_HOST` and `OLLAMA_MODEL` to override the local defaults.

## Tests And Checks

```powershell
python -m unittest discover -s tests -v
python -m pip install --require-hashes -r requirements-dev.lock
ruff check app.py orchestrator.py runtime.py tools.py deploy tests
pip-audit -r requirements.lock
```

The CI workflow runs these tests, lint, and dependency auditing on Python 3.12. The range-based `requirements.txt` and `requirements-dev.txt` files are lock inputs; production and CI install from the hash-pinned lock files.

To intentionally refresh the locks, install the development lock and compile both inputs against the configured package index:

```powershell
python -m pip install --require-hashes -r requirements-dev.lock
pip-compile --allow-unsafe --generate-hashes --resolver=backtracking --output-file=requirements.lock requirements.txt
pip-compile --allow-unsafe --generate-hashes --resolver=backtracking --output-file=requirements-dev.lock requirements-dev.txt
```

## Cloudflare Tunnel Deployment

The included Compose stack runs the app, Ollama, a model-pull initialization job, a restricted Squid egress proxy, and `cloudflared`. The app starts only after Ollama is healthy and the configured model pull succeeds. It publishes no host ports. Ollama's API is on an internal Docker network and is never routed through the tunnel; the tunnel connector does not share Ollama's egress network. The app has no direct egress route; its proxy permits HTTPS CONNECT only to `*.cloudflareaccess.com` for Access signing-key retrieval. Ollama and `cloudflared` use separate egress-enabled networks to download models and connect to Cloudflare, respectively. Containers use bounded JSON log rotation; the app, proxy, and tunnel use read-only root filesystems, drop Linux capabilities, and disallow privilege escalation. The SQLite request limiter persists in the local named volume and coordinates processes sharing that volume on one host. Cross-host scaling requires a shared limiter.

1. Create a remotely managed Cloudflare Tunnel. Create a Cloudflare Access self-hosted application and a deny-by-default Allow policy for the intended users **before** publishing a public hostname.
2. Add a public hostname route targeting `http://app:8501` from the tunnel connector. Enable Access JWT validation with the tunnel's **Protect with Access** setting and configure the Access policy and session duration.
3. Obtain the Access team slug and the application's AUD tag. Get verified immutable digest references for Python, Ollama, cloudflared, and Squid images from trusted registries.
4. Copy `.env.example` to `.env` and replace every image and Access placeholder with the verified values. Use a cloudflared image version 2025.4.0 or later (required for token-file support). Create `secrets/cloudflared-token` containing only the tunnel token, with filesystem access restricted to deployment administrators. This path is ignored by Git and excluded from the app build context.
5. Start the stack. Compose waits for the configured model pull to finish before starting the app:

```powershell
Copy-Item .env.example .env
# Replace all image placeholders with verified immutable digests and create the tunnel token file.
python deploy/check_compose.py
docker compose up --build -d
```

6. In Cloudflare, confirm the hostname has the intended Access application and policy. Test that an unauthenticated browser is denied, an authorized browser can use chat, the origin has no published host port, and the public hostname cannot access Ollama. Test expiration and reauthentication as well. Confirm the Squid proxy can reach the tenant's signing-key endpoint while denying unrelated domains.

Production startup requires `APP_ENV=production`, `CF_ACCESS_TEAM`, and `CF_ACCESS_AUD`; Compose sets production mode and fails if required deployment settings are missing. Every app request validates the Cloudflare Access JWT's signature, issuer, audience, and required claims. SQLite-backed quotas allow 10 requests per identity per minute and one concurrent model request across processes sharing the state volume. Chat input is limited to 1,500 characters, history to 5,000 serialized characters, tool output to 2,000 characters per call, and generated output to 512 tokens.

Do not set `APP_ENV=development` on a published service. The development mode intentionally bypasses authentication. If Cloudflare Access is not validating the origin token at the tunnel, the app still validates it itself, but the tunnel-side validation is defense in depth and should be enabled.

## Operational Limitations

- This is a single-host demo deployment, not a highly available production architecture. Ollama needs sufficient RAM/VRAM; model inference capacity has not been load-tested.
- The SQLite limiter only coordinates processes that share the same local `admission_state` volume. Use a shared service such as Redis before deploying replicas across hosts. Back up or deliberately discard the rate-limit volume according to the deployment quota and retention policy.
- Dependency locks are generated with hashes and used for production image and CI installation. Review lock updates and run the dependency audit before release. The deployment preflight rejects mutable image tags and example Access values, but digest syntax alone does not establish registry trust; replace the image placeholders with digests verified against trusted registries.
- Configure host backups for the `ollama_models` volume, service monitoring, disk and GPU alerts, incident response, and an update/rollback schedule. Avoid collecting prompts or tokens in logs.
- Real data requires separate least-privilege connectors, authorization by authenticated user and tenant, provenance and freshness metadata, audit logging, privacy/retention rules, and security testing. The current tools must remain demo-only.

## Architecture

```text
Browser
  -> Cloudflare Access
  -> Cloudflare Tunnel
  -> Streamlit app (JWT validation, UI, SQLite admission limits)
       -> restricted Squid proxy -> Cloudflare Access signing keys
       -> Ollama on private Docker network
       -> deterministic domain routing -> fixed demo tools
```
