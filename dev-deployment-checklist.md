Repeatable development redeploy checklist (Unraid + external Cloudflare Tunnel)

Use this every time you ship an update.

1) Pre-flight config check
- Confirm stack file is unchanged/valid in [`deploy/unraid/docker-compose.yml`](deploy/unraid/docker-compose.yml).
- Confirm your live env file matches the template shape in [`deploy/unraid/.env.unraid.example`](deploy/unraid/.env.unraid.example).
- Confirm CORS origins still include your public hostname and any LAN hostname you use.
- Confirm Cloudflare Tunnel is still managed externally (not in this stack) and ingress target remains the Tessiture service.

2) Build quality gate
- Run backend checks locally: make test, make lint, make typecheck.
- If frontend changed, also run frontend tests and a production build.
- Build the container image for this commit.
- Tag image with an immutable version (for example date + short commit).

3) Publish artifact
- Push the new image tag to your registry.
- Record previous stable tag and new candidate tag in your release notes.

4) Update Unraid stack (development rollout)
- In your Unraid stack env, update only the image tag value.
- Redeploy stack using [`deploy/unraid/docker-compose.yml`](deploy/unraid/docker-compose.yml).
- Verify container restart policy, healthcheck state, and mounted paths are healthy.

5) Smoke test immediately after deploy
- Open app UI and submit a small audio file.
- Verify the full API flow: analyze -> status polling -> results download (json/csv/pdf).
- Verify uploads/outputs are being written to expected mounted directories.
- Check logs for CORS errors, 4xx spikes, or worker exceptions.

6) External path validation (through existing Cloudflare Tunnel)
- Confirm public hostname resolves and serves the updated version.
- Confirm no router port-forwarding is required/active for this service.
- Confirm Caddy remains LAN-only for this app path.

7) Stabilization window
- Monitor for 15–30 minutes after each deploy:
  - error rate
  - restart count
  - request latency
  - disk growth in uploads/outputs paths

8) Rollback procedure (if anything fails)
- Revert Unraid stack image tag to previous stable.
- Redeploy stack.
- Re-run smoke test.
- If needed, temporarily pin Cloudflare ingress back to previously known-good target behavior documented in [`README.md`](README.md).

9) End-of-cycle hygiene
- Keep only a small number of recent image tags on Unraid.
- Document what changed, deployed tag, validation result, and rollback tag.
- Update deployment notes in [`README.md`](README.md) when process changes.

Fast daily mini-checklist
- Build/test -> tag/push -> update tag in stack -> redeploy -> smoke test -> monitor -> done.