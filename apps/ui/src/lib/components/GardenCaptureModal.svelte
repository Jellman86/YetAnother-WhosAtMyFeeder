<script lang="ts">
    /**
     * One Garden capture opened from the Explorer, in the record's shape: the photograph with
     * the detector's box takes the larger half, the decisions the smaller one.
     *
     * Presence and species are separate decisions, as on the Garden page. Nothing here is a
     * bird action: scoring again, video scans and audio matching do not apply to an animal.
     */
    import { onMount } from 'svelte';
    import { get } from 'svelte/store';
    import { _ } from 'svelte-i18n';
    import GardenAutomaticAssessment from './GardenAutomaticAssessment.svelte';
    import GardenExplorerMarker from './GardenExplorerMarker.svelte';
    import {
        fetchGardenIdentification,
        identifyGarden,
        reviewGarden,
        reviewGardenIdentification,
        type GardenCapture,
        type GardenIdentificationStatus
    } from '../api/garden';
    import { withAuthParams } from '../api/core';
    import { gardenPhotoOutline } from '../utils/garden-photo';
    import { gardenEntryText, gardenEntryView } from '../utils/garden-explorer';
    import { formatDateTime } from '../utils/datetime';
    import { trapFocus } from '../utils/focus-trap';
    import { lockDocumentScroll } from '../utils/document-scroll-lock';
    import { toastStore } from '../stores/toast.svelte';

    interface Props {
        capture: GardenCapture;
        onclose: () => void;
        /** The capture after a review, or null once it has left the Explorer. */
        onchanged: (capture: GardenCapture | null) => void;
    }
    let { capture, onclose, onchanged }: Props = $props();

    let dialog = $state<HTMLElement | null>(null);
    let size = $state<readonly [number, number] | undefined>(undefined);
    let photoFailed = $state(false);
    let saving = $state(false);
    let error = $state<string | null>(null);
    let identification = $state.raw<GardenIdentificationStatus | null>(null);

    const view = $derived(gardenEntryView(capture));
    const outline = $derived(gardenPhotoOutline(capture, size));
    const photoReady = $derived(Boolean(capture.snapshot_url && size && !photoFailed));
    // Whole image first, as the Garden page offers it; the tracked-crop model answers too.
    const variant = $derived(
        identification?.models.find((model) => model.variant === '4.0.3b' && model.installed)?.variant
            ?? identification?.models.find((model) => model.variant === '4.0.3a' && model.installed)?.variant
            ?? null
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
    const title = $derived(gardenEntryText(capture, view, (key, fallback, values) => get(_)(key, { values, default: fallback })).title);

    onMount(() => {
        const release = lockDocumentScroll();
        const controller = new AbortController();
        fetchGardenIdentification(controller.signal)
            .then((status) => (identification = status))
            .catch(() => (identification = null));
        return () => {
            controller.abort();
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

    async function act(run: () => Promise<GardenCapture>, done: (next: GardenCapture) => GardenCapture | null): Promise<void> {
        if (saving) return;
        saving = true;
        error = null;
        try {
            onchanged(done(await run()));
        } catch (failure) {
            error = failure instanceof Error ? failure.message : $_('garden.save_error', { default: 'Could not save your review. Try again.' });
        } finally {
            saving = false;
        }
    }

    function confirmPresence(): Promise<void> {
        return act(() => reviewGarden(capture.id, 'confirm'), (next) => {
            toastStore.success($_('garden.photo_confirmed', { default: 'Photo confirmed.' }));
            return next;
        });
    }

    function dismissCapture(): Promise<void> {
        return act(() => reviewGarden(capture.id, 'dismiss'), () => {
            toastStore.success($_('garden.explorer.dismissed', { default: 'Capture dismissed. You can return it to review from Garden, Dismissed.' }));
            return null;
        });
    }

    function suggestSpecies(): Promise<void> {
        const chosen = variant;
        if (!chosen) return Promise.resolve();
        return act(() => identifyGarden(capture.id, { variant: chosen, provider: 'cpu' }), (next) => next);
    }

    function reviewName(action: 'accept' | 'dismiss'): Promise<void> {
        return act(() => reviewGardenIdentification(capture.id, action), (next) => next);
    }

    function onkeydown(event: KeyboardEvent): void {
        if (event.key === 'Escape') {
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
                        <img
                            class="absolute inset-0 h-full w-full object-contain"
                            src={withAuthParams(capture.snapshot_url)}
                            alt={$_('garden.photo_alt', { default: 'Animal capture from {camera}', values: { camera: capture.camera } })}
                            onload={photoLoaded}
                            onerror={() => (photoFailed = true)}
                        />
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
                            {capture.status === 'confirmed'
                                ? $_('garden.explorer.photo_expired', { default: 'The photo has expired. The confirmed record is kept.' })
                                : $_('garden.snapshot_unavailable', { default: 'Snapshot unavailable' })}
                        </p>
                    {/if}
                </div>
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
                            <p class="break-words text-base font-semibold">{capture.identification.name}</p>
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
                        <button type="button" class="btn btn-primary min-h-11 whitespace-normal px-4 py-2" disabled={saving || !photoReady} onclick={confirmPresence}>
                            {$_('garden.confirm', { default: 'Confirm animal present' })}
                        </button>
                        {#if !photoReady}
                            <p class="text-xs text-slate-600 dark:text-slate-400">{$_('garden.explorer.confirm_needs_photo', { default: 'An animal can be confirmed only while its photo is shown.' })}</p>
                        {/if}
                    {:else if view.nameState === 'suggested' && view.name}
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
                            {identifyBlocked ?? $_('garden.explorer.identify_runs', { default: 'Runs SpeciesNet {variant} on the CPU. The suggestion still needs your confirmation.', values: { variant: variant ?? '' } })}
                        </p>
                    {/if}
                    <button type="button" class="btn btn-secondary min-h-11 whitespace-normal px-4 py-2" disabled={saving} onclick={dismissCapture}>
                        {$_('garden.dismiss', { default: 'Dismiss capture' })}
                    </button>
                    <p class="text-xs text-slate-600 dark:text-slate-400">{$_('garden.explorer.dismiss_effect', { default: 'Dismissing removes it from the Explorer. It stays under Garden, Dismissed while its photo lasts.' })}</p>
                </div>
            </div>
        </div>
    </div>
</div>
