<script lang="ts">
    import { onMount } from 'svelte';
    import { fetchCameraStatuses, fetchClassifierStatus } from '../api';
    import type { CameraStatusResponse, ClassifierStatus } from '../api';
    import { detectionsStore } from '../stores/detections.svelte';
    import { settingsStore } from '../stores/settings.svelte';
    import { authStore } from '../stores/auth.svelte';
    import { getErrorMessage, isTransientRequestError } from '../utils/error-handling';
    import { logger } from '../utils/logger';
    import { _ } from 'svelte-i18n';

    /**
     * The pipeline every install has, annotated with what this one is actually doing.
     * A step whose status cannot be read says so; it never claims to be healthy.
     */

    type Tone = 'ok' | 'off' | 'unknown';

    interface Step {
        key: string;
        kind: 'local' | 'optional' | 'external';
        detail: string;
        state: string | null;
        tone: Tone;
    }

    let cameraStatus = $state<CameraStatusResponse | null>(null);
    let cameraFailed = $state(false);
    let classifier = $state<ClassifierStatus | null>(null);
    let classifierFailed = $state(false);

    onMount(() => {
        const controller = new AbortController();

        void (async () => {
            try {
                cameraStatus = await fetchCameraStatuses(controller.signal);
            } catch (error) {
                if (controller.signal.aborted) return;
                cameraFailed = true;
                if (isTransientRequestError(error)) {
                    logger.warn('Camera status unavailable', { message: getErrorMessage(error) });
                } else {
                    logger.error('Failed to fetch camera status', error);
                }
            }
        })();

        void (async () => {
            try {
                classifier = await fetchClassifierStatus();
            } catch (error) {
                if (controller.signal.aborted) return;
                classifierFailed = true;
                if (isTransientRequestError(error)) {
                    logger.warn('Classifier status unavailable', { message: getErrorMessage(error) });
                } else {
                    logger.error('Failed to fetch classifier status', error);
                }
            }
        })();

        return () => controller.abort();
    });

    const unknown = $_('about.pipeline.unknown', { default: 'unknown' });

    const birdnetEnabled = $derived(
        settingsStore.settings?.birdnet_enabled ?? authStore.birdnetEnabled ?? false
    );

    const notificationsEnabled = $derived(
        Boolean(
            settingsStore.settings?.notifications_discord_enabled ||
                settingsStore.settings?.notifications_telegram_enabled ||
                settingsStore.settings?.notifications_pushover_enabled ||
                settingsStore.settings?.notifications_email_enabled
        )
    );

    const cameraSummary = $derived.by(() => {
        if (cameraFailed) return { detail: unknown, state: unknown, tone: 'unknown' as Tone };
        if (!cameraStatus) return { detail: '…', state: null, tone: 'unknown' as Tone };
        const cameras = cameraStatus.cameras ?? [];
        const online = cameras.filter((camera) => camera.status === 'online').length;
        return {
            detail: $_('about.pipeline.cameras_count', {
                values: { online, total: cameras.length },
                default: '{online} of {total} cameras online'
            }),
            state:
                cameras.length > 0 && online === cameras.length
                    ? $_('about.pipeline.online', { default: 'online' })
                    : $_('about.pipeline.degraded', { default: 'check' }),
            tone: (cameras.length > 0 && online === cameras.length ? 'ok' : 'off') as Tone
        };
    });

    const classifierSummary = $derived.by(() => {
        if (classifierFailed) return { detail: unknown, state: unknown, tone: 'unknown' as Tone };
        if (!classifier) return { detail: '…', state: null, tone: 'unknown' as Tone };
        const model = classifier.effective_model_id ?? classifier.active_model_id ?? '—';
        const provider = classifier.active_provider ?? classifier.inference_backend ?? '';
        return {
            detail: provider ? `${model} · ${provider}` : String(model),
            state: classifier.loaded
                ? $_('about.pipeline.loaded', { default: 'loaded' })
                : $_('about.pipeline.not_loaded', { default: 'not loaded' }),
            tone: (classifier.loaded ? 'ok' : 'off') as Tone
        };
    });

    const steps = $derived<Step[]>([
        {
            key: 'frigate',
            kind: 'external',
            detail: cameraSummary.detail,
            state: cameraSummary.state,
            tone: cameraSummary.tone
        },
        {
            key: 'mqtt',
            kind: 'external',
            detail: $_('about.pipeline.mqtt_detail', { default: 'frigate/events' }),
            // No status endpoint for the broker, so this step stays unannotated.
            state: null,
            tone: 'unknown'
        },
        {
            key: 'classifier',
            kind: 'local',
            detail: classifierSummary.detail,
            state: classifierSummary.state,
            tone: classifierSummary.tone
        },
        {
            key: 'audio',
            kind: 'optional',
            detail: $_('about.pipeline.audio_detail', { default: 'BirdNET-Go correlation' }),
            state: birdnetEnabled
                ? $_('about.pipeline.enabled', { default: 'enabled' })
                : $_('about.pipeline.off', { default: 'off' }),
            tone: (birdnetEnabled ? 'ok' : 'off') as Tone
        },
        {
            key: 'store',
            kind: 'local',
            detail: $_('about.pipeline.store_detail', { default: 'SQLite under /data' }),
            state: null,
            tone: 'unknown'
        },
        {
            key: 'notify',
            kind: 'optional',
            detail: notificationsEnabled
                ? $_('about.pipeline.notify_on', { default: 'at least one channel configured' })
                : $_('about.pipeline.notify_off', { default: 'nothing configured' }),
            state: notificationsEnabled
                ? $_('about.pipeline.enabled', { default: 'enabled' })
                : $_('about.pipeline.off', { default: 'off' }),
            tone: (notificationsEnabled ? 'ok' : 'off') as Tone
        },
        {
            key: 'browser',
            kind: 'external',
            detail: $_('about.pipeline.browser_detail', { default: 'live updates over SSE' }),
            state: detectionsStore.connected
                ? $_('about.pipeline.streaming', { default: 'streaming' })
                : $_('about.pipeline.offline', { default: 'offline' }),
            tone: (detectionsStore.connected ? 'ok' : 'off') as Tone
        }
    ]);

    function toneClass(tone: Tone): string {
        if (tone === 'ok') return 'text-emerald-700 dark:text-emerald-300';
        if (tone === 'off') return 'text-slate-500 dark:text-slate-400';
        return 'text-slate-400 dark:text-slate-500';
    }

    function kindClass(kind: Step['kind']): string {
        if (kind === 'local') return 'border-brand-300 bg-brand-50/70 dark:border-brand-800 dark:bg-brand-950/30';
        if (kind === 'optional') return 'border-dashed border-slate-300 dark:border-slate-600';
        return 'border-slate-200 dark:border-slate-700';
    }
