from pathlib import Path

import pytest
import xml.etree.ElementTree as ET


REPO_ROOT = Path(__file__).resolve().parents[2]
BACKEND_ROOT = REPO_ROOT / "backend"


def test_recommended_monolith_defaults_to_stable_release_channel() -> None:
    compose = (REPO_ROOT / "docker-compose.monolith.yml").read_text(encoding="utf-8")
    example_env = (REPO_ROOT / ".env.example").read_text(encoding="utf-8")
    deployment_guides = [
        (REPO_ROOT / relative_path).read_text(encoding="utf-8")
        for relative_path in (
            "README.md",
            "DEVELOPMENT.md",
            "DEVELOPER.md",
            "INTEGRATION_TESTING.md",
            "docs/setup/getting-started.md",
            "docs/setup/environment-variables.md",
            "docs/setup/hardware-acceleration.md",
        )
    ]

    assert "${YAWAMF_MONALITHIC_TAG:-latest}" in compose
    assert "${YAWAMF_MONALITHIC_TAG:-dev}" not in compose
    assert "YAWAMF_MONALITHIC_TAG=latest" in example_env
    assert "YAWAMF_MONALITHIC_TAG=latest-intel" in deployment_guides[-1]
    # This misspelling is an established public compatibility contract. Do not
    # silently introduce a differently spelled variable in switching guidance.
    assert all("YAWAMF_MONOLITHIC_TAG" not in guide for guide in deployment_guides)
    assert all("YAWAMF_MONOLITHIC_IMAGE" not in guide for guide in deployment_guides)


def test_active_docs_describe_the_complete_runtime_flavor_contract() -> None:
    docs = {
        relative_path: (REPO_ROOT / relative_path).read_text(encoding="utf-8")
        for relative_path in (
            "DEVELOPER.md",
            "DEVELOPMENT.md",
            "INTEGRATION_TESTING.md",
            "docs/api.md",
            "docs/development/releasing.md",
            "docs/features/ai-models.md",
            "docs/features/model-accuracy.md",
            "docs/setup/configuration.md",
            "docs/setup/hardware-acceleration.md",
            "docs/troubleshooting/diagnostics.md",
        )
    }

    hardware = docs["docs/setup/hardware-acceleration.md"]
    for tag in ("latest", "latest-cpu", "latest-intel", "latest-cuda"):
        assert f"`{tag}`" in hardware
    assert "`/config` and `/data` mounts" in hardware
    assert "full → CPU → full" in hardware

    api = docs["docs/api.md"]
    diagnostics = docs["docs/troubleshooting/diagnostics.md"]
    for field in ("image_flavor", "packaged_inference_providers", "image_flavor_warning"):
        assert f"`{field}`" in api
        assert field in diagnostics

    assert "full, CPU, Intel, and CUDA" in docs["DEVELOPER.md"]
    assert "full → CPU → full" in docs["docs/development/releasing.md"]
    assert "CPU, Intel, and Raspberry Pi images do not contain the CUDA runtime" in docs["INTEGRATION_TESTING.md"]
    assert "The official YA-WAMF images now package the CUDA" not in "\n".join(docs.values())


def test_unraid_template_keeps_provider_selection_in_app_and_documents_flavors() -> None:
    template_path = REPO_ROOT / "unraid/yawamf.xml"
    root = ET.parse(template_path).getroot()
    guide = (REPO_ROOT / "docs/setup/unraid.md").read_text(encoding="utf-8")

    assert root.findtext("Repository") == "ghcr.io/jellman86/yawamf-monalithic:latest"
    config_targets = {str(config.get("Target") or "") for config in root.findall("Config")}
    assert "CLASSIFICATION__INFERENCE_PROVIDER" not in config_targets
    assert "YAWAMF_IMAGE_FLAVOR" not in config_targets

    requirements = root.findtext("Requires") or ""
    for tag in ("latest-cpu", "latest-intel", "latest-cuda"):
        assert tag in requirements
        assert f"`{tag}`" in guide
    assert "Settings → Detection" in requirements

    assert "CLASSIFICATION__INFERENCE_PROVIDER" in guide
    assert "overrides the in-app value" in guide
    assert "NVIDIA Driver" in guide
    assert "NVIDIA_VISIBLE_DEVICES" in guide
    assert "NVIDIA_DRIVER_CAPABILITIES" in guide


