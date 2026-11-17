<script lang="ts">
    import { _ } from 'svelte-i18n';
    import type { Detection } from '../../api';
    import { formatDateTime } from '../../utils/datetime';
    import type { VideoFailureInsight } from '../../utils/frigate-errors';

    /**
     * The one line that says how the identification was reached when the video did not decide it,
     * as a plain row in the rail rather than a box inside it: an icon and title in the tone, the
     * cause in body ink, and the technical evidence behind a disclosure only when there is a
     * recorded error or diagnostics to show. Fail is kept for a video that failed with nothing to
     * fall back on, attention for a borderline fallback, neutral for a confident one.
     */
    type Props = {
        detection: Detection;
        tone: 'fail' | 'attention' | 'neutral';
        title: string;
        description: string;
        insight: VideoFailureInsight;
        /** Frigate's integrity check recorded the event as missing. */
        upstreamMissing: boolean;
        showTechnicalDetails: boolean;
        docsUrl: string;
    };

    let { detection, tone, title, description, insight, upstreamMissing, showTechnicalDetails, docsUrl }: Props = $props();

    let detailsOpen = $state(false);
    const diagnostics = $derived(detection.video_classification_diagnostics ?? null);
    const sources = $derived(Object.entries(diagnostics?.sources ?? {}));
    const toneInk = $derived(tone === 'fail' ? 'text-status-fail' : tone === 'attention' ? 'text-status-attention' : 'text-muted');

    function sourceLabel(source: string): string {
        if (source === 'full_frame') return $_('detection.video_analysis.evidence.full_frame', { default: 'Full frame' });
        if (source === 'frigate_hint_crop') return $_('detection.video_analysis.evidence.frigate_hint_crop', { default: 'Frigate-guided crop' });
        if (source === 'frigate_region_crop') return $_('detection.video_analysis.evidence.frigate_region_crop', { default: 'Frigate-tracked area' });
        if (source === 'model_crop') return $_('detection.video_analysis.evidence.model_crop', { default: 'AI crop' });
        return source.replaceAll('_', ' ');
    }
</script>

<div class="flex items-start gap-2" role="status" data-video-status-notice={tone}>
    <svg class="mt-0.5 h-4 w-4 shrink-0 {toneInk}" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
        {#if tone === 'fail'}
            <circle cx="12" cy="12" r="10" /><line x1="12" y1="8" x2="12" y2="12" /><line x1="12" y1="16" x2="12.01" y2="16" />
        {:else if tone === 'attention'}
            <path d="M10.29 3.86L1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z" /><line x1="12" y1="9" x2="12" y2="13" /><line x1="12" y1="17" x2="12.01" y2="17" />
        {:else}
            <circle cx="12" cy="12" r="10" /><line x1="12" y1="16" x2="12" y2="12" /><line x1="12" y1="8" x2="12.01" y2="8" />
        {/if}
    </svg>
    <div class="flex min-w-0 flex-1 flex-col gap-1">
        <span class="text-xs font-semibold {tone === 'neutral' ? 'text-strong' : toneInk}">{title}</span>
        <span class="text-xs leading-snug text-ink" data-video-status-cause>{description}</span>
        {#if upstreamMissing && detection.frigate_last_checked_at}
            <span class="text-xs text-muted">
                {$_('detection.upstream_missing.last_checked', { default: 'Last checked' })}:
                {formatDateTime(detection.frigate_last_checked_at)}
                ·
                <a href={docsUrl} target="_blank" rel="noopener noreferrer" class="rounded-sm font-semibold text-accent-ink underline underline-offset-2 focus-ring">
                    {$_('detection.upstream_missing.learn_more', { default: 'Learn more' })}
                </a>
            </span>
        {/if}
        {#if showTechnicalDetails}
            <details class="mt-1" bind:open={detailsOpen}>
                <summary class="flex min-h-11 cursor-pointer select-none items-center rounded-sm text-xs font-semibold text-muted hover:text-strong focus-ring">
                    {detailsOpen
                        ? $_('detection.video_analysis.error_details.hide', { default: 'Hide technical details' })
                        : $_('detection.video_analysis.error_details.show', { default: 'Show technical details' })}
                </summary>
                <div class="mt-1 space-y-2 text-xs text-ink">
                    {#if insight.errorCode}
                        <p class="font-mono text-muted">
                            {$_('detection.video_analysis.error_details.error_code', { default: 'Error code: {code}', values: { code: insight.errorCode } })}
                        </p>
                    {/if}
                    {#if diagnostics}
                        <section aria-labelledby="video-evidence-heading">
                            <p id="video-evidence-heading" class="font-semibold text-strong">
                                {$_('detection.video_analysis.evidence.title', { default: 'Evidence from this run' })}
                            </p>
                            <p class="mt-0.5 text-muted">
                                {$_('detection.video_analysis.evidence.summary', {
                                    default: '{processed} of {sampled} sampled frames were decoded. A frame needed at least {threshold}% confidence to vote.',
                                    values: {
                                        processed: diagnostics.processed_frames,
                                        sampled: diagnostics.sampled_frames,
                                        threshold: Math.round(diagnostics.minimum_frame_score * 100)
                                    }
                                })}
                            </p>
                            <dl class="mt-2 divide-y divide-line-soft">
                                {#each sources as [source, evidence] (source)}
                                    <div class="py-2 first:pt-0 last:pb-0">
                                        <div class="flex items-baseline justify-between gap-3">
                                            <dt class="font-semibold text-strong">{sourceLabel(source)}</dt>
                                            <dd class="shrink-0 tabular-nums text-muted">
                                                {evidence.confident_frames}/{evidence.independent_frames ?? evidence.evaluated_frames}
                                                {$_('detection.video_analysis.evidence.confident_short', { default: 'confident' })}
                                            </dd>
                                        </div>
                                        <p class="mt-0.5 text-muted">
                                            {$_('detection.video_analysis.evidence.required', {
                                                default: 'Needed {required} matching confident moments from this source.',
                                                values: { required: evidence.required_supporting_frames }
                                            })}
                                        </p>
                                        {#if evidence.top_candidates.length > 0}
                                            <ul class="mt-1 flex flex-wrap gap-x-3 gap-y-1 text-muted" aria-label={$_('detection.video_analysis.evidence.top_candidates', { default: 'Top recurring candidates' })}>
                                                {#each evidence.top_candidates as candidate, index (index)}
                                                    <li>
                                                        <span class="font-semibold text-ink">{candidate.label}</span>
                                                        · {candidate.supporting_frames}× · {Math.round(candidate.median_score * 100)}%
                                                    </li>
                                                {/each}
                                            </ul>
                                        {/if}
                                    </div>
                                {/each}
                            </dl>
                        </section>
                    {/if}
                    {#if insight.causes.length > 0}
                        <div>
                            <p class="font-semibold text-strong">{$_('detection.video_analysis.error_details.why', { default: 'Why this can happen' })}</p>
                            <ul class="mt-1 list-disc space-y-1 pl-5">
                                {#each insight.causes as cause, index (index)}<li>{cause}</li>{/each}
                            </ul>
                        </div>
                    {/if}
                    {#if insight.checks.length > 0}
                        <div>
                            <p class="font-semibold text-strong">{$_('detection.video_analysis.error_details.checks', { default: 'What to check' })}</p>
                            <ul class="mt-1 list-disc space-y-1 pl-5">
                                {#each insight.checks as check, index (index)}<li>{check}</li>{/each}
                            </ul>
                        </div>
                    {/if}
                </div>
            </details>
        {/if}
    </div>
</div>
