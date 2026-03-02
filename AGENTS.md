# AGENTS.md

Operational rules for AI/code agents working in the Tessiture repository.

---

## 1) Purpose and Scope

This document defines **active, repo-specific operating rules** for agent work in Tessiture.

It is intended to:
- Keep changes safe, reproducible, and reviewable.
- Align backend, frontend, and deployment workflows.
- Provide concrete defaults for local development and debugging.

Scope:
- Applies to all tasks performed within this repository unless higher-priority instructions override it.
- Covers Python backend work, Vite/React frontend work, and Unraid/Caddy deployment context.

---

## 2) Instruction Precedence

When instructions conflict, use this order (highest first):

1. System/developer/runtime constraints from the active agent platform.
2. Direct user task instructions for the current request.
3. This `AGENTS.md` file (**active repo policy**).
4. Other repository documentation (`README.md`, plans, checklists).
5. Personal/default agent behavior.

If two sources at the same level conflict, prefer the more specific and more recent instruction.

---

## 3) Active Project Requirements (Mandatory)

The following rules are always active and must be preserved:

1. Use Python virtual environment at `.tessiture/` in project root when applicable.
2. Active Caddyfile is located outside of project workspace at `/mnt/user/appdata/caddy/Caddyfile`.
3. Tessiture production URL is `https://tess.indecisivephysicist.space`, use it for debugging/testing.

Do not remove, weaken, or silently reinterpret these requirements.

---

## 3A) System-Wide Versioning Rule (Mandatory)

Automatic semantic versioning is an active, system-wide Kilo Code rule for this repository.

- For versioned Unraid image builds, prefer Makefile release targets `unraid-build`, `unraid-build-push`, and `unraid-one-shot` over ad-hoc Docker commands.
- Default automated strategy for normal releases is `VERSION_BUMP=auto`.
- A `major` version bump requires explicit user intent confirming a breaking change.
- When `VERSION_BUMP=auto` is used, the effective bump is determined by existing helper behavior in `deploy/unraid/scripts/build.sh` (including `--version-bump auto|patch|minor|major|none`).
- After build updates, treat `TESSITURE_IMAGE` in the Unraid environment as the deployment source of truth for subsequent deployment steps.

---

## 4) Environment and Tooling Defaults

### 4.1 Working Directory
- Repository root: `/mnt/user/public/tessiture`
- Prefer running commands from repo root unless a task explicitly requires a subdirectory.

### 4.2 Python Backend Defaults
- Activate venv before Python tooling:

```bash
source .tessiture/bin/activate
```

- Install/refresh dependencies as needed:

```bash
pip install -r requirements.txt
```

- For package-style execution, prefer module-safe invocations when possible (for example, `python -m pytest`).

### 4.3 Frontend Defaults (Vite/React)
- Frontend location: `frontend/`
- Use npm commands from `frontend/`:

```bash
npm ci
npm run dev
npm run build
npm run test
```

### 4.4 Makefile First
When a workflow exists in `Makefile`, prefer it over ad-hoc shell commands to keep behavior consistent.

---

## 5) Project-Specific Paths and Targets

Use these canonical paths/targets when reasoning about this repository:

- Backend API surface: `api/`
- Analysis pipeline: `analysis/`
- Calibration logic: `calibration/`
- Reporting/export logic: `reporting/`
- Tests: `tests/`
- Frontend app: `frontend/`
- Unraid deployment assets: `deploy/unraid/`
- Active Caddy config (external): `/mnt/user/appdata/caddy/Caddyfile`
- Production system URL: `https://tess.indecisivephysicist.space`

---

## 6) Coding and Editing Guardrails

### 6.1 Change Scope
- Make the smallest change that fully satisfies the task.
- Do not perform unrelated refactors in the same patch.
- Preserve public behavior unless the task explicitly requests behavior changes.

### 6.2 Safety and Compatibility
- Prefer backward-compatible changes for API contracts and report formats.
- Do not hardcode environment-specific secrets/credentials.
- Keep filesystem paths configurable where the code already expects configuration.

### 6.3 Style and Structure
- Follow existing project style in the touched file/module.
- Keep naming and module organization consistent with neighboring code.
- Update relevant documentation when behavior, commands, or interfaces change.

