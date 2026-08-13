<script lang="ts">
    import { onMount } from 'svelte';
    import { fetchClassifierStatus, fetchReadiness, fetchUpdateStatus } from '../api';
    import type { UpdateStatus } from '../api';
    import { fetchUptimeWindow, type UptimeWindowResponse } from '../api/leaderboard';
    import type { ClassifierStatus, VersionInfo } from '../api';
    import { authStore } from '../stores/auth.svelte';
    import { getErrorMessage, isTransientRequestError } from '../utils/error-handling';
    import { logger } from '../utils/logger';
    import { formatDate, formatTime } from '../utils/datetime';
    import { _ } from 'svelte-i18n';

    interface Props {
        versionInfo: VersionInfo;
    }

    let { versionInfo }: Props = $props();

    let classifier = $state<ClassifierStatus | null>(null);
    let startedAt = $state<string | null>(null);
    let uptimeWindow = $state<UptimeWindowResponse | null>(null);
    let updateStatus = $state<UpdateStatus | null>(null);
    let copied = $state(false);
    let copyFailed = $state(false);

    const isOwner = $derived(authStore.showSettings);

    onMount(() => {
        void (async () => {
            try {
                const readiness = await fetchReadiness();
                startedAt = readiness.startup_started_at ?? null;
            } catch {
                // Uptime is supporting detail; the card stands without it.
            }
            try {
                uptimeWindow = await fetchUptimeWindow(24);
            } catch {
                // No heartbeat history yet, so the strip stays out.
            }
            try {
                updateStatus = await fetchUpdateStatus();
            } catch {
                // Update checking is optional and may be disabled.
            }
        })();

        void (async () => {
            try {
                classifier = await fetchClassifierStatus();
            } catch (error) {
                if (isTransientRequestError(error)) {
                    logger.warn('Classifier status unavailable', { message: getErrorMessage(error) });
                } else {
                    logger.error('Failed to fetch classifier status', error);
                }
            }
        })();
    });

    const acceleration = $derived(
        classifier?.active_provider ??
            classifier?.inference_backend ??
            $_('about.pipeline.unknown', { default: 'unknown' })
    );

    // The readiness probe records when this process started. There is no health history,
    // so this is honestly "running since", not a 24-hour availability strip.
    const availability = $derived.by(() => {
        const ratio = uptimeWindow?.uptime_ratio;
        if (ratio === null || ratio === undefined) return null;
        // One decimal only below 100, so a full window reads "100% up" rather than "100.0% up".
        const percent = ratio * 100;
        return percent >= 99.95 ? '100' : percent.toFixed(1);
    });

    const uptime = $derived.by(() => {
        if (!startedAt) return null;
        const started = Date.parse(startedAt);
        if (Number.isNaN(started)) return null;
        const minutes = Math.max(Math.floor((Date.now() - started) / 60000), 0);
        if (minutes < 60) {
            return $_('about.instance.uptime_minutes', {
                values: { count: minutes },
                default: '{count} min'
            });
        }
        const hours = Math.floor(minutes / 60);
        if (hours < 48) {
            return $_('about.instance.uptime_hours', { values: { count: hours }, default: '{count} h' });
        }
        return $_('about.instance.uptime_days', {
            values: { count: Math.floor(hours / 24) },
            default: '{count} days'
        });
    });

    // Deliberately no keys, URLs or camera names: this is meant to be pasted in public.
    const supportSummary = $derived(
        [
            `v${versionInfo.base_version}`,
            versionInfo.branch,
            versionInfo.git_hash,
            acceleration,
            classifier?.effective_model_id ?? classifier?.active_model_id ?? 'no model'
        ]
            .filter(Boolean)
            .join(' · ')
    );

    async function copySummary(): Promise<void> {
        try {
            await navigator.clipboard.writeText(supportSummary);
            copied = true;
            copyFailed = false;
            setTimeout(() => (copied = false), 2000);
        } catch (error) {
            // Clipboard access can be refused; the text stays selectable either way.
            copyFailed = true;
            logger.warn('Clipboard write refused', { message: getErrorMessage(error) });
        }
    }
</script>

