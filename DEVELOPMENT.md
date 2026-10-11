# Develop and review a YA-WAMF change

Start from current `dev`, make one reviewable change on a short-lived branch,
and submit it through a pull request. Everyday changes target `dev`; release
pull requests alone target `main`.

Read [CLAUDE.md](CLAUDE.md) before making changes. The
[architecture guide](DEVELOPER.md) explains the component boundaries;
[documentation standards](docs/documentation-standard.md) apply to user-facing text
and screenshots.

## Start a branch

From a clean checkout:

```bash
git fetch origin
git switch -c fix/describe-the-change origin/dev
```

Keep unrelated local work on its own branch/worktree. Do not merge locally into
`dev` or push directly to `dev`/`main` to bypass review. Urgent fixes use the same
reviewed path; release promotion follows the
[release workflow](docs/development/releasing.md).

## Prepare a local development environment

Use Python 3.12 and Node.js 22, matching CI. From the repository root:

```bash
python3.12 -m venv backend/.venv
source backend/.venv/bin/activate
python -m pip install -r backend/requirements.txt
npm --prefix apps/ui ci
npm --prefix apps/telemetry-worker ci
```

The full requirements file includes all provider runtimes and development tools.
For a platform-specific native environment, use the base, matching provider and
development requirements as described in [testing](docs/development/testing.md).
Do not add conversion dependencies to the live application's environment.

For direct backend/UI development, use dedicated writable development paths and
non-production integration credentials. This example runs the backend on loopback;
run it from `backend/` with the virtual environment active:

```bash
mkdir -p ../config ../data/development
export CONFIG_FILE="$PWD/../config/development.json"
export DATA_DIR="$PWD/../data/development"
export DB_PATH="$PWD/../data/development/speciesid.db"
export SPECIES_CATALOG_PATH="$PWD/../data/development/species_catalog.db"
export MEDIA_CACHE_DIR="$PWD/../data/development/media_cache"
export MODEL_DIR="$PWD/../data/development/models"
uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

Startup applies migrations to these development databases. Never point a local
experiment, reset, test fixture or migration rehearsal at production mounts.
Configure your development Frigate/MQTT connection only when needed; a live
connection can ingest real events and write sublabels or send enabled notifications.
Keep outbound integrations disabled unless you intend their real effects.

In another terminal, from the repository root:

```bash
VITE_BACKEND_PROXY_TARGET=http://127.0.0.1:8000 npm --prefix apps/ui run dev
```

Open `http://localhost:3000`. Vite proxies `/api` and `/health` to that backend;
without the override its committed target is `http://yawamf-backend:8000`, suitable
for the legacy Docker network rather than a direct host process. Native FastAPI
OpenAPI is at `http://127.0.0.1:8000/docs`.

To run the published application instead of local source servers, follow
[Getting started](docs/setup/getting-started.md). The default `docker-compose.yml`
is a legacy split deployment; it is not a shortcut for building the current
monolith locally.

## Implement and prove the change

1. Reproduce the problem with a failing test. Keep pure policy tests independent
   of databases, networks and models; substitute external services at their boundary.
2. Implement the smallest change that preserves history, identity, secrets and
   owner choices. Review second-order effects on imports, worker recovery,
   media cleanup, notifications and guests when they share the affected path.
3. Add a reversible migration for every schema change in the correct stream.
   Keep one head in each stream and prove upgrade, downgrade and repeated upgrade
   against disposable databases. Never edit a released migration.
4. Update user-facing documentation and **Unreleased** in `CHANGELOG.md` when
   behaviour, settings, endpoints or UI labels change. Pure documentation cleanup
   does not invent a new release version or date.
5. Run the gates in [testing](docs/development/testing.md), including root-level
   lint/format, backend regression coverage, frontend check/unit/dead-code/build,
   telemetry tests and documentation consistency. Add browser interactions or
   trusted-host hardware checks where the change needs them.

API changes also require regenerated OpenAPI and frontend types. From `backend/`:

```bash
python scripts/export_openapi.py
python scripts/export_openapi_types.py
python scripts/export_openapi.py --check
python scripts/export_openapi_types.py --check
```

A release version bump happens before those exports, because the schema embeds
the application version. Models need the checkpoint's actual preprocessing and
output mapping, then hardware/accuracy evidence with clear limits; follow
[model conversion](docs/conversions/birder-model-conversion.md).

## Commit and open a pull request

Stage only the intended paths and commit after the required checks are green.
Use a message describing the concrete outcome. Commit messages, PR descriptions
and issue comments have no tool attribution or co-author trailers.

Push the short-lived branch and open a PR into `dev`. State:

- the problem and resulting behaviour;
- included/excluded scope and any migration, data, security or operational risk;
- checks actually completed, including material limitations.

Wait for required checks and resolve blocking review conversations before merging.
An image build is separate from a successful merge: documentation-only paths can
skip image publication. Verify the exact commit and completed promotion before
claiming a channel tag contains the change.

## Verify a published development image

[Build and Push Docker Images](.github/workflows/build-and-push.yml) publishes
commit candidates first. Full, CPU, Intel and CUDA startup checks and the
shared-volume full → CPU → full persistence gate must pass before mutable tags
are promoted. Packaging a provider does not certify a physical accelerator.

For a Compose-managed test installation, the monolith supports
`YAWAMF_MONALITHIC_TAG=dev`, `dev-cpu`, `dev-intel` and `dev-cuda`. Use a dedicated
stack and data paths; preserve a working production installation. Git-managed
platforms must use their own sync/deploy workflow. See
[hardware acceleration](docs/setup/hardware-acceleration.md) for packaging,
provider selection, active runtime and same-commit rollback checks.

Publishing a stable release requires a separate reviewed release state, matching
version/tag, green exact-tag checks and human-first release notes. Follow
[releasing](docs/development/releasing.md); merging a documentation PR does not
publish a new application release.
