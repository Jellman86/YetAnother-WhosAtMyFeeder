# Inference runtime image flavors

**Roadmap item:** pre-3.0 deployment and performance hardening; supports the
[monolith-only 3.0 runtime](../../ROADMAP.md#17-breaking-changes--removals--required-at-30)
without reintroducing a split application deployment.
**Standards applied:** [CLAUDE.md](../../CLAUDE.md) §§1, 2, 6 and 9,
[documentation standard](../documentation-standard.md), and the existing
[hardware-acceleration guide](../setup/hardware-acceleration.md).
**Status:** Implemented on `dev`, including image-aware on-hardware provider validation.

## 1. Decision

Publish four x86-64 variants of the same monolithic YA-WAMF application:

| Image flavor | Packaged inference providers | Intended host |
|---|---|---|
| `full` | ONNX CPU/CUDA and OpenVINO CPU/GPU/NPU | Compatibility, diagnostics and broad hardware testing |
| `cpu` | ONNX CPU | Hosts without a supported accelerator |
| `intel` | ONNX CPU and OpenVINO CPU/GPU/NPU | Intel CPU, integrated/discrete GPU or Core Ultra NPU |
| `cuda` | ONNX Runtime CUDA and its CPU execution provider | NVIDIA GPU hosts |

The Raspberry Pi image remains a separate ARM64 repository and uses the CPU dependency set while
reporting its image flavor as `rpi`.

This is a **runtime-family split**, not one image for every provider name. `intel_cpu`, `intel_gpu`
and `intel_npu` share OpenVINO and Intel's userspace driver stack, so separating those providers
would duplicate packages and create three image lines with no useful isolation. The CUDA package
already retains ONNX Runtime's CPU execution provider, so the CUDA image also has a safe local CPU
fallback.

Every flavor contains the same frontend, API, migrations, entrypoint and application code. It uses
the same `/config` and `/data` volumes. Switching flavor does not migrate or rewrite user data.

## 2. Why this is needed

The `d505d1ee` `dev` manifest was measured directly in GHCR before this change:

- compressed layers totalled approximately **3.58 GB**;
- the installed Python dependency layer was approximately **2.60 GB**;
- the retained wheel layer was approximately **696 MB**; and
- the operating-system/runtime layer, including Intel userspace, was approximately **234 MB**.

The current full image installs CUDA/cuDNN, OpenVINO and Intel GPU/NPU userspace on every x86 host.
That gives `auto` broad compatibility, but it also couples unrelated runtime upgrades, increases
first-pull and dependency-update cost, and expands the package/security surface for users who can
only use one accelerator family.

The family boundary follows the upstream runtime contracts:

- [ONNX Runtime's CUDA package](https://onnxruntime.ai/docs/install/) has a CUDA/cuDNN compatibility
  contract and is distinct from the CPU package.
- [NVIDIA Container Toolkit](https://docs.nvidia.com/datacenter/cloud-native/container-toolkit/latest/install-guide.html)
  remains a host prerequisite; packaging CUDA userspace does not remove the driver/runtime boundary.
- [OpenVINO system requirements](https://docs.openvino.ai/2026/about-openvino/release-notes-openvino/system-requirements.html?language=en)
  require separate Intel GPU/NPU drivers. OpenVINO itself supports CPU, GPU and NPU, which is why
  they remain one `intel` image family.

## 3. Compatibility and tag contract

Existing tags keep their current meaning and continue to publish the full image:

| Channel | Full compatibility tag | Additive variant tags |
|---|---|---|
| Development | `dev` | `dev-cpu`, `dev-intel`, `dev-cuda` |
| Main | `main` | `main-cpu`, `main-intel`, `main-cuda` |
| Stable floating | `latest` | `latest-cpu`, `latest-intel`, `latest-cuda` |
| Release | `vX.Y.Z` | `vX.Y.Z-cpu`, `vX.Y.Z-intel`, `vX.Y.Z-cuda` |
| Immutable commit | `<sha>` | `<sha>-cpu`, `<sha>-intel`, `<sha>-cuda` |

`docker-compose.monolith.yml` therefore remains unchanged in its default behaviour:
`YAWAMF_MONALITHIC_TAG=latest` selects `full`, and Quark's `YAWAMF_MONALITHIC_TAG=dev` continues to
select the full development image. An owner opts into a smaller image only by adding the appropriate
suffix to the existing tag variable.

There is no mutable provider installation at container startup. A container image is reproducible,
works without PyPI/GitHub access after it has been pulled, and never edits a live Python environment
in `/config` or `/data`.

## 4. Build architecture

### 4.1 Dependency sets

Split Python requirements into one shared runtime set, one development/test set, and four provider
sets. `backend/requirements.txt` remains the full developer environment so the documented local
workflow does not change. Container builds install only:

```text
requirements-base.txt + requirements-provider-<resolved flavor>.txt
```

`rpi` resolves to the CPU provider file. Provider files are intentionally small and mutually
exclusive: CPU and Intel use `onnxruntime`; CUDA and full use `onnxruntime-gpu`; only Intel and full
install OpenVINO.

### 4.2 Docker layers

The monolith Dockerfile accepts `RUNTIME_FLAVOR`, defaulting to `full`. A shared, testable shell
helper validates the flavor, resolves its provider requirements and decides whether Intel userspace
belongs in the image. The legacy split backend continues to build only the full runtime until that
deployment is removed in 3.0; it consumes the same base/full requirement files and layer improvements
but does not create another provider-variant matrix for a deprecated artifact.

The final image consumes wheels from the builder through a BuildKit bind mount. It does not `COPY`
the wheelhouse into a permanent layer. Development tools (`pytest`, Coverage and Ruff) are excluded
from runtime images. These changes reduce all flavors, including `full`, without changing runtime
behaviour. This follows Docker's guidance to use
[multi-stage builds](https://docs.docker.com/build/building/multi-stage/) to leave build-only tools
behind and [ephemeral build bind mounts](https://docs.docker.com/build/cache/optimize/#use-bind-mounts)
when an input should not persist as an image or cache layer.

The Intel GPU packages remain mandatory for `full` and `intel`. The currently Quark-validated
[Intel NPU driver v1.17.0](https://github.com/intel/linux-npu-driver/releases/tag/v1.17.0)
stays pinned during this packaging change; changing that driver at the same time would make
an image-layout regression indistinguishable from a hardware-runtime regression. Its installation
is mandatory and its three upstream release assets are SHA-256 verified, so CI cannot silently
publish an Intel-capable image with a missing or replaced NPU userspace package. Runtime capability
probes still decide whether a host actually exposes an NPU. A future driver update must update the
reviewed digests and be hardware-validated independently.

### 4.3 Runtime identity and diagnostics

Each image sets `YAWAMF_IMAGE_FLAVOR` (`full`, `cpu`, `intel`, `cuda` or `rpi`). Runtime diagnostics
expose:

- the image flavor;
- providers the flavor is designed to package;
- providers actually available on this host; and
- a machine-readable warning when an explicitly selected provider cannot exist in that flavor.

Hardware and package availability remain separate. For example, `cuda` means the CUDA runtime is
packaged; `cuda_available=false` can still be correct when NVIDIA Container Toolkit or a GPU is
missing. `auto` never raises a flavor warning because falling back to an actually available CPU path
is its documented behaviour.

The UI-triggered validation contract uses the intersection of the providers packaged by this
flavor, providers whose runtime/device probe passes on the host, and providers supported by the
selected model. Every candidate runs in an isolated process. ONNX CPU/CUDA and OpenVINO CPU/GPU/NPU
are compared against a CPU baseline on real bird images when the model-evaluation panel is
available. The full image evaluates both runtime families: merely having OpenVINO CPU installed no
longer prevents CUDA from being tested. Persisted eligibility records the exact flavor per model;
after a flavor switch the model must be revalidated even when the new image packages a provider
with the same name.

## 5. CI and publication

The image workflow uses a four-entry matrix. It first publishes immutable SHA tags for all x86
flavors from the same commit. `full` retains the unsuffixed SHA; other matrix entries append their
stable suffix. Mutable `dev`, `main`, release and `latest` tags are promoted from those exact
manifests only after the complete validation chain succeeds.

Validation is layered:

1. Pure tests verify flavor normalization, provider-family mapping and wrong-flavor warnings.
2. Deployment-contract tests verify dependency isolation, default compatibility tags and the CI
   publication matrix.
3. A shell contract tests every flavor and rejects unsupported flavor/architecture combinations.
4. Existing monolith smoke and non-root tests continue to build and run `full`, including an
   assertion that the image reports `YAWAMF_IMAGE_FLAVOR=full`.
5. Each immutable matrix entry starts without accelerator passthrough, reaches its Docker
   healthcheck, reports the expected flavor, and passes an explicit in-container healthcheck. This
   proves the required CPU fallback path starts even when accelerator hardware is absent.
6. A full → CPU → full round trip uses the same named `/config` and `/data` volumes. It proves the
   configured provider is not rewritten, application config plus a model artifact and its sidecar
   remain byte-identical, SQLite stays healthy with persisted state intact, and all images report
   the same Git identity.
7. A promotion job verifies all four immutable manifests exist before moving any mutable channel
   tags. The update/version marker is published only after promotion.
8. The publish matrix proves every flavor can resolve dependencies and build.
9. Quark remains the full-image Intel GPU/NPU validation target. The application validation sweep
   is covered for every flavor/provider intersection; dedicated CUDA execution on physical NVIDIA
   hardware remains an explicit follow-up rather than a claim inferred from a build.

The workflow uses per-flavor BuildKit caches and GHCR layer de-duplication. A failure in any flavor
or the persistence round trip leaves existing mutable tags untouched and blocks the version
publication marker, preventing the update service from advertising an incomplete image family.

## 6. User documentation

Update the hardware guide first: it owns the choice table, exact tags, host prerequisites and the
distinction between “packaged” and “available”. Keep Getting Started and the README on the full image
for the compatibility transition, with a short link to the smaller alternatives. Update:

- `README.md` and `docs/setup/getting-started.md`;
- `docs/setup/hardware-acceleration.md`;
- `docs/setup/docker-stack.md` and `docs/setup/migrate-split-to-monolith.md`;
- `docs/setup/raspberry-pi.md`, `.env.example` and `.env.rpi.example`;
- `docs/setup/configuration.md`, `docs/setup/environment-variables.md`, and the
  troubleshooting/API runtime-field references;
- `docs/features/ai-models.md`, model evaluation/accuracy testing, and conversion guidance;
- `DEVELOPER.md`, `DEVELOPMENT.md`, `INTEGRATION_TESTING.md`, and the release checklist/template;
- `docs/features/telemetry.md`; and
- `ROADMAP.md` plus `CHANGELOG.md`.

Do not present a smaller image as faster inference. It improves distribution size, isolation and
runtime maintenance; inference performance is still decided by the model, hardware and active
provider.

## 7. Rollout and rollback

### Rollout

1. Land the additive flavors while retaining the current full tags.
2. Let CI publish all flavors for `dev`.
3. Deploy and validate the unchanged `dev` full image on Quark.
4. For controlled Quark comparison, use the Dockhand API only and select the immutable full tag for
   the successful commit. Then change only `YAWAMF_MONALITHIC_TAG` to the same SHA with `-intel`,
   leaving the Git-managed Compose project and its `/config` and `/data` mounts unchanged. Restore
   the unsuffixed SHA through Dockhand after testing. Never pull or edit Compose directly on Quark.
5. Publish the same matrix for the next release and document flavor selection as optional.
6. Use anonymous telemetry only to understand adoption; do not remove `full` based on assumptions.

### Rollback

Changing back to the same commit's unsuffixed tag restores `full`. No database, model or
configuration rollback is required because all flavors use identical application code and
persistent-volume contracts. If a variant build or switch verification fails, two-phase publication
leaves the previous mutable flavor family in place and does not publish the update-version marker.

## 8. Risks and second-order consequences

- **More artifacts can drift.** One matrix and contract tests generate every tag from one Dockerfile
  and commit; no copied Dockerfiles are allowed.
- **A packaged runtime can be mistaken for working hardware.** Diagnostics keep packaged providers
  separate from detected/validated providers, and model activation retains its on-host gate.
- **CPU fallback could disappear accidentally.** Every flavor includes an ONNX CPU execution path;
  tests enforce the mapping.
- **Provider-specific dependency upgrades can diverge.** That isolation is intentional, but a
  release still publishes one application version and must pass every image build before it is
  advertised.
- **Registry storage and CI time increase.** Shared layers de-duplicate in GHCR; per-flavor caches and
  parallel matrix builds contain CI cost. The substantial reduction in user pull size and coupled
  dependency risk justifies the bounded matrix.
- **The full image remains large.** This is deliberate during compatibility testing. Removing it is
  not part of this change and would require a separately reviewed migration decision.

## 9. Acceptance criteria

- Unsuffixed tags still build `full`; existing Compose and Quark configuration need no edit.
- `cpu`, `intel`, `cuda` and `rpi` contain only their declared provider dependency families.
- Every flavor retains CPU fallback and starts without accelerator hardware.
- Intel system packages are absent from `cpu`, `cuda` and `rpi`.
- Runtime and telemetry report the build flavor independently from the branch/tag.
- An explicit provider/flavor mismatch is visible in diagnostics and falls back safely.
- A full → CPU → full CI round trip preserves config, database state and model storage while keeping
  the explicitly selected provider unchanged.
- All four x86 variants publish from one CI matrix; RPi publishes with `RUNTIME_FLAVOR=rpi`.
- Full monolith smoke, non-root smoke, backend/frontend tests, lint, formatting, docs consistency and
  repository diff checks pass.
- `CHANGELOG.md` records the behaviour and all setup/migration guidance is current.

## 10. Implementation record

The implementation uses one validated flavor contract in `docker/runtime-flavor.sh`, split runtime
and development requirement files under `backend/`, and one `RUNTIME_FLAVOR` argument in the
monolith Dockerfile. The backend exposes image identity and mismatch state through classifier
status; the advanced Detection settings surface presents the result as a small inline diagnostic
in all nine locales rather than adding another configuration card.

The build workflow publishes immutable and smoke-starts `full`, `cpu`, `intel`, and `cuda` from the
same commit. It then performs the persistent full → CPU → full switch contract before promoting
channel tags. Existing unsuffixed tags and both existing full-image smoke tests remain unchanged in
meaning. The Raspberry Pi job explicitly builds `rpi` from the CPU requirement set.

Local verification completed with 1,551 backend tests passing (65 platform/model skips), 543
frontend tests passing, a clean production frontend build, zero Svelte errors or warnings, clean
Ruff lint/format, shell contract and syntax checks, generated API type parity, documentation
consistency, workflow YAML parsing, dependency dry-run resolution, and a clean repository diff
check. The local workstation has no Docker client, so image build/start and hardware execution are
intentionally left to the mandatory CI smoke matrix and the Quark rollout steps instead of being
claimed from source-only checks.
