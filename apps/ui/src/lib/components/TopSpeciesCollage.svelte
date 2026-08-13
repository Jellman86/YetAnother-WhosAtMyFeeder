<script lang="ts">
    import { fetchEvents, getThumbnailUrl } from '../api';
    import type { Detection, LeaderboardSpan } from '../api';
    import {
        advanceCollageSlots,
        collageDateQuery,
        selectCollagePhotos
    } from '../leaderboard/collage';
    import { getErrorMessage, isTransientRequestError } from '../utils/error-handling';
    import { logger } from '../utils/logger';
    import { fade } from 'svelte/transition';
    import { _ } from 'svelte-i18n';

    interface Props {
        species: string;
        displayName: string;
        subName?: string | null;
        seenCount: number;
        heardCount?: number;
        span: LeaderboardSpan;
        sourceMode: 'seen' | 'both';
        windowStart?: string | null;
        windowEnd?: string | null;
        onopen?: () => void;
    }

    let {
        species,
        displayName,
        subName = null,
        seenCount,
        heardCount = 0,
        span,
        sourceMode,
        windowStart = null,
        windowEnd = null,
        onopen
    }: Props = $props();

    const TILES = 4;
    const MAX_PHOTOS = 12;
    const CYCLE_MS = 3600;
    const FADE_MS = 1400;

    let loading = $state(true);
    let photos = $state<Detection[]>([]);
    /** Stable event IDs keep tile positions fixed while their photographs crossfade. */
    let slots = $state<string[]>([]);
    let nextTile = $state(0);
    let reduceMotion = $state(false);

    $effect(() => {
        if (typeof window === 'undefined') return;
        const query = window.matchMedia('(prefers-reduced-motion: reduce)');
        const syncPreference = () => {
            reduceMotion = query.matches;
        };
        syncPreference();
        query.addEventListener('change', syncPreference);
        return () => query.removeEventListener('change', syncPreference);
    });

    $effect(() => {
        const name = species;
        const dateQuery = collageDateQuery(span, windowStart, windowEnd);
        photos = [];
        slots = [];
        nextTile = 0;
        loading = true;
        if (!name || !dateQuery) {
            loading = false;
            return;
        }

        const controller = new AbortController();
        void (async () => {
            try {
                const events = await fetchEvents({
                    species: name,
                    limit: 500,
                    startDate: dateQuery.startDate,
                    endDate: dateQuery.endDate,
                    fields: 'list',
                    requestKey: null,
                    signal: controller.signal
                });
                if (controller.signal.aborted) return;
                photos = selectCollagePhotos(events, {
                    windowStart: span === 'all' ? null : windowStart,
                    windowEnd: span === 'all' ? null : windowEnd,
                    maxPhotos: MAX_PHOTOS
                });
                slots = photos.slice(0, TILES).map((photo) => photo.frigate_event);
            } finally {
                if (!controller.signal.aborted) loading = false;
            }
        })().catch((error) => {
            if (controller.signal.aborted) return;
            if (isTransientRequestError(error)) {
                logger.warn('Top species photos unavailable', { message: getErrorMessage(error) });
            } else {
                logger.error('Failed to load top species photos', error);
            }
        });
        return () => controller.abort();
    });

    const canCycle = $derived(!reduceMotion && photos.length > TILES);

    $effect(() => {
        if (!canCycle) return;
        const timer = setInterval(() => {
            const advanced = advanceCollageSlots(
                slots,
                photos.map((photo) => photo.frigate_event),
                nextTile
            );
            slots = advanced.slots;
            nextTile = advanced.nextTile;
        }, CYCLE_MS);
        return () => clearInterval(timer);
    });

    const visible = $derived(
        slots
            .map((eventId) => photos.find((photo) => photo.frigate_event === eventId))
            .filter((photo): photo is Detection => Boolean(photo))
    );

    function markPhotoUnavailable(eventId: string): void {
        photos = photos.filter((photo) => photo.frigate_event !== eventId);
        const available = photos.map((photo) => photo.frigate_event);
        const nextSlots = slots.filter((slot) => slot !== eventId && available.includes(slot));
        for (const candidate of available) {
            if (nextSlots.length >= TILES) break;
            if (!nextSlots.includes(candidate)) nextSlots.push(candidate);
        }
        slots = nextSlots;
        nextTile = slots.length > 0 ? nextTile % slots.length : 0;
    }

    const spanLabel = $derived(
        sourceMode === 'both'
            ? $_('leaderboard.most_active', { default: 'Most active' })
            : span === 'day'
              ? $_('leaderboard.most_detected_day', { default: 'Most detected today' })
              : span === 'week'
                ? $_('leaderboard.most_detected_week', { default: 'Most detected this week' })
                : span === 'all'
                  ? $_('leaderboard.most_detected_all', { default: 'Most detected ever' })
                  : $_('leaderboard.most_detected_month', { default: 'Most detected this month' })
    );
</script>

{#if loading && visible.length === 0}
    <div
        class="aspect-[16/9] animate-pulse rounded-2xl border border-slate-200/70 bg-slate-100 sm:aspect-[21/9] dark:border-slate-700/50 dark:bg-slate-800/60"
        aria-hidden="true"
    ></div>
{:else if visible.length > 0}
    <section
        class="relative aspect-[16/9] overflow-hidden rounded-2xl border border-slate-200/70 sm:aspect-[21/9] dark:border-slate-700/50"
        data-leaderboard-collage
    >
        <div
            class="absolute -inset-x-6 inset-y-0 grid gap-1 {visible.length === 1
                ? 'grid-cols-1'
                : visible.length === 2
                  ? 'grid-cols-2'
                  : 'grid-cols-2 sm:grid-cols-4'}"
            aria-hidden="true"
        >
            {#each visible as photo, index (index)}
                <span class="collage-tile relative block overflow-hidden">
                    {#key photo.frigate_event}
                        <span
                            class="collage-unskew absolute inset-0 block"
                            in:fade={{ duration: reduceMotion ? 0 : FADE_MS }}
                            out:fade={{ duration: reduceMotion ? 0 : FADE_MS }}
                        >
                            <img
                                src={getThumbnailUrl(photo.frigate_event)}
                                alt=""
                                loading="lazy"
                                decoding="async"
                                class="collage-frame h-full w-full object-cover"
                                onerror={() => markPhotoUnavailable(photo.frigate_event)}
                            />
                        </span>
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
                    values: { seen: seenCount.toLocaleString() },
                    default: '{seen} visits'
                })}
                {#if sourceMode === 'both' && heardCount > 0}
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
    @keyframes -global-collage-drift {
        from {
            transform: scale(1.03) translate3d(0, 0, 0);
        }
        to {
            transform: scale(1.09) translate3d(0, -1.5%, 0);
        }
    }

    .collage-tile {
        transform: skewX(-7deg);
    }

    .collage-unskew {
        transform: skewX(7deg) scale(1.18);
    }

    .collage-frame {
        animation: collage-drift 16s ease-in-out infinite alternate;
        will-change: transform;
    }

    @media (prefers-reduced-motion: reduce) {
        .collage-frame {
            animation: none;
        }
    }
</style>