def test_full_runtime_remains_the_unsuffixed_compatibility_default() -> None:
    dockerfile = (REPO_ROOT / "Dockerfile").read_text(encoding="utf-8")
    workflow = (REPO_ROOT / ".github/workflows/build-and-push.yml").read_text(encoding="utf-8")

    assert "ARG RUNTIME_FLAVOR=full" in dockerfile
    assert "RUNTIME_FLAVOR=${{ matrix.flavor }}" in workflow
    assert "flavor: full" in workflow
    assert 'suffix: ""' in workflow
    for flavor in ("cpu", "intel", "cuda"):
        assert f"flavor: {flavor}" in workflow
        assert f'suffix: "-{flavor}"' in workflow


def test_each_published_runtime_flavor_gets_a_no_accelerator_smoke_test() -> None:
    workflow = (REPO_ROOT / ".github/workflows/build-and-push.yml").read_text(encoding="utf-8")
    smoke_script = REPO_ROOT / "tests/e2e/monolith_runtime_flavor_smoke.sh"

    assert smoke_script.exists()
    assert "monolith_runtime_flavor_smoke.sh" in workflow
    assert "${{ matrix.flavor }}" in workflow
    assert "${{ env.CANARY }}${{ matrix.suffix }}" in workflow


def test_runtime_flavor_builds_use_a_cache_capable_buildx_driver() -> None:
    workflow = (REPO_ROOT / ".github/workflows/build-and-push.yml").read_text(encoding="utf-8")
    build_job = workflow.split("  build-monolith:", 1)[1].split("  build-monolith-rpi:", 1)[0]

    setup_offset = build_job.index("uses: docker/setup-buildx-action@v4")
    build_offset = build_job.index("uses: docker/build-push-action@v7")
    assert setup_offset < build_offset
    assert "cache-from: type=gha,scope=monolith-${{ matrix.flavor }}" in build_job
    assert "cache-to: ${{ matrix.cache_export }}" in build_job
    assert 'cache_export: ""' in build_job
    for flavor in ("cpu", "intel", "cuda"):
        assert f"cache_export: type=gha,mode=max,scope=monolith-{flavor}" in build_job


def test_publication_is_blocked_until_full_and_cpu_share_persistent_state() -> None:
    workflow = (REPO_ROOT / ".github/workflows/build-and-push.yml").read_text(encoding="utf-8")
    switch_script = REPO_ROOT / "tests/e2e/monolith_runtime_flavor_switch.sh"

    assert switch_script.exists()
    switch_contract = switch_script.read_text(encoding="utf-8")
    assert "monolith_runtime_flavor_switch.sh" in workflow
    assert "verify-monolith-flavor-switch:" in workflow
    assert "needs: [build-monolith]" in workflow
    assert "needs: [promote-monolith-flavors]" in workflow
    assert "${{ env.CANARY }}-cpu" in workflow
    assert "/config/config.json" in switch_contract
    assert "/data/speciesid.db" in switch_contract
    assert "/data/models/runtime-flavor-switch-contract/model.onnx" in switch_contract
    assert "/data/models/runtime-flavor-switch-contract/model_config.json" in switch_contract
    assert "PRAGMA integrity_check" in switch_contract
    assert "selected_provider_not_packaged" in switch_contract


