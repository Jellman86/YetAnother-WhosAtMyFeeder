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
    import GardenExplorerMarker from './GardenExplorerMarker.svelte';
    import GardenPhotoCheckDialog from './GardenPhotoCheckDialog.svelte';
    import GardenCaptureThumbnail from './GardenCaptureThumbnail.svelte';
    import TaxonomyLineage from './TaxonomyLineage.svelte';
    import {
        checkGardenPhoto,
        fetchGardenIdentification,
        identifyGarden,
        reviewGarden,
        reviewGardenBatch,
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
    import { gardenEntryText, gardenEntryView } from '../utils/garden-explorer';
    import { formatDateTime, formatTime } from '../utils/datetime';
    import { trapFocus } from '../utils/focus-trap';
    import { lockDocumentScroll } from '../utils/document-scroll-lock';
    import { toastStore } from '../stores/toast.svelte';

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
        ongroupdismissed?: (ids: string[], skipped: number) => void;
    }
    let { capture, group = [capture], groupKind = 'position', groupTotal = group.length, groupOffset = 0, groupLoading = false, groupError = null, onpage, onclose, onchanged, onselect, ongroupdismissed }: Props = $props();

    let dialog = $state<HTMLElement | null>(null);
    let size = $state<readonly [number, number] | undefined>(undefined);
    let sizeCapture = $state<string | null>(null);
    let failedPhoto = $state<string | null>(null);
    let failedCrop = $state<string | null>(null);
    let mediaWidth = $state(0);
    let mediaHeight = $state(0);
    let peekCapture = $state<string | null>(null);
    let saving = $state(false);
    let manualOverride = $state(false);
    let error = $state<string | null>(null);
    let identification = $state.raw<GardenIdentificationStatus | null>(null);
    let chosenVariant = $state<Variant | null>(null);
    let provider = $state<Provider>('cpu');
    let photoCheck = $state.raw<GardenPhotoCheck | null>(null);
    let photoCheckOpen = $state(false);
    let photoCheckBusy = $state(false);
    let photoCheckError = $state<string | null>(null);
    let photoCheckRun = $state(0);
    let photoCheckController: AbortController | null = null;

    const index = $derived(Math.max(0, group.findIndex((item) => item.id === capture.id)));
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
        chosenVariant && installed.includes(chosenVariant) ? chosenVariant : installed.includes('4.0.3b') ? '4.0.3b' : installed.includes('4.0.3a') ? '4.0.3a' : null
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
    const title = $derived(gardenEntryText(capture, view, (key, fallback, values) => get(_)(key, { values, default: fallback })).title);
    // Catalogue context needs a name that stands: one the owner or the check accepted, or a suggestion.
    const referenceName = $derived(view.name && capture.identification?.rank === 'species' ? view.name : null);
    const lineageName = $derived(view.name ? capture.scientific_name ?? null : null);
    let speciesInfo = $state.raw<SpeciesInfo | null>(null);
    let speciesInfoLoading = $state(false);
    let speciesInfoError = $state<string | null>(null);
    let failedReference = $state<string | null>(null);
    const referenceUrl = $derived(
        speciesInfo?.thumbnail_url && speciesInfo.thumbnail_url !== failedReference ? speciesInfo.thumbnail_url : null
    );
    const namedFrom = $derived.by((): string | null => {
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
        const entry = gardenEntryText(capture, view, (key, fallback, values) => get(_)(key, { values, default: fallback }));
        if (view.review === 'species') {
            return { text: $_('garden.explorer.review_species', { default: 'Needs review: the species was suggested, not confirmed.' }), tone: 'review' };
        }
        if (view.review === 'presence') return { text: entry.state, tone: 'review' };
        if (capture.status === 'confirmed') {
            const text = view.nameState === 'automatic'
                ? $_('garden.explorer.status_automatic', { default: 'Confirmed and named automatically' })
                : view.nameState === 'confirmed'
                  ? $_('garden.explorer.status_confirmed', { default: 'Animal and species confirmed by you' })
                  : $_('garden.explorer.state_unnamed', { default: 'Animal confirmed, species not named' });
            return { text, tone: 'confirmed' };
        }
        return { text: entry.state, tone: 'neutral' };
    });
    const providers = $derived<{ value: Provider; label: string }[]>([
        { value: 'cpu', label: 'CPU' },
        { value: 'intel_cpu', label: 'Intel CPU' },
        { value: 'intel_gpu', label: 'Intel GPU' },
        { value: 'intel_npu', label: 'Intel NPU' },
        { value: 'cuda', label: 'NVIDIA GPU' }
    ]);

    onMount(() => {
        const release = lockDocumentScroll();
        const controller = new AbortController();
        fetchGardenIdentification(controller.signal)
            .then((status) => (identification = status))
            .catch(() => (identification = null));
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
        speciesInfo = null;
        speciesInfoError = null;
        if (!name) {
            speciesInfoLoading = false;
            return;
        }
        const controller = new AbortController();
        speciesInfoLoading = true;
        fetchSpeciesInfo(name, controller.signal)
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
              ? $_('garden.explorer.dismissed', { default: 'Capture dismissed. Find it under Garden visitors, Dismissed.' })
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
        if (event.key === 'Escape' && !photoCheckOpen) {
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
                    <div class="hidden sm:block">
                        <h2 id="garden-capture-title" class="truncate text-xl font-bold leading-tight text-white drop-shadow-lg">{title}</h2>
                        <p class="mt-2 text-3xs font-semibold text-white/50">{formatDateTime(capture.observed_at)} &middot; {capture.camera}</p>
                    </div>
                    {#if groupTotal > 1}
                        <div class="space-y-2" data-garden-capture-group>
                            <p class="text-sm font-semibold text-white">
                                {groupKind === 'position'
                                    ? $_('garden.group_count', { default: '{count} photos around the same position', values: { count: groupTotal } })
                                    : $_('garden.explorer.visit_heading', { default: '{count} captures in this visit', values: { count: groupTotal } })}
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
                            <span class="text-xs tabular-nums text-white/80" aria-live="polite">{$_('garden.photo_count', { default: 'Photo {index} of {count}', values: { index: groupOffset + index + 1, count: groupTotal } })}</span>
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
                                    ? $_('detection.identified_by_you', { default: 'Identified by you' })
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
                            {#if view.name && capture.identification?.rank && capture.identification.rank !== 'species'}
                                <p class="mt-1 text-xs text-slate-500 dark:text-slate-400">{$_('garden.group_only', { default: 'Animal group only; species is unresolved.' })}</p>
                            {/if}
                        </div>
                    </div>
                    {#if view.score !== null}
                        <div class="mt-2 flex flex-wrap items-center gap-2.5" data-garden-capture-score>
                            <span class="text-sm font-bold tabular-nums text-slate-900 dark:text-white">{Math.round(view.score * 100)}%</span>
                            <span class="text-xs text-slate-500 dark:text-slate-400">
                                {$_('detection.fact_species_match', { default: 'Species match' })} &middot;
                                {view.score >= 0.85
                                    ? $_('detection.confidence_high', { default: 'confident' })
                                    : view.score >= 0.6
                                      ? $_('detection.confidence_mid', { default: 'likely' })
                                      : $_('detection.confidence_low', { default: 'uncertain' })}
                            </span>
                            <span class="h-1.5 flex-1 overflow-hidden rounded-full bg-slate-200 dark:bg-slate-700">
                                <span class="block h-full rounded-full {view.score >= 0.85 ? 'bg-success-500' : view.score >= 0.6 ? 'bg-brand-500' : 'bg-amber-500'}" style="width: {view.score * 100}%"></span>
                            </span>
                        </div>
                    {/if}
                </div>

                <!-- The record's state, said once. Amber only when it waits on a person. -->
                <p
                    class="flex items-start gap-2 text-sm font-semibold {status.tone === 'review'
                        ? 'rounded-xl border border-amber-500/50 bg-amber-500/10 px-3 py-2 text-amber-800 dark:text-amber-200'
                        : status.tone === 'confirmed'
                          ? 'text-success-700 dark:text-success-300'
                          : 'text-slate-700 dark:text-slate-200'}"
                    role="status"
                    data-garden-capture-status={status.tone}
                >
                    {#if status.tone !== 'neutral'}
                        <span class="mt-1.5 h-2 w-2 shrink-0 rounded-full {status.tone === 'review' ? 'bg-amber-500' : 'bg-success-500'}" aria-hidden="true"></span>
                    {/if}
                    {status.text}
                </p>
                {#if capture.identification?.outcome === 'unknown' && capture.identification.review !== 'dismissed'}
                    <p class="text-sm text-slate-600 dark:text-slate-300" data-garden-identification-unknown>
                        {$_('garden.identification_unknown', { default: 'No reliable identification. Leave this animal unidentified or try another model.' })}
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

                {#if groupError}
                    <p role="alert" class="text-sm text-red-700 dark:text-red-300">{groupError}</p>
                    <button type="button" class="btn btn-secondary" disabled={groupLoading} onclick={() => onpage?.(groupOffset + index)}>{$_('common.retry')}</button>
                {/if}
                {#if error}<p class="text-sm font-semibold text-red-700 dark:text-red-300" role="alert">{error}</p>{/if}

                <div class="flex flex-col gap-2 border-t border-line-soft pt-3" data-garden-capture-actions>
                    {#if capture.status === 'pending'}
                        <details open={manualOverride} ontoggle={(event) => manualOverride = event.currentTarget.open} class="group/manual space-y-2" data-garden-manual-override>
                            <summary class="flex min-h-11 cursor-pointer list-none items-center justify-between gap-2 py-3 text-sm font-semibold focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-500 [&::-webkit-details-marker]:hidden">
                                <span>{$_('garden.manual_override', { default: 'Manual override' })}</span>
                                <svg class="h-4 w-4 shrink-0 transition-transform group-open/manual:rotate-180 motion-reduce:transition-none" viewBox="0 0 20 20" fill="none" stroke="currentColor" stroke-width="1.5" aria-hidden="true"><path stroke-linecap="round" stroke-linejoin="round" d="m5 7.5 5 5 5-5" /></svg>
                            </summary>
                        <button type="button" class="btn btn-primary min-h-11 whitespace-normal px-4 py-2" disabled={saving || !photoReady} onclick={() => review('confirm')}>
                            {$_('garden.confirm_manually', { default: 'Confirm animal manually' })}
                        </button>
                        {#if !photoReady}
                            <p class="text-xs text-slate-600 dark:text-slate-400">{$_('garden.explorer.confirm_needs_photo', { default: 'An animal can be confirmed only while its photo is shown.' })}</p>
                        {/if}
                        {#if capture.motion_source}
                            <button type="button" class="btn btn-secondary min-h-11 whitespace-normal px-4 py-2" disabled={saving || !canCheckPhoto} onclick={checkPhoto} aria-describedby="garden-capture-check-note">
                                {$_('garden.check_photo', { default: 'Check photo' })}
                            </button>
                            <p id="garden-capture-check-note" class="text-xs text-slate-600 dark:text-slate-400">
                                {canCheckPhoto
                                    ? $_('garden.explorer.check_effect', { default: 'Asks the tracked-crop model about this photo only. Nothing is saved; the decision stays yours.' })
                                    : $_('garden.explorer.check_needs_model', { default: 'Photo checks need the automatic check model. Download it under Garden models in Settings → Beta features.' })}
                            </p>
                        {/if}
                        </details>
                    {:else if capture.status === 'confirmed'}
                        {#if view.nameState === 'suggested' && view.name}
                            <button type="button" class="btn btn-primary min-h-11 whitespace-normal px-4 py-2" disabled={saving || !photoReady} onclick={() => reviewName('accept')}>
                                {$_('garden.explorer.confirm_name', { default: 'Confirm {name}', values: { name: view.name } })}
                            </button>
                            <button type="button" class="btn btn-secondary min-h-11 whitespace-normal px-4 py-2" disabled={saving} onclick={() => reviewName('dismiss')}>
                                {$_('garden.dismiss_suggestion', { default: 'Dismiss suggestion' })}
                            </button>
                        {:else if view.nameState === 'confirmed' || view.nameState === 'automatic'}
                            <button type="button" class="btn btn-secondary min-h-11 whitespace-normal px-4 py-2" disabled={saving} onclick={() => reviewName('dismiss')}>
                                {$_('garden.discard_identification', { default: 'Discard identification' })}
                            </button>
                        {:else}
                            <button type="button" class="btn btn-secondary min-h-11 whitespace-normal px-4 py-2" disabled={saving || !photoReady || identifyBlocked !== null} onclick={suggestSpecies} aria-describedby="garden-capture-identify-note">
                                {saving ? $_('garden.working', { default: 'Working…' }) : $_('garden.suggest_species', { default: 'Suggest species' })}
                            </button>
                            <p id="garden-capture-identify-note" class="text-xs text-slate-600 dark:text-slate-400">
                                {identifyBlocked ?? $_('garden.explorer.manual_suggestion_help', { default: 'Requests a new species suggestion for this photo. Review it before confirming; choose its model and device below.' })}
                            </p>
                        {/if}
                    {/if}

                    {#if capture.status === 'dismissed'}
                        <button type="button" class="btn btn-primary min-h-11 whitespace-normal px-4 py-2" disabled={saving || !capture.snapshot_url} onclick={() => review('restore')}>
                            {$_('garden.restore', { default: 'Return to review' })}
                        </button>
                        {#if !capture.snapshot_url}
                            <p class="text-xs text-slate-600 dark:text-slate-400">{$_('garden.photo_restore_unavailable', { default: 'Photo unavailable. It cannot return to review.' })}</p>
                        {/if}
                    {:else}
                        <!-- Deciding presence is the pending record's main question; once confirmed, dismissing is the quiet escape. -->
                        <button type="button" class="btn {capture.status === 'pending' ? 'btn-secondary' : 'btn-ghost'} min-h-11 whitespace-normal px-4 py-2" disabled={saving} onclick={() => review('dismiss')} data-garden-capture-dismiss>
                            {$_('garden.dismiss', { default: 'Dismiss capture' })}
                        </button>
                        <p class="text-xs text-slate-600 dark:text-slate-400">{$_('garden.explorer.dismiss_effect', { default: 'Dismissing removes it from the animals. It stays under Garden visitors, Dismissed while its photo lasts.' })}</p>
                    {/if}

                    {#if groupTotal > 1 && groupTotal === group.length && capture.status === 'pending' && (view.review || manualOverride)}
                        <div class="space-y-2 border-t border-line-soft pt-3" data-garden-capture-group-review>
                            <p class="text-sm font-semibold">{$_('garden.group_review', { default: 'Review this stack' })}</p>
                            <p class="text-xs text-slate-600 dark:text-slate-400">{$_('garden.group_dismiss_help', { default: 'Confirm any animal photos first, then dismiss the remaining photos in this stack. Confirmed photos are kept; future captures are unaffected.' })}</p>
                            <button type="button" class="btn btn-secondary min-h-11 w-full whitespace-normal px-4 py-2" disabled={saving} onclick={dismissGroup}>
                                {$_('garden.group_dismiss', { default: 'Dismiss remaining {count} photos', values: { count: groupTotal } })}
                            </button>
                        </div>
                    {/if}
                </div>


                {#if lineageName}
                    <TaxonomyLineage scientificName={lineageName} />
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
                            <p class="line-clamp-4 text-sm leading-relaxed text-slate-600 dark:text-slate-300">
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

                <!-- How it was named, and the choices for a new manual check: there when wanted, closed by default. -->
                <details class="group border-t border-line-soft pt-1" data-garden-capture-details>
                    <summary class="flex min-h-11 cursor-pointer list-none items-center justify-between gap-2 text-sm font-semibold focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-500 [&::-webkit-details-marker]:hidden">
                        <span>{$_('garden.explorer.details', { default: 'Details' })}</span>
                        <svg class="h-4 w-4 shrink-0 transition-transform group-open:rotate-180 motion-reduce:transition-none" viewBox="0 0 20 20" fill="none" stroke="currentColor" stroke-width="1.5" aria-hidden="true"><path stroke-linecap="round" stroke-linejoin="round" d="m5 7.5 5 5 5-5" /></svg>
                    </summary>
                    <div class="space-y-4 pb-2 pt-1">
                        {#if capture.identification && capture.identification.review !== 'dismissed'}
                            <dl class="space-y-1 text-xs text-slate-600 dark:text-slate-400" data-garden-capture-identification>
                                <div class="flex flex-wrap justify-between gap-x-3">
                                    <dt>{$_('garden.explorer.detail_model', { default: 'Species model' })}</dt>
                                    <dd class="font-medium text-slate-800 dark:text-slate-100">SpeciesNet {capture.identification.variant} · {capture.identification.devices.join(', ')}</dd>
                                </div>
                                <div class="flex flex-wrap justify-between gap-x-3">
                                    <dt>{$_('garden.explorer.detail_country', { default: 'Location rule' })}</dt>
                                    <dd class="font-medium text-slate-800 dark:text-slate-100">{capture.identification.country}</dd>
                                </div>
                                <div class="flex flex-wrap justify-between gap-x-3">
                                    <dt>{$_('garden.explorer.detail_input', { default: 'Model input' })}</dt>
                                    <dd class="font-medium text-slate-800 dark:text-slate-100">
                                        {capture.identification.input_kind === 'tracked_crop'
                                            ? $_('garden.tracked_crop', { default: 'Tracked snapshot crop' })
                                            : $_('garden.whole_image', { default: 'Whole image with model border trim' })}
                                    </dd>
                                </div>
                            </dl>
                        {/if}
                        {#if capture.automatic_check && capture.status === 'confirmed'}
                            <GardenAutomaticAssessment assessment={capture.automatic_check} overridden={capture.automatic_check_overridden} named={view.nameState === 'automatic'} />
                        {/if}
                        {#if capture.status !== 'dismissed'}
                            <div class="space-y-1" data-garden-capture-model>
                                <p class="text-3xs font-semibold uppercase tracking-[0.14em] text-slate-500 dark:text-slate-400">{$_('garden.explorer.model_and_device', { default: 'Model and device' })}</p>
                        <div class="grid gap-3 pb-2 pt-1 sm:grid-cols-2">
                            <label class="space-y-1 text-sm"><span>{$_('garden.model', { default: 'Garden model' })}</span>
                                <select class="select-base w-full" value={variant ?? ''} onchange={(event) => (chosenVariant = (event.currentTarget as HTMLSelectElement).value as Variant)} disabled={saving || installed.length === 0}>
                                    {#if installed.includes('4.0.3b')}<option value="4.0.3b">{$_('garden.model_whole', { default: 'SpeciesNet 4.0.3b · Whole image' })}</option>{/if}
                                    {#if installed.includes('4.0.3a')}<option value="4.0.3a">{$_('garden.model_crop', { default: 'SpeciesNet 4.0.3a · Tracked crop' })}</option>{/if}
                                </select>
                            </label>
                            <label class="space-y-1 text-sm"><span>{$_('garden.provider', { default: 'Run garden model on' })}</span>
                                <select class="select-base w-full" bind:value={provider} onchange={clearPhotoCheck} disabled={saving}>
                                    {#each providers as option (option.value)}<option value={option.value}>{option.label}</option>{/each}
                                </select>
                            </label>
                        </div>
                        <p class="pb-2 text-xs text-slate-600 dark:text-slate-400">{$_('garden.explorer.identify_runs_on', { default: 'New manual suggestion: SpeciesNet {variant} on {device}. The suggestion still needs your confirmation.', values: { variant: variant ?? '', device: providers.find((option) => option.value === provider)?.label ?? provider } })}</p>
                        <p class="pb-2 text-xs text-slate-600 dark:text-slate-400">{$_('garden.explorer.manual_device_note', { default: 'These settings apply to a new manual check. Saved automatic results report their own device and time above. An unavailable manual device fails rather than switching devices.' })}</p>
                            </div>
                        {/if}
                    </div>
                </details>
            </div>
        </div>
    </div>
</div>

{#if photoCheckOpen && size}
    <GardenPhotoCheckDialog capture={capture} assessment={photoCheck} busy={photoCheckBusy} error={photoCheckError} runId={photoCheckRun} {size} onClose={clearPhotoCheck} />
{/if}