### 6.4 File Hygiene
- Do not create throwaway files in repository root.
- Remove temporary debugging artifacts before finishing.
- Keep diffs readable and review-friendly.

---

## 7) Testing and Verification Policy

### 7.1 Default Expectation
Every non-trivial change should include at least one verification step and report what was run.

### 7.2 Preferred Verification Order
1. Targeted tests nearest the modified code.
2. Broader suite(s) if risk or blast radius is significant.
3. Build checks for impacted runtimes (backend/frontend/deploy scripts as applicable).

### 7.3 Typical Commands
Backend (repo root, venv active):

```bash
python -m pytest tests/test_api/test_routes.py
python -m pytest tests/test_analysis
```

Frontend (`frontend/`):

```bash
npm run test
npm run build
```

### 7.4 When Tests Cannot Run
If verification cannot be executed (missing dependency, environment limitation, time constraint), explicitly state:
- What was attempted.
- Why it could not complete.
- Residual risk and the recommended next command.

---

## 8) Deployment and Ops Constraints (Unraid + Caddy)

- Unraid deployment scripts live in `deploy/unraid/scripts/`.
- Treat deployment scripts and compose definitions as production-sensitive.
- Any Caddy routing/TLS/proxy edits must be made against:
  - `/mnt/user/appdata/caddy/Caddyfile`
- Validate syntax and routing assumptions before applying/restarting services.
- Do not assume Caddyfile changes are tracked in this repository; call out external-file impact in reports.

---

## 9) Debugging Targets and Environments

### 9.1 Primary Debug Target
Use production URL for real-environment checks when requested:
- `https://tess.indecisivephysicist.space`

### 9.2 Local/Pre-Prod Debugging
Use local stacks for iterative debugging first when possible:
- Backend routes and job flow (`api/`, `api/routes.py`)
- Frontend API integration (`frontend/src/api.js`)
- Analysis/reporting modules (`analysis/`, `reporting/`)

### 9.3 Debugging Practice
- Reproduce with the smallest input that still demonstrates the issue.
- Capture concrete evidence (error text, status code, failing command, screenshot path when available).
- Distinguish between code defects, environment/config defects, and data/input defects.

---

## 10) Reporting and Output Expectations

For each completed task, provide a concise report containing:

1. **Summary of changes** by file/path.
2. **Verification performed** (exact commands + outcomes).
3. **Operational impact** (deploy/config/runtime implications).
4. **Known limitations or follow-ups** (if any).

If external systems were touched (for example Caddyfile outside repo), explicitly include that in the summary.

---

## 11) Quick Execution Templates (Active)

### 11.1 Backend Task Template

```bash
source .tessiture/bin/activate
python -m pytest -q
```

### 11.2 Frontend Task Template

```bash
cd frontend
npm ci
npm run test
npm run build
```

### 11.3 Unraid Deployment Review Template

```bash
# Inspect deployment artifacts before execution
ls deploy/unraid
ls deploy/unraid/scripts
```

---

## 12) Optional Future Rules and Templates (REFERENCE ONLY — NOT ACTIVE)

The items below are **examples for future adoption** and are **not enforced** unless explicitly promoted into an active section above.

### 12.1 Optional Rule Candidates (Not Active)
- Require coverage thresholds (for example backend >= 85%, frontend >= 80%).
- Require changelog entry for every user-visible behavior change.
- Require architecture decision record (ADR) for deployment topology changes.

### 12.2 Optional Output Template (Not Active)

```md
## Change Summary
- <file>: <what changed>

## Verification
- `<command>`: <pass/fail + key output>

## Ops Impact
- <none|details>

## Risks / Follow-ups
- <none|details>
```

### 12.3 Optional Incident Debug Template (Not Active)

```md
## Incident Snapshot
- Environment: <prod/stage/local>
- URL/Endpoint: <target>
- Symptom: <observed failure>

## Reproduction
1. <step>
2. <step>

## Evidence
- Logs: <path/snippet>
- HTTP status: <code>
- Screenshot: <path>

## Probable Cause
- <cause hypothesis>

## Mitigation
- <short-term>
- <long-term>
```

---

## 13) Maintenance Notes

- Keep this file concise and operational.
- Promote optional rules to active status only when the team explicitly decides.
- Re-check external path accuracy over time (especially Caddy and deployment locations).
