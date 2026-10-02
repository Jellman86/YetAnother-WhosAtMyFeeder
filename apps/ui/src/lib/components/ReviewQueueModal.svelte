<script lang="ts">
    import { onDestroy, untrack } from 'svelte';
    import { applySnapshotCandidate, fetchFeederSpecies, fetchSnapshotCandidates, getSnapshotUrl, getThumbnailUrl, searchSpecies } from '../api';
    import type { BirdObservation, Detection, SearchResult, SnapshotCandidate } from '../api';
    import FrameStrip from './FrameStrip.svelte';
    import CountedBirds from './CountedBirds.svelte';
    import MediaImage from './MediaImage.svelte';
    import { getBirdNames } from '../naming';
    import { settingsStore } from '../stores/settings.svelte';
    import { authStore } from '../stores/auth.svelte';
    import { detectionsStore } from '../stores/detections.svelte';
    import {
        currentMoment,
        groupCandidatesIntoMoments,
        preferredCandidate,
        type FrameMoment
    } from '../utils/frame-moments';
    import { getErrorMessage } from '../utils/error-handling';
    import { speciesPickerNames, withoutCurrentSpecies } from '../utils/species-picker';
    import { getManualTagSearchOptions } from '../search/manual-tag-search';
    import { toastStore } from '../stores/toast.svelte';
    import { confirmAction } from '../stores/confirm_dialog.svelte';
    import { advance, createReviewSession, type ReviewSession } from '../utils/review-session';
    import { formatDate, formatTime } from '../utils/datetime';
    import { trapFocus } from '../utils/focus-trap';
    import { portal } from '../utils/portal';
    import { findMatchingFullFrameCandidate, sameFrameCropCandidates } from '../utils/detection-evidence';
    import { WholeScenePeek } from '../utils/whole-scene-peek.svelte';
    import type { ReviewReason } from '../utils/review-queue';
    import { _ } from 'svelte-i18n';

    interface Props {
        queue: Detection[];
        /** Species the classifier knows, offered when correcting a counted bird. */
        labels?: string[];
        /** Why each detection is queued; absent means a low score. */
        reasons?: Map<string, ReviewReason>;
        onidentify: (detection: Detection, species: string) => Promise<void> | void;
        onhide: (detection: Detection) => Promise<void> | void;
        /** Add the detection's species to the blocked list (#310). */
        onblock?: (detection: Detection) => Promise<void> | void;
        /** Delete outright, for when Frigate caught a rock rather than a bird (#375). */
        ondelete?: (detection: Detection) => Promise<void> | void;
        onopen?: (detection: Detection) => void;
        onclose: () => void;
        onbirdschanged?: () => void;
    }

    let { queue, labels = [], reasons, onidentify, onhide, onblock, ondelete, onopen, onclose, onbirdschanged }: Props = $props();

    let session = $state<ReviewSession>(untrack(() => createReviewSession(queue)));
    // The photograph is the record's own saved snapshot, the picture already chosen for it. The
    // candidate list only describes it: which frames exist, where the crop sits in its scene,
    // which birds were counted. A candidate file can be gone while its row remains, so the list
    // never swaps a working photograph for one of its own URLs.
    let fullFrame = $state<SnapshotCandidate | null>(null);
    let cropLoading = $state(false);
    /** Advanced when the saved photograph changes on the server, so the old bytes are not reused. */
    let photographVersion = $state(0);
    /** A finished reclassification can also save a new photograph and frames for this capture. */
    const settledMediaVersion = $derived(
        session.current ? detectionsStore.settledMediaVersion(session.current.frigate_event) : 0
    );
    // Every frame kept from the visit, in one strip, the same as the detection record (#256):
    // a reviewer deciding what a blurred shape is should see every moment, not only the crop
    // and its whole scene. Choosing one changes the photograph and nothing else.
    let candidates = $state<SnapshotCandidate[]>([]);
    let countedBirds = $state<BirdObservation[]>([]);
    /** Advanced on every reread of the birds, so an edit answered after it is not applied. */
    let countedBirdsGeneration = $state(0);
    let photograph = $state<SnapshotCandidate | null>(null);
    const wholeSceneCrops = $derived(sameFrameCropCandidates(candidates, photograph));
    let currentCandidateId = $state<string | null>(null);
    let currentSource = $state<string | null>(null);
    let applyingKey = $state<string | null>(null);
    let applyPending = $state(false);
    const moments = $derived<FrameMoment[]>(
        // The current frame still has the saved photograph even when its candidate files expired.
        groupCandidatesIntoMoments(candidates.filter((item) =>
            item.thumbnail_url || item.image_url || item.candidate_id === currentCandidateId
        ))
    );
    const activeMoment = $derived(currentMoment(moments, currentCandidateId, currentSource));
    // The photograph is the crop; the whole scene is a look, not a mode (#256). Same
    // controller as the detection record, so the two surfaces behave alike.
    // A whole scene that failed to load is not offered again; the photograph stays where it was.
    let failedSceneUrls = $state<ReadonlySet<string>>(new Set());
    const wholeSceneSources = $derived(
        // Full resolution only: a scene thumbnail is too small to judge by and cannot carry the outlines.
        [fullFrame?.image_url].filter(
            (url): url is string => !!url && !failedSceneUrls.has(url)
        )
    );
    const canPeek = $derived(Boolean(photograph?.crop_box) && wholeSceneSources.length > 0);
    const wholeScene = new WholeScenePeek(() => canPeek);
    let search = $state('');
    let busy = $state(false);
    let dialogEl = $state<HTMLElement | null>(null);

    // The queue is captured once on open: items resolving underneath would move the
    // ground while someone is working, and the count is shown up front.
    // An 11,000-label list sorted alphabetically opens on earthworms and spiders, which is
    // no help at a bird feeder. Until someone types, offer what this feeder actually sees.
    // The same opening list as "Pick a different species" on the full record (#503): the
    // feeder's own species, most visits first. Today's sightings alone offered two species
    // on a feeder with forty, and never the likely answer to a first-time oddity.
    let feederSpecies = $state.raw<SearchResult[] | null>(null);
    let feederSpeciesFailed = $state(false);
    fetchFeederSpecies()
        .then((results) => (feederSpecies = results))
        .catch(() => (feederSpeciesFailed = true));

    // Typing searches the species catalogue, not the raw classifier labels: many models
    // label by scientific name only, so "Goldcrest" matched nothing while "Regulus regulus"
    // did. The answer is kept with the words it answers, so a late reply to an earlier
    // query can never fill the list under a newer one.
    const SEARCH_DEBOUNCE_MS = 200;
    let searchAnswer = $state.raw<{ term: string; results: SearchResult[]; failed: boolean } | null>(null);
    const searchTerm = $derived(search.trim());
    const searching = $derived(searchTerm.length > 0);
    const currentAnswer = $derived(searching && searchAnswer?.term === searchTerm ? searchAnswer : null);

    $effect(() => {
        const term = searchTerm;
        // Clearing, moving to the next visit, closing, or losing owner access all rerun or
        // tear down this effect, which abandons whatever search was still outstanding.
        if (!term || !authStore.hasOwnerAccess) return;
        const controller = new AbortController();
        const timer = setTimeout(async () => {
            const options = getManualTagSearchOptions(term);
            try {
                const results = await searchSpecies(term, options.limit, options.hydrateMissing, controller.signal);
                if (!controller.signal.aborted) searchAnswer = { term, results, failed: false };
            } catch {
                if (!controller.signal.aborted) searchAnswer = { term, results: [], failed: true };
            }
        }, SEARCH_DEBOUNCE_MS);
        return () => {
            clearTimeout(timer);
            controller.abort();
        };
    });

    const matches = $derived.by(() => {
        const results = searching
            ? (currentAnswer?.results ?? [])
            : withoutCurrentSpecies(feederSpecies ?? [], session.current);
        return results
            .map((result) => ({ id: result.id, ...speciesPickerNames(result) }))
            .filter((choice, index, all) => all.findIndex((other) => other.id === choice.id) === index);
    });

    $effect(() => {
        // A new subject starts with a clean picker.
        void session.current?.frigate_event;
        search = '';
    });

    let candidateReadEpoch = 0;

    async function loadCandidates(eventId: string, isCancelled: () => boolean): Promise<void> {
        const requestEpoch = ++candidateReadEpoch;
        const isCurrent = () => requestEpoch === candidateReadEpoch && !isCancelled()
            && session.current?.frigate_event === eventId && authStore.hasOwnerAccess;
        if (!isCurrent()) return;
        cropLoading = true;
        try {
            const response = await fetchSnapshotCandidates(eventId);
            if (!isCurrent()) return;
            const all = response.candidates ?? [];
            // Which candidate the saved photograph is. Its record, not its file: the file may be
            // gone, and the photograph on screen does not depend on it.
            photograph = all.find((candidate) => candidate.candidate_id === response.current_candidate_id)
                ?? all.find((candidate) => candidate.selected)
                ?? null;
            fullFrame = findMatchingFullFrameCandidate(
                response.candidates ?? [],
                photograph?.candidate_id ?? null
            );
            candidates = all;
            countedBirds = response.birds ?? [];
            countedBirdsGeneration += 1;
            currentCandidateId = response.current_candidate_id ?? null;
            currentSource = response.current_source ?? null;
        } catch {
            // No scan has been run for this event, so there is no crop to show.
            if (isCurrent()) {
                fullFrame = null;
                photograph = null;
                candidates = [];
                countedBirds = [];
                countedBirdsGeneration += 1;
            }
        } finally {
            if (isCurrent()) cropLoading = false;
        }
    }

    let candidateSubject: string | null = null;

    $effect(() => {
        const eventId = session.current?.frigate_event;
        void settledMediaVersion;
        candidateReadEpoch += 1;
        // A settled run rereads the same capture in place, keeping its frames on screen meanwhile.
        const sameCapture = !!eventId && eventId === candidateSubject && authStore.hasOwnerAccess;
        candidateSubject = eventId ?? null;
        if (!sameCapture) {
            fullFrame = null;
            photograph = null;
            candidates = [];
            countedBirds = [];
            // Read untracked: this effect must not rerun because it advanced the generation.
            untrack(() => { countedBirdsGeneration += 1; });
            currentCandidateId = null;
            currentSource = null;
            failedSceneUrls = new Set();
            wholeScene.reset();
        }
        if (!eventId || !authStore.hasOwnerAccess) return;

        let cancelled = false;
        void loadCandidates(eventId, () => cancelled);
        return () => {
            cancelled = true;
            candidateReadEpoch += 1;
        };
    });

    async function useMoment(moment: FrameMoment): Promise<void> {
        const eventId = session.current?.frigate_event;
        const candidate = preferredCandidate(moment);
        if (!eventId || !candidate || applyPending) return;
        applyPending = true;
        applyingKey = moment.key;
        try {
            await applySnapshotCandidate(eventId, { mode: 'candidate', candidate_id: candidate.candidate_id });
            wholeScene.reset();
            photographVersion += 1;
            await loadCandidates(eventId, () => session.current?.frigate_event !== eventId);
            toastStore.success($_('detection.snapshot_apply_success', { default: 'Snapshot updated' }));
        } catch (e) {
            toastStore.error(getErrorMessage(e) || $_('common.error', { default: 'Action failed' }));
        } finally {
            applyPending = false;
            applyingKey = null;
        }
    }

    // The saved photograph first, then the camera's thumbnail of the same capture: a working
    // picture is never given up for a missing one.
    const photographSources = $derived(
        session.current
            ? [
                  withVersion(getSnapshotUrl(session.current.frigate_event), photographVersion, settledMediaVersion),
                  getThumbnailUrl(session.current.frigate_event, settledMediaVersion)
              ]
            : []
    );

    /** The bands the visual standard sets, in their tones for the dark media surface. */
    function scoreTone(score: number): string {
        if (score < 0.6) return 'text-accent-300';
        if (score < 0.85) return 'text-brand-300';
        return 'text-success-300';
    }

    function withVersion(url: string, version: number, settledVersion: number): string {
        if (version === 0 && settledVersion === 0) return url;
        return `${url}${url.includes('?') ? '&' : '?'}v=${version}.${settledVersion}`;
    }

    let sceneEl = $state<HTMLImageElement | null>(null);
    /** The scene URL that has finished drawing; until then the photograph stays visible beneath. */
    let sceneLoadedUrl = $state<string | null>(null);
    const sceneReady = $derived(wholeScene.showing && sceneLoadedUrl !== null && sceneLoadedUrl === wholeSceneSources[0]);

    function sceneLoaded(image: HTMLImageElement): void {
        sceneLoadedUrl = image.getAttribute('src');
        measureWholeScene();
    }

    function sceneFailed(url: string): void {
        failedSceneUrls = new Set([...failedSceneUrls, url]);
        if (wholeSceneSources.length === 0) wholeScene.reset();
    }

    // The outlines are DOM measurements, taken once the whole scene has loaded and again when
    // the window changes size.
    function measureWholeScene(): void {
        // Crop boxes are frame pixels; only the full-resolution scene shares them, never its thumbnail.
        if (!fullFrame?.image_url || !sceneEl || sceneEl.getAttribute('src') !== fullFrame.image_url) {
            wholeScene.outline = null;
            wholeScene.otherOutlines = [];
            return;
        }
        const otherCropBoxes = wholeSceneCrops.slice(1).flatMap((candidate) =>
            candidate.crop_box ? [candidate.crop_box] : []
        );
        wholeScene.measure(sceneEl, wholeSceneCrops[0]?.crop_box, otherCropBoxes);
    }
    $effect(() => {
        if (!wholeScene.showing) {
            wholeScene.outline = null;
            wholeScene.otherOutlines = [];
            sceneLoadedUrl = null;
            return;
        }
        measureWholeScene();
        window.addEventListener('resize', measureWholeScene);
        return () => window.removeEventListener('resize', measureWholeScene);
    });
    onDestroy(wholeScene.destroy);

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

    async function remove(): Promise<void> {
        const current = session.current;
        if (!current || busy || !ondelete) return;
        // The record and its media go for good, so it is confirmed with the copy that says so
        // and names hiding as the alternative sitting next to it.
        if (!(await confirmAction({
            title: $_('actions.delete_detection', { default: 'Delete this visit permanently' }),
            message: $_('actions.confirm_delete', { values: { species: current.display_name } }),
            confirmLabel: $_('dashboard.review_session.delete', { default: 'Delete permanently' })
        }))) return;
        busy = true;
        try {
            await ondelete(current);
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
            // A pinned whole scene closes first; the queue stays open.
            if (wholeScene.pinned) {
                wholeScene.reset();
                return;
            }
            onclose();
            return;
        }
        // Skip is the only shortcut: identifying by accident is not recoverable in one keystroke.
        const shortcutFocus = event.target === dialogEl || event.target instanceof HTMLButtonElement;
        if (event.key === 's' && shortcutFocus && !event.ctrlKey && !event.metaKey && !event.altKey && !busy && !session.done) {
            event.preventDefault();
            skip();
        }
    }