def test_mutable_monolith_tags_are_promoted_only_after_switch_verification() -> None:
    workflow = (REPO_ROOT / ".github/workflows/build-and-push.yml").read_text(encoding="utf-8")
    build_job = workflow.split("  build-monolith:", 1)[1].split("  build-monolith-rpi:", 1)[0]
    promotion_job = workflow.split("  promote-monolith-flavors:", 1)[1].split("  # Record the version", 1)[0]

    assert "promote-monolith-flavors:" in workflow
    assert "needs: [verify-monolith-flavor-switch]" in promotion_job
    assert "${{ env.IMAGE_TAG }}${{ matrix.suffix }}" not in build_job
    assert "${{ env.CANARY }}${{ matrix.suffix }}" in build_job
    assert "docker buildx imagetools inspect" in promotion_job
    assert "docker buildx imagetools create" in promotion_job
    assert "needs: [promote-monolith-flavors]" in workflow


def test_image_flavor_selection_cannot_change_persistent_mount_paths() -> None:
    compose = (REPO_ROOT / "docker-compose.monolith.yml").read_text(encoding="utf-8")

    assert compose.count("./config:/config") == 1
    assert compose.count("./data:/data") == 1
    assert "RUNTIME_FLAVOR" not in compose
    assert "YAWAMF_IMAGE_FLAVOR" not in compose


def test_provider_requirement_files_are_isolated_by_runtime_family() -> None:
    requirements = {
        flavor: (BACKEND_ROOT / f"requirements-provider-{flavor}.txt").read_text(encoding="utf-8")
        for flavor in ("full", "cpu", "intel", "cuda")
    }

    assert "onnxruntime-gpu[cuda,cudnn]" in requirements["full"]
    assert "openvino>=" in requirements["full"]

    assert "onnxruntime>=" in requirements["cpu"]
    assert "onnxruntime-gpu" not in requirements["cpu"]
    assert "openvino" not in requirements["cpu"]

    assert "onnxruntime>=" in requirements["intel"]
    assert "onnxruntime-gpu" not in requirements["intel"]
    assert "openvino>=" in requirements["intel"]

    assert "onnxruntime-gpu[cuda,cudnn]" in requirements["cuda"]
    assert "openvino" not in requirements["cuda"]


def test_litert_runtime_markers_use_the_small_arm64_interpreter() -> None:
    base_requirements = (BACKEND_ROOT / "requirements-base.txt").read_text(encoding="utf-8")
    lines = [line.strip() for line in base_requirements.splitlines()]
    linux_cpu_line = next(line for line in lines if line.startswith("tensorflow-cpu"))
    arm64_line = next(line for line in lines if line.startswith("ai-edge-litert"))
    non_linux_line = next(line for line in lines if line.startswith("tensorflow;"))

    assert 'sys_platform == "linux"' in linux_cpu_line
    assert 'sys_platform == "linux"' in arm64_line
    assert "ai-edge-litert==2.1.6" in arm64_line
    assert not any(line.startswith("tensorflow-aarch64") for line in lines)
    assert 'sys_platform != "linux"' in non_linux_line


def test_monolith_compose_passes_classifier_pressure_controls_into_the_container() -> None:
    compose = (REPO_ROOT / "docker-compose.monolith.yml").read_text(encoding="utf-8")
    rpi_env = (REPO_ROOT / ".env.rpi.example").read_text(encoding="utf-8")

    assert "CLASSIFIER_IMAGE_MAX_CONCURRENT=${CLASSIFIER_IMAGE_MAX_CONCURRENT:-2}" in compose
    assert "CLASSIFIER_IMAGE_ADMISSION_TIMEOUT_SECONDS=${CLASSIFIER_IMAGE_ADMISSION_TIMEOUT_SECONDS:-0.5}" in compose
    assert "FRIGATE__CLIPS_ENABLED=${FRIGATE__CLIPS_ENABLED:-true}" in compose
    assert "CLASSIFIER_IMAGE_MAX_CONCURRENT=1" in rpi_env
    assert "CLASSIFICATION_IMAGE_MAX_CONCURRENT" not in rpi_env


