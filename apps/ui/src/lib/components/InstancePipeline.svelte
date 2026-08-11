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

    const isOwner = $derived(authStore.showSettings);

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

    const outbound = $derived([
        {
            key: 'inat',
            on: true
        },
        {
            key: 'weather',
            on: true
        },
        {
            key: 'llm',
            on: Boolean(settingsStore.settings?.llm_enabled)
        },
        {
            key: 'telemetry',
            on: Boolean(settingsStore.settings?.telemetry_enabled)
        }
    ]);

    // Table names are identifiers, not copy, so they are never translated.
    const storageTables = [
        { key: 'detections', table: 'detections' },
        { key: 'audio', table: 'audio_detections' },
        { key: 'taxonomy', table: 'taxonomy_cache' }
    ];

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
        {#each steps as step (step.key)}
            <li class="rounded-xl border p-3 {kindClass(step.kind)}">
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
    </div>

    <div class="grid gap-6 border-t border-slate-200 pt-5 sm:grid-cols-2 dark:border-slate-700">
        <section aria-labelledby="about-stores-title">
            <h3 id="about-stores-title" class="text-sm font-bold text-slate-900 dark:text-white">
                {$_('about.storage.title', { default: 'What it stores' })}
            </h3>
            <dl class="mt-2 divide-y divide-slate-200/70 text-xs dark:divide-slate-700/50">
                {#each storageTables as row (row.key)}
                    <div class="py-1.5">
                        <dt class="font-mono text-[11px] font-semibold text-slate-800 dark:text-slate-100">
                            {row.table}
                        </dt>
                        <dd class="text-slate-500 dark:text-slate-400">
                            {$_(`about.storage.${row.key}_desc`)}
                        </dd>
                    </div>
                {/each}
            </dl>
            <p class="mt-2 text-[11px] text-slate-500 dark:text-slate-400">
                {$_('about.storage.note', {
                    default: 'SQLite under /data. Schema changes ship reversible migrations.'
                })}
            </p>
        </section>

        <section aria-labelledby="about-outbound-title">
            <h3 id="about-outbound-title" class="text-sm font-bold text-slate-900 dark:text-white">
                {$_('about.outbound.title', { default: 'What leaves your network' })}
            </h3>
            <dl class="mt-2 divide-y divide-slate-200/70 text-xs dark:divide-slate-700/50">
                {#each outbound as item (item.key)}
                    <div class="flex items-center gap-3 py-1.5">
                        <span class="min-w-0 flex-1">
                            <dt class="font-semibold text-slate-800 dark:text-slate-100">
                                {$_(`about.outbound.${item.key}`)}
                            </dt>
                            <dd class="text-slate-500 dark:text-slate-400">
                                {$_(`about.outbound.${item.key}_desc`)}
                            </dd>
                        </span>
                        <span
                            class="shrink-0 rounded px-1.5 py-0.5 text-[10px] font-bold uppercase tracking-wider {item.on
                                ? 'bg-emerald-100 text-emerald-800 dark:bg-emerald-950/50 dark:text-emerald-300'
                                : 'bg-slate-100 text-slate-500 dark:bg-slate-800 dark:text-slate-400'}"
                        >
                            {item.on
                                ? $_('about.pipeline.enabled', { default: 'enabled' })
                                : $_('about.pipeline.off', { default: 'off' })}
                        </span>
                    </div>
                {/each}
            </dl>
            {#if !isOwner}
                <p class="mt-2 text-[11px] text-slate-500 dark:text-slate-400">
                    {$_('about.outbound.guest_note', {
                        default: 'Shown for transparency. Only the owner can change these.'
                    })}
                </p>
            {/if}
        </section>
    </div>
</div>