{#if isOwner}
    <section class="card-base space-y-4 p-6" data-about-instance aria-labelledby="about-instance-heading">
        <div class="flex flex-wrap items-center gap-3">
            <h2 id="about-instance-heading" class="font-display text-xl font-bold text-slate-900 dark:text-white">
                {$_('about.instance.title', { default: 'This instance' })}
            </h2>

            {#if updateStatus?.enabled}
                <span
                    class="ml-auto inline-flex items-center gap-1.5 rounded-full border px-2.5 py-1 text-[11px] font-semibold {updateStatus.update_available
                        ? 'border-accent-300 text-accent-800 dark:border-accent-800 dark:text-accent-200'
                        : 'border-slate-200 text-slate-600 dark:border-slate-700 dark:text-slate-300'}"
                    data-instance-update
                >
                    <span
                        class="h-1.5 w-1.5 rounded-full {updateStatus.update_available
                            ? 'bg-accent-500'
                            : 'bg-emerald-500'}"
                        aria-hidden="true"
                    ></span>
                    {#if updateStatus.update_available}
                        {$_('about.instance.update_available', {
                            values: { version: updateStatus.latest_version ?? '' },
                            default: 'v{version} is available'
                        })}
                    {:else}
                        {$_('about.instance.up_to_date', { default: 'Up to date' })}
                    {/if}
                    {#if updateStatus.checked_at}
                        <span class="font-normal text-slate-500 dark:text-slate-400">
                            {$_('about.instance.checked', {
                                values: { when: formatTime(updateStatus.checked_at) },
                                default: 'checked {when}'
                            })}
                        </span>
                    {/if}
                </span>
            {/if}
        </div>

        <div class="grid gap-6 sm:grid-cols-[minmax(0,0.7fr)_minmax(0,0.7fr)_minmax(0,1.6fr)]">
            <div>
                <p class="text-[11px] font-semibold uppercase tracking-[0.12em] text-slate-500 dark:text-slate-400">
                    {$_('about.instance.acceleration', { default: 'Acceleration' })}
                </p>
                <p class="font-display text-2xl font-bold text-slate-900 dark:text-white">{acceleration}</p>
                {#if classifier?.fallback_reason}
                    <p class="mt-1 text-[11px] leading-snug text-slate-500 dark:text-slate-400">
                        {classifier.fallback_reason}
                    </p>
                {/if}
            </div>

            <div data-instance-uptime>
                <p class="text-[11px] font-semibold uppercase tracking-[0.12em] text-slate-500 dark:text-slate-400">
                    {$_('about.instance.uptime', { default: 'Running for' })}
                </p>
                <p class="font-display text-2xl font-bold text-slate-900 dark:text-white">
                    {uptime ?? $_('about.pipeline.unknown', { default: 'unknown' })}
                </p>

                {#if uptimeWindow}
                    {#if availability}
                        <p class="mt-0.5 text-xs font-semibold tabular-nums text-emerald-700 dark:text-emerald-300">
                            {$_('about.instance.availability', {
                                values: { percent: availability },
                                default: '{percent}% up'
                            })}
                        </p>
                    {/if}
                    <div
                        class="mt-2 flex gap-[2px]"
                        role="img"
                        aria-label={$_('about.instance.strip_label', {
                            values: { hours: 24 },
                            default: 'Availability over the last {hours} hours'
                        })}
                        data-uptime-strip
                    >
                        {#each uptimeWindow.buckets as bucket (bucket.start)}
                            <span
                                class="h-4 flex-1 rounded-[2px] transition-transform duration-150 hover:scale-y-125 {bucket.state === 'up'
                                    ? 'bg-emerald-500/80'
                                    : bucket.state === 'down'
                                      ? 'bg-accent-500'
                                      : 'bg-slate-200 dark:bg-slate-700'}"
                                title={`${formatTime(bucket.start)} · ${bucket.state}`}
                            ></span>
                        {/each}
                    </div>
                    <!-- A 24 bar strip with no scale leaves the reader guessing which end is now. -->
                    <div
                        class="mt-1 flex justify-between text-[10px] tabular-nums text-slate-400 dark:text-slate-500"
                        aria-hidden="true"
                    >
                        <span>{$_('about.instance.window_start', { values: { hours: 24 }, default: '{hours} h ago' })}</span>
                        <span>{$_('about.instance.window_now', { default: 'now' })}</span>
                    </div>
                    <p class="mt-1.5 text-[11px] text-slate-500 dark:text-slate-400">
                        {#if uptimeWindow.longest_gap_minutes > 0 && uptimeWindow.longest_gap_start}
                            {$_('about.instance.gap', {
                                values: {
                                    minutes: uptimeWindow.longest_gap_minutes,
                                    when: formatTime(uptimeWindow.longest_gap_start)
                                },
                                default: '{minutes} minutes missing at {when}'
                            })}
                        {:else if uptimeWindow.uptime_ratio === null}
                            {$_('about.instance.no_history', {
                                default: 'No history recorded yet for this window.'
                            })}
                        {:else}
                            {$_('about.instance.no_gaps', { default: 'No gaps in the last 24 hours.' })}
                        {/if}
                    </p>
                {:else}
                    <div class="mt-2 flex gap-[2px]" aria-hidden="true">
                        {#each { length: 24 } as _, slot (slot)}
                            <span class="h-4 flex-1 rounded-[2px] bg-slate-200/70 dark:bg-slate-700/50"></span>
                        {/each}
                    </div>
                    <p class="mt-1.5 text-[11px] text-slate-500 dark:text-slate-400">
                        {$_('about.instance.history_unavailable', {
                            default: 'No availability history to show here.'
                        })}
                    </p>
                {/if}
                {#if startedAt}
                    <p class="mt-1 text-[11px] text-slate-500 dark:text-slate-400">
                        {$_('about.instance.since', {
                            values: { when: `${formatDate(startedAt)} ${formatTime(startedAt)}` },
                            default: 'since {when}'
                        })}
                    </p>
                {/if}
            </div>

            <div>
                <p class="text-[11px] font-semibold uppercase tracking-[0.12em] text-slate-500 dark:text-slate-400">
                    {$_('about.instance.for_issue', { default: 'For an issue report' })}
                </p>
                <div class="mt-1.5 flex items-center gap-2 rounded-xl border border-slate-200 bg-slate-50 px-3 py-2 dark:border-slate-700 dark:bg-slate-900/50">
                    <code class="min-w-0 flex-1 truncate font-mono text-xs text-slate-700 dark:text-slate-200">
                        {supportSummary}
                    </code>
                    <button class="btn btn-secondary min-h-11 shrink-0 px-3 py-1.5 text-xs" onclick={copySummary}>
                        {copied
                            ? $_('about.instance.copied', { default: 'Copied' })
                            : $_('about.instance.copy', { default: 'Copy' })}
                    </button>
                </div>
                <p class="mt-1.5 text-[11px] text-slate-500 dark:text-slate-400">
                    {copyFailed
                        ? $_('about.instance.copy_failed', {
                              default: 'Copying was refused, select the text instead.'
                          })
                        : $_('about.instance.no_secrets', {
                              default: 'Contains no keys, URLs or camera names.'
                          })}
                </p>
            </div>
        </div>
    </section>
{/if}
