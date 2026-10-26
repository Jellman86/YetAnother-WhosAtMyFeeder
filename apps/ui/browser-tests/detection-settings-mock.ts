import { expect, type Page } from '@playwright/test';

// A realistic Detection tab: an Intel host with CPU, GPU and NPU routes, the
// registry's recommended lineup, both accurate bird finders and the fast
// fallback. Each test owns its counters, so saves and reads can be asserted.

const classifier = (model: Record<string, unknown>) => ({ artifact_kind: 'classifier', runtime: 'onnx', ...model });
const finder = (model: Record<string, unknown>) => ({
    artifact_kind: 'crop_detector', runtime: 'onnx', taxonomy_scope: 'system', advanced_only: true, ...model
});

const availableModels = [
    finder({
        id: 'bird_crop_detector', name: 'Bird Crop Detector', architecture: 'SSD-MobileNet V1 INT8',
        description: 'Fast bird-localization detector for generated thumbnail crops.', file_size_mb: 12.4,
        accuracy_tier: 'System', inference_speed: 'Fast', supported_inference_providers: ['cpu'], tier: 'fast',
        recommended_for: 'CPU-friendly cropped thumbnails.', estimated_ram_mb: 256, sort_order: 5, status: 'stable'
    }),
    finder({
        id: 'bird_crop_detector_accurate_yolox_tiny', name: 'Bird Crop Detector Accurate (YOLOX-Tiny)',
        architecture: 'YOLOX-Tiny', description: 'Higher-accuracy bird-localization detector.', file_size_mb: 19.3,
        accuracy_tier: 'Higher', inference_speed: 'Medium', tier: 'accurate', estimated_ram_mb: 512, sort_order: 6,
        supported_inference_providers: ['cpu', 'intel_cpu', 'cuda', 'intel_gpu', 'intel_npu'], status: 'experimental',
        recommended_for: 'Tighter generated thumbnail crops when CPU budget allows.'
    }),
    finder({
        id: 'bird_crop_detector_accurate_rfdetr_nano', name: 'Bird Finder (RF-DETR Nano)', architecture: 'RF-DETR Nano',
        description: 'Finds small and distant birds in full camera frames.', file_size_mb: 102.8,
        accuracy_tier: 'Higher', inference_speed: 'Slow', tier: 'accurate', estimated_ram_mb: 900, sort_order: 7,
        supported_inference_providers: ['cpu', 'intel_cpu', 'intel_gpu', 'intel_npu'], status: 'experimental',
        recommended_for: 'Feeder cameras where birds are small in a wide, high-resolution frame.'
    }),
    classifier({
        id: 'mobilenet_v2_birds', name: 'MobileNet V2 (Fast)', architecture: 'MobileNetV2', runtime: 'tflite',
        description: 'Lightweight iNat bird classifier (~960 species).', file_size_mb: 3.4, accuracy_tier: 'Medium',
        inference_speed: 'Fast (~30ms)', supported_inference_providers: ['cpu'], tier: 'cpu_only',
        taxonomy_scope: 'birds_only', recommended_for: 'CPU and low-RAM devices.', estimated_ram_mb: 128,
        advanced_only: true, sort_order: 10, status: 'stable', recommended_threshold: 0.7
    }),
    classifier({
        id: 'rope_vit_b14_inat21', name: 'RoPE ViT-B14 (Medium Accuracy)', architecture: 'RoPE-ViT-B14-CAPI',
        description: 'Mid-tier iNat21 classifier for 10,000 species.', file_size_mb: 375, accuracy_tier: 'Very High (87%+)',
        inference_speed: 'Medium-Slow (~220-400ms)', supported_inference_providers: ['cpu', 'cuda', 'intel_cpu', 'intel_npu'],
        tier: 'medium', taxonomy_scope: 'wildlife_wide', recommended_for: 'Most setups.', estimated_ram_mb: 1536,
        advanced_only: false, sort_order: 17, status: 'experimental', recommended_threshold: 0.45
    }),
    classifier({
        id: 'convnext_large_inat21', name: 'ConvNeXt Large (High Accuracy)', architecture: 'ConvNeXt-Large-MLP',
        description: 'iNat21 classifier for 10,000 species.', file_size_mb: 760, accuracy_tier: 'Very High (90%+)',
        inference_speed: 'Slow (~500-800ms)', supported_inference_providers: ['cpu', 'cuda', 'intel_cpu', 'intel_npu'],
        tier: 'large', taxonomy_scope: 'wildlife_wide', recommended_for: 'General-purpose wildlife classification.',
        estimated_ram_mb: 2048, advanced_only: false, sort_order: 20, status: 'stable', recommended_threshold: 0.45
    }),
    classifier({
        id: 'eva02_large_inat21', name: 'EVA-02 Large (Elite Accuracy)', architecture: 'EVA-02-Large',
        description: 'iNat21 classifier for 10,000 species.', file_size_mb: 1200, accuracy_tier: 'Elite (91%+)',
        inference_speed: 'Slow (~1s)', supported_inference_providers: ['cpu', 'cuda', 'intel_cpu', 'intel_npu'],
        tier: 'advanced', taxonomy_scope: 'wildlife_wide', recommended_for: 'Hosts with more compute and RAM.',
        estimated_ram_mb: 3072, advanced_only: true, sort_order: 30, status: 'stable', recommended_threshold: 0.45
    })
];