def test_rpi_image_is_smoked_before_mutable_tags_are_promoted() -> None:
    workflow = (REPO_ROOT / ".github/workflows/build-and-push.yml").read_text(encoding="utf-8")
    rpi_job = workflow.split("  build-monolith-rpi:", 1)[1].split("  verify-monolith-flavor-switch:", 1)[0]
    smoke = (REPO_ROOT / "tests/e2e/monolith_runtime_flavor_smoke.sh").read_text(encoding="utf-8")

    immutable_tag = "yawamf-monalithic-rpi:${{ env.CANARY }}"
    assert immutable_tag in rpi_job
    assert "monolith_runtime_flavor_smoke.sh" in rpi_job
    assert '"rpi"' in rpi_job
    assert '"linux/arm64"' in rpi_job
    assert 'platform="${3:-}"' in smoke
    assert 'docker_args+=(--platform "$platform")' in smoke
    assert "yawamf-monalithic-rpi:${{ env.IMAGE_TAG }}" not in rpi_job.split("Smoke-test Raspberry Pi image", 1)[0]
    assert rpi_job.index("Smoke-test Raspberry Pi image") < rpi_job.index("Promote Raspberry Pi monolithic tag")


def test_each_run_promotes_only_the_canary_it_built() -> None:
    """The canary tag is keyed on the ref as well as the sha (#437).

    A push to main, its release tag, and the dev fast-forward build the same commit
    within minutes, each stamped with a different APP_BRANCH. When all three pushed
    the same `<sha>` canary, the tag run promoted whichever build landed last:
    v2.19.4's `latest*` said `dev`, v2.19.5's said `main`, and neither said `stable`.
    """
    workflow = (REPO_ROOT / ".github/workflows/build-and-push.yml").read_text(encoding="utf-8")
    monolith_jobs = workflow[workflow.index("  build-monolith:") : workflow.index("  publish-version:")]
    canary_step = "CANARY=${GITHUB_SHA}-$(printf '%s' \"${GITHUB_REF_NAME}\""

    for job in (
        "build-monolith:",
        "build-monolith-rpi:",
        "verify-monolith-flavor-switch:",
        "promote-monolith-flavors:",
    ):
        assert job in monolith_jobs
    assert monolith_jobs.count(canary_step) == 4, "every monolith job names the canary the same way"
    assert "yawamf-monalithic:${{ github.sha }}" not in monolith_jobs
    assert "yawamf-monalithic-rpi:${{ github.sha }}" not in monolith_jobs
    assert "yawamf-monalithic:${GITHUB_SHA}${suffix}" not in monolith_jobs
    assert "yawamf-monalithic:${CANARY}${suffix}" in monolith_jobs
    # The OCI revision label still names the commit; only the tag carries the ref.
    assert "org.opencontainers.image.revision=${{ github.sha }}" in monolith_jobs


def test_images_bundle_a_checksum_verified_cpu_fallback_classifier() -> None:
    dockerfile = (REPO_ROOT / "Dockerfile").read_text(encoding="utf-8")
    smoke = (REPO_ROOT / "tests/e2e/monolith_runtime_flavor_smoke.sh").read_text(encoding="utf-8")

    assert "104342d2d3480b3e66203073dac24f4e2dbb4c41" in dockerfile
    assert "350fcd8cf1df1560060d464595dfed8b174b05792788052896004848d9ad04f9" in dockerfile
    assert "a16108dfe3f8daff015b87a97ab6a17e717b9b1bccd719f6d8f747746d7b9277" in dockerfile
    assert "sha256sum -c" in dockerfile
    assert "releases/download/models/mobilenet_v2_birds_model_config.json" not in dockerfile
    assert (BACKEND_ROOT / "app/assets/model_config.json").exists()
    assert (BACKEND_ROOT / "app/assets/mobilenet-v2-inat-bird.LICENSE.txt").exists()
    assert (BACKEND_ROOT / "app/assets/mobilenet-v2-inat-bird.NOTICE.md").exists()
    assert 'status.get("loaded") is not True' in smoke
    assert "/api/classifier/classify" in smoke


