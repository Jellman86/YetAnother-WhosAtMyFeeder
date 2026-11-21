<script lang="ts">
    import { onMount } from 'svelte';
    import { checkHealth, fetchReadiness, readClassifierStatus, readUpdateStatus } from '../api';
    import type { UpdateStatus } from '../api';
    import { fetchUptimeWindow, type UptimeWindowResponse } from '../api/leaderboard';
    import type { ClassifierStatus, VersionInfo } from '../api';
    import { authStore } from '../stores/auth.svelte';
    import { getErrorMessage, isTransientRequestError } from '../utils/error-handling';
    import { logger } from '../utils/logger';
    import { formatDate, formatTime } from '../utils/datetime';
    import { describeRuntime, startedAtFrom } from '../utils/instance-facts';
    import IdentificationStatusLine from './IdentificationStatusLine.svelte';
    import { uptimeCoverage } from '../utils/uptime-coverage';
    import { _ } from 'svelte-i18n';

    interface Props {
        versionInfo: VersionInfo;
    }

    type UptimeLoadState = 'loading' | 'ready' | 'error';

    let { versionInfo }: Props = $props();

    let classifier = $state<ClassifierStatus | null>(null);
    let startedAt = $state<string | null>(null);
    let startRead = $state(false);
    let uptimeWindow = $state<UptimeWindowResponse | null>(null);
    let uptimeLoadState = $state<UptimeLoadState>('loading');
    let updateStatus = $state<UpdateStatus | null>(null);
    let copied = $state(false);
    let copyFailed = $state(false);

    const isOwner = $derived(authStore.showSettings);

    onMount(() => {
        void (async () => {
            // Both probes report the same process start; the second is asked only when the
            // first could not be read, and with neither the card says it was not measured.
            const readiness = await fetchReadiness().catch(() => null);
            startedAt = startedAtFrom(readiness) ?? startedAtFrom(await checkHealth().catch(() => null));
            startRead = true;
            try {
                uptimeWindow = await fetchUptimeWindow(24);
                uptimeLoadState = 'ready';
            } catch {
                // A failed request is different from a successful window with no history.
                uptimeLoadState = 'error';
            }
            try {
                updateStatus = await readUpdateStatus();
            } catch {
                // Update checking is optional and may be disabled.
            }
        })();

        void (async () => {
            try {
                classifier = await readClassifierStatus();
            } catch (error) {
                if (isTransientRequestError(error)) {
                    logger.warn('Classifier status unavailable', { message: getErrorMessage(error) });
                } else {
                    logger.error('Failed to fetch classifier status', error);
                }
            }
        })();
    });

    // Two separate measurements share this card and are never merged: how long this process
    // has run (from its own start time), and the share of the last 24 hours it was recorded up.
    const availability = $derived.by(() => {
        const ratio = uptimeWindow?.uptime_ratio;
        if (ratio === null || ratio === undefined) return null;
        // One decimal only below 100, so a full window reads "100% up" rather than "100.0% up".
        const percent = ratio * 100;
        return percent >= 99.95 ? '100' : percent.toFixed(1);
    });

    const coverage = $derived(uptimeWindow ? uptimeCoverage(uptimeWindow.buckets, uptimeWindow.bucket_minutes) : null);

    const uptime = $derived.by(() => {
        if (!startedAt) return null;
        const started = Date.parse(startedAt);
        if (Number.isNaN(started)) return null;
        const minutes = Math.max(Math.floor((Date.now() - started) / 60000), 0);
        if (minutes < 60) {
            return $_('about.instance.uptime_minutes', {
                values: { count: minutes },
                default: '{count} min'
            });
        }
        const hours = Math.floor(minutes / 60);
        if (hours < 48) {
            return $_('about.instance.uptime_hours', { values: { count: hours }, default: '{count} h' });
        }
        return $_('about.instance.uptime_days', {
            values: { count: Math.floor(hours / 24) },
            default: '{count, plural, one {# day} other {# days}}'
        });
    });

    // The technical runtime ("TFLite on CPU") belongs in a pasted support summary, not on the card.
    const runtime = $derived(describeRuntime(classifier));
    const runtimeLabel = $derived(
        !runtime
            ? null
            : runtime.device
              ? $_('about.instance.runtime_on', { values: { runtime: runtime.runtime, device: runtime.device }, default: '{runtime} on {device}' })
              : runtime.runtime
    );

    // Deliberately no keys, URLs or camera names: this is meant to be pasted in public.
    // Kept as parts so the page can break the line between them and never inside a model name.
    const supportParts = $derived(
        [
            `v${versionInfo.base_version}`,
            versionInfo.branch,
            versionInfo.git_hash,
            runtimeLabel,
            classifier?.effective_model_id ?? classifier?.active_model_id ?? 'no model'
        ].filter((part): part is string => Boolean(part))
    );
    const supportSummary = $derived(supportParts.join(' · '));

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
    <section class="card-base min-w-0 max-w-full space-y-4 p-6" data-about-instance aria-labelledby="about-instance-heading">
        <div class="flex flex-wrap items-center gap-3">
            <h2 id="about-instance-heading" class="font-display text-xl font-bold text-strong">
                {$_('about.instance.title', { default: 'This instance' })}
            </h2>

            {#if updateStatus?.enabled}
                <span
                    class="ml-auto inline-flex items-center gap-1.5 rounded-full border px-2.5 py-1 text-2xs font-semibold {updateStatus.update_available
                        ? 'border-accent-line text-accent-ink'
                        : 'border-line text-muted'}"
                    data-instance-update
                >
                    <span
                        class="h-1.5 w-1.5 rounded-full {updateStatus.update_available
                            ? 'bg-accent'
                            : 'bg-status-ok'}"
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
                        <span class="font-normal text-muted">
                            {$_('about.instance.checked', {
                                values: { when: formatTime(updateStatus.checked_at) },
                                default: 'checked {when}'
                            })}
                        </span>
                    {/if}
                </span>
            {/if}
        </div>

        <!-- Bird identification takes the whole row: its sentence can be long (a model to download) and in a
             narrow first column it ran to seven lines beside two short ones. -->
        <div class="grid min-w-0 gap-6 sm:grid-cols-3">
            <div class="min-w-0 sm:col-span-3" data-instance-runtime>
                <p class="text-2xs font-semibold text-muted wrap-anywhere">
                    {$_('about.instance.runtime', { default: 'Bird identification' })}
                </p>
                <!-- The same sentence Settings › Models and the setup wizard show, from the same report. -->
                <div class="mt-1 max-w-prose">
                    <IdentificationStatusLine classifierStatus={classifier} context="about" />
                </div>
            </div>

            <div data-instance-uptime class="min-w-0">
                <p class="text-2xs font-semibold text-muted wrap-anywhere">
                    {$_('about.instance.uptime', { default: 'Running for' })}
                </p>
                {#if uptime && startedAt}
                    <p class="font-display text-2xl font-bold text-strong" data-instance-running-for>{uptime}</p>
                    <p class="text-2xs text-muted">
                        {$_('about.instance.since', {
                            values: { when: `${formatDate(startedAt)} ${formatTime(startedAt)}` },
                            default: 'since {when}'
                        })}
                    </p>
                {:else if startRead}
                    <!-- A dash where the figure would be, and one muted line for why: never a sentence as the value. -->
                    <p class="font-display text-2xl font-bold text-strong" data-instance-running-unmeasured>
                        <span aria-hidden="true">&mdash;</span>
                        <span class="sr-only">{$_('about.instance.uptime_unmeasured_value', { default: 'Not measured' })}</span>
                    </p>
                    <p class="text-2xs text-muted">
                        {$_('about.instance.uptime_unmeasured', { default: 'The backend did not report when it started.' })}
                    </p>
                {:else}
                    <p class="mt-1 text-sm text-muted" role="status">{$_('common.loading', { default: 'Loading…' })}</p>
                {/if}

                <p class="mt-4 text-2xs font-semibold text-muted wrap-anywhere">
                    {$_('about.instance.availability_heading', { values: { hours: 24 }, default: 'Availability, last {hours} hours' })}
                </p>
                {#if uptimeLoadState === 'ready' && uptimeWindow}
                    {#if availability}
                        <!-- The percentage covers only the hours that were recorded, and says so. -->
                        <p class="font-display text-2xl font-bold tabular-nums text-strong" data-uptime-availability>
                            {#if coverage && !coverage.complete}
                                {$_('about.instance.availability_partial', {
                                    values: { percent: availability, hours: coverage.recordedHours },
                                    default: '{percent}% up over the {hours} h recorded'
                                })}
                            {:else}
                                {$_('about.instance.availability', {
                                    values: { percent: availability },
                                    default: '{percent}% up'
                                })}
                            {/if}
                        </p>
                    {/if}
                    <div
                        class="mt-2 flex w-full min-w-0 max-w-full gap-0.5"
                        role="img"
                        aria-label={$_('about.instance.strip_label', {
                            values: { hours: 24 },
                            default: 'Availability over the last {hours} hours'
                        })}
                        data-uptime-strip
                    >
                        {#each uptimeWindow.buckets as bucket (bucket.start)}
                            <span
                                class="h-4 min-w-0 flex-1 rounded-xs {bucket.state === 'up'
                                    ? 'bg-status-ok'
                                    : bucket.state === 'down'
                                      ? 'bg-status-fail'
                                      : 'bg-line'}"
                                title={`${formatTime(bucket.start)} · ${bucket.state}`}
                            ></span>
                        {/each}
                    </div>
                    <!-- A 24 bar strip with no scale leaves the reader guessing which end is now. -->
                    <div
                        class="mt-1 flex justify-between text-3xs tabular-nums text-muted"
                        aria-hidden="true"
                    >
                        <span>{$_('about.instance.window_start', { values: { hours: 24 }, default: '{hours} h ago' })}</span>
                        <span>{$_('about.instance.window_now', { default: 'now' })}</span>
                    </div>
                    <p class="mt-1.5 text-2xs text-muted">
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
                        {:else if coverage && !coverage.complete && coverage.recordedSince}
                            {$_('about.instance.no_gaps_since', {
                                values: { when: formatTime(coverage.recordedSince) },
                                default: 'No gaps since recording began at {when}.'
                            })}
                        {:else}
                            {$_('about.instance.no_gaps', { default: 'No gaps in the last 24 hours.' })}
                        {/if}
                    </p>
                {:else if uptimeLoadState === 'loading'}
                    <div class="mt-2 flex w-full min-w-0 max-w-full gap-0.5" aria-hidden="true">
                        {#each { length: 24 } as _, slot (slot)}
                            <span class="h-4 min-w-0 flex-1 rounded-xs bg-line"></span>
                        {/each}
                    </div>
                    <p class="mt-1.5 text-2xs text-muted">
                        {$_('about.instance.history_loading', { default: 'Loading availability…' })}
                    </p>
                {:else if uptimeLoadState === 'error'}
                    <div class="mt-2 flex w-full min-w-0 max-w-full gap-0.5" aria-hidden="true">
                        {#each { length: 24 } as _, slot (slot)}
                            <span class="h-4 min-w-0 flex-1 rounded-xs bg-line"></span>
                        {/each}
                    </div>
                    <p class="mt-1.5 text-2xs text-muted">
                        {$_('about.instance.history_unavailable', {
                            default: 'Availability could not be read.'
                        })}
                    </p>
                {/if}
            </div>

            <div class="min-w-0 sm:col-span-2" data-instance-report>
                <p class="text-2xs font-semibold text-muted wrap-anywhere">
                    {$_('about.instance.for_issue', { default: 'For an issue report' })}
                </p>
                <div class="mt-1.5 flex min-w-0 flex-col items-stretch gap-2 rounded-xl border border-line bg-surface-raised px-3 py-2 sm:flex-row sm:items-center">
                    <code class="min-w-0 max-w-full whitespace-normal font-mono text-xs leading-relaxed text-ink sm:flex-1">
                        {#each supportParts as part, position (position)}{#if position > 0}{' · '}{/if}<span class="inline-block max-w-full align-top wrap-anywhere">{part}</span>{/each}
                    </code>
                    <button class="btn btn-secondary min-h-11 w-full sm:w-auto shrink-0 px-3 py-1.5 text-xs" onclick={copySummary}>
                        {copied
                            ? $_('about.instance.copied', { default: 'Copied' })
                            : $_('about.instance.copy', { default: 'Copy' })}
                    </button>
                </div>
                <p class="mt-1.5 text-2xs text-muted">
                    {copyFailed
                        ? $_('about.instance.copy_failed', {
                              default: 'The browser refused to copy. Select the text and copy it yourself.'
                          })
                        : $_('about.instance.no_secrets', {
                              default: 'Contains no keys, URLs or camera names.'
                          })}
                </p>
            </div>
        </div>
    </section>
{/if}