const ROPE = 'rope_vit_b14_inat21';
const YOLOX = 'bird_crop_detector_accurate_yolox_tiny';
const RFDETR = 'bird_crop_detector_accurate_rfdetr_nano';

function installed(id: string, extra: Record<string, unknown> = {}) {
    return {
        id, path: `/data/models/${id}`, labels_path: `/data/models/${id}/labels.txt`, is_active: false,
        ready: true, reason: 'ready', validated: true, validation_reason: 'validated',
        validated_inference_providers: ['cpu'], provider_preference_order: ['cpu'], ...extra
    };
}

export type DetectionMockOptions = {
    finderExecution?: Record<string, unknown>;
    savedFinder?: 'yolox_tiny' | 'rfdetr_nano';
    rfdetrInstalled?: boolean;
    saveFails?: boolean;
    savedProvider?: string;
    savedFinderProvider?: string;
};

export type DetectionMockState = {
    settingsReads: number;
    saves: Record<string, unknown>[];
    savedFinder: 'yolox_tiny' | 'rfdetr_nano';
    savedProvider: string;
    savedFinderProvider: string;
};

function classifierStatus(state: DetectionMockState, rfdetrInstalled: boolean, execution?: Record<string, unknown>) {
    const rfdetrChosen = state.savedFinder === 'rfdetr_nano';
    const finderInUse = rfdetrChosen && rfdetrInstalled ? RFDETR : YOLOX;
    return {
        loaded: true, error: null, labels_count: 10000, enabled: true, active_model_id: ROPE,
        image_execution_mode: 'subprocess', runtime_source: 'worker', selected_provider: state.savedProvider,
        active_provider: 'intel_npu', inference_backend: 'openvino', image_flavor: 'full',
        packaged_inference_providers: ['cpu', 'cuda', 'intel_cpu', 'intel_gpu', 'intel_npu'],
        host_available_providers: ['cpu', 'intel_cpu', 'intel_gpu', 'intel_npu'],
        available_providers: ['cpu', 'intel_cpu', 'intel_npu'],
        provider_preference_order: ['intel_npu', 'intel_cpu', 'cpu'],
        openvino_available: true, intel_cpu_available: true, intel_gpu_available: true, intel_npu_available: true,
        cuda_available: false, cuda_provider_installed: true, cuda_hardware_available: false,
        resolved_live_workers: 1, resolved_background_workers: 1, active_model_estimated_ram_mb: 1536,
        host_device_eligibility: { verified_providers: ['cpu', 'intel_cpu', 'intel_npu'], generated_at: '2026-10-20T09:12:00Z' },
        personalized_rerank_enabled: false, personalization_feedback_rows: 4, personalization_min_feedback_tags: 20,
        crop_detector: {
            last_execution: execution,
            model_id: finderInUse, chosen_model_id: rfdetrChosen ? RFDETR : YOLOX, selected_tier: 'accurate',
            resolved_tier: 'accurate', installed: true, healthy: true, enabled_for_runtime: true,
            reason: rfdetrChosen && !rfdetrInstalled ? 'fallback_default_accurate' : 'ready'
        }
    };
}

