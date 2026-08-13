<script lang="ts">
    import { fetchEvents, getThumbnailUrl } from '../api';
    import type { Detection } from '../api';
    import { getErrorMessage, isTransientRequestError } from '../utils/error-handling';
    import { logger } from '../utils/logger';
    import { _ } from 'svelte-i18n';

    interface Props {
        species: string;
        displayName: string;
        subName?: string | null;
        seenCount: number;
        heardCount?: number;
        /** Matches LeaderboardSpan, so the caption follows the selected period. */
        span?: string | undefined;
        onopen?: () => void;
    }

    let {
        species,
        displayName,
        subName = null,
        seenCount,
        heardCount = 0,
        span = 'month',
        onopen
    }: Props = $props();

    /** Tiles on screen. Anything beyond this is cycled through them. */
    const TILES = 4;
    /** One tile changes per tick, so the collage drifts rather than cutting. */
    const CYCLE_MS = 3600;
    const FADE_MS = 1600;

    let photos = $state<Detection[]>([]);
    /** Which photo each tile is showing. Only one entry changes per tick. */
    let slots = $state<number[]>([]);
    let nextTile = $state(0);

    $effect(() => {
        const name = species;
        photos = [];
        slots = [];
        nextTile = 0;
        if (!name) return;

        const controller = new AbortController();
        void (async () => {
            try {
                const events = await fetchEvents({ species: name, limit: 12 });
                if (controller.signal.aborted) return;
                photos = events.filter((event) => event.has_snapshot !== false);
                slots = Array.from({ length: Math.min(TILES, photos.length) }, (_unused, i) => i);
            } catch (error) {
                if (controller.signal.aborted) return;
                // The collage is decoration over the rankings; its absence is not an error state.
                if (isTransientRequestError(error)) {
                    logger.warn('Top species photos unavailable', { message: getErrorMessage(error) });
                } else {
                    logger.error('Failed to load top species photos', error);
                }
            }
        })();
        return () => controller.abort();
    });

    // Only cycle when there is genuinely more to show than fits, and never against a
    // reduced-motion preference.
    const canCycle = $derived(photos.length > TILES);

    $effect(() => {
        if (!canCycle) return;
        if (typeof window !== 'undefined' && window.matchMedia?.('(prefers-reduced-motion: reduce)').matches) {
            return;
        }
        const timer = setInterval(() => {
            // Advance a single tile to a photo none of the others is showing.
            const shown = new Set(slots);
            let candidate = (Math.max(...slots) + 1) % photos.length;
            for (let step = 0; step < photos.length && shown.has(candidate); step++) {
                candidate = (candidate + 1) % photos.length;
            }
            slots = slots.map((current, index) => (index === nextTile ? candidate : current));
            nextTile = (nextTile + 1) % slots.length;
        }, CYCLE_MS);
        return () => clearInterval(timer);
    });

    const visible = $derived(slots.map((photoIndex) => photos[photoIndex]).filter(Boolean));

    const spanLabel = $derived(
        span === 'day'
            ? $_('leaderboard.most_detected_day', { default: 'Most detected today' })
            : span === 'week'
              ? $_('leaderboard.most_detected_week', { default: 'Most detected this week' })
              : span === 'all'
                ? $_('leaderboard.most_detected_all', { default: 'Most detected ever' })
                : $_('leaderboard.most_detected_month', { default: 'Most detected this month' })
    );
</script>

{#if visible.length > 0}
    <section
        class="relative aspect-[16/9] overflow-hidden rounded-2xl border border-slate-200/70 sm:aspect-[21/9] dark:border-slate-700/50"
        data-leaderboard-collage
    >
        <!-- One frame reads as a portrait; several read as a collage. -->
        <div
            class="absolute inset-0 grid gap-0.5 {visible.length === 1
                ? 'grid-cols-1'
                : visible.length === 2
                  ? 'grid-cols-2'
                  : 'grid-cols-2 sm:grid-cols-4'}"
            aria-hidden="true"
        >
            {#each visible as photo, index (index)}
                <span class="relative block overflow-hidden">
                    {#key photo.frigate_event}
                        <img
                            src={getThumbnailUrl(photo.frigate_event)}
                            alt=""
                            loading="lazy"
                            decoding="async"
                            class="absolute inset-0 h-full w-full object-cover motion-reduce:animate-none"
                            style="animation: collage-fade {FADE_MS}ms ease-in-out"
                        />
                    {/key}
                </span>
            {/each}
        </div>
        <div class="absolute inset-0 bg-gradient-to-t from-slate-950/90 via-slate-950/35 to-slate-950/10"></div>

        <button
            type="button"
            class="absolute inset-x-0 bottom-0 block px-4 pb-4 pt-16 text-left focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-400 focus-visible:ring-offset-2"
            onclick={() => onopen?.()}
        >
            <span class="text-xs font-semibold uppercase tracking-[0.16em] text-white/75">
                {spanLabel}
            </span>
            <span class="mt-0.5 block font-display text-2xl font-bold text-white sm:text-3xl">
                {displayName}
            </span>
            {#if subName}
                <span class="block text-xs italic text-white/70">{subName}</span>
            {/if}
            <span class="mt-1 block text-xs text-white/80">
                {$_('leaderboard.collage_counts', {
                    values: { seen: seenCount.toLocaleString(), heard: heardCount.toLocaleString() },
                    default: '{seen} visits'
                })}
                {#if heardCount > 0}
                    &middot; {$_('leaderboard.heard_count', {
                        values: { count: heardCount.toLocaleString() },
                        default: '{count} heard'
                    })}
                {/if}
            </span>
        </button>
    </section>
{/if}

<style>
    /* The incoming frame fades up over the one it replaces, which stays put underneath. */
    @keyframes collage-fade {
        from {
            opacity: 0;
            transform: scale(1.04);
        }
        to {
            opacity: 1;
            transform: scale(1);
        }
    }

    @media (prefers-reduced-motion: reduce) {
        :global([data-leaderboard-collage] img) {
            animation: none !important;
        }
    }
</style>
