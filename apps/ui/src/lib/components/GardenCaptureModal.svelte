<script lang="ts">
    /**
     * One Garden capture opened from the Explorer, in the record's shape: the photograph with
     * the animal crop takes the larger half, the decisions the smaller one.
     *
     * Presence and species are separate decisions. Photos proposed around the same position
     * open together, one photo at a time, because position does not identify an animal; the
     * remaining ones can be dismissed as a group. The rail follows the bird record's order: the
     * identification with its catalogue names and lineage, the state said once, the facts, the
     * decisions, what the species is, then the technical details closed by default.
     */
    import { onMount } from 'svelte';
    import { get } from 'svelte/store';
    import { _ } from 'svelte-i18n';
    import GardenAutomaticAssessment from './GardenAutomaticAssessment.svelte';
    import GardenDomesticSuggestion from './GardenDomesticSuggestion.svelte';
    import GardenExplorerMarker from './GardenExplorerMarker.svelte';
    import GardenPhotoCheckDialog from './GardenPhotoCheckDialog.svelte';
    import GardenCaptureThumbnail from './GardenCaptureThumbnail.svelte';
    import TaxonomyLineage from './TaxonomyLineage.svelte';
    import RecordTechnicalDetails from './RecordTechnicalDetails.svelte';
    import GardenSpeciesPicker from './GardenSpeciesPicker.svelte';
    import {
        checkGardenPhoto,
        renameGardenSpecies,
        clearGardenSpecies,
        fetchGardenIdentification,
        identifyGarden,
        reviewGarden,
        reviewGardenBatch,
        dismissGardenCaptures,
        reviewGardenIdentification,
        type GardenCapture,
        type GardenIdentificationStatus,
        type GardenIdentifyRequest,
        type GardenPhotoCheck
    } from '../api/garden';
    import { withAuthParams } from '../api/core';
    import { fetchSpeciesInfo, type SpeciesInfo } from '../api/species';
    import { getErrorMessage } from '../utils/error-handling';
    import { gardenPhotoOutline, gardenPreviewStyle } from '../utils/garden-photo';
    import { WholeScenePeek } from '../utils/whole-scene-peek.svelte';
    import { gardenEntryText, gardenEntryView, type GardenViewer } from '../utils/garden-explorer';
    import { formatDateTime, formatTime } from '../utils/datetime';
    import { trapFocus } from '../utils/focus-trap';
    import { lockDocumentScroll } from '../utils/document-scroll-lock';
    import { toastStore } from '../stores/toast.svelte';
    import { authStore } from '../stores/auth.svelte';
    import { SCORE_FILL, scoreBand } from '../utils/score-tone';

    type Variant = NonNullable<GardenIdentifyRequest['variant']>;
    type Provider = NonNullable<GardenIdentifyRequest['provider']>;

    interface Props {
        capture: GardenCapture;
        /** Photos opened together, in display order, including this one. */
        group?: GardenCapture[];
        /** `position`: motion proposals around one spot. `visit`: one animal's stay. */
        groupTotal?: number;
        groupOffset?: number;
        groupLoading?: boolean;
        groupError?: string | null;
        onpage?: (index: number) => void;
        groupKind?: 'position' | 'visit';
        onclose: () => void;
        /** The capture after any saved review; the Explorer decides whether it still belongs. */
        onchanged: (capture: GardenCapture) => void;
        onselect?: (capture: GardenCapture) => void;
        /** Photos dismissed together, for the page to offer Undo. */
        ongroupdismissed?: (ids: string[], skipped: number, restoreMode?: 'review') => void;
        /** Plays the capture's Frigate clip, as its card and row do. */
        onplay?: (capture: GardenCapture) => void;
    }
    let { capture, group = [capture], groupKind = 'position', groupTotal = group.length, groupOffset = 0, groupLoading = false, groupError = null, onpage, onclose, onchanged, onselect, ongroupdismissed, onplay }: Props = $props();

    let dialog = $state<HTMLElement | null>(null);
    let size = $state<readonly [number, number] | undefined>(undefined);
    let sizeCapture = $state<string | null>(null);
    let failedPhoto = $state<string | null>(null);
    let failedCrop = $state<string | null>(null);
    let mediaWidth = $state(0);
    let mediaHeight = $state(0);
    let peekCapture = $state<string | null>(null);
    let saving = $state(false);
    let editCapture = $state<string | null>(null);
    // Visitors read the record; every decision on it is the owner's.
    const canReview = $derived(authStore.hasOwnerAccess);
    const viewer = $derived<GardenViewer>(authStore.hasOwnerAccess ? 'owner' : 'visitor');
    const canDismissVisit = $derived(groupTotal <= 128 && groupTotal === group.length
        && group.every((item) => item.status === 'confirmed' && item.review_token));
    // The hide control dismisses what the Explorer shows as one entry, as a bird's hides its visit.
    const entryKind = $derived<'capture' | 'visit' | 'stack'>(groupTotal <= 1 ? 'capture' : groupKind === 'visit' ? 'visit' : 'stack');
    const entryBlocked = $derived.by((): string | null => {
        if (entryKind === 'capture') return null;
        if (groupTotal > 128) return $_('garden.visit_dismiss_limit', { default: 'Visits with more than 128 captures must be dismissed one capture at a time.' });
        if (groupLoading || groupTotal !== group.length) return $_('garden.visit_dismiss_reload', { default: 'Load this visit’s captures again before dismissing them together.' });
        if (group.every((item) => item.status === 'pending')) return null;
        if (canDismissVisit) return null;
        return $_('garden.entry_dismiss_mixed', { default: 'Captures here are in different review states. Dismiss them one capture at a time.' });
    });
    const entryDismissLabel = $derived(entryKind === 'visit'
        ? $_('garden.visit_dismiss', { default: '{count, plural, one {Dismiss # capture in this visit} other {Dismiss # captures in this visit}}', values: { count: groupTotal } })
        : entryKind === 'stack'
          ? $_('garden.group_dismiss', { default: '{count, plural, one {Dismiss remaining # photo} other {Dismiss remaining # photos}}', values: { count: groupTotal } })
          : $_('garden.dismiss', { default: 'Dismiss capture' }));
    let manualOverride = $state(false);
    let error = $state<string | null>(null);
    let identification = $state.raw<GardenIdentificationStatus | null>(null);
    const provider = $derived<Provider>(
        identification?.preferred_provider === 'intel_npu' ? 'intel_npu'
        : identification?.preferred_provider === 'intel_gpu' ? 'intel_gpu'
        : identification?.preferred_provider === 'intel_cpu' ? 'intel_cpu'
        : identification?.preferred_provider === 'cuda' ? 'cuda' : 'cpu'
    );
    let photoCheck = $state.raw<GardenPhotoCheck | null>(null);
    let photoCheckOpen = $state(false);
    let photoCheckBusy = $state(false);
    let photoCheckError = $state<string | null>(null);
    let photoCheckRun = $state(0);
    let photoCheckController: AbortController | null = null;

    const index = $derived(Math.max(0, group.findIndex((item) => item.id === capture.id)));
    // A capture carries its clip only while clips are on, and for a visitor only while video is shared.
    const canPlay = $derived(Boolean(onplay && capture.clip_event));
    // YA-WAMF's own copies, which outlast Frigate's retention; read-only evidence for Details.
    const keptMedia = $derived([capture.photo_kept && 'photo', capture.clip_kept && 'clip'].filter(Boolean).join(', ') || 'none');
    const view = $derived(gardenEntryView(capture));
    const originalFailed = $derived(failedPhoto === capture.id);
    const originalSize = $derived(sizeCapture === capture.id ? size : undefined);
    const canPeek = $derived(Boolean(capture.snapshot_url && !originalFailed && (
        (capture.crop_url && failedCrop !== capture.id) || gardenPhotoOutline(capture, originalSize)
    )));
    const peek = new WholeScenePeek(() => canPeek);
    const showingWhole = $derived(peekCapture === capture.id && peek.showing);
    const showingSavedCrop = $derived(Boolean(capture.crop_url && failedCrop !== capture.id && !showingWhole));
    const photoUrl = $derived(showingSavedCrop ? capture.crop_url : capture.snapshot_url);
    const outline = $derived(showingSavedCrop ? null : gardenPhotoOutline(capture, originalSize));
    const cropStyle = $derived(!showingSavedCrop && !showingWhole
        ? gardenPreviewStyle(capture, originalSize, mediaWidth > 0 && mediaHeight > 0 ? mediaWidth / mediaHeight : 4 / 3) : null);
    const imageStyle = $derived(cropStyle
        ? `width:${cropStyle.width}%;height:${cropStyle.height}%;left:${cropStyle.left}%;top:${cropStyle.top}%;max-width:none`
        : 'left:0;top:0');
    const photoFailed = $derived(showingSavedCrop ? failedCrop === capture.id : originalFailed);
    const photoReady = $derived(Boolean(capture.snapshot_url && !originalFailed && (originalSize || showingSavedCrop)));
    const installed = $derived((identification?.models ?? []).filter((model) => model.installed).map((model) => model.variant));
    // Whole image first, as Garden always offered it; the tracked-crop model answers too.
    const variant = $derived<Variant | null>(
        installed.includes('4.0.3b') ? '4.0.3b' : installed.includes('4.0.3a') ? '4.0.3a' : null
    );
    const identifyBlocked = $derived.by((): string | null => {
        if (!capture.snapshot_url || originalFailed) return $_('garden.snapshot_unavailable', { default: 'Snapshot unavailable' });
        if (!identification) return $_('garden.model_status_unavailable', { default: 'Model status unavailable. Refresh to try again.' });
        if (identification.error) return identification.error;
        if (!identification.catalogue_ready) return $_('garden.catalogue_unavailable', { default: 'Garden species data is unavailable. Check the application startup diagnostics.' });
        if (!identification.country) return $_('garden.country_missing', { default: 'Set a recognised country or ISO code in Settings → Location' });
        if (!variant) return $_('garden.model_download_in_settings', { default: 'This model is not downloaded. Download it under Garden models in Settings → Beta features.' });
        if (identification.busy) return $_('garden.explorer.model_busy', { default: 'The Garden model is busy with another photo. Try again shortly.' });
        return null;
    });
    const canCheckPhoto = $derived(Boolean(
        identification?.catalogue_ready && !identification.error && !identification.busy && installed.includes('4.0.3a')
        && capture.motion_source && capture.status === 'pending' && photoReady
    ));
    const title = $derived(gardenEntryText(capture, view, (key, fallback, values) => get(_)(key, { values, default: fallback }), viewer).title);
    // Catalogue context needs a name that stands: one the owner or the check accepted, or a suggestion.
    const referenceName = $derived(view.name && capture.scientific_name && (capture.owner_identification || capture.identification?.rank === 'species') ? view.name : null);
    const referenceScientificName = $derived(capture.scientific_name ?? null);
    const lineageName = $derived(view.name ? capture.scientific_name ?? null : null);
    let speciesInfo = $state.raw<SpeciesInfo | null>(null);
    let speciesInfoLoading = $state(false);
    let speciesInfoError = $state<string | null>(null);
    let failedReference = $state<string | null>(null);
    const referenceUrl = $derived(
        speciesInfo?.thumbnail_url && speciesInfo.thumbnail_url !== failedReference ? speciesInfo.thumbnail_url : null
    );
    const namedFrom = $derived.by((): string | null => {
        if (capture.owner_identification) {
            return viewer === 'owner'
                ? $_('garden.rename.chosen_by_you', { default: 'Species chosen by you' })
                : $_('garden.rename.chosen_by_owner', { default: 'Species chosen by the owner' });
        }
        const route = capture.status === 'confirmed' ? capture.domestic_route : null;
        if (route) {
            return route.origin === 'bird_detection'
                ? $_('garden.named_from.domestic_bird_model', { default: 'A domestic bird you keep, recognised by the bird model' })
                : route.origin === 'moved_from_birds'
                  ? $_('garden.named_from.domestic_moved', { default: 'A domestic bird you keep, moved from bird history; the bird record is hidden' })
                  : $_('garden.named_from.domestic_garden', { default: 'A domestic bird you keep, recognised by the automatic check' });
        }
        const named = capture.identification;
        if (!view.name || !named) return null;
        if (named.input_kind === 'whole_image') {
            return $_('garden.named_from.whole_image', { default: 'Named from the whole photo, so it may not refer to one animal' });
        }
        return capture.source_kind === 'motion'
            ? $_('garden.named_from.motion_crop', { default: 'Named from the animal crop in motion footage' })
            : $_('garden.named_from.tracked_crop', { default: "Named from Frigate's tracked animal in the snapshot" });
    });
    const status = $derived.by((): { text: string; tone: 'review' | 'confirmed' | 'neutral' } => {
        const entry = gardenEntryText(capture, view, (key, fallback, values) => get(_)(key, { values, default: fallback }), viewer);
        if (view.review === 'species') {
            return { text: $_('garden.explorer.review_species', { default: 'Needs review: the species was suggested, not confirmed.' }), tone: 'review' };
        }
        if (view.review === 'presence') return { text: entry.state, tone: 'review' };
        if (capture.status === 'confirmed') {
            const text = view.nameState === 'automatic'
                ? $_('garden.explorer.status_automatic', { default: 'Confirmed and named automatically' })
                : view.nameState === 'confirmed'
                  ? viewer === 'owner'
                    ? $_('garden.explorer.status_confirmed', { default: 'Animal and species confirmed by you' })
                    : $_('visits.owner_confirmed', { default: 'Owner confirmed' })
                  : $_('garden.explorer.state_unnamed', { default: 'Animal confirmed, species not named' });
            return { text, tone: 'confirmed' };
        }
        return { text: entry.state, tone: 'neutral' };
    });
    onMount(() => {
        const release = lockDocumentScroll();
        const controller = new AbortController();
        if (canReview) {
            fetchGardenIdentification(controller.signal)
                .then((status) => (identification = status))
                .catch(() => (identification = null));
        }
        return () => {
            controller.abort();
            clearPhotoCheck();
            peek.destroy();
            release();
        };
    });

    $effect(() => {
        if (dialog) return trapFocus(dialog);
    });

    // The species summary comes from the same reference service the bird record reads.
    $effect(() => {
        const name = referenceName;
        const scientificName = referenceScientificName;
        speciesInfo = null;
        speciesInfoError = null;
        if (!name || !scientificName) {
            speciesInfoLoading = false;
            return;
        }
        const controller = new AbortController();
        speciesInfoLoading = true;
        fetchSpeciesInfo(name, controller.signal, scientificName)
            .then((info) => { if (!controller.signal.aborted) speciesInfo = info; })
            .catch((failure: unknown) => { if (!controller.signal.aborted) speciesInfoError = getErrorMessage(failure); })
            .finally(() => { if (!controller.signal.aborted) speciesInfoLoading = false; });
        return () => controller.abort();
    });

    function photoLoaded(event: Event): void {
        const image = event.currentTarget;
        if (image instanceof HTMLImageElement && image.naturalWidth > 0 && image.naturalHeight > 0) {
            size = [image.naturalWidth, image.naturalHeight];
            sizeCapture = capture.id;
        }
    }

    function clearPhotoCheck(): void {
        photoCheckRun++;
        photoCheckController?.abort();
        photoCheckController = null;
        photoCheckOpen = false;
        photoCheck = null;
        photoCheckError = null;
        photoCheckBusy = false;
    }

    function move(direction: -1 | 1): void {
        if (saving || groupLoading) return;
        const next = group[index + direction];
        if (next) select(next);
        else { clearPhotoCheck(); size = undefined; error = null; onpage?.(groupOffset + index + direction); }
    }

    function select(next: GardenCapture | undefined): void {
        if (!next || saving || groupLoading) return;
        clearPhotoCheck();
        peek.reset();
        size = undefined;
        error = null;
        onselect?.(next);
    }

    function peekPhoto(action: 'enter' | 'show' | 'toggle'): void {
        if (peekCapture !== capture.id) peek.reset();
        peekCapture = capture.id;
        peek[action]();
    }

    async function act(run: () => Promise<GardenCapture>, message?: string): Promise<void> {
        if (saving) return;
        clearPhotoCheck();
        saving = true;
        error = null;
        try {
            const next = await run();
            if (message) toastStore.success(message);
            onchanged(next);
        } catch (failure) {
            error = failure instanceof Error ? failure.message : $_('garden.save_error', { default: 'Could not save your review. Try again.' });
            toastStore.error(error);
        } finally {
            saving = false;
        }
    }

    function review(action: 'confirm' | 'dismiss' | 'restore'): Promise<void> {
        const message = action === 'confirm'
            ? $_('garden.photo_confirmed', { default: 'Photo confirmed.' })
            : action === 'dismiss'
              ? $_('garden.explorer.dismissed', { default: 'Capture dismissed. Find it under Garden animals, Dismissed.' })
              : $_('garden.photo_restored', { default: 'Photo returned to review.' });
        // Similar photos stay; saying so keeps one decision from reading as the whole stack's.
        const remaining = groupTotal > 1 && action !== 'restore'
            ? ` ${$_('garden.group_remaining', { default: 'Other photos in this group still need review.' })}`
            : '';
        return act(() => reviewGarden(capture.id, action), message + remaining);
    }

    function suggestSpecies(): Promise<void> {
        const chosen = variant;
        if (!chosen) return Promise.resolve();
        return act(() => identifyGarden(capture.id, { variant: chosen, provider }));
    }

    const reviewName = (action: 'accept' | 'dismiss'): Promise<void> => act(() => reviewGardenIdentification(capture.id, action));

    async function dismissGroup(): Promise<void> {
        if (saving) return;
        clearPhotoCheck();
        saving = true;
        error = null;
        try {
            const result = await reviewGardenBatch(group.map((item) => item.id), 'dismiss');
            ongroupdismissed?.(result.updated_ids, result.skipped_count);
        } catch (failure) {
            error = failure instanceof Error ? failure.message : $_('garden.save_error', { default: 'Could not save your review. Try again.' });
            toastStore.error(error);
        } finally {
            saving = false;
        }
    }

    async function dismissVisit(): Promise<void> {
        if (saving || groupLoading || !canDismissVisit) return;
        const targets = group.flatMap((item) => item.review_token ? [{ id: item.id, review_token: item.review_token }] : []);
        clearPhotoCheck();
        saving = true;
        error = null;
        try {
            const result = await dismissGardenCaptures(targets);
            ongroupdismissed?.(result.updated_ids, result.skipped_count, 'review');
        } catch (failure) {
            error = getErrorMessage(failure);
            toastStore.error(error);
        } finally {
            saving = false;
        }
    }

    function dismissEntry(): Promise<void> {
        if (entryKind === 'capture') return review('dismiss');
        if (entryBlocked) return Promise.resolve();
        return group.every((item) => item.status === 'pending') ? dismissGroup() : dismissVisit();
    }

    async function checkPhoto(): Promise<void> {
        const source = capture.motion_source;
        const frame = size;
        if (!canCheckPhoto || !source || !frame) return;
        clearPhotoCheck();
        const run = photoCheckRun;
        const selectedProvider = provider;
        const controller = new AbortController();
        photoCheckController = controller;
        photoCheckOpen = true;
        photoCheckBusy = true;
        try {
            const result = await checkGardenPhoto(capture.id, { image_sha256: source.image_sha256, provider: selectedProvider }, controller.signal);
            if (run !== photoCheckRun || controller.signal.aborted) return;
            // The check must describe the photograph on screen, through the box on screen.
            if (result.capture_id !== capture.id || result.image_sha256 !== source.image_sha256 || result.provider !== selectedProvider
                || JSON.stringify(result.box_xywh) !== JSON.stringify(source.box_xywh) || JSON.stringify(result.frame_size) !== JSON.stringify(frame)) {
                throw new Error($_('garden.check_changed', { default: 'The photo check does not match the displayed photo. Refresh before trying again.' }));
            }
            photoCheck = result;
        } catch (failure) {
            if (run === photoCheckRun && !controller.signal.aborted) {
                photoCheckError = failure instanceof Error ? failure.message : $_('garden.check_unavailable', { default: 'Photo check unavailable. Review the photo yourself.' });
            }
        } finally {
            if (run === photoCheckRun) photoCheckBusy = false;
        }
    }

    function onkeydown(event: KeyboardEvent): void {
        // The photo check sits above the record and closes first.
        if (event.key === 'Escape' && !photoCheckOpen && !saving) {
            event.preventDefault();
            if (showingWhole) peek.reset();
            else onclose();
        }
        if (!photoCheckOpen && groupTotal > 1 && ['ArrowLeft', 'ArrowRight'].includes(event.key)
            && !(event.target instanceof HTMLInputElement || event.target instanceof HTMLTextAreaElement || event.target instanceof HTMLSelectElement)) {
            event.preventDefault();
            move(event.key === 'ArrowLeft' ? -1 : 1);
        }
    }