</script>

<div
    use:portal
    class="fixed inset-0 z-[70] flex items-center justify-center bg-slate-950/70 p-0 backdrop-blur-sm sm:p-4"
    data-review-queue-modal
>
    <div
        bind:this={dialogEl}
        role="dialog"
        aria-modal="true"
        aria-labelledby="review-session-title"
        tabindex="-1"
        onkeydown={handleKeydown}
        class="flex h-[100dvh] max-h-[100dvh] w-full max-w-5xl flex-col overflow-hidden rounded-none border border-white/20 bg-white shadow-2xl dark:bg-slate-800 sm:h-auto sm:max-h-[92vh] sm:rounded-3xl"
    >
        <header class="relative flex items-center gap-3 border-b border-slate-200 py-1.5 pl-5 pr-2 dark:border-slate-700">
            <div class="flex min-w-0 items-baseline gap-x-2.5">
                <h2 id="review-session-title" class="truncate font-display text-base font-bold text-slate-900 dark:text-white">
                    {$_('dashboard.review_queue.title', { default: 'Needs your call' })}
                </h2>
                <p class="shrink-0 text-xs tabular-nums text-slate-500 dark:text-slate-400" data-review-position>
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

            <button
                type="button"
                class="ml-auto inline-flex h-11 w-11 shrink-0 items-center justify-center rounded-full text-slate-500 transition-colors hover:bg-slate-100 hover:text-slate-900 focus:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-brand-500/60 dark:text-slate-400 dark:hover:bg-slate-800 dark:hover:text-white"
                aria-label={$_('common.close', { default: 'Close' })}
                onclick={onclose}
            >
                <svg class="h-5 w-5" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true"><path d="M18 6 6 18M6 6l12 12" stroke-linecap="round" /></svg>
            </button>

            <!-- Progress rides the header's own rule, on every screen size; the words above say it too. -->
            <div class="absolute inset-x-0 -bottom-px h-0.5" aria-hidden="true">
                <div
                    class="h-full bg-brand-500 transition-[width] duration-300 motion-reduce:transition-none"
                    style="width: {session.total === 0 ? 100 : (session.index / session.total) * 100}%"
                ></div>
            </div>
        </header>

        {#if session.done}
            <div class="flex flex-col items-center justify-center gap-3 px-6 py-14 text-center">
                <div class="grid h-14 w-14 place-items-center rounded-full bg-success-100 text-success-700 dark:bg-success-950/50 dark:text-success-300">
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
            {@const naming = getBirdNames(current, settingsStore.displayCommonNames, settingsStore.scientificNamePrimary)}
            {@const isNewSpecies = reasons?.get(current.frigate_event) === 'new_species'}
            <!-- A column on phones: the media block keeps its own height and never overlaps the
                 rail beneath it. The two-column grid only applies where there is room. -->
            <div class="flex min-h-0 flex-1 flex-col overflow-y-auto md:grid md:grid-cols-[minmax(0,1.25fr)_minmax(0,0.75fr)] md:overflow-hidden">
                <div class="flex shrink-0 flex-col bg-slate-950 md:min-h-0 md:justify-center">
                    <!-- One box for the photograph whatever it is doing: loading, drawn, peeking at the
                         whole scene or missing. Nothing beneath it moves when an image arrives or fails. -->
                    <div class="relative aspect-[4/3] max-h-[52vh] w-full overflow-hidden" data-review-photograph>
                        <MediaImage
                            sources={photographSources}
                            alt={$_('dashboard.review_session.image_alt', {
                                values: { camera: current.camera_name },
                                default: 'Unidentified detection on {camera}'
                            })}
                            class="absolute inset-0 h-full w-full object-contain"
                            placeholderClass="text-slate-700"
                            iconClass="h-10 w-10"
                        />
                        {#if canPeek}
                            <!-- The whole scene is drawn over the photograph only once it has loaded, so a
                                 scene that is slow or missing never takes the photograph away. -->
                            {#if wholeScene.showing}
                                <MediaImage
                                    bind:element={sceneEl}
                                    sources={wholeSceneSources}
                                    alt=""
                                    class="absolute inset-0 h-full w-full bg-slate-950 object-contain transition-opacity duration-150 motion-reduce:transition-none {sceneReady ? 'opacity-100' : 'opacity-0'}"
                                    placeholderClass="hidden"
                                    onload={sceneLoaded}
                                    onfail={sceneFailed}
                                    data-review-whole-scene-image
                                />
                            {/if}
                            <!-- Hover or focus peeks at the whole scene with same-frame crops outlined; a tap or
                                 click pins it. No switch, and no strategy name: how the crop was found is
                                 the app's plumbing, not the reviewer's concern. -->
                            <button
                                type="button"
                                class="absolute inset-0 {wholeScene.pinned ? 'cursor-zoom-out' : 'cursor-zoom-in'} focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-white/70"
                                data-review-whole-scene-peek
                                aria-pressed={wholeScene.pinned}
                                aria-label={wholeScene.pinned
                                    ? $_('detection.whole_scene_back', { default: 'Back to the crop' })
                                    : $_('detection.whole_scene_show', { default: 'Show the whole scene' })}
                                onmouseenter={wholeScene.enter}
                                onmouseleave={wholeScene.leave}
                                onfocus={wholeScene.show}
                                onblur={wholeScene.leave}
                                onclick={wholeScene.toggle}
                            ></button>
                            {#if sceneReady && wholeScene.outline}
                                <div
                                    class="pointer-events-none absolute z-20 rounded-sm border-2 border-solid border-sky-300 {wholeScene.otherOutlines.length === 0 ? 'shadow-[0_0_0_9999px_rgba(2,6,23,0.35)]' : ''}"
                                    style="left: {wholeScene.outline.left}px; top: {wholeScene.outline.top}px; width: {wholeScene.outline.width}px; height: {wholeScene.outline.height}px;"
                                    data-review-whole-scene-outline
                                    aria-hidden="true"
                                ><span class="absolute left-0 top-0 rounded bg-sky-300 px-1.5 py-0.5 text-[10px] font-bold text-slate-950">{$_('detection.frame_chosen_badge', { default: 'Chosen' })}</span></div>
                                {#each wholeScene.otherOutlines as outline}
                                    <div
                                        class="pointer-events-none absolute z-10 rounded-sm border-2 border-dashed border-white/90"
                                        style="left: {outline.left}px; top: {outline.top}px; width: {outline.width}px; height: {outline.height}px;"
                                        data-review-other-bird-outline
                                        aria-hidden="true"
                                    ></div>
                                {/each}
                            {/if}
                            {#if sceneReady}
                                <span class="pointer-events-none absolute left-3 top-3 z-30 rounded-full border border-white/15 bg-slate-950/70 px-2.5 py-1 text-[11px] font-semibold text-white backdrop-blur-sm">
                                    {wholeScene.otherOutlines.length > 0
                                        ? $_('detection.whole_scene_multiple_outlined', { values: { count: wholeScene.otherOutlines.length + 1 }, default: 'Whole scene, {count} crop regions outlined' })
                                        : wholeScene.pinned
                                            ? $_('detection.whole_scene_chip_pinned', { default: 'Whole scene, the crop is outlined' })
                                            : $_('detection.whole_scene_chip', { default: 'Whole scene' })}
                                </span>
                            {/if}
                        {/if}
                    </div>
                    <!-- Who, then when and where, as one block: the record's media footer reads the same way.
                         The way into the full record sits with the capture it opens, not among the decisions. -->
                    <div class="flex items-start gap-3 px-4 pt-3 {authStore.hasOwnerAccess ? '' : 'pb-4'}" data-review-species-heading>
                        <div class="min-w-0 flex-1">
                            <h3 class="break-words font-display text-xl font-bold leading-tight text-white">{naming.primary}</h3>
                            {#if naming.secondary}
                                <p class="mt-0.5 break-words text-sm italic text-slate-300">{naming.secondary}</p>
                            {/if}
                            <p class="mt-1.5 flex flex-wrap items-center gap-x-1.5 gap-y-1 text-[11px] text-slate-400">
                                <span>{formatDate(current.detection_time)} {formatTime(current.detection_time)}</span>
                                <span aria-hidden="true">&middot;</span>
                                <span>{current.camera_name}</span>
                                <span aria-hidden="true">&middot;</span>
                                <span class="font-semibold tabular-nums {scoreTone(current.score ?? 0)}">
                                    <span class="sr-only">{$_('detection.confidence', { default: 'Confidence' })}</span>
                                    {Math.round((current.score ?? 0) * 100)}%
                                </span>
                                {#if current.weather_condition}
                                    <span aria-hidden="true">&middot;</span>
                                    <span>{current.weather_condition}</span>
                                {/if}
                            </p>
                        </div>
                        {#if onopen}
                            <button
                                type="button"
                                class="inline-flex min-h-11 min-w-11 shrink-0 items-center justify-center gap-1.5 rounded-full border border-white/20 bg-white/5 text-xs font-semibold text-white/90 transition-colors hover:bg-white/10 hover:text-white focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-white/70 sm:px-3.5"
                                onclick={() => onopen?.(current)}
                            >
                                <!-- A phone keeps the width for the name; the arrow alone still names itself. -->
                                <span class="sr-only sm:not-sr-only">{$_('dashboard.review_session.full_record', { default: 'Open full record' })}</span>
                                <svg class="h-3.5 w-3.5" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true"><path d="M7 17 17 7M9 7h8v8" stroke-linecap="round" stroke-linejoin="round" /></svg>
                            </button>
                        {/if}
                    </div>
                    {#if authStore.hasOwnerAccess}
                        <!-- Held from the first paint, so the frames arriving do not push anything down. -->
                        <div class="pt-3" data-review-frame-strip>
                            <FrameStrip
                                {moments}
                                current={activeMoment}
                                primaryName={current.display_name}
                                loading={cropLoading}
                                {applyingKey}
                                busy={applyPending || busy}
                                photographUrl={photographSources[0] ?? null}
                                emptyText={candidates.some((candidate) => candidate.crop_box)
                                    ? null
                                    : $_('dashboard.review_session.no_crop', {
                                          default: 'No crop stored for this detection. Open the full record to scan for one.'
                                      })}
                                onuse={(moment) => { void useMoment(moment); }}
                            />
                        </div>
                    {/if}
                </div>

                <div class="flex flex-col gap-3 p-4 md:min-h-0 md:overflow-y-auto">
                    <!-- Why this needs a person, in words, with the amber wash flagged rows carry elsewhere.
                         The header already asks for the call, so there is no second heading over it. -->
                    <p class="-mx-4 -mt-4 flex items-start gap-2 bg-gradient-to-r from-amber-50 to-transparent px-4 py-3 text-sm text-slate-700 dark:from-amber-500/10 dark:text-slate-200" data-review-reason>
                        <span class="mt-1.5 h-2 w-2 shrink-0 rounded-full bg-amber-500" aria-hidden="true"></span>
                        <span>
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
                        </span>
                    </p>

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

                    <p id="review-species-choices" class="-mb-1 text-[11px] font-semibold uppercase tracking-[0.12em] text-slate-500 dark:text-slate-400">
                        {searching
                            ? $_('dashboard.review_session.all_species', { default: 'All species' })
                            : $_('dashboard.review_session.seen_here', { default: 'Seen at this feeder' })}
                    </p>

                    <!-- One list, rows split by hairlines rather than a stack of cards. -->
                    <ul
                        class="flex flex-col divide-y divide-slate-200/70 border-y border-slate-200/70 md:min-h-40 md:flex-1 md:overflow-y-auto dark:divide-slate-700/50 dark:border-slate-700/50"
                        aria-labelledby="review-species-choices"
                    >
                        {#each matches as choice (choice.id)}
                            <li>
                                <button
                                    class="group flex min-h-11 w-full items-center justify-between gap-3 rounded-lg px-2 py-2 text-left text-sm text-slate-800 transition-colors hover:bg-brand-50 focus-ring disabled:opacity-50 dark:text-slate-100 dark:hover:bg-brand-950/30"
                                    disabled={busy}
                                    onclick={() => identify(choice.id)}
                                >
                                    <span class="min-w-0">
                                        <span class="block truncate font-medium">{choice.primary}</span>
                                        {#if choice.secondary}
                                            <span class="block truncate text-xs italic text-slate-500 dark:text-slate-400">
                                                {choice.secondary}
                                            </span>
                                        {/if}
                                    </span>
                                    <!-- Said on every row for the button's name, but only the row in hand calls attention to it. -->
                                    <span class="shrink-0 text-xs font-semibold text-slate-500 transition-colors group-hover:text-brand-700 group-focus-visible:text-brand-700 dark:text-slate-400 dark:group-hover:text-brand-300 dark:group-focus-visible:text-brand-300">
                                        {$_('dashboard.field_log.identify', { default: 'Identify' })}
                                    </span>
                                </button>
                            </li>
                        {:else}
                            <li class="px-2 py-3 text-xs text-slate-500 dark:text-slate-400">
                                {#if searching && !currentAnswer}
                                    {$_('common.loading')}
                                {:else if currentAnswer?.failed}
                                    {$_('dashboard.review_session.search_failed', {
                                        default: "Couldn't search species. Edit the search to try again."
                                    })}
                                {:else if searching}
                                    {$_('dashboard.review_session.no_matches', {
                                        default: 'No species matches that. Try fewer letters.'
                                    })}
                                {:else if feederSpeciesFailed}
                                    {$_('dashboard.review_session.suggestions_unavailable', {
                                        default: "Couldn't load this feeder's species. Search the full list above."
                                    })}
                                {:else if feederSpecies === null}
                                    {$_('common.loading')}
                                {:else}
                                    {$_('dashboard.review_session.no_suggestions', {
                                        default: 'No species recorded yet. Search the full list above.'
                                    })}
                                {/if}
                            </li>
                        {/each}
                    </ul>

                    <!-- On a phone the list can run to every species this feeder has seen, so the ways out
                         stay pinned at the foot of the screen until their own place scrolls into view. -->
                    <div class="sticky bottom-0 z-10 -mx-4 flex flex-wrap gap-2 border-t border-slate-200/70 bg-white px-4 py-3 md:static md:mx-0 md:border-t-0 md:bg-transparent md:px-0 md:py-0 md:pt-1 dark:border-slate-700/50 dark:bg-slate-800 md:dark:bg-transparent" data-review-actions>
                        <button class="btn btn-secondary min-h-11 px-3 py-2 text-xs" disabled={busy} onclick={skip}>
                            {$_('dashboard.review_session.skip', { default: 'Skip for now' })}
                        </button>
                        <button class="btn btn-ghost min-h-11 px-3 py-2 text-xs" disabled={busy} onclick={hide}>
                            {$_('dashboard.review_session.not_a_bird', { default: 'Not a bird, hide it' })}
                        </button>
                        {#if ondelete}
                            <button
                                class="btn btn-ghost min-h-11 px-3 py-2 text-xs text-red-600 hover:bg-red-50 dark:text-red-400 dark:hover:bg-red-900/20"
                                disabled={busy}
                                onclick={remove}
                            >
                                {$_('dashboard.review_session.delete', { default: 'Delete permanently' })}
                            </button>
                        {/if}
                    </div>
                    <!-- The decision comes first on every screen; the birds counted in the capture are
                         supporting detail one scroll beneath it, in focus order as well as on screen. -->
                    {#if countedBirds.length > 0}
                        {#key current.frigate_event}
                            <CountedBirds
                                eventId={current.frigate_event}
                                birds={countedBirds}
                                {candidates}
                                {photograph}
                                speciesOptions={labels}
                                generation={countedBirdsGeneration}
                                onchanged={(updated) => { countedBirds = countedBirds.map((bird) => bird.id === updated.id ? updated : bird); onbirdschanged?.(); }}
                                onstale={() => { const eventId = current.frigate_event; void loadCandidates(eventId, () => session.current?.frigate_event !== eventId); onbirdschanged?.(); }}
                            />
                        {/key}
                    {/if}
                </div>
            </div>

        {/if}
    </div>
</div>
