<script lang="ts">
    import { untrack } from 'svelte';
    import { fetchSnapshotCandidates, getThumbnailUrl } from '../api';
    import type { Detection, SnapshotCandidate } from '../api';
    import { advance, createReviewSession, remaining, type ReviewSession } from '../utils/review-session';
    import { formatDate, formatTime } from '../utils/datetime';
    import { trapFocus } from '../utils/focus-trap';
    import { portal } from '../utils/portal';
    import { findMatchingFullFrameCandidate } from '../utils/detection-evidence';
    import type { ReviewReason } from '../utils/review-queue';
    import { _ } from 'svelte-i18n';

    interface Props {
        queue: Detection[];
        /** Species the classifier knows, searched only once someone types. */
        labels?: string[];
        /** Species this feeder actually sees, offered first. */
        suggestions?: string[];
        /** Why each detection is queued; absent means a low score. */
        reasons?: Map<string, ReviewReason>;
        onidentify: (detection: Detection, species: string) => Promise<void> | void;
        onhide: (detection: Detection) => Promise<void> | void;
        /** Add the detection's species to the blocked list (#310). */
        onblock?: (detection: Detection) => Promise<void> | void;
        onopen?: (detection: Detection) => void;
        onclose: () => void;
    }

    let { queue, labels = [], suggestions = [], reasons, onidentify, onhide, onblock, onopen, onclose }: Props = $props();

    let session = $state<ReviewSession>(untrack(() => createReviewSession(queue)));
    // A wide feeder shot does not settle what a 56% blur is; the crop the classifier
    // scored does. Crops exist only for events that have been scanned, so this is a
    // best-effort enrichment rather than something the flow depends on.
    let crop = $state<SnapshotCandidate | null>(null);
    let fullFrame = $state<SnapshotCandidate | null>(null);
    let cropLoading = $state(false);
    let view = $state<'crop' | 'full'>('crop');
    let search = $state('');
    let busy = $state(false);
    let failedImageUrls = $state<Set<string>>(new Set());
    let dialogEl = $state<HTMLElement | null>(null);

    // The queue is captured once on open: items resolving underneath would move the
    // ground while someone is working, and the count is shown up front.
    // An 11,000-label list sorted alphabetically opens on earthworms and spiders, which is
    // no help at a bird feeder. Until someone types, offer what this feeder actually sees.
    const searching = $derived(search.trim().length > 0);
    const matches = $derived.by(() => {
        const term = search.trim().toLowerCase();
        if (!term) return suggestions.slice(0, 8);
        return labels.filter((label) => label.toLowerCase().includes(term)).slice(0, 8);
    });

    $effect(() => {
        // A new subject starts with a clean picker.
        void session.current?.frigate_event;
        search = '';
        failedImageUrls = new Set();
    });

    $effect(() => {
        const eventId = session.current?.frigate_event;
        crop = null;
        fullFrame = null;
        view = 'crop';
        if (!eventId) return;

        let cancelled = false;
        cropLoading = true;
        void (async () => {
            try {
                const response = await fetchSnapshotCandidates(eventId);
                if (cancelled) return;
                const cropped = (response.candidates ?? []).filter(
                    (candidate) => candidate.crop_box && (candidate.image_url || candidate.thumbnail_url)
                );
                const preferredCrop =
                    cropped.find((candidate) => candidate.selected) ??
                    cropped.sort((left, right) => right.ranking_score - left.ranking_score)[0] ??
                    null;
                crop = preferredCrop;
                fullFrame = findMatchingFullFrameCandidate(
                    response.candidates ?? [],
                    preferredCrop?.candidate_id ?? null
                );
            } catch {
                // No scan has been run for this event, so there is no crop to show.
                if (!cancelled) {
                    crop = null;
                    fullFrame = null;
                }
            } finally {
                if (!cancelled) cropLoading = false;
            }
        })();

        return () => {
            cancelled = true;
        };
    });

    const imageUrl = $derived(
        view === 'crop' && (crop?.image_url || crop?.thumbnail_url)
            ? (crop.image_url ?? crop.thumbnail_url ?? '')
            : view === 'full' && (fullFrame?.image_url || fullFrame?.thumbnail_url)
              ? (fullFrame.image_url ?? fullFrame.thumbnail_url ?? '')
            : session.current
              ? getThumbnailUrl(session.current.frigate_event)
              : ''
    );
    const imageFailed = $derived(Boolean(imageUrl && failedImageUrls.has(imageUrl)));

    function markImageFailed(url: string): void {
        failedImageUrls = new Set([...failedImageUrls, url]);
    }

    $effect(() => {
        if (!dialogEl) return;
        return trapFocus(dialogEl);
    });

    async function identify(species: string): Promise<void> {
        const current = session.current;
        if (!current || busy) return;
        busy = true;
        try {
            await onidentify(current, species);
            session = advance(session, 'resolved');
        } finally {
            busy = false;
        }
    }

    async function hide(): Promise<void> {
        const current = session.current;
        if (!current || busy) return;
        busy = true;
        try {
            await onhide(current);
            session = advance(session, 'resolved');
        } finally {
            busy = false;
        }
    }

    async function block(): Promise<void> {
        const current = session.current;
        if (!current || busy || !onblock) return;
        busy = true;
        try {
            await onblock(current);
            session = advance(session, 'resolved');
        } finally {
            busy = false;
        }
    }

    function skip(): void {
        if (busy) return;
        session = advance(session, 'skipped');
    }

    function handleKeydown(event: KeyboardEvent): void {
        if (event.key === 'Escape') {
            event.preventDefault();
            onclose();
            return;
        }
        // Skip is the only shortcut: identifying by accident is not recoverable in one keystroke.
        if (event.key === 's' && !busy && !session.done && event.target === dialogEl) {
            event.preventDefault();
            skip();
        }
    }
