<script lang="ts">
    /**
     * One BirdNET-Go call at a size worth reading: its spectrogram, wide and stretched along time,
     * with the clip playing across it.
     *
     * The spectrogram is the clip drawn as an image, so it is also the scrubber: a playhead moves
     * over it, a click or an arrow key seeks, and the part already heard is lit. The browser's own
     * audio control is never shown; it looked like a second, unrelated player.
     */
    import { _ } from 'svelte-i18n';
    import { withAuthParams } from '../api/core';
    import { appApiPath } from '../app/url-base';
    import { formatTime } from '../utils/datetime';
    import { heardConfidenceTone } from '../utils/heard-labels';

    interface Props {
        birdnetId: number;
        species: string;
        heardAt: string;
        confidence: number;
        sourceName?: string | null;
        /** BirdNET-Go's own page for the detection, for an owner who can open it. */
        birdnetUrl?: string | null;
    }
    let { birdnetId, species, heardAt, confidence, sourceName = null, birdnetUrl = null }: Props = $props();

    let audio = $state<HTMLAudioElement>();
    let paused = $state(true);
    let currentTime = $state(0);
    let duration = $state(0);
    let pictureFailed = $state(false);
    let clipFailed = $state(false);

    const picture = $derived(withAuthParams(`${appApiPath(`/audio/spectrogram/${birdnetId}`)}?width=800`));
    const clip = $derived(withAuthParams(appApiPath(`/audio/clip/${birdnetId}`)));
    // The playhead and the lit part are drawn from one position, read every frame while playing:
    // timeupdate arrives only a few times a second, so following it made the light trail the line.
    let position = $state(0);
    $effect(() => {
        if (paused || !audio) {
            position = currentTime;
            return;
        }
        const element = audio;
        let frame = requestAnimationFrame(function follow() {
            position = element.currentTime;
            frame = requestAnimationFrame(follow);
        });
        return () => cancelAnimationFrame(frame);
    });
    const played = $derived(duration > 0 ? Math.min(1, position / duration) : 0);
    const score = $derived(Math.round(confidence * 100));
    const clock = (seconds: number): string => {
        const whole = Math.max(0, Math.floor(Number.isFinite(seconds) ? seconds : 0));
        return `${Math.floor(whole / 60)}:${String(whole % 60).padStart(2, '0')}`;
    };

    function toggle(): void {
        if (!audio || clipFailed) return;
        if (audio.paused) audio.play().catch(() => {
            // A refused play (no user gesture yet, another tab holding audio) is not a broken clip;
            // only the media element's own error says that.
        });
        else audio.pause();
    }

    function seekTo(fraction: number): void {
        if (!audio || !duration) return;
        audio.currentTime = Math.min(1, Math.max(0, fraction)) * duration;
        if (audio.paused) audio.play().catch(() => {
            // A refused play (no user gesture yet, another tab holding audio) is not a broken clip;
            // only the media element's own error says that.
        });
    }

    function seekFromPointer(event: MouseEvent): void {
        const box = (event.currentTarget as HTMLElement).getBoundingClientRect();
        if (box.width > 0) seekTo((event.clientX - box.left) / box.width);
    }

    function seekFromKeys(event: KeyboardEvent): void {
        if (!audio || !duration) return;
        const step = event.key === 'ArrowRight' ? 1 : event.key === 'ArrowLeft' ? -1 : 0;
        if (step === 0) return;
        event.preventDefault();
        audio.currentTime = Math.min(duration, Math.max(0, audio.currentTime + step));
    }
</script>

