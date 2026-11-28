<script lang="ts">
    import { _ } from 'svelte-i18n';
    import Panel from '../ui/Panel.svelte';
    import StatusChip from '../ui/StatusChip.svelte';
    import type { ReadingDisagreement } from './reading-agreement';

    /**
     * The snapshot reading and the video reading side by side when they named different birds
     * (#804). While the owner has not named the bird, the disagreement is work for a person: it
     * says so in words, with the one amber chip, and points at the decision under the name. Once
     * the owner has named it, both readings stay as evidence and nothing asks for a look.
     */
    type Props = {
        disagreement: ReadingDisagreement;
        snapshotName: string;
        videoName: string;
        /** What the video reading was taken from, such as cropped video frames. */
        videoInput: string | null;
        /** Score the clip again and apply the result, offered while the video's name is not the record's. */
        onscoreagain?: () => void;
        scoreAgainDisabled?: boolean;
    };

    let { disagreement, snapshotName, videoName, videoInput, onscoreagain, scoreAgainDisabled = false }: Props = $props();

    const headingId = $props.id();

    function percent(score: number | null): string | null {
        return typeof score === 'number' && Number.isFinite(score) ? `${Math.round(score * 100)}%` : null;
    }

    const snapshotScore = $derived(percent(disagreement.snapshot.score));
    const videoScore = $derived(percent(disagreement.videoScore));
</script>

<Panel as="div" data-record-readings={disagreement.needsPerson ? 'needs-person' : 'decided'}>
    <section aria-labelledby={headingId} class="space-y-3">
        <div class="flex flex-wrap items-center justify-between gap-2">
            <h4 id={headingId} class="text-xs font-semibold text-muted">
                {$_('detection.readings.title', { default: 'Snapshot and video' })}
            </h4>
            {#if disagreement.needsPerson}
                <StatusChip tone="attention" label={$_('detection.readings.disagree', { default: 'Readings disagree' })} />
            {/if}
        </div>
        <p class="text-sm text-ink" data-record-readings-cause>
            {disagreement.needsPerson
                ? $_('detection.readings.needs_person', {
                    default: 'The snapshot and the video named different birds. Look at the photo and the clip, then confirm the name or pick a different species.'
                })
                : $_('detection.readings.owner_decided', {
                    default: 'The snapshot and the video named different birds. You chose the name shown.'
                })}
        </p>
        <dl class="divide-y divide-line-soft border-y border-line-soft">
            <div class="flex items-baseline justify-between gap-3 py-2" data-record-reading="snapshot">
                <dt class="shrink-0 text-xs text-muted">{$_('detection.readings.snapshot', { default: 'Snapshot' })}</dt>
                <dd class="min-w-0 text-right">
                    <span class="text-sm font-semibold text-strong wrap-break-word">{snapshotName}</span>
                    {#if snapshotScore}<span class="ml-1.5 text-xs font-semibold tabular-nums text-ink">{snapshotScore}</span>{/if}
                </dd>
            </div>
            <div class="flex items-baseline justify-between gap-3 py-2" data-record-reading="video">
                <dt class="shrink-0 text-xs text-muted">{$_('detection.readings.video', { default: 'Video' })}</dt>
                <dd class="min-w-0 text-right">
                    <span class="text-sm font-semibold text-strong wrap-break-word">{videoName}</span>
                    {#if videoScore}<span class="ml-1.5 text-xs font-semibold tabular-nums text-ink">{videoScore}</span>{/if}
                    {#if videoInput}<span class="block text-xs text-muted">{videoInput}</span>{/if}
                </dd>
            </div>
        </dl>
        {#if onscoreagain}
            <button type="button" class="btn btn-secondary min-h-11 px-4 text-sm" disabled={scoreAgainDisabled} onclick={onscoreagain} data-record-readings-score-again>
                {$_('detection.score_again', { default: 'Score again' })}
            </button>
        {/if}
    </section>
</Panel>
