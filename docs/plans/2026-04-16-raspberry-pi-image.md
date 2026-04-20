# Raspberry Pi ARM64 Image Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add a separate monolithic ARM64 Raspberry Pi image with docs and CI publishing, without changing the main monolith image behavior.

**Architecture:** Reuse the existing monolith Dockerfile, but make architecture-specific dependencies conditional. Publish a dedicated `yawamf-monalithic-rpi` image from CI and document it as a best-effort ARM64 path.

**Tech Stack:** Docker, Docker Buildx, GitHub Actions, Python requirements markers, Markdown docs

---

### Task 1: Make ARM64 Python dependencies explicit

**Files:**
- Modify: `backend/requirements.txt`
- Test: local ARM64 dependency resolution check via Docker build

**Step 1: Write the failing test**

Document the expected behavior before code:

- ARM64 installs `onnxruntime`
- non-ARM64 keeps `onnxruntime-gpu[cuda,cudnn]`

**Step 2: Run test to verify it fails**

Run:

```bash
docker buildx build --platform linux/arm64 -f /config/workspace/YA-WAMF/Dockerfile /config/workspace/YA-WAMF --target backend-builder
```

Expected before fix: dependency resolution or wheel build path is unsafe for ARM64 because `onnxruntime-gpu` remains in the graph.

**Step 3: Write minimal implementation**

Change `backend/requirements.txt` to use environment markers, for example:

```txt
onnxruntime-gpu[cuda,cudnn]>=1.24.0 ; platform_machine != "aarch64"
onnxruntime>=1.24.0 ; platform_machine == "aarch64"
```

Keep OpenVINO pinned as-is for now unless ARM64 build evidence proves it must also be conditioned.

**Step 4: Run test to verify it passes**

Run the same `docker buildx build --platform linux/arm64 ... --target backend-builder` command.

Expected: dependency install/wheel build progresses past the previous blocker.

**Step 5: Commit**

```bash
git add backend/requirements.txt
git commit -m "build: make onnxruntime dependency architecture-aware"
```

### Task 2: Make the monolith Dockerfile ARM-safe

**Files:**
- Modify: `Dockerfile`
- Test: ARM64 monolith image build

**Step 1: Write the failing test**

Use an ARM64 build attempt as the regression test. The current Intel GPU runtime setup is x86-specific and should be skipped on ARM64.

**Step 2: Run test to verify it fails**

Run:

```bash
docker buildx build --platform linux/arm64 -f /config/workspace/YA-WAMF/Dockerfile /config/workspace/YA-WAMF
```

Expected before fix: the Intel GPU APT setup is inappropriate for ARM64.

**Step 3: Write minimal implementation**

Wrap the Intel GPU repository and package install block in an architecture check, for example using `dpkg --print-architecture` or `uname -m`.

Implementation constraints:

- keep existing x86 behavior unchanged
- still install generic runtime packages needed by the app on ARM64
- only skip the Intel GPU repo/key/package path on ARM64

**Step 4: Run test to verify it passes**

Run the same ARM64 monolith `docker buildx build` command.

Expected: Dockerfile completes or progresses past the Intel GPU setup stage successfully.

**Step 5: Commit**

```bash
git add Dockerfile
git commit -m "build: guard monolith Intel GPU setup on arm64"
```

### Task 3: Add dedicated Raspberry Pi image publishing in CI

**Files:**
- Modify: `.github/workflows/build-and-push.yml`
- Test: workflow syntax review plus targeted YAML inspection

**Step 1: Write the failing test**

Define the expected release behavior:

- a dedicated `yawamf-monalithic-rpi` image is published
- it targets `linux/arm64`
- it runs on release tags and manual dispatch
- it does not replace the main monolith image flow

**Step 2: Run test to verify it fails**

Inspect current workflow:

```bash
rg -n "build-monolith|buildx|qemu|platforms|yawamf-monalithic-rpi" /config/workspace/YA-WAMF/.github/workflows/build-and-push.yml
```

Expected before fix: no dedicated RPi image job exists.

**Step 3: Write minimal implementation**

Add:

- `docker/setup-qemu-action`
- `docker/setup-buildx-action`
- a dedicated build-and-push job for `ghcr.io/jellman86/yawamf-monalithic-rpi`
- `platforms: linux/arm64`
- tag strategy aligned with release tags and optional manual dispatch