</script>

<div class="space-y-4" data-about-pipeline>
    <ol class="grid grid-cols-1 gap-2 sm:grid-cols-2 lg:grid-cols-4 xl:grid-cols-7">
        {#each steps as step, index (step.key)}
            <li class="relative rounded-xl border p-3 {kindClass(step.kind)}">
                {#if index > 0}
                    <span
                        class="absolute -left-[9px] top-1/2 hidden -translate-y-1/2 text-slate-300 xl:block dark:text-slate-600"
                        aria-hidden="true"
                    >
                        <svg class="h-3 w-3" viewBox="0 0 12 12" fill="none" stroke="currentColor" stroke-width="1.6">
                            <path stroke-linecap="round" stroke-linejoin="round" d="m4 2 4 4-4 4" />
                        </svg>
                    </span>
                {/if}
                {#if step.state}
                    <span class="block text-[10px] font-bold uppercase tracking-[0.12em] {toneClass(step.tone)}">
                        {step.state}
                    </span>
                {/if}
                <span class="mt-0.5 block text-sm font-semibold text-slate-900 dark:text-white">
                    {$_(`about.pipeline.${step.key}`)}
                </span>
                <span class="mt-0.5 block text-[11px] leading-snug text-slate-500 dark:text-slate-400">
                    {step.detail}
                </span>
            </li>
        {/each}
    </ol>

    <div class="flex flex-wrap items-center gap-x-5 gap-y-2 text-[11px] text-slate-500 dark:text-slate-400">
        <span class="flex items-center gap-1.5">
            <i class="h-2.5 w-2.5 rounded-sm border border-brand-300 bg-brand-50 dark:border-brand-800 dark:bg-brand-950/40" aria-hidden="true"></i>
            {$_('about.pipeline.legend_local', { default: 'runs on your hardware' })}
        </span>
        <span class="flex items-center gap-1.5">
            <i class="h-2.5 w-2.5 rounded-sm border border-dashed border-slate-400 dark:border-slate-500" aria-hidden="true"></i>
            {$_('about.pipeline.legend_optional', { default: 'optional' })}
        </span>
        <span class="flex items-center gap-1.5">
            <i class="h-2.5 w-2.5 rounded-sm border border-slate-300 dark:border-slate-600" aria-hidden="true"></i>
            {$_('about.pipeline.legend_external', { default: 'your broker and browser' })}
        </span>
        <span class="sm:ml-auto">
            {$_('about.pipeline.legend_note', {
                default: 'Nothing leaves your network except the calls listed below.'
            })}
        </span>
    </div>

</div>