def test_runtime_images_exclude_development_dependencies_and_permanent_wheelhouse() -> None:
    dockerfile = (REPO_ROOT / "Dockerfile").read_text(encoding="utf-8")

    assert "requirements-base.txt" in dockerfile
    assert 'yawamf-runtime-flavor requirements "$RUNTIME_FLAVOR"' in dockerfile
    assert "requirements-dev.txt" not in dockerfile
    assert "COPY --from=backend-builder /wheels /wheels" not in dockerfile
    assert "--mount=type=bind,from=backend-builder,source=/wheels,target=/wheels" in dockerfile


def test_intel_npu_assets_are_pinned_verified_and_required() -> None:
    dockerfile = (REPO_ROOT / "Dockerfile").read_text(encoding="utf-8")

    assert "NPU_VER=1.17.0.20250508-14912879441" in dockerfile
    assert "sha256sum -c" in dockerfile
    assert "cebbac7bdb56eb72529b8060bb1601afdcd4e90f2e5c29018b5ceaff98b7c63c" in dockerfile
    assert "24309e17063e94729330ae9c02c5f2ea8ca5c27cdb067303e4e26ad1f4656a13" in dockerfile
    assert "07ee5332d0523661f5b3cec69593197fecc95439c8a9a401905e05cb7690097b" in dockerfile
    assert '|| echo "WARN: Intel NPU driver install failed' not in dockerfile


def test_legacy_intel_gpu_assets_are_pinned_verified_and_do_not_downgrade_gmmlib() -> None:
    dockerfile = (REPO_ROOT / "Dockerfile").read_text(encoding="utf-8")

    assert "LEGACY_IGC_VER=1.0.17537.24" in dockerfile
    assert "LEGACY_COMPUTE_VER=24.35.30872.36" in dockerfile
    assert "LEGACY_LEVEL_ZERO_VER=1.5.30872.36" in dockerfile
    for checksum in (
        "c1e1ecdfe2064c047c552651cfdcdafc504f2033afafba65654338b880048b67",
        "dd016400f87fa2b6a9fa9fbcca7eb4a2629174a29de679709f9bec5cede88b0e",
        "40dfbd15ab62de036a00824b304a2aa1fa2d81ad60ef83da09cfe3c5a80c429f",
        "bbe71e4f414259e06a10cde72c29a2bd78d41b2bb2f6f8463b1806797fe66e85",
    ):
        assert checksum in dockerfile

    assert "intel-opencl-icd-legacy1_${LEGACY_COMPUTE_VER}_amd64.deb" in dockerfile
    assert "intel-level-zero-gpu-legacy1_${LEGACY_LEVEL_ZERO_VER}_amd64.deb" in dockerfile
    assert "libigdgmm12_22.5.0_amd64.deb" not in dockerfile
    assert "./*.deb" not in dockerfile


@pytest.mark.parametrize("dockerfile_path", ["Dockerfile", "backend/Dockerfile"])
def test_intel_gpu_runtime_is_pinned_verified_and_newer_than_the_crashing_apt_build(dockerfile_path: str) -> None:
    """The apt channel's compute-runtime 25.18 / IGC 2.11 crashed compiling models for the iGPU on the
    Debian 13 base, so the runtime and its compiler come from pinned, checksummed release assets."""
    dockerfile = (REPO_ROOT / dockerfile_path).read_text(encoding="utf-8")

    assert "COMPUTE_VER=26.35.39758.10" in dockerfile
    assert "IGC_VER=2.41.5" in dockerfile
    assert "GMM_VER=22.10.0" in dockerfile
    for checksum in (
        "0a6e64a663ae65a0fa02d6912ae3b6b37cf85b90c21cc423fd9fef70aaf4f628",
        "779e1b9e88098eb25711e9a8f67c2752665bad22f134aa40ed5649f6e1b87058",
        "61712caaddeba3d38e4f79e2a0fb23fea25596ca2d72c3144c6eea2331ec4301",
        "c19a641b953d55aebbf1d51bec364a84bf629f985e02fbbe6dc70224c0e88470",
        "6031a63d6e8a12ce61c14efc15f2c8e727061286e3820b8594e6d00615e04d54",
    ):
        assert checksum in dockerfile
    # IGC 2.x installs into /usr/local/lib; without ldconfig the driver cannot find it.
    assert "ldconfig" in dockerfile
    # The runtime itself must not come back from the apt channel.
    apt_lines = [line for line in dockerfile.splitlines() if line.strip().startswith(("intel-opencl-icd \\", "libze-intel-gpu1 \\"))]
    assert apt_lines == []