Keep the main image jobs intact.

**Step 4: Run test to verify it passes**

Run:

```bash
rg -n "yawamf-monalithic-rpi|setup-qemu-action|setup-buildx-action|platforms: linux/arm64" /config/workspace/YA-WAMF/.github/workflows/build-and-push.yml
```

Expected: all four elements are present in the workflow.

**Step 5: Commit**

```bash
git add .github/workflows/build-and-push.yml
git commit -m "ci: publish dedicated arm64 raspberry pi monolith image"
```

### Task 4: Add Raspberry Pi setup documentation

**Files:**
- Create: `docs/setup/raspberry-pi.md`
- Modify: `docs/index.md`
- Modify: `README.md`
- Test: doc link and wording review

**Step 1: Write the failing test**

Define the minimum required doc outcomes:

- users can discover the Pi guide from README and docs index
- guide explains support status, image name, setup steps, and limitations

**Step 2: Run test to verify it fails**

Run:

```bash
rg -n "raspberry-pi|yawamf-monalithic-rpi" /config/workspace/YA-WAMF/README.md /config/workspace/YA-WAMF/docs/index.md /config/workspace/YA-WAMF/docs/setup
```

Expected before fix: no dedicated Pi setup guide exists.

**Step 3: Write minimal implementation**

Create `docs/setup/raspberry-pi.md` with:

- support statement: best-effort, not maintainer hardware-validated yet
- hardware/OS expectations: Pi 4/5, 64-bit OS
- image reference: `ghcr.io/jellman86/yawamf-monalithic-rpi`
- storage recommendation: SSD preferred
- recommended model/settings guidance
- known limitations: CPU-only inference, slower large models, no CUDA/OpenVINO acceleration
- compose example using the Pi image

Then add links from `README.md` and `docs/index.md`.

**Step 4: Run test to verify it passes**

Run:

```bash
rg -n "raspberry-pi|yawamf-monalithic-rpi" /config/workspace/YA-WAMF/README.md /config/workspace/YA-WAMF/docs/index.md /config/workspace/YA-WAMF/docs/setup/raspberry-pi.md
```

Expected: the new guide and both links are present.

**Step 5: Commit**

```bash
git add README.md docs/index.md docs/setup/raspberry-pi.md
git commit -m "docs: add raspberry pi arm64 setup guide"
```

### Task 5: Verify the full path

**Files:**
- Verify: `backend/requirements.txt`
- Verify: `Dockerfile`
- Verify: `.github/workflows/build-and-push.yml`
- Verify: `README.md`
- Verify: `docs/index.md`
- Verify: `docs/setup/raspberry-pi.md`

**Step 1: Run ARM64 build verification**

Run:

```bash
docker buildx build --platform linux/arm64 -f /config/workspace/YA-WAMF/Dockerfile /config/workspace/YA-WAMF
```

Expected: the monolith image builds successfully for ARM64, or at minimum reaches a concrete new blocker that is not the original GPU/runtime issue.

**Step 2: Run text verification**

Run:

```bash
rg -n "yawamf-monalithic-rpi|raspberry-pi|platforms: linux/arm64|setup-qemu-action|setup-buildx-action" /config/workspace/YA-WAMF/README.md /config/workspace/YA-WAMF/docs/index.md /config/workspace/YA-WAMF/docs/setup/raspberry-pi.md /config/workspace/YA-WAMF/.github/workflows/build-and-push.yml
```

Expected: all new user-facing and CI references are present.

**Step 3: Run existing lightweight repo verification**

Run:

```bash
npm --prefix /config/workspace/YA-WAMF/apps/ui run check
/config/workspace/YA-WAMF/backend/venv/bin/python -m pytest /config/workspace/YA-WAMF/tests/unit -q
```

Expected:

- `svelte-check found 0 errors and 0 warnings`
- backend unit tests pass

**Step 4: Commit**

```bash
git add backend/requirements.txt Dockerfile .github/workflows/build-and-push.yml README.md docs/index.md docs/setup/raspberry-pi.md
git commit -m "feat: add raspberry pi arm64 monolith image path"
```