</script>

<svelte:window {onkeydown} />

<div
    class="fixed inset-0 z-50 flex items-center justify-center bg-slate-950/65 p-0 backdrop-blur-sm sm:p-4"
    role="presentation"
    onclick={(event) => { if (event.target === event.currentTarget && !saving) onclose(); }}
>
    <!-- The bird record's shape: the photograph full-bleed on the left with its subject over it,
         the decisions on the right, and the close control floating over both. -->
    <div
        bind:this={dialog}
        class="relative flex max-h-[100dvh] w-full max-w-5xl flex-col overflow-hidden rounded-none border border-white/20 bg-surface shadow-2xl sm:max-h-[92vh] sm:rounded-2xl"
        role="dialog"
        aria-modal="true"
        aria-labelledby="garden-capture-title"
        aria-busy={saving}
        tabindex="-1"
        data-garden-capture-modal
    >
        <button
            type="button"
            class="absolute right-4 top-4 z-40 inline-flex h-11 w-11 items-center justify-center rounded-full border border-white/25 bg-black/45 text-white shadow-lg backdrop-blur-sm transition-colors hover:bg-black/60 focus:outline-none focus-visible:ring-2 focus-visible:ring-white/60"
            onclick={onclose}
            disabled={saving}
            aria-label={$_('common.close', { default: 'Close' })}
        >
            <svg class="h-5 w-5" fill="none" stroke="currentColor" viewBox="0 0 24 24" aria-hidden="true"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2.5" d="M6 18L18 6M6 6l12 12" /></svg>
        </button>

        <div class="flex flex-1 flex-col overflow-y-auto overscroll-contain lg:grid lg:grid-cols-[minmax(0,1.1fr)_minmax(0,1fr)] lg:overflow-hidden">
            <div class="flex min-h-0 shrink-0 flex-col bg-slate-950 lg:shrink lg:overflow-y-auto lg:border-r lg:border-slate-200/70 dark:lg:border-slate-700/60" data-garden-capture-media>
                <div bind:clientWidth={mediaWidth} bind:clientHeight={mediaHeight} class="relative aspect-[4/3] min-h-72 min-w-0 shrink-0 overflow-hidden bg-slate-950 sm:aspect-video lg:flex-1">
                    {#if photoUrl && !photoFailed}
                        {#key `${capture.id}:${photoUrl}`}
                            <img src={withAuthParams(photoUrl)} alt="" aria-hidden="true" class="absolute inset-0 h-full w-full scale-110 object-cover opacity-25 blur-2xl" />
                            <div class="absolute inset-0 bg-slate-950/55" aria-hidden="true"></div>
                            <img
                                class="absolute h-full w-full object-contain"
                                style={imageStyle}
                                src={withAuthParams(photoUrl)}
                                alt={$_('garden.photo_alt', { default: 'Animal capture from {camera}', values: { camera: capture.camera } })}
                                onload={showingSavedCrop ? undefined : photoLoaded}
                                onerror={() => { if (showingSavedCrop) failedCrop = capture.id; else failedPhoto = capture.id; }}
                                data-garden-capture-photo
                            />
                        {/key}
                        {#if showingSavedCrop && (!capture.snapshot_url || originalFailed)}
                            <p class="absolute bottom-3 left-3 right-3 rounded bg-black/70 p-2 text-xs text-white" data-garden-saved-crop>
                                {$_('garden.saved_crop_only', { default: 'Saved animal crop. The original photo is unavailable.' })}
                            </p>
                        {/if}
                        {#if outline && !cropStyle}
                            {@const box = outline.box}
                            {@const frame = outline.size}
                            <svg class="pointer-events-none absolute inset-0 h-full w-full text-amber-400" viewBox={`0 0 ${frame[0]} ${frame[1]}`} preserveAspectRatio="xMidYMid meet" aria-hidden="true" data-garden-capture-box>
                                <rect x={box[0] * frame[0]} y={box[1] * frame[1]} width={box[2] * frame[0]} height={box[3] * frame[1]} fill="none" stroke="black" stroke-width="4" vector-effect="non-scaling-stroke" />
                                <rect x={box[0] * frame[0]} y={box[1] * frame[1]} width={box[2] * frame[0]} height={box[3] * frame[1]} fill="none" stroke="currentColor" stroke-width="2" vector-effect="non-scaling-stroke" />
                            </svg>
                        {/if}
                        {#if canPeek}
                            <button type="button" class="absolute inset-0 z-20 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-white"
                                aria-label={$_('garden.explorer.show_whole_photo', { default: 'Show whole photo' })} aria-pressed={peek.pinned && showingWhole}
                                onmouseenter={() => peekPhoto('enter')} onmouseleave={peek.leave}
                                onfocus={() => peekPhoto('show')} onblur={peek.leave} onclick={() => peekPhoto('toggle')}>
                                <span class="absolute bottom-3 left-3 right-3 rounded bg-black/70 p-2 text-xs text-white">
                                    {showingWhole
                                        ? $_('garden.explorer.whole_photo_hint', { default: 'Whole photo. Select again to return to the crop.' })
                                        : $_('garden.explorer.crop_photo_hint', { default: 'Animal crop. Open the whole photo for context.' })}
                                </span>
                            </button>
                        {/if}
                    {:else}
                        <p class="absolute inset-0 flex items-center justify-center p-4 text-center text-sm text-white/70">
                            {capture.status !== 'pending'
                                ? $_('garden.explorer.photo_expired', { default: 'The photo has expired. The confirmed record is kept.' })
                                : $_('garden.snapshot_unavailable', { default: 'Snapshot unavailable' })}
                        </p>
                    {/if}
                    <div class="absolute left-3 top-3 z-30"><GardenExplorerMarker overlay /></div>
                </div>
                <div class="relative flex shrink-0 flex-col gap-3 bg-slate-950 px-5 pb-5 pt-4">
                    <!-- On a phone the rail's title sits right under the picture, so this would say it twice. -->
                    <div class="flex flex-wrap items-center justify-between gap-3">
                        <div class="hidden min-w-0 flex-1 sm:block">
                            <h2 id="garden-capture-title" class="truncate text-xl font-bold leading-tight text-white drop-shadow-lg">{title}</h2>
                            <p class="mt-2 text-3xs font-semibold text-white/50">{formatDateTime(capture.observed_at)} &middot; {capture.camera}</p>
                        </div>
                        {#if canPlay}
                            <button
                                type="button"
                                class="btn btn-secondary min-h-11 shrink-0 gap-2 px-3 text-xs"
                                disabled={saving}
                                onclick={() => onplay?.(capture)}
                                aria-label={$_('garden.explorer.play_clip', { values: { name: title }, default: 'Play clip of {name}' })}
                                data-garden-capture-play
                            >
                                <svg class="h-3.5 w-3.5" viewBox="0 0 24 24" fill="currentColor" aria-hidden="true"><path d="M8 5v14l11-7z" /></svg>
                                {$_('garden.explorer.play_clip_short', { default: 'Play clip' })}
                            </button>
                        {/if}
                    </div>
                    {#if groupTotal > 1}
                        <div class="space-y-2" data-garden-capture-group>
                            <p class="text-sm font-semibold text-white">
                                {groupKind === 'position'
                                    ? $_('garden.group_count', { default: '{count, plural, one {# photo around the same position} other {# photos around the same position}}', values: { count: groupTotal } })
                                    : $_('garden.explorer.visit_heading', { default: '{count, plural, one {# capture in this visit} other {# captures in this visit}}', values: { count: groupTotal } })}
                            </p>
                            <p class="text-xs text-white/70">
                                {groupKind === 'position'
                                    ? $_('garden.group_help', { default: 'Position does not identify an animal. This group can contain different visitors.' })
                                    : $_('garden.explorer.visit_help', { default: 'Same camera and same animal, captures less than a minute apart, as bird visits are grouped. It can still be more than one animal.' })}
                            </p>
                            <div class="flex gap-2 overflow-x-auto pb-2" role="group" aria-label={$_('garden.explorer.visit_photos', { default: 'Photos in this group' })} aria-busy={groupLoading}>
                                {#each group as item, choiceIndex (item.id)}
                                    <button type="button" class="shrink-0 rounded border-2 p-1 text-white focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-white {item.id === capture.id ? 'border-white' : 'border-transparent hover:border-white/50'}"
                                        disabled={saving || groupLoading} aria-pressed={item.id === capture.id}
                                        aria-label={$_('garden.explorer.show_photo', { default: 'Show photo {index} of {count}, {time}', values: { index: groupOffset + choiceIndex + 1, count: groupTotal, time: formatDateTime(item.observed_at) } })}
                                        data-garden-capture-choice={item.id} onclick={() => select(item)}>
                                        <GardenCaptureThumbnail capture={item} />
                                        <span class="mt-1 block text-3xs tabular-nums">{formatTime(item.observed_at, { hour: '2-digit', minute: '2-digit', second: '2-digit' })}</span>
                                    </button>
                                {/each}
                            </div>
                            <div class="flex flex-wrap items-center justify-between gap-2">
                                <span class="text-xs tabular-nums text-white/80" aria-live="polite">{$_('garden.photo_count', { default: 'Photo {index} of {count}', values: { index: groupOffset + index + 1, count: groupTotal } })}</span>
                                {#if canReview && capture.status !== 'dismissed'}
                                    <!-- One capture out of the group, as a bird's photo is removed from its strip. -->
                                    <button type="button" class="btn btn-ghost min-h-11 px-3 text-xs text-white hover:bg-white/10" disabled={saving} onclick={() => review('dismiss')} data-garden-capture-dismiss>
                                        {$_('garden.dismiss', { default: 'Dismiss capture' })}
                                    </button>
                                {/if}
                            </div>
                            {#if groupOffset > 0 || groupOffset + group.length < groupTotal}
                                <div class="flex gap-2">
                                    <button type="button" class="btn btn-secondary min-h-11" disabled={saving || groupLoading || groupOffset === 0} onclick={() => onpage?.(groupOffset - 1)}>{$_('garden.explorer.earlier_photos', { default: 'Previous photos' })}</button>
                                    <button type="button" class="btn btn-secondary min-h-11" disabled={saving || groupLoading || groupOffset + group.length >= groupTotal} onclick={() => onpage?.(groupOffset + group.length)}>{$_('garden.explorer.later_photos', { default: 'More photos' })}</button>
                                </div>
                            {/if}
                        </div>
                    {/if}
                </div>
            </div>

            <div class="min-w-0 space-y-5 p-5 sm:p-6 lg:overflow-y-auto" data-garden-capture-rail>
                <!-- Identification: what it is, and how sure, in one place, as the bird record states it. -->
                <div class="pr-12" data-garden-capture-identity>
                    <div class="flex items-start gap-3">
                        {#if referenceUrl}
                            <img
                                src={referenceUrl}
                                alt={$_('detection.species_reference_alt', { values: { species: title }, default: 'Reference photograph of {species}' })}
                                loading="lazy"
                                onerror={() => (failedReference = referenceUrl)}
                                class="h-12 w-12 shrink-0 rounded-full border border-slate-200 object-cover dark:border-slate-700"
                                data-garden-species-reference
                            />
                        {/if}
                        <div class="min-w-0">
                            <p class="text-3xs font-semibold uppercase tracking-[0.14em] text-slate-500 dark:text-slate-400">
                                {view.nameState === 'confirmed'
                                    ? viewer === 'owner'
                                        ? $_('detection.identified_by_you', { default: 'Identified by you' })
                                        : $_('detection.identified_by_owner', { default: 'Identified by the owner' })
                                    : view.nameState === 'automatic'
                                      ? $_('detection.identified_as', { default: 'Identified as' })
                                      : view.nameState === 'suggested'
                                        ? $_('garden.explorer.suggested_as', { default: 'Suggested as' })
                                        : $_('garden.explorer.eyebrow_capture', { default: 'Garden capture' })}
                            </p>
                            <h3 class="font-display text-2xl font-bold text-slate-900 dark:text-white">{title}</h3>
                            {#if view.name && capture.scientific_name && capture.scientific_name !== view.name}
                                <p class="text-xs italic text-slate-500 dark:text-slate-400" data-garden-scientific-name>{capture.scientific_name}</p>
                            {/if}
                            {#if namedFrom}
                                <p class="mt-1 text-xs text-slate-500 dark:text-slate-400" data-garden-named-from>{namedFrom}</p>
                            {/if}
                            {#if view.name && !capture.owner_identification && capture.identification?.rank && capture.identification.rank !== 'species'}
                                <p class="mt-1 text-xs text-slate-500 dark:text-slate-400">{$_('garden.group_only', { default: 'Animal group only; species is unresolved.' })}</p>
                            {/if}
                        </div>
                    </div>
                    {#if view.score !== null}
                        <div class="mt-2 flex flex-wrap items-center gap-2.5" data-garden-capture-score>
                            <span class="text-sm font-bold tabular-nums text-slate-900 dark:text-white">{Math.round(view.score * 100)}%</span>
                            <span class="text-xs text-slate-500 dark:text-slate-400">
                                {$_('detection.fact_species_match', { default: 'Species match' })} &middot;
                                {scoreBand(view.score) === 'high'
                                    ? $_('detection.confidence_high', { default: 'confident' })
                                    : scoreBand(view.score) === 'mid'
                                      ? $_('detection.confidence_mid', { default: 'likely' })
                                      : $_('detection.confidence_low', { default: 'uncertain' })}
                            </span>
                            <span class="h-1.5 flex-1 overflow-hidden rounded-full bg-slate-200 dark:bg-slate-700">
                                <span class="block h-full rounded-full {SCORE_FILL[scoreBand(view.score)]}" style="width: {view.score * 100}%"></span>
                            </span>
                        </div>
                    {/if}
                </div>

                <!-- The record's state, said once. Amber only when it waits on a person. -->
                <p
                    class="flex items-start gap-2 text-sm font-semibold {status.tone === 'review'
                        ? 'rounded-xl border border-attention-500/50 bg-attention-500/10 px-3 py-2 text-attention-800 dark:text-attention-200'
                        : status.tone === 'confirmed'
                          ? 'text-success-700 dark:text-success-300'
                          : 'text-slate-700 dark:text-slate-200'}"
                    role="status"
                    data-garden-capture-status={status.tone}
                >
                    {#if status.tone !== 'neutral'}
                        <span class="mt-1.5 h-2 w-2 shrink-0 rounded-full {status.tone === 'review' ? 'bg-attention-500' : 'bg-success-500'}" aria-hidden="true"></span>
                    {/if}
                    {status.text}
                </p>
                {#if !capture.owner_identification && capture.identification?.outcome === 'unknown' && capture.identification.review !== 'dismissed'}
                    <p class="text-sm text-slate-600 dark:text-slate-300" data-garden-identification-unknown>
                        {$_('garden.identification_unknown', { default: 'No reliable identification. Leave this animal unidentified or request a new suggestion.' })}
                    </p>
                {/if}

                <!-- The bird record's facts, in its rows: when and where, then what proposed it. -->
                <dl class="divide-y divide-slate-200/70 border-y border-slate-200/70 text-xs dark:divide-slate-700/50 dark:border-slate-700/50" data-garden-capture-facts>
                    <div class="flex flex-wrap items-baseline justify-between gap-x-3 gap-y-1 py-2">
                        <dt class="flex items-center gap-2 text-slate-500 dark:text-slate-400">
                            <svg class="h-3.5 w-3.5 shrink-0 text-slate-400 dark:text-slate-500" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" aria-hidden="true"><path stroke-linecap="round" stroke-linejoin="round" d="M15 10l4.55-2.28A1 1 0 0121 8.62v6.76a1 1 0 01-1.45.9L15 14M5 18h8a2 2 0 002-2V8a2 2 0 00-2-2H5a2 2 0 00-2 2v8a2 2 0 002 2z" /></svg>
                            {$_('detection.fact_seen', { default: 'Seen' })}
                        </dt>
                        <dd class="min-w-0 max-w-full text-right font-medium text-slate-800 dark:text-slate-100">
                            <time datetime={capture.observed_at}>{formatDateTime(capture.observed_at)}</time> &middot; {capture.camera}
                        </dd>
                    </div>
                    <div class="flex flex-wrap items-baseline justify-between gap-x-3 gap-y-1 py-2">
                        <dt class="text-slate-500 dark:text-slate-400">{$_('garden.explorer.fact_source', { default: 'Proposed by' })}</dt>
                        <dd class="min-w-0 max-w-full break-words text-right font-medium text-slate-800 dark:text-slate-100">
                            {capture.source_kind === 'motion'
                                ? $_('garden.motion_source', { default: 'Candidate from retained motion footage' })
                                : $_('garden.frigate_suggested', { default: 'Frigate suggested: {label}', values: { label: capture.frigate_label } })}
                        </dd>
                    </div>
                    {#if outline}
                        <div class="py-2 text-slate-600 dark:text-slate-400">
                            {outline.kind === 'presence'
                                ? $_('garden.presence_box', { default: 'Box: MegaDetector Cedar candidate. Check the photo before confirming.' })
                                : $_('garden.explorer.identification_box', { default: 'Box: the crop the species model read.' })}
                        </div>
                    {/if}
                </dl>

                <!-- Until a person or the check has settled it, the check's result is the reason for the state above. -->
                {#if capture.automatic_check && capture.status !== 'confirmed'}
                    <GardenAutomaticAssessment assessment={capture.automatic_check} overridden={capture.automatic_check_overridden} named={false} />
                {/if}
                {#if viewer === 'owner' && capture.automatic_check?.domestic_candidate}
                    <GardenDomesticSuggestion bird={capture.automatic_check.domestic_candidate} />
                {/if}

                {#if groupError}
                    <p role="alert" class="text-sm text-red-700 dark:text-red-300">{groupError}</p>
                    <button type="button" class="btn btn-secondary" disabled={groupLoading} onclick={() => onpage?.(groupOffset + index)}>{$_('common.retry')}</button>
                {/if}
                {#if error}<p class="text-sm font-semibold text-red-700 dark:text-red-300" role="alert">{error}</p>{/if}

                {#if lineageName}
                    <TaxonomyLineage scientificName={lineageName} subject="animal" />
                {/if}

                {#if referenceName && (speciesInfoLoading || speciesInfo || speciesInfoError)}
                    <section class="space-y-2" data-garden-species-info>
                        <h4 class="text-xs font-semibold uppercase tracking-[0.12em] text-slate-500 dark:text-slate-400">
                            {$_('garden.explorer.about_species', { default: 'About {species}', values: { species: title } })}
                        </h4>
                        {#if speciesInfoLoading}
                            <div class="flex flex-col gap-2" aria-hidden="true">
                                <div class="h-3 w-3/4 animate-pulse rounded bg-slate-200 motion-reduce:animate-none dark:bg-slate-700"></div>
                                <div class="h-3 w-full animate-pulse rounded bg-slate-200 motion-reduce:animate-none dark:bg-slate-700"></div>
                            </div>
                        {:else if speciesInfoError}
                            <p class="text-xs text-slate-500 dark:text-slate-400">{speciesInfoError}</p>
                        {:else if speciesInfo}
                            {@const summary = speciesInfo.extract || speciesInfo.description}
                            <p class="line-clamp-4 whitespace-pre-line text-sm leading-relaxed text-slate-600 dark:text-slate-300">
                                {summary || $_('species_detail.no_info', { default: 'No description is available for this species.' })}
                            </p>
                            {#if speciesInfo.summary_source_url}
                                <a href={speciesInfo.summary_source_url} target="_blank" rel="noopener noreferrer" class="inline-flex min-h-11 items-center gap-1 text-xs font-semibold text-brand-700 hover:underline focus-ring dark:text-brand-300">
                                    {speciesInfo.summary_source || speciesInfo.source || $_('garden.explorer.source', { default: 'Source' })}
                                    <svg class="h-3 w-3" fill="none" stroke="currentColor" viewBox="0 0 24 24" aria-hidden="true"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M10 6H6a2 2 0 00-2 2v10a2 2 0 002 2h10a2 2 0 002-2v-4M14 4h6m0 0v6m0-6L10 14" /></svg>
                                </a>
                            {/if}
                        {/if}
                    </section>
                {/if}

                <!-- The decisions, in the bird record's row: the main one first, each named by its effect. -->
                {#if canReview}
                    <div class="flex flex-col gap-2 sm:flex-row sm:flex-wrap" data-garden-capture-actions>
                        {#if capture.status === 'pending'}
                            <details open={manualOverride} ontoggle={(event) => manualOverride = event.currentTarget.open} class="group/manual w-full" data-garden-manual-override>
                                <summary class="flex min-h-11 cursor-pointer list-none items-center justify-between gap-2 py-3 text-sm font-semibold focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-500 [&::-webkit-details-marker]:hidden">
                                    <span>{$_('garden.manual_override', { default: 'Manual override' })}</span>
                                    <svg class="h-4 w-4 shrink-0 transition-transform group-open/manual:rotate-180 motion-reduce:transition-none" viewBox="0 0 20 20" fill="none" stroke="currentColor" stroke-width="1.5" aria-hidden="true"><path stroke-linecap="round" stroke-linejoin="round" d="m5 7.5 5 5 5-5" /></svg>
                                </summary>
                                <div class="flex flex-col gap-2 sm:flex-row sm:flex-wrap">
                                    <button type="button" class="btn min-h-11 min-w-0 w-full whitespace-normal px-4 text-sm sm:w-auto btn-primary sm:flex-1" disabled={saving || !photoReady} onclick={() => review('confirm')}>
                                        {$_('garden.confirm_manually', { default: 'Confirm animal manually' })}
                                    </button>
                                    {#if capture.motion_source}
                                        <button type="button" class="btn min-h-11 min-w-0 w-full whitespace-normal px-4 text-sm sm:w-auto btn-secondary sm:flex-1" disabled={saving || !canCheckPhoto} onclick={checkPhoto} aria-describedby={canCheckPhoto ? undefined : 'garden-capture-check-note'}>
                                            {$_('garden.check_photo', { default: 'Check photo' })}
                                        </button>
                                    {/if}
                                </div>
                                {#if !photoReady}
                                    <p class="mt-2 text-xs text-slate-600 dark:text-slate-400">{$_('garden.explorer.confirm_needs_photo', { default: 'An animal can be confirmed only while its photo is shown.' })}</p>
                                {/if}
                                {#if capture.motion_source && !canCheckPhoto}
                                    <p id="garden-capture-check-note" class="mt-2 text-xs text-slate-600 dark:text-slate-400">{$_('garden.explorer.check_needs_model', { default: 'Photo checks need the automatic check model. Download it under Garden models in Settings → Beta features.' })}</p>
                                {/if}
                            </details>
                        {:else if capture.status === 'confirmed'}
                            {#if view.nameState === 'suggested' && view.name && !capture.owner_identification}
                                <button type="button" class="btn min-h-11 min-w-0 w-full whitespace-normal px-4 text-sm sm:w-auto btn-primary sm:flex-1" disabled={saving || !photoReady} onclick={() => reviewName('accept')}>
                                    <span class="min-w-0 [overflow-wrap:anywhere]">{$_('garden.explorer.confirm_name', { default: 'Confirm {name}', values: { name: view.name } })}</span>
                                </button>
                            {/if}
                            {#if capture.review_token}
                                <button type="button" class="btn min-h-11 min-w-0 w-full whitespace-normal px-4 text-sm sm:w-auto btn-secondary sm:flex-1" disabled={saving} aria-expanded={editCapture === capture.id} onclick={() => { editCapture = editCapture === capture.id ? null : capture.id; }} data-garden-pick-species>
                                    <span class="min-w-0 [overflow-wrap:anywhere]">{view.name
                                        ? $_('actions.pick_species', { default: 'Pick a different species' })
                                        : $_('garden.rename.pick', { default: 'Pick a species' })}</span>
                                </button>
                            {/if}
                            {#if capture.owner_identification}
                                <button type="button" class="btn min-h-11 min-w-0 w-full whitespace-normal px-4 text-sm sm:w-auto btn-ghost" disabled={saving || !capture.review_token} onclick={() => act(() => clearGardenSpecies(capture.id, capture.review_token ?? ''))}>
                                    {$_('garden.rename.revert', { default: 'Remove my species correction' })}
                                </button>
                            {:else if view.nameState === 'suggested' && view.name}
                                <button type="button" class="btn min-h-11 min-w-0 w-full whitespace-normal px-4 text-sm sm:w-auto btn-ghost" disabled={saving} onclick={() => reviewName('dismiss')}>
                                    {$_('garden.dismiss_suggestion', { default: 'Dismiss suggestion' })}
                                </button>
                            {:else if capture.domestic_route && capture.domestic_route.origin !== 'garden_check'}
                                <!-- Named from the owner's list, not a model suggestion: Pick a different species corrects it. -->
                            {:else if view.nameState === 'confirmed' || view.nameState === 'automatic'}
                                <button type="button" class="btn min-h-11 min-w-0 w-full whitespace-normal px-4 text-sm sm:w-auto btn-ghost" disabled={saving} onclick={() => reviewName('dismiss')}>
                                    {$_('garden.discard_identification', { default: 'Discard identification' })}
                                </button>
                            {:else}
                                <button type="button" class="btn min-h-11 min-w-0 w-full whitespace-normal px-4 text-sm sm:w-auto btn-ghost" disabled={saving || !photoReady || identifyBlocked !== null} onclick={suggestSpecies} aria-describedby={identifyBlocked ? 'garden-capture-identify-note' : undefined}>
                                    {saving ? $_('garden.working', { default: 'Working…' }) : $_('garden.suggest_species', { default: 'Suggest species' })}
                                </button>
                            {/if}
                        {:else}
                            <button type="button" class="btn min-h-11 min-w-0 w-full whitespace-normal px-4 text-sm sm:w-auto btn-primary sm:flex-1" disabled={saving || !capture.snapshot_url} onclick={() => review('restore')}>
                                {$_('garden.restore', { default: 'Return to review' })}
                            </button>
                        {/if}
                    </div>
                    {#if capture.status === 'confirmed' && !capture.owner_identification && view.nameState !== 'suggested' && view.nameState !== 'confirmed' && view.nameState !== 'automatic' && identifyBlocked}
                        <p id="garden-capture-identify-note" class="text-xs text-slate-600 dark:text-slate-400">{identifyBlocked}</p>
                    {/if}
                    {#if capture.status === 'dismissed' && !capture.snapshot_url}
                        <p class="text-xs text-slate-600 dark:text-slate-400">{$_('garden.photo_restore_unavailable', { default: 'Photo unavailable. It cannot return to review.' })}</p>
                    {/if}
                    {#if capture.status === 'confirmed' && capture.review_token && editCapture === capture.id}
                        {#key capture.id}
                            <GardenSpeciesPicker busy={saving} oncancel={() => { editCapture = null; }} onsave={(species) => {
                                void act(() => renameGardenSpecies(capture.id, species, capture.review_token ?? '')).then(() => { if (!error) editCapture = null; });
                            }} />
                        {/key}
                    {/if}
                {/if}

                <!-- The bird record's bottom row: the hide control dismisses the whole entry, reversible
                     from Garden animals, Dismissed; one capture is dismissed beside its photo. -->
                {#if canReview && capture.status !== 'dismissed'}
                    <div class="flex flex-wrap items-center gap-2 pt-2" data-garden-capture-bottom-actions>
                        <button
                            type="button"
                            class="rounded-xl bg-slate-100 p-3 text-slate-600 transition-colors hover:bg-slate-200 disabled:opacity-50 dark:bg-slate-700 dark:text-slate-300 dark:hover:bg-slate-600"
                            disabled={saving || entryBlocked !== null}
                            onclick={dismissEntry}
                            title={entryDismissLabel}
                            aria-label={entryDismissLabel}
                            aria-describedby={entryBlocked ? 'garden-entry-dismiss-note' : undefined}
                            data-garden-entry-dismiss={entryKind}
                        >
                            <svg class="h-5 w-5" fill="none" stroke="currentColor" viewBox="0 0 24 24" aria-hidden="true"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M13.875 18.825A10.05 10.05 0 0112 19c-4.478 0-8.268-2.943-9.543-7a9.97 9.97 0 011.563-3.029m5.858.908a3 3 0 114.243 4.243M9.878 9.878l4.242 4.242M9.88 9.88l-3.29-3.29m7.532 7.532l3.29 3.29M3 3l3.59 3.59m0 0A9.953 9.953 0 0112 5c4.478 0 8.268 2.943 9.543 7a10.025 10.025 0 01-4.132 5.411m0 0L21 21" /></svg>
                        </button>
                    </div>
                    {#if entryBlocked}
                        <p id="garden-entry-dismiss-note" class="text-xs text-slate-600 dark:text-slate-400">{entryBlocked}</p>
                    {/if}
                {/if}

                <!-- The saved run and capture evidence, read-only and closed by default. -->
                <RecordTechnicalDetails title={$_('garden.explorer.details', { default: 'Details' })} command="yawamf garden show" identifier={capture.id} data-garden-capture-details>
                    <dl class="mt-3 space-y-2">
                        {#each [['camera', capture.camera], ['source', capture.source_kind ?? 'frigate_event'], ['observed_at', capture.observed_at], ['kept_media', keptMedia]] as [key, value] (key)}
                            <div class="flex flex-wrap justify-between gap-x-3 gap-y-1"><dt class="text-slate-400">{key}</dt><dd class="min-w-0 max-w-full break-all">{value}</dd></div>
                        {/each}
                    </dl>
                    {#if capture.identification}
                        {@const evidence = capture.identification}
                        <dl class="mt-3 space-y-2 border-t border-slate-700 pt-3" data-garden-capture-identification>
                            <div class="flex flex-wrap justify-between gap-x-3 gap-y-1"><dt class="text-slate-400">model</dt><dd class="min-w-0 max-w-full break-all">SpeciesNet {evidence.variant} · {evidence.devices.join(', ')}</dd></div>
                            {#each [['model_species', evidence.name ?? ''], ['model_score', evidence.score == null ? '' : `${Math.round(evidence.score * 100)}%`], ['country', evidence.country], ['input_kind', evidence.input_kind], ['identified_at', evidence.identified_at], ['model_sha256', evidence.model_sha256], ['package_sha256', evidence.package_sha256], ['image_sha256', evidence.image_sha256]] as [key, value] (key)}
                                {#if value}<div class="flex flex-wrap justify-between gap-x-3 gap-y-1"><dt class="text-slate-400">{key}</dt><dd class="min-w-0 max-w-full break-all">{value}</dd></div>{/if}
                            {/each}
                        </dl>
                    {/if}
                    {#if capture.domestic_route}
                        {@const route = capture.domestic_route}
                        <dl class="mt-3 space-y-2 border-t border-slate-700 pt-3" data-garden-domestic-route>
                            {#each [['domestic_bird', route.domestic_bird], ['origin', route.origin], ['source_label', route.source_label], ['source_scientific_name', route.source_scientific_name ?? ''], ['source_score', route.source_score == null ? '' : `${Math.round(route.source_score * 100)}%`], ['source_model', route.source_model ?? ''], ['detection_id', route.detection_id == null ? '' : String(route.detection_id)], ['routed_at', route.routed_at]] as [key, value] (key)}
                                {#if value}<div class="flex flex-wrap justify-between gap-x-3 gap-y-1"><dt class="text-slate-400">{key}</dt><dd class="min-w-0 max-w-full break-all">{value}</dd></div>{/if}
                            {/each}
                        </dl>
                    {/if}
                    {#if capture.owner_identification}
                        <dl class="mt-3 space-y-2 border-t border-slate-700 pt-3" data-garden-owner-identity>
                            {#each [['owner_species', capture.owner_identification.name], ['owner_species_id', String(capture.owner_identification.species_id)], ['owner_changed_at', capture.owner_identification.changed_at]] as [key, value] (key)}
                                <div class="flex flex-wrap justify-between gap-x-3 gap-y-1"><dt class="text-slate-400">{key}</dt><dd class="min-w-0 max-w-full break-all">{value}</dd></div>
                            {/each}
                        </dl>
                    {/if}
                    {#if capture.motion_source}
                        {@const motion = capture.motion_source}
                        <dl class="mt-3 space-y-2 border-t border-slate-700 pt-3">
                            {#each [['clip_window', `${motion.clip_start} – ${motion.clip_end}`], ['frame_index', String(motion.frame_index)], ['box_xywh', JSON.stringify(motion.box_xywh)], ['detector_sha256', motion.detector_sha256], ['source_image_sha256', motion.image_sha256]] as [key, value] (key)}
                                <div class="flex flex-wrap justify-between gap-x-3 gap-y-1"><dt class="text-slate-400">{key}</dt><dd class="min-w-0 max-w-full break-all">{value}</dd></div>
                            {/each}
                        </dl>
                    {/if}
                    {#if capture.automatic_check && capture.status === 'confirmed'}
                        <div class="mt-3 border-t border-slate-700 pt-3">
                            <GardenAutomaticAssessment assessment={capture.automatic_check} overridden={capture.automatic_check_overridden} named={view.nameState === 'automatic'} terminal />
                        </div>
                    {/if}
                </RecordTechnicalDetails>
            </div>
        </div>
    </div>
</div>

{#if photoCheckOpen && size}
    <GardenPhotoCheckDialog capture={capture} assessment={photoCheck} busy={photoCheckBusy} error={photoCheckError} runId={photoCheckRun} {size} onClose={clearPhotoCheck} />
{/if}
