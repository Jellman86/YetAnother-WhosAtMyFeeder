<script lang="ts">
    /**
     * One Garden capture opened from the Explorer, in the record's shape: the photograph with
     * the detector's box takes the larger half, the decisions the smaller one.
     *
     * Presence and species are separate decisions. Photos proposed around the same position
     * open together, one photo at a time, because position does not identify an animal; the
     * remaining ones can be dismissed as a group. Nothing here is a bird action: scoring again,
     * video scans and audio matching do not apply to an animal.
     */
    import { onMount } from 'svelte';
    import { get } from 'svelte/store';
    import { _ } from 'svelte-i18n';
    import GardenAutomaticAssessment from './GardenAutomaticAssessment.svelte';
    import GardenExplorerMarker from './GardenExplorerMarker.svelte';
    import GardenPhotoCheckDialog from './GardenPhotoCheckDialog.svelte';
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
    import { gardenPhotoOutline } from '../utils/garden-photo';
    import { gardenEntryText, gardenEntryView } from '../utils/garden-explorer';
    import { formatDateTime } from '../utils/datetime';
    import { trapFocus } from '../utils/focus-trap';
    import { lockDocumentScroll } from '../utils/document-scroll-lock';
    import { toastStore } from '../stores/toast.svelte';

    type Variant = NonNullable<GardenIdentifyRequest['variant']>;
    type Provider = NonNullable<GardenIdentifyRequest['provider']>;

    interface Props {
        capture: GardenCapture;
        /** Photos proposed around the same position, in display order, including this one. */
        group?: GardenCapture[];
        onclose: () => void;
        /** The capture after any saved review; the Explorer decides whether it still belongs. */
        onchanged: (capture: GardenCapture) => void;
        onselect?: (capture: GardenCapture) => void;
        /** Photos dismissed together, for the page to offer Undo. */
        ongroupdismissed?: (ids: string[], skipped: number) => void;
    }
    let { capture, group = [capture], onclose, onchanged, onselect, ongroupdismissed }: Props = $props();

    let dialog = $state<HTMLElement | null>(null);
    let size = $state<readonly [number, number] | undefined>(undefined);
    let failedPhoto = $state<string | null>(null);
    let saving = $state(false);
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
    const outline = $derived(gardenPhotoOutline(capture, size));
    const photoFailed = $derived(failedPhoto === capture.id);
    const photoReady = $derived(Boolean(capture.snapshot_url && size && !photoFailed));
    const installed = $derived((identification?.models ?? []).filter((model) => model.installed).map((model) => model.variant));
    // Whole image first, as Garden always offered it; the tracked-crop model answers too.
    const variant = $derived<Variant | null>(
        chosenVariant && installed.includes(chosenVariant) ? chosenVariant : installed.includes('4.0.3b') ? '4.0.3b' : installed.includes('4.0.3a') ? '4.0.3a' : null
    );
    const identifyBlocked = $derived.by((): string | null => {
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
            release();
        };
    });

    $effect(() => {
        if (dialog) return trapFocus(dialog);
    });

    function photoLoaded(event: Event): void {
        const image = event.currentTarget;
        if (image instanceof HTMLImageElement && image.naturalWidth > 0 && image.naturalHeight > 0) {
            size = [image.naturalWidth, image.naturalHeight];
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

    function select(next: GardenCapture | undefined): void {
        if (!next || saving) return;
        clearPhotoCheck();
        size = undefined;
        error = null;
        onselect?.(next);
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
        const remaining = group.length > 1 && action !== 'restore'
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
            onclose();
        }
    }
</script>

<svelte:window {onkeydown} />

<div
    class="fixed inset-0 z-50 flex items-center justify-center bg-slate-950/65 p-0 backdrop-blur-sm sm:p-4"
    role="presentation"
    onclick={(event) => { if (event.target === event.currentTarget && !saving) onclose(); }}
>
    <div
        bind:this={dialog}
        class="flex h-[100dvh] w-full max-w-6xl flex-col overflow-hidden bg-surface shadow-2xl sm:h-auto sm:max-h-[92dvh] sm:rounded-2xl sm:border sm:border-line"
        role="dialog"
        aria-modal="true"
        aria-labelledby="garden-capture-title"
        aria-busy={saving}
        tabindex="-1"
        data-garden-capture-modal
    >
        <header class="flex items-center justify-between gap-3 border-b border-line-soft px-4 py-3 sm:px-6">
            <div class="min-w-0">
                <div class="flex flex-wrap items-center gap-2">
                    <GardenExplorerMarker />
                    <h2 id="garden-capture-title" class="break-words text-lg font-bold text-slate-900 dark:text-white">{title}</h2>
                </div>
                <p class="mt-0.5 break-words text-xs text-slate-600 dark:text-slate-400">
                    {capture.camera} · <time datetime={capture.observed_at}>{formatDateTime(capture.observed_at)}</time>
                </p>
            </div>
            <button
                type="button"
                class="btn btn-ghost min-h-11 min-w-11 shrink-0 px-2"
                onclick={onclose}
                disabled={saving}
                aria-label={$_('common.close', { default: 'Close' })}
            >
                <svg class="h-5 w-5" fill="none" stroke="currentColor" viewBox="0 0 24 24" aria-hidden="true"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12" /></svg>
            </button>
        </header>

        <div class="grid min-h-0 flex-1 content-start overflow-y-auto overscroll-contain md:grid-cols-[1.1fr_1fr]">
            <div class="min-w-0 border-b border-line-soft p-4 md:border-b-0 md:border-r">
                <div class="relative aspect-video w-full overflow-hidden rounded-xl bg-surface-raised">
                    {#if capture.snapshot_url && !photoFailed}
                        {#key capture.id}
                            <img
                                class="absolute inset-0 h-full w-full object-contain"
                                src={withAuthParams(capture.snapshot_url)}
                                alt={$_('garden.photo_alt', { default: 'Animal capture from {camera}', values: { camera: capture.camera } })}
                                onload={photoLoaded}
                                onerror={() => (failedPhoto = capture.id)}
                            />
                        {/key}
                        {#if outline}
                            {@const box = outline.box}
                            {@const frame = outline.size}
                            <svg class="pointer-events-none absolute inset-0 h-full w-full text-amber-400" viewBox={`0 0 ${frame[0]} ${frame[1]}`} preserveAspectRatio="xMidYMid meet" aria-hidden="true" data-garden-capture-box>
                                <rect x={box[0] * frame[0]} y={box[1] * frame[1]} width={box[2] * frame[0]} height={box[3] * frame[1]} fill="none" stroke="black" stroke-width="4" vector-effect="non-scaling-stroke" />
                                <rect x={box[0] * frame[0]} y={box[1] * frame[1]} width={box[2] * frame[0]} height={box[3] * frame[1]} fill="none" stroke="currentColor" stroke-width="2" vector-effect="non-scaling-stroke" />
                            </svg>
                        {/if}
                    {:else}
                        <p class="absolute inset-0 flex items-center justify-center p-4 text-center text-sm text-slate-600 dark:text-slate-400">
                            {capture.status !== 'pending'
                                ? $_('garden.explorer.photo_expired', { default: 'The photo has expired. The confirmed record is kept.' })
                                : $_('garden.snapshot_unavailable', { default: 'Snapshot unavailable' })}
                        </p>
                    {/if}
                </div>
                {#if group.length > 1}
                    <div class="mt-3 space-y-2" data-garden-capture-group>
                        <p class="text-sm font-semibold">{$_('garden.group_count', { default: '{count} photos around the same position', values: { count: group.length } })}</p>
                        <p class="text-xs text-slate-600 dark:text-slate-400">{$_('garden.group_help', { default: 'Position does not identify an animal. This group can contain different visitors.' })}</p>
                        <div class="flex flex-wrap items-center gap-2">
                            <button type="button" class="btn btn-secondary min-h-11 whitespace-normal px-3 py-2" disabled={saving || index === 0} onclick={() => select(group[index - 1])}>{$_('garden.previous_photo', { default: 'Previous photo' })}</button>
                            <span class="text-xs tabular-nums" aria-live="polite">{$_('garden.photo_count', { default: 'Photo {index} of {count}', values: { index: index + 1, count: group.length } })}</span>
                            <button type="button" class="btn btn-secondary min-h-11 whitespace-normal px-3 py-2" disabled={saving || index + 1 >= group.length} onclick={() => select(group[index + 1])}>{$_('garden.next_photo', { default: 'Next photo' })}</button>
                        </div>
                    </div>
                {/if}
                <p class="mt-3 break-words text-sm text-slate-700 dark:text-slate-300">
                    {capture.source_kind === 'motion'
                        ? $_('garden.motion_source', { default: 'Candidate from retained motion footage' })
                        : $_('garden.frigate_suggested', { default: 'Frigate suggested: {label}', values: { label: capture.frigate_label } })}
                </p>
                {#if outline?.kind === 'presence'}
                    <p class="text-xs text-slate-600 dark:text-slate-400">{$_('garden.presence_box', { default: 'Box: MegaDetector Cedar candidate. Check the photo before confirming.' })}</p>
                {:else if outline?.kind === 'identification'}
                    <p class="text-xs text-slate-600 dark:text-slate-400">{$_('garden.explorer.identification_box', { default: 'Box: the crop the species model read.' })}</p>
                {/if}
            </div>

            <div class="min-w-0 space-y-4 p-4" data-garden-capture-rail>
                {#if view.review === 'presence'}
                    <p class="flex items-start gap-2 rounded-xl border border-amber-500/50 bg-amber-500/10 px-3 py-2 text-sm font-semibold text-amber-800 dark:text-amber-200" role="status">
                        <span class="mt-1.5 h-2 w-2 shrink-0 rounded-full bg-amber-500" aria-hidden="true"></span>
                        {$_('garden.explorer.review_presence', { default: 'Needs review: check that an animal is in the photo.' })}
                    </p>
                {:else if view.review === 'species'}
                    <p class="flex items-start gap-2 rounded-xl border border-amber-500/50 bg-amber-500/10 px-3 py-2 text-sm font-semibold text-amber-800 dark:text-amber-200" role="status">
                        <span class="mt-1.5 h-2 w-2 shrink-0 rounded-full bg-amber-500" aria-hidden="true"></span>
                        {$_('garden.explorer.review_species', { default: 'Needs review: the species was suggested, not confirmed.' })}
                    </p>
                {:else if capture.status === 'dismissed'}
                    <p class="text-sm font-semibold text-slate-700 dark:text-slate-200" role="status">
                        {$_('garden.explorer.state_dismissed', { default: 'Dismissed, not counted as an animal' })}
                    </p>
                {:else}
                    <p class="flex items-start gap-2 text-sm font-semibold text-success-700 dark:text-success-300" role="status">
                        <span class="mt-1.5 h-2 w-2 shrink-0 rounded-full bg-success-500" aria-hidden="true"></span>
                        {$_('garden.explorer.confirmed_animal', { default: 'Animal confirmed' })}
                    </p>
                {/if}

                {#if capture.identification && capture.identification.review !== 'dismissed'}
                    <section class="space-y-1 border-t border-line-soft pt-3 text-sm" data-garden-capture-identification>
                        <p class="font-semibold">{$_('garden.explorer.species_heading', { default: 'Species' })}</p>
                        {#if capture.identification.outcome === 'suggestion'}
                            <p class="text-xs text-slate-600 dark:text-slate-400">
                                {capture.identification.review === 'accepted'
                                    ? (capture.identification.automatic
                                        ? $_('garden.identification_automatic', { default: 'Named automatically. Discard the name if it is wrong.' })
                                        : $_('garden.identification_confirmed', { default: 'Identification confirmed by you' }))
                                    : $_('garden.identification_needs_review', { default: 'Suggested identification · Needs your review' })}
                            </p>
                            {#if capture.identification.rank !== 'species'}<p class="text-xs">{$_('garden.group_only', { default: 'Animal group only; species is unresolved.' })}</p>{/if}
                            <p class="text-xs">{$_('garden.model_score', { default: 'Model score: {score}%', values: { score: ((capture.identification.score ?? 0) * 100).toFixed(1) } })}</p>
                        {:else}
                            <p>{$_('garden.identification_unknown', { default: 'No reliable identification. Leave this animal unidentified or try another model.' })}</p>
                        {/if}
                        <p class="break-words text-xs text-slate-600 dark:text-slate-400">
                            {capture.identification.variant} · {capture.identification.devices.join(', ')} · {capture.identification.country} · {capture.identification.input_kind === 'tracked_crop'
                                ? $_('garden.tracked_crop', { default: 'Tracked snapshot crop' })
                                : $_('garden.whole_image', { default: 'Whole image with model border trim' })}
                        </p>
                    </section>
                {/if}

                {#if capture.automatic_check}
                    <GardenAutomaticAssessment
                        assessment={capture.automatic_check}
                        overridden={capture.automatic_check_overridden}
                        named={view.nameState === 'automatic'}
                    />
                {/if}

                {#if error}<p class="text-sm font-semibold text-red-700 dark:text-red-300" role="alert">{error}</p>{/if}

                <div class="flex flex-col gap-2 border-t border-line-soft pt-3" data-garden-capture-actions>
                    {#if capture.status === 'pending'}
                        <button type="button" class="btn btn-primary min-h-11 whitespace-normal px-4 py-2" disabled={saving || !photoReady} onclick={() => review('confirm')}>
                            {$_('garden.confirm', { default: 'Confirm animal present' })}
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
                                {identifyBlocked ?? $_('garden.explorer.identify_runs_on', { default: 'Runs SpeciesNet {variant} on {device}. The suggestion still needs your confirmation.', values: { variant: variant ?? '', device: providers.find((option) => option.value === provider)?.label ?? provider } })}
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
                        <button type="button" class="btn btn-secondary min-h-11 whitespace-normal px-4 py-2" disabled={saving} onclick={() => review('dismiss')}>
                            {$_('garden.dismiss', { default: 'Dismiss capture' })}
                        </button>
                        <p class="text-xs text-slate-600 dark:text-slate-400">{$_('garden.explorer.dismiss_effect', { default: 'Dismissing removes it from the animals. It stays under Garden visitors, Dismissed while its photo lasts.' })}</p>
                    {/if}

                    {#if group.length > 1 && capture.status === 'pending'}
                        <div class="space-y-2 border-t border-line-soft pt-3" data-garden-capture-group-review>
                            <p class="text-sm font-semibold">{$_('garden.group_review', { default: 'Review this stack' })}</p>
                            <p class="text-xs text-slate-600 dark:text-slate-400">{$_('garden.group_dismiss_help', { default: 'Confirm any animal photos first, then dismiss the remaining photos in this stack. Confirmed photos are kept; future captures are unaffected.' })}</p>
                            <button type="button" class="btn btn-secondary min-h-11 w-full whitespace-normal px-4 py-2" disabled={saving} onclick={dismissGroup}>
                                {$_('garden.group_dismiss', { default: 'Dismiss remaining {count} photos', values: { count: group.length } })}
                            </button>
                        </div>
                    {/if}
                </div>

                {#if capture.status !== 'dismissed'}
                    <!-- The defaults suit most installations; the choice is for a model or device you prefer. -->
                    <details class="group border-t border-line-soft pt-1" data-garden-capture-model>
                        <summary class="flex min-h-11 cursor-pointer list-none items-center justify-between gap-2 text-sm font-semibold focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-500 [&::-webkit-details-marker]:hidden">
                            <span>{$_('garden.explorer.model_and_device', { default: 'Model and device' })}</span>
                            <svg class="h-4 w-4 shrink-0 transition-transform group-open:rotate-180 motion-reduce:transition-none" viewBox="0 0 20 20" fill="none" stroke="currentColor" stroke-width="1.5" aria-hidden="true"><path stroke-linecap="round" stroke-linejoin="round" d="m5 7.5 5 5 5-5" /></svg>
                        </summary>
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
                        <p class="pb-2 text-xs text-slate-600 dark:text-slate-400">{$_('garden.explorer.device_note', { default: 'Used for species suggestions and photo checks. A device that is not available here fails instead of falling back to the CPU.' })}</p>
                    </details>
                {/if}
            </div>
        </div>
    </div>
</div>

{#if photoCheckOpen && size}
    <GardenPhotoCheckDialog capture={capture} assessment={photoCheck} busy={photoCheckBusy} error={photoCheckError} runId={photoCheckRun} {size} onClose={clearPhotoCheck} />
{/if}
