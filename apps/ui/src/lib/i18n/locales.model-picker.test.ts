import { describe, expect, it } from 'vitest';
import de from './locales/de.json';
import en from './locales/en.json';
import es from './locales/es.json';
import fr from './locales/fr.json';
import itLocale from './locales/it.json';
import ja from './locales/ja.json';
import pt from './locales/pt.json';
import ru from './locales/ru.json';
import zh from './locales/zh.json';

type LocaleRoot = Record<string, unknown>;

function pick(obj: LocaleRoot, path: string): unknown {
    return path.split('.').reduce<unknown>((current, segment) => {
        if (!current || typeof current !== 'object') return undefined;
        return (current as Record<string, unknown>)[segment];
    }, obj);
}

const REQUIRED_KEYS = [
    'settings.detection.model_lineup_eyebrow',
    'settings.detection.model_lineup_title',
    'settings.detection.model_lineup_description',
    'settings.detection.model_lineup_advanced_note',
    'settings.detection.personalized_rerank',
    'settings.detection.personalized_rerank_desc',
    'settings.detection.video_max_concurrent',
    'settings.detection.video_max_concurrent_label',
    'settings.detection.video_frames',
    'settings.detection.video_frames_label',
    'settings.detection.inference_provider',
    'settings.detection.inference_provider_desc',
    'settings.detection.provider_auto',
    'settings.detection.provider_cpu',
    'settings.detection.provider_cuda',
    'settings.detection.provider_intel_gpu',
    'settings.detection.provider_intel_cpu',
    'settings.detection.execution_mode',
    'settings.detection.execution_mode_desc',
    'settings.detection.mode_subprocess',
    'settings.detection.mode_in_process',
    'settings.detection.gpu_setup_docs',
    'settings.detection.cuda_runtime_only',
    'settings.detection.openvino_status',
    'settings.detection.intel_gpu_status',
    'settings.detection.auto_detected',
    'settings.detection.selected_provider_label',
    'settings.detection.active_provider_label',
    'settings.detection.inference_backend_label',
    'settings.detection.personalization_status_label',
    'settings.detection.personalization_active_pairs',
    'settings.detection.personalization_feedback_rows',
    'settings.detection.personalization_min_tags',
    'settings.detection.provider_fallback_reason',
    'settings.detection.openvino_compile_failure',
    'settings.detection.openvino_compile_failure_detail',
    'settings.detection.openvino_diagnostics',
    'settings.detection.model_manager_title',
    'settings.detection.model_manager_subtitle',
    'settings.detection.model_manager_runtime_tflite',
    'settings.detection.model_manager_runtime_onnx',
    'settings.detection.model_manager_refresh',
    'settings.detection.model_manager_lineup_title',
    'settings.detection.model_manager_lineup_desc',
    'settings.detection.model_manager_hide_advanced',
    'settings.detection.model_manager_show_advanced',
    'settings.detection.model_manager_count',
    'settings.detection.model_manager_advanced_hidden',
    'settings.detection.model_manager_active',
    'settings.detection.model_manager_recommended_for',
    'settings.detection.model_manager_notes',
    'settings.detection.model_manager_architecture',
    'settings.detection.model_manager_size',
    'settings.detection.model_manager_accuracy',
    'settings.detection.model_manager_speed',
    'settings.detection.model_manager_runtime',
    'settings.detection.model_manager_provider_pills',
    'settings.detection.model_manager_host_verification',
    'settings.detection.model_manager_downloading',
    'settings.detection.model_manager_redownloading',
    'settings.detection.model_manager_currently_active',
    'settings.detection.model_manager_activating',
    'settings.detection.model_manager_activate',
    'settings.detection.model_manager_redownload',
    'settings.detection.model_manager_download',
    'settings.detection.model_manager_activate_error',
    'settings.detection.model_manager_load_error',
    'settings.detection.model_manager_status_unavailable',
    'settings.detection.model_manager_status_refresh_failed',
    'settings.detection.model_manager_start_failed',
    'settings.detection.model_manager_provider_cpu_fallback_title',
    'settings.detection.model_manager_provider_cuda_available_title',
    'settings.detection.model_manager_provider_cuda_unavailable_title',
    'settings.detection.model_manager_provider_openvino_cpu_fallback_title',
    'settings.detection.model_manager_provider_openvino_cpu_available_title',
    'settings.detection.model_manager_provider_openvino_cpu_unavailable_title',
    'settings.detection.model_manager_provider_openvino_gpu_fallback_title',
    'settings.detection.model_manager_provider_openvino_gpu_available_title',
    'settings.detection.model_manager_provider_openvino_gpu_unavailable_title',
    'settings.detection.model_manager_provider_active_suffix',
    'settings.detection.model_manager_provider_available_suffix',
    'settings.detection.model_manager_provider_unavailable_suffix',
    'settings.detection.model_manager_provider_fallback_suffix',
    'settings.detection.model_manager_tier_cpu_only',
    'settings.detection.model_manager_scope_birds_only',
    'settings.detection.model_manager_scope_wildlife_wide',
    'settings.detection.model_manager_provider_cpu',
    'settings.detection.model_manager_provider_cuda',
    'settings.detection.model_manager_provider_intel_cpu',
    'settings.detection.model_manager_provider_intel_gpu',
    'jobs.model_download_title',
    'jobs.model_download_preparing',
    'jobs.model_download_running',
    'jobs.model_download_failed',
    'jobs.model_download_complete'
];

const LOCALES: Array<[string, LocaleRoot]> = [
    ['en', en as LocaleRoot],
    ['de', de as LocaleRoot],
    ['es', es as LocaleRoot],
    ['fr', fr as LocaleRoot],
    ['it', itLocale as LocaleRoot],
    ['ja', ja as LocaleRoot],
    ['pt', pt as LocaleRoot],
    ['ru', ru as LocaleRoot],
    ['zh', zh as LocaleRoot]
];

describe('locale coverage for model picker and detection settings strings', () => {
    for (const [localeName, locale] of LOCALES) {
        it(`${localeName} has required keys`, () => {
            for (const key of REQUIRED_KEYS) {
                const value = pick(locale, key);
                expect(typeof value).toBe('string');
                expect(String(value).length).toBeGreaterThan(0);
            }
        });
    }
});