export async function openDetectionSettings(page: Page, options: DetectionMockOptions = {}): Promise<DetectionMockState> {
    const rfdetrInstalled = options.rfdetrInstalled ?? true;
    const state: DetectionMockState = {
        settingsReads: 0, saves: [], savedFinder: options.savedFinder ?? 'yolox_tiny',
        savedFinderProvider: options.savedFinderProvider ?? 'auto',
        savedProvider: options.savedProvider ?? 'auto'
    };
    await page.route('https://fonts.googleapis.com/**', route => route.fulfill({ body: '' }));
    await page.route('https://fonts.gstatic.com/**', route => route.abort());
    await page.route(url => url.pathname === '/health' || url.pathname.startsWith('/api/'), route => {
        const request = route.request();
        const path = new URL(request.url()).pathname;
        if (path === '/api/settings' && request.method() === 'POST') {
            const body = request.postDataJSON() as Record<string, unknown>;
            if (options.saveFails) {
                return route.fulfill({ status: 500, json: { detail: 'Settings store unavailable' } });
            }
            state.saves.push(body);
            if (body.bird_crop_accurate_detector === 'yolox_tiny' || body.bird_crop_accurate_detector === 'rfdetr_nano') {
                state.savedFinder = body.bird_crop_accurate_detector;
            }
            if (typeof body.bird_crop_inference_provider === 'string') state.savedFinderProvider = body.bird_crop_inference_provider;
            if (typeof body.inference_provider === 'string') state.savedProvider = body.inference_provider;
            return route.fulfill({ json: { status: 'updated' } });
        }
        if (path === '/api/settings') {
            state.settingsReads++;
            return route.fulfill({ json: {
                frigate_url: 'http://frigate:5000', mqtt_server: 'mqtt', mqtt_port: 1883, mqtt_auth: false,
                trusted_proxy_hosts: ['*'], notifications_mode: 'standard',
                classification_threshold: 0.6, classification_min_confidence: 0.4,
                inference_provider: state.savedProvider, image_execution_mode: 'subprocess',
                bird_crop_accurate_detector: state.savedFinder,
                bird_crop_inference_provider: state.savedFinderProvider
            } });
        }
        if (path === '/api/classifier/status') return route.fulfill({ json: classifierStatus(state, rfdetrInstalled, options.finderExecution) });
        if (path === '/api/models/available') return route.fulfill({ json: availableModels });
        if (path === '/api/models/installed') {
            return route.fulfill({ json: [
                installed(ROPE, { is_active: true, validated_inference_providers: ['cpu', 'intel_cpu', 'intel_npu'] }),
                installed('bird_crop_detector'),
                // No current evidence for YOLOX-Tiny; RF-DETR passed on the Intel GPU.
                installed(YOLOX, { validated_inference_providers: [], provider_preference_order: [] }),
                ...(rfdetrInstalled ? [installed(RFDETR, {
                    validated_inference_providers: ['cpu', 'intel_gpu', 'intel_npu'], provider_preference_order: ['intel_gpu', 'intel_npu', 'cpu']
                })] : [])
            ] });
        }
        if (path.endsWith('/audio/sources')) return route.fulfill({ json: [] });
        if (path.endsWith('/frigate/config')) return route.fulfill({ json: { cameras: {} } });
        if (path.endsWith('/backfill/status')) return route.fulfill({ json: null });
        return route.fulfill({ json: {} });
    });
    await page.goto('/browser-tests/settings-backfill.html');
    const mobileNavigation = page.getByRole('combobox', { name: 'Settings', exact: true });
    await expect(mobileNavigation.or(page.getByRole('link', { name: 'Detection', exact: true }))).toBeVisible();
    if (await mobileNavigation.isVisible()) await mobileNavigation.selectOption('detection');
    else await page.getByRole('link', { name: 'Detection', exact: true }).click();
    return state;
}