</script>

<div
    use:portal
    class="fixed inset-0 z-[70] flex items-center justify-center bg-slate-950/70 p-4 backdrop-blur-sm"
    data-review-queue-modal
>
    <div
        bind:this={dialogEl}
        role="dialog"
        aria-modal="true"
        aria-labelledby="review-session-title"
        tabindex="-1"
        onkeydown={handleKeydown}
        class="flex max-h-[92vh] w-full max-w-4xl flex-col overflow-hidden rounded-2xl border border-slate-200 bg-white shadow-2xl dark:border-slate-700 dark:bg-slate-900"
    >
        <header class="flex items-center gap-3 border-b border-slate-200 px-5 py-3 dark:border-slate-700">
            <div class="min-w-0">
                <h2 id="review-session-title" class="font-display text-base font-bold text-slate-900 dark:text-white">
                    {$_('dashboard.review_queue.title', { default: 'Needs your call' })}
                </h2>
                <p class="text-xs text-slate-500 dark:text-slate-400">
                    {session.done
                        ? $_('dashboard.review_session.summary', {
                              values: { resolved: session.resolved, skipped: session.skipped },
                              default: '{resolved} decided, {skipped} skipped'
                          })
                        : $_('dashboard.review_session.position', {
                              values: { position: session.position, total: session.total },
                              default: '{position} of {total}'
                          })}
                </p>
            </div>

            <div class="ml-auto flex items-center gap-3">
                <div class="hidden h-1.5 w-32 overflow-hidden rounded-full bg-slate-200 sm:block dark:bg-slate-700" aria-hidden="true">
                    <div
                        class="h-full rounded-full bg-brand-500 transition-[width] duration-300 motion-reduce:transition-none"
                        style="width: {session.total === 0 ? 100 : (session.index / session.total) * 100}%"
                    ></div>
                </div>
                <button class="btn btn-ghost min-h-11 px-3 py-1.5 text-sm" onclick={onclose}>
                    {$_('common.close', { default: 'Close' })}
                </button>
            </div>
        </header>

        {#if session.done}
            <div class="flex flex-col items-center justify-center gap-3 px-6 py-14 text-center">
                <div class="grid h-14 w-14 place-items-center rounded-full bg-emerald-100 text-emerald-700 dark:bg-emerald-950/50 dark:text-emerald-300">
                    <svg class="h-7 w-7" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" aria-hidden="true">
                        <path stroke-linecap="round" stroke-linejoin="round" d="m5 12 4 4L19 6" />
                    </svg>
                </div>
                <h3 class="font-display text-xl font-bold text-slate-900 dark:text-white">
                    {session.skipped > 0
                        ? $_('dashboard.review_session.done_with_skips', { default: 'Queue worked through' })
                        : $_('dashboard.review_session.done', { default: 'Queue clear' })}
                </h3>
                <p class="max-w-sm text-sm text-slate-600 dark:text-slate-300">
                    {session.skipped > 0
                        ? $_('dashboard.review_session.skipped_note', {
                              values: { count: session.skipped },
                              default: '{count} left for later. They stay in the queue.'
                          })
                        : $_('dashboard.review_session.done_note', {
                              default: 'Every visit has a species. Your corrections feed the per-camera ranking.'
                          })}
                </p>
                <button class="btn btn-primary mt-2 min-h-11 px-5 py-2" onclick={onclose}>
                    {$_('dashboard.review_session.back', { default: 'Back to the dashboard' })}
                </button>
            </div>
        {:else if session.current}
            {@const current = session.current}
            {@const isNewSpecies = reasons?.get(current.frigate_event) === 'new_species'}
            <div class="grid min-h-0 flex-1 gap-0 overflow-y-auto md:grid-cols-[minmax(0,1.25fr)_minmax(0,0.75fr)] md:overflow-hidden">
                <div class="flex min-h-0 flex-col justify-center bg-slate-950">
                    {#if imageFailed}
                        <div class="flex items-center justify-center py-16 text-slate-600">
                            <svg class="h-10 w-10" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="1.5" aria-hidden="true">
                                <path stroke-linecap="round" stroke-linejoin="round" d="M4 16l4.586-4.586a2 2 0 012.828 0L16 16m-2-2 1.586-1.586a2 2 0 012.828 0L20 14M6 20h12a2 2 0 002-2V6a2 2 0 00-2-2H6a2 2 0 00-2 2v12a2 2 0 002 2z" />
                            </svg>
                        </div>
                    {:else}
                        <img
                            src={imageUrl}
                            alt={$_('dashboard.review_session.image_alt', {
                                values: { camera: current.camera_name },
                                default: 'Unidentified detection on {camera}'
                            })}
                            class="max-h-[52vh] w-full object-contain"
                            onerror={() => markImageFailed(imageUrl)}
                        />
                    {/if}
                    {#if crop?.thumbnail_url && fullFrame?.thumbnail_url}
                        <div class="flex gap-1 px-4 pt-2" role="group" aria-label={$_('dashboard.review_session.view_label', { default: 'Which frame to show' })}>
                            <button
                                class="min-h-11 rounded-lg px-2.5 py-1 text-[11px] font-semibold transition-colors focus-ring {view === 'crop' ? 'bg-white/15 text-white' : 'text-slate-400 hover:text-slate-200'}"
                                aria-pressed={view === 'crop'}
                                onclick={() => (view = 'crop')}
                            >
                                {$_('dashboard.review_session.crop', { default: 'Best crop' })}
                            </button>
                            <button
                                class="min-h-11 rounded-lg px-2.5 py-1 text-[11px] font-semibold transition-colors focus-ring {view === 'full' ? 'bg-white/15 text-white' : 'text-slate-400 hover:text-slate-200'}"
                                aria-pressed={view === 'full'}
                                onclick={() => (view = 'full')}
                            >
                                {$_('dashboard.review_session.full_frame', { default: 'Full frame' })}
                            </button>
                            {#if crop.crop_strategy}
                                <span class="ml-auto self-center text-[10px] text-slate-500">{crop.crop_strategy}</span>
                            {/if}
                        </div>
                    {:else if !cropLoading}
                        <p class="px-4 pt-2 text-[10px] text-slate-500">
                            {$_('dashboard.review_session.no_crop', {
                                default: 'No crop stored for this detection. Open the full record to scan for one.'
                            })}
                        </p>
                    {/if}

                    <p class="flex flex-wrap items-center gap-x-3 gap-y-1 px-4 py-2.5 text-[11px] text-slate-400">
                        <span>{formatDate(current.detection_time)} {formatTime(current.detection_time)}</span>
                        <span>{current.camera_name}</span>
                        <span class="font-semibold text-accent-300">
                            {Math.round((current.score ?? 0) * 100)}%
                        </span>
                        {#if current.weather_condition}<span>{current.weather_condition}</span>{/if}
                    </p>
                </div>

                <div class="flex min-h-0 flex-col gap-3 overflow-y-auto p-4">
                    <div>
                        <p class="text-[11px] font-semibold uppercase tracking-[0.12em] text-slate-500 dark:text-slate-400">
                            {$_('dashboard.review_session.what_is_it', { default: 'What is it?' })}
                        </p>
                        <p class="mt-0.5 text-xs text-slate-500 dark:text-slate-400">
                            {#if isNewSpecies}
                                {$_('dashboard.review_session.new_species_note', {
                                    values: { species: current.display_name },
                                    default: 'First {species} recorded here. Confirm it, correct it, or block the species.'
                                })}
                            {:else}
                                {$_('dashboard.review_session.threshold_note', {
                                    default: 'The model scored this below the naming threshold.'
                                })}
                            {/if}
                        </p>
                    </div>

                    {#if isNewSpecies}
                        <div class="flex flex-wrap gap-2" data-review-new-species-actions>
                            <button
                                class="btn btn-primary min-h-11 flex-1 px-3 py-2 text-xs"
                                disabled={busy}
                                onclick={() => identify(current.display_name)}
                            >
                                {$_('dashboard.review_session.confirm_species', {
                                    values: { species: current.display_name },
                                    default: 'Confirm {species}'
                                })}
                            </button>
                            {#if onblock}
                                <button
                                    class="btn btn-secondary min-h-11 px-3 py-2 text-xs"
                                    disabled={busy}
                                    onclick={block}
                                >
                                    {$_('dashboard.review_session.block_species', {
                                        default: 'Block this species'
                                    })}
                                </button>
                            {/if}
                        </div>
                    {/if}

                    <label class="block">
                        <span class="sr-only">{$_('detection.search_species', { default: 'Search species' })}</span>
                        <input
                            class="input-base"
                            type="search"
                            bind:value={search}
                            placeholder={$_('dashboard.review_session.search', { default: 'Search species…' })}
                        />
                    </label>

                    <p class="text-[11px] font-semibold uppercase tracking-[0.12em] text-slate-500 dark:text-slate-400">
                        {searching
                            ? $_('dashboard.review_session.all_species', { default: 'All species' })
                            : $_('dashboard.review_session.seen_here', { default: 'Seen at this feeder' })}
                    </p>

                    <ul class="flex min-h-0 flex-1 flex-col gap-1.5 overflow-y-auto">
                        {#each matches as label (label)}
                            <li>
                                <button
                                    class="flex w-full items-center justify-between gap-2 rounded-xl border border-slate-200 px-3 py-2 text-left text-sm text-slate-800 transition-colors hover:border-brand-400 hover:bg-brand-50 focus-ring disabled:opacity-50 dark:border-slate-700 dark:text-slate-100 dark:hover:border-brand-600 dark:hover:bg-brand-950/30"
                                    disabled={busy}
                                    onclick={() => identify(label)}
                                >
                                    <span class="truncate">{label}</span>
                                    <span class="shrink-0 text-[11px] font-semibold text-brand-700 dark:text-brand-300">
                                        {$_('dashboard.field_log.identify', { default: 'Identify' })}
                                    </span>
                                </button>
                            </li>
                        {:else}
                            <li class="px-1 py-2 text-xs text-slate-500 dark:text-slate-400">
                                {searching
                                    ? $_('dashboard.review_session.no_matches', {
                                          default: 'No species matches that. Try fewer letters.'
                                      })
                                    : $_('dashboard.review_session.no_suggestions', {
                                          default: 'No species recorded yet. Search the full list above.'
                                      })}
                            </li>
                        {/each}
                    </ul>

                    <div class="flex flex-wrap gap-2 border-t border-slate-200 pt-3 dark:border-slate-700">
                        <button class="btn btn-secondary min-h-11 px-3 py-2 text-xs" disabled={busy} onclick={skip}>
                            {$_('dashboard.review_session.skip', { default: 'Skip for now' })}
                        </button>
                        <button class="btn btn-ghost min-h-11 px-3 py-2 text-xs" disabled={busy} onclick={hide}>
                            {$_('dashboard.review_session.not_a_bird', { default: 'Not a bird, hide it' })}
                        </button>
                        <button
                            class="btn btn-ghost ml-auto min-h-11 px-3 py-2 text-xs"
                            onclick={() => onopen?.(current)}
                        >
                            {$_('dashboard.review_session.full_record', { default: 'Open full record' })}
                        </button>
                    </div>
                </div>
            </div>

            <footer class="border-t border-slate-200 px-5 py-2 text-[11px] text-slate-500 dark:border-slate-700 dark:text-slate-400">
                {$_('dashboard.review_session.remaining', {
                    values: { count: remaining(session) },
                    default: '{count} still to look at'
                })}
            </footer>
        {/if}
    </div>
</div>