def test_every_published_image_names_its_git_revision() -> None:
    """A running container can be tied to its commit with `docker inspect` alone.

    Every image the workflow pushes carries the OCI revision, version, and source
    labels. The in-app update prompt does not read them: it compares the GIT_HASH
    build argument with the published commit, so the labels are metadata for
    operators and Dockhand, never an input to "is there an update?".
    """
    workflow = (REPO_ROOT / ".github/workflows/build-and-push.yml").read_text(encoding="utf-8")
    steps = workflow.split("uses: docker/build-push-action@")[1:]
    assert len(steps) >= 4, "expected the backend, frontend, monolith and rpi image builds"
    for step in steps:
        with_block = step.split("\n      - name:", 1)[0]
        assert "labels: |" in with_block
        assert "org.opencontainers.image.revision=${{ github.sha }}" in with_block
        assert "org.opencontainers.image.version=${{ env.APP_VERSION_BASE }}" in with_block
        assert "org.opencontainers.image.source=https://github.com/${{ github.repository }}" in with_block


def test_unraid_template_exposes_documentation_license_and_existing_brand_assets() -> None:
    from urllib.parse import urlparse
    from PIL import Image

    template = ET.parse(REPO_ROOT / "unraid/yawamf.xml").getroot()
    profile = ET.parse(REPO_ROOT / "ca_profile.xml").getroot()
    base = "https://raw.githubusercontent.com/Jellman86/YetAnother-WhosAtMyFeeder/main/"
    assert template.findtext("ReadMe") == (
        "https://github.com/Jellman86/YetAnother-WhosAtMyFeeder/blob/main/docs/setup/unraid.md"
    )
    assert template.findtext("License") == "MIT"
    assert template.findtext("Icon") == profile.findtext("Icon")
    for field in ("Icon", "Screenshot"):
        url = template.findtext(field)
        assert url and urlparse(url).scheme == "https" and url.startswith(base)
        path = REPO_ROOT / url.removeprefix(base)
        with Image.open(path) as asset:
            asset.verify()
        if field == "Icon":
            with Image.open(path) as icon:
                assert icon.size == (512, 512)


def test_unraid_connection_settings_remain_editable_after_restart() -> None:
    template = ET.parse(REPO_ROOT / "unraid/yawamf.xml").getroot()
    pinned_connections = [
        config.get("Target")
        for config in template.findall("Config")
        if (config.get("Target") or "").startswith("FRIGATE__")
    ]
    assert pinned_connections == []


def test_unraid_guide_has_a_local_template_import_and_complete_connection_setup() -> None:
    guide = (REPO_ROOT / "docs/setup/unraid.md").read_text(encoding="utf-8")
    assert "paste the template URL" not in guide
    assert "/boot/config/plugins/dockerMan/templates-user/my-YA-WAMF.xml" in guide
    assert "Frigate & MQTT connection" in guide
    assert "Settings → Connection" in guide
    assert "FRIGATE__FRIGATE_URL" in guide and "overrides" in guide
    assert "Docker Safe New" not in guide
