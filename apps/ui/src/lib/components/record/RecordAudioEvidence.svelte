<script lang="ts">
    import { _ } from 'svelte-i18n';
    import type { AudioContextDetection } from '../../api';
    import { withAuthParams } from '../../api/core';
    import { appApiPath } from '../../app/url-base';
    import Disclosure from '../ui/Disclosure.svelte';

    /**
     * What was heard around the visit: the matching call as a spectrogram that plays and seeks, and
     * every call in the window behind one disclosure. A match is stated once, in the facts above with
     * its score; here it is only the evidence. The parent remounts it for each record, so a playing
     * clip never carries over to the next bird.
     */
    type Props = {
        confirmed: boolean;
        nearbySummary: string;
        /** The call to show and play: the match, or the closest heard one. */
        entry: AudioContextDetection | null;
        calls: AudioContextDetection[];
        loading: boolean;
        loaded: boolean;
        error: string | null;
        /** Calls heard on a microphone this camera is not mapped to. */
        suppressed: number;
    };

    let { confirmed, nearbySummary, entry, calls, loading, loaded, error, suppressed }: Props = $props();

    // The spectrogram picture and the clip cannot send auth headers, so the token rides as a query
    // parameter, as Frigate media URLs do.
    const spectrogramUrl = $derived(entry?.birdnet_id != null ? withAuthParams(`${appApiPath(`/audio/spectrogram/${entry.birdnet_id}`)}?width=600`) : null);
    const clipUrl = $derived(entry?.birdnet_id != null ? withAuthParams(appApiPath(`/audio/clip/${entry.birdnet_id}`)) : null);

    /** The picture that failed, so its box keeps the quiet placeholder until another call is shown. */
    let failedSpectrogramUrl = $state<string | null>(null);
    let currentTime = $state(0);
    let duration = $state(0);
    let paused = $state(true);
    let audioElement = $state<HTMLAudioElement | null>(null);
    const progress = $derived(duration > 0 ? Math.min(100, Math.max(0, (currentTime / duration) * 100)) : 0);

    function clipTime(seconds: number): string {
        if (!isFinite(seconds) || seconds < 0) return '0:00';
        const total = Math.floor(seconds);
        return `${Math.floor(total / 60)}:${String(total % 60).padStart(2, '0')}`;
    }

    function offsetLabel(offsetSeconds: number): string {
        if (offsetSeconds === 0) return '0s';
        const abs = Math.abs(offsetSeconds);
        const minutes = Math.floor(abs / 60);
        return `${offsetSeconds > 0 ? '+' : '-'}${minutes > 0 ? `${minutes}m` : `${abs % 60}s`}`;
    }

    function togglePlayback(): void {
        if (!audioElement) return;
        if (audioElement.paused) audioElement.play().catch(() => {});
        else audioElement.pause();
    }

    function seekFromSpectrogram(event: MouseEvent): void {
        if (!audioElement || !audioElement.duration || !isFinite(audioElement.duration)) return;
        const picture = (event.currentTarget as HTMLElement).querySelector('img');
        const rect = picture?.getBoundingClientRect();
        if (!rect || rect.width <= 0) return;
        audioElement.currentTime = (Math.min(1, Math.max(0, (event.clientX - rect.left) / rect.width))) * audioElement.duration;
        if (audioElement.paused) audioElement.play().catch(() => {});
    }
</script>