<figure class="overflow-hidden rounded-xl border border-line-soft bg-surface" data-call-player>
    <audio
        bind:this={audio}
        bind:paused
        bind:currentTime
        bind:duration
        src={clip}
        preload="metadata"
        onerror={() => (clipFailed = true)}
    ></audio>
    <!-- Time runs across the width, so the clip is stretched along it; every frequency stays in view
         except the top quarter, which BirdNET-Go always leaves silent. -->
    <div class="relative h-44 w-full overflow-hidden bg-slate-950 sm:h-52">
        {#if pictureFailed}
            <p class="flex h-full items-center justify-center px-4 text-center text-xs text-slate-400">
                {$_('events.heard.no_spectrogram', { default: 'BirdNET-Go has no spectrogram for these calls any more.' })}
            </p>
        {:else}
            <img
                src={picture}
                alt={$_('events.heard.spectrogram_alt', { values: { species, time: formatTime(heardAt) }, default: 'Spectrogram of the strongest {species} call, {time}' })}
                class="absolute inset-x-0 top-[-33.333%] h-[133.333%] w-full object-fill"
                onerror={() => (pictureFailed = true)}
            />
            <!-- Once playing, what is still to come is dimmed and what has been heard stays bright.
                 Before that the whole call is shown at full strength. -->
            {#if duration > 0 && position > 0}
                <span class="pointer-events-none absolute inset-y-0 right-0 bg-slate-950/45" style="left: {played * 100}%" aria-hidden="true"></span>
                <span class="pointer-events-none absolute inset-y-0 w-0.5 -translate-x-1/2 bg-white shadow-[0_0_0_1px_rgb(0_0_0/0.35)]" style="left: {played * 100}%" aria-hidden="true"></span>
            {/if}
            <button
                type="button"
                class="absolute inset-0 cursor-pointer focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-brand-400 disabled:cursor-default"
                aria-label={$_('events.heard.seek', { default: 'Play from a point in the call. Arrow keys move one second.' })}
                disabled={clipFailed}
                onclick={seekFromPointer}
                onkeydown={seekFromKeys}
            ></button>
        {/if}
    </div>
    <figcaption class="flex flex-wrap items-center gap-x-3 gap-y-2 px-3 py-2.5">
        <button
            type="button"
            class="inline-flex h-11 w-11 shrink-0 items-center justify-center rounded-full bg-brand-600 text-white transition-colors hover:bg-brand-500 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-400 focus-visible:ring-offset-2 focus-visible:ring-offset-surface disabled:bg-slate-400 dark:disabled:bg-slate-700"
            aria-label={paused
                ? $_('events.heard.play_call', { values: { species }, default: 'Play the {species} call' })
                : $_('events.heard.pause_call', { values: { species }, default: 'Pause the {species} call' })}
            disabled={clipFailed}
            onclick={toggle}
            data-call-play
        >
            {#if paused}
                <svg class="ml-0.5 h-4 w-4" viewBox="0 0 24 24" fill="currentColor" aria-hidden="true"><path d="M8 5v14l11-7z" /></svg>
            {:else}
                <svg class="h-4 w-4" viewBox="0 0 24 24" fill="currentColor" aria-hidden="true"><path d="M7 5h4v14H7zM13 5h4v14h-4z" /></svg>
            {/if}
        </button>
        <span class="figure text-sm tabular-nums text-slate-800 dark:text-slate-100" aria-live="off">
            {clock(currentTime)}<span class="text-slate-400 dark:text-slate-500">{' / '}{duration ? clock(duration) : '–:––'}</span>
        </span>
        <span class="min-w-0 flex-1 text-xs text-slate-500 dark:text-slate-400">
            {#if clipFailed}
                {$_('events.heard.clip_unavailable', { default: 'BirdNET-Go could not play this clip.' })}
            {:else}
                {$_('events.heard.strongest_call', { default: 'Strongest call' })}
                <span class="font-semibold {heardConfidenceTone(confidence)}">{score}%</span>
                <span aria-hidden="true">{' · '}</span>
                <time datetime={heardAt} class="tabular-nums">{formatTime(heardAt, { hour: '2-digit', minute: '2-digit', second: '2-digit' })}</time>
                {#if sourceName}<span aria-hidden="true">{' · '}</span>{sourceName}{/if}
            {/if}
        </span>
        {#if birdnetUrl}
            <a
                href={birdnetUrl}
                target="_blank"
                rel="noopener noreferrer"
                class="inline-flex min-h-11 items-center gap-1.5 rounded-lg px-2 text-xs font-semibold text-brand-700 transition-colors hover:bg-surface-raised focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-500 dark:text-brand-300"
            >
                {$_('audio.table.open_birdnet', { default: 'Open in BirdNET-Go' })}
                <svg class="h-3.5 w-3.5" viewBox="0 0 20 20" fill="none" stroke="currentColor" stroke-width="1.8" aria-hidden="true"><path stroke-linecap="round" stroke-linejoin="round" d="M8 4H4v12h12v-4M11 3h6v6M17 3l-8 8" /></svg>
            </a>
        {/if}
    </figcaption>
</figure>
