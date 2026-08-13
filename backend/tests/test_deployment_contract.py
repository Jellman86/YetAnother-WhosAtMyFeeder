from pathlib import Path
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
    assert "${{ github.sha }}${{ matrix.suffix }}" in workflow


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
    assert "${{ github.sha }}-cpu" in workflow
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
    assert "${{ github.sha }}${{ matrix.suffix }}" in build_job
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

    immutable_tag = "yawamf-monalithic-rpi:${{ github.sha }}"
    assert immutable_tag in rpi_job
    assert "monolith_runtime_flavor_smoke.sh" in rpi_job
    assert '"rpi"' in rpi_job
    assert '"linux/arm64"' in rpi_job
    assert 'platform="${3:-}"' in smoke
    assert 'docker_args+=(--platform "$platform")' in smoke
    assert "yawamf-monalithic-rpi:${{ env.IMAGE_TAG }}" not in rpi_job.split("Smoke-test Raspberry Pi image", 1)[0]
    assert rpi_job.index("Smoke-test Raspberry Pi image") < rpi_job.index("Promote Raspberry Pi monolithic tag")


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