<section data-detection-audio-section class="space-y-3 border-t border-line pt-5">
    <div class="min-w-0">
        <h3 class="text-xs font-semibold text-muted">
            {confirmed ? $_('detection.audio_match_evidence', { default: 'The matching call' }) : $_('detection.audio_context')}
        </h3>
        {#if !confirmed}
            <p class="text-sm font-bold text-ink wrap-break-word">
                {nearbySummary
                    ? $_('detection.audio_nearby', { values: { species: nearbySummary }, default: 'Nearby audio: {species}' })
                    : $_('detection.audio_no_match_desc', { default: 'No nearby BirdNET species in the matching window' })}
            </p>
        {/if}
    </div>

    {#if spectrogramUrl}
        <figure class="group/spec overflow-hidden rounded-xl border border-line-soft bg-media-raised">
            <!-- One fixed box whether the picture arrives or not: time runs across the width, as in the
                 call player, so a failed picture never collapses the row or spills its alt text. -->
            <div class="relative h-32 sm:h-40" data-record-spectrogram>
                <button
                    type="button"
                    class="relative m-0 block h-full w-full border-0 bg-transparent p-0 {clipUrl ? 'cursor-crosshair' : 'cursor-default'}"
                    onclick={clipUrl ? seekFromSpectrogram : undefined}
                    disabled={!clipUrl}
                    aria-label={$_('detection.audio_seek_spectrogram_aria', { default: 'Click to seek the audio clip' })}
                >
                    {#if failedSpectrogramUrl !== spectrogramUrl}
                        <img
                            src={spectrogramUrl}
                            alt={$_('detection.audio_spectrogram_alt', { default: 'BirdNET-Go spectrogram for the matched audio detection' })}
                            loading="lazy"
                            class="pointer-events-none absolute inset-0 block h-full w-full select-none object-fill"
                            onerror={() => { failedSpectrogramUrl = spectrogramUrl; }}
                        />
                    {/if}
                    {#if clipUrl && duration > 0}
                        <!-- A short trail behind the playhead, so the eye follows it. -->
                        <div
                            class="playhead pointer-events-none absolute top-0 bottom-0 w-12 max-w-1/6 bg-linear-to-r from-transparent to-on-media/30"
                            style="left: calc({progress}% - 3rem);"
                            aria-hidden="true"
                        ></div>
                        <div class="playhead pointer-events-none absolute top-0 bottom-0 w-px bg-on-media" style="left: {progress}%" aria-hidden="true"></div>
                    {/if}
                    {#if clipUrl}
                        <!-- Dimmed while paused, so the play button reads as the thing to press. -->
                        <div class="pointer-events-none absolute inset-0 transition-opacity duration-200 {paused ? 'bg-media/30 opacity-100 group-hover/spec:opacity-60' : 'opacity-0'}" aria-hidden="true"></div>
                    {/if}
                </button>
                {#if failedSpectrogramUrl === spectrogramUrl}
                    <p class="pointer-events-none absolute inset-x-0 bottom-0 px-3 py-2 text-xs text-on-media/80" data-record-spectrogram-unavailable>
                        {$_('detection.audio_spectrogram_unavailable', { default: 'No spectrogram for this call. It can still be played.' })}
                    </p>
                {/if}
                {#if clipUrl}
                    <!-- A sibling of the seek button, not inside it, so there is no button in a button. -->
                    <button
                        type="button"
                        onclick={(event) => { event.stopPropagation(); togglePlayback(); }}
                        class="absolute top-1/2 left-1/2 flex h-12 w-12 -translate-x-1/2 -translate-y-1/2 items-center justify-center rounded-full border border-on-media/25 bg-media-raised/80 text-on-media shadow-lg transition-opacity duration-150 hover:bg-media-raised focus-ring {paused ? 'opacity-95' : 'opacity-0 group-hover/spec:opacity-90 focus-visible:opacity-100'}"
                        aria-label={paused ? $_('detection.audio_play', { default: 'Play audio clip' }) : $_('detection.audio_pause', { default: 'Pause audio clip' })}
                    >
                        {#if paused}
                            <svg class="ml-0.5 h-5 w-5" viewBox="0 0 24 24" fill="currentColor" aria-hidden="true"><path d="M8 5v14l11-7z" /></svg>
                        {:else}
                            <svg class="h-5 w-5" viewBox="0 0 24 24" fill="currentColor" aria-hidden="true"><path d="M6 4h4v16H6zM14 4h4v16h-4z" /></svg>
                        {/if}
                    </button>
                    {#if duration > 0}
                        <div class="pointer-events-none absolute right-2 bottom-1.5 rounded-md bg-media-raised/90 px-1.5 py-0.5 text-xs font-semibold tabular-nums text-on-media">
                            {clipTime(currentTime)} / {clipTime(duration)}
                        </div>
                    {/if}
                {/if}
            </div>
            {#if clipUrl}
                <!-- Drives the playhead, trail and time; the buttons above are its controls. -->
                <audio
                    bind:this={audioElement}
                    bind:currentTime
                    bind:duration
                    bind:paused
                    preload="metadata"
                    src={clipUrl}
                    class="hidden"
                    aria-label={$_('detection.audio_clip_aria', { default: 'BirdNET-Go audio clip for the matched detection' })}
                ></audio>
            {/if}
            {#if entry}
                <figcaption class="flex flex-wrap items-center justify-between gap-x-3 bg-media-raised px-3 py-1.5 text-xs font-semibold text-on-media">
                    <span class="wrap-break-word">{entry.species}</span>
                    <span class="flex shrink-0 items-center gap-2 tabular-nums">
                        <span>{(entry.confidence * 100).toFixed(0)}%</span>
                        <span class="text-on-media/80">{offsetLabel(entry.offset_seconds)}</span>
                    </span>
                </figcaption>
            {/if}
        </figure>
    {:else if confirmed && loaded && calls.length > 0}
        <p class="text-xs text-muted">
            {$_('detection.audio_spectrogram_unavailable', { default: 'No spectrogram for this call. It can still be played.' })}
        </p>
    {/if}

    <Disclosure label={$_('detection.audio_context_all', { default: 'All calls heard around this visit' })} data-detection-audio-calls>
        {#if loading}
            <p class="text-xs text-muted" role="status">{$_('detection.audio_context_loading')}</p>
        {:else if error}
            <p class="text-xs font-semibold text-status-fail">{error}</p>
        {:else if calls.length === 0 && suppressed > 0}
            <p class="text-xs text-muted">
                {$_('detection.audio_context_suppressed', {
                    values: { count: suppressed },
                    default: 'Nearby audio was heard, but on a microphone this camera is not mapped to. Change the sensor mapping in Settings to include it.'
                })}
            </p>
        {:else if calls.length === 0}
            <p class="text-xs text-muted">{$_('detection.audio_context_empty')}</p>
        {:else}
            <ul class="divide-y divide-line-soft border-y border-line-soft">
                {#each calls as call, index (call.birdnet_id ?? index)}
                    <li class="flex items-center justify-between gap-3 py-2 text-xs">
                        <div class="min-w-0">
                            <p class="font-semibold text-ink wrap-break-word">{call.species}</p>
                            <p class="text-muted tabular-nums">
                                {(call.confidence * 100).toFixed(0)}%{#if call.sensor_id}{` · ${call.sensor_id}`}{/if}
                            </p>
                        </div>
                        <span class="shrink-0 font-semibold tabular-nums text-muted">{offsetLabel(call.offset_seconds)}</span>
                    </li>
                {/each}
            </ul>
        {/if}
    </Disclosure>
</section>

<style>
    /* The playhead and its trail glide between time updates, and jump where motion is reduced. */
    .playhead {
        transition: left 75ms linear;
    }
    @media (prefers-reduced-motion: reduce) {
        .playhead {
            transition: none;
        }
    }
</style>
