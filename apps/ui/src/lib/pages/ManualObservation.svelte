<script lang="ts">
    import { onDestroy, onMount } from 'svelte';
    import { _ } from 'svelte-i18n';
    import {
        confirmManualObservation,
        discardManualObservation,
        fetchClassifierLabels,
        fetchManualObservation,
        retryManualObservation,
        uploadManualObservation,
        type ManualObservation,
        type ManualObservationPrediction,
    } from '../api';
    import { withAuthParams } from '../api/core';
    import LocationPicker from '../components/LocationPicker.svelte';
    import { settingsStore } from '../stores/settings.svelte';
    import { toastStore } from '../stores/toast.svelte';

    let { onNavigate } = $props<{ onNavigate: (path: string) => void }>();

    let fileInput = $state<HTMLInputElement | null>(null);
    let selectedFile = $state<File | null>(null);
    let localPreviewUrl = $state<string | null>(null);
    let draft = $state<ManualObservation | null>(null);
    let uploading = $state(false);
    let saving = $state(false);
    let dragActive = $state(false);
    let errorMessage = $state<string | null>(null);
    let pollTimer: ReturnType<typeof setTimeout> | null = null;
    let speciesLabels = $state<string[]>([]);
    let selectedLabel = $state('');
    let cameraName = $state('Manual upload');
    let notes = $state('');
    let observedAt = $state('');
    let latitude = $state<number | null>(null);
    let longitude = $state<number | null>(null);
    let locationSource = $state<'image_metadata' | 'manual_pin' | 'none' | null>(null);
    let locationTouched = false;

    const stage = $derived.by(() => {
        if (draft?.status === 'saved') return 4;
        if (draft?.status === 'ready') return 3;
        if (draft && ['queued', 'analyzing', 'failed'].includes(draft.status)) return 2;
        return 1;
    });
    const previewUrl = $derived(draft ? withAuthParams(draft.preview_url) : localPreviewUrl);
    const progress = $derived(draft?.progress_percent ?? (uploading ? 8 : 0));
    const topPrediction = $derived(draft?.predictions?.[0] ?? null);
    const hasLocation = $derived(latitude != null && longitude != null);
    const locationIncomplete = $derived((latitude == null) !== (longitude == null));
    const locationOutOfRange = $derived(
        latitude != null && longitude != null &&
        (latitude < -90 || latitude > 90 || longitude < -180 || longitude > 180)
    );
    const defaultMapCenter = $derived.by((): [number, number] => {
        const configuredLatitude = settingsStore.settings?.location_latitude;
        const configuredLongitude = settingsStore.settings?.location_longitude;
        return typeof configuredLatitude === 'number' && typeof configuredLongitude === 'number'
            ? [configuredLatitude, configuredLongitude]
            : [20, 0];
    });
    const sourceLabel = $derived.by(() => {
        const source = topPrediction?.input_source;
        if (!source) return $_('manual_observation.evidence.full_frame', { default: 'Full frame' });
        if (source.includes('crop')) return $_('manual_observation.evidence.crop', { default: 'Best crop' });
        return source.replaceAll('_', ' ');
    });
    const steps = $derived([
        { number: 1, title: $_('manual_observation.steps.upload', { default: 'Upload' }), detail: $_('manual_observation.steps.upload_detail', { default: 'Choose original media' }) },
        { number: 2, title: $_('manual_observation.steps.analyse', { default: 'Analyse' }), detail: $_('manual_observation.steps.analyse_detail', { default: 'Find the strongest evidence' }) },
        { number: 3, title: $_('manual_observation.steps.review', { default: 'Review' }), detail: $_('manual_observation.steps.review_detail', { default: 'Confirm the species' }) },
        { number: 4, title: $_('manual_observation.steps.save', { default: 'Save' }), detail: $_('manual_observation.steps.save_detail', { default: 'Add to observations' }) },
    ]);

    function clearPoll(): void {
        if (pollTimer) clearTimeout(pollTimer);
        pollTimer = null;
    }

    function applyDraft(value: ManualObservation): void {
        draft = value;
        if (!locationTouched) {
            latitude = value.latitude ?? null;
            longitude = value.longitude ?? null;
            locationSource = value.latitude != null && value.longitude != null
                ? (value.location_source ?? 'image_metadata')
                : null;
        }
    }

    function predictionPrimaryName(prediction: ManualObservationPrediction): string {
        return prediction.common_name?.trim() || prediction.label;
    }

    function predictionSecondaryName(prediction: ManualObservationPrediction): string | null {
        const primary = predictionPrimaryName(prediction).toLocaleLowerCase();
        const scientific = prediction.scientific_name?.trim();
        if (scientific && scientific.toLocaleLowerCase() !== primary) return scientific;
        if (prediction.label.toLocaleLowerCase() !== primary) return prediction.label;
        return null;
    }

    function chooseLocation(nextLatitude: number, nextLongitude: number): void {
        latitude = nextLatitude;
        longitude = nextLongitude;
        locationSource = 'manual_pin';
        locationTouched = true;
    }

    function updateCoordinate(axis: 'latitude' | 'longitude', raw: string): void {
        const parsed = raw.trim() === '' ? null : Number(raw);
        if (axis === 'latitude') latitude = Number.isFinite(parsed) ? parsed : null;
        else longitude = Number.isFinite(parsed) ? parsed : null;
        locationSource = latitude == null && longitude == null ? 'none' : 'manual_pin';
        locationTouched = true;
    }

    function clearLocation(): void {
        latitude = null;
        longitude = null;
        locationSource = 'none';
        locationTouched = true;
    }

    function schedulePoll(): void {
        clearPoll();
        if (!draft || !['queued', 'analyzing'].includes(draft.status)) return;
        pollTimer = setTimeout(() => void refreshDraft(), 1200);
    }

    async function refreshDraft(): Promise<void> {
        if (!draft) return;
        try {
            applyDraft(await fetchManualObservation(draft.id));
            if (draft.status === 'ready' && !selectedLabel) selectedLabel = draft.predictions[0]?.label ?? '';
            sessionStorage.setItem('manual_observation_draft', draft.id);
            schedulePoll();
        } catch (error) {
            errorMessage = error instanceof Error ? error.message : $_('manual_observation.errors.load', { default: 'The analysis status could not be loaded.' });
            pollTimer = setTimeout(() => void refreshDraft(), 3000);
        }
    }

    function setFile(file: File | null): void {
        errorMessage = null;
        if (!file) return;
        const supported = ['image/jpeg', 'image/png', 'image/webp', 'video/mp4', 'video/quicktime', 'video/webm'];
        if (!supported.includes(file.type)) {
            errorMessage = $_('manual_observation.errors.type', { default: 'Choose a JPEG, PNG, WebP, MP4, MOV, or WebM file.' });
            return;
        }
        if (localPreviewUrl) URL.revokeObjectURL(localPreviewUrl);
        selectedFile = file;
        localPreviewUrl = URL.createObjectURL(file);
    }

    function handleDrop(event: DragEvent): void {
        event.preventDefault();
        dragActive = false;
        setFile(event.dataTransfer?.files?.[0] ?? null);
    }

    async function beginAnalysis(): Promise<void> {
        if (!selectedFile || uploading) return;
        uploading = true;
        errorMessage = null;
        try {
            locationTouched = false;
            const uploadedDraft = await uploadManualObservation(selectedFile);
            applyDraft(uploadedDraft);
            sessionStorage.setItem('manual_observation_draft', uploadedDraft.id);
            schedulePoll();
        } catch (error) {
            errorMessage = error instanceof Error ? error.message : $_('manual_observation.errors.upload', { default: 'The media could not be uploaded.' });
        } finally {
            uploading = false;
        }
    }

    async function retryAnalysis(): Promise<void> {
        if (!draft) return;
        errorMessage = null;
        try {
            draft = await retryManualObservation(draft.id);
            schedulePoll();
        } catch (error) {
            errorMessage = error instanceof Error ? error.message : $_('manual_observation.errors.retry', { default: 'The analysis could not be restarted.' });
        }
    }

    async function startOver(): Promise<void> {
        clearPoll();
        if (draft && draft.status !== 'saved') {
            try { await discardManualObservation(draft.id); } catch { /* The draft may already have expired. */ }
        }
        sessionStorage.removeItem('manual_observation_draft');
        draft = null;
        selectedFile = null;
        selectedLabel = '';
        notes = '';
        observedAt = '';
        cameraName = 'Manual upload';
        latitude = null;
        longitude = null;
        locationSource = null;
        locationTouched = false;
        errorMessage = null;
        if (localPreviewUrl) URL.revokeObjectURL(localPreviewUrl);
        localPreviewUrl = null;
        if (fileInput) fileInput.value = '';
    }

    async function saveObservation(): Promise<void> {
        if (!draft || !selectedLabel.trim() || saving || locationIncomplete || locationOutOfRange) return;
        saving = true;
        errorMessage = null;
        try {
            const saved = await confirmManualObservation(draft.id, {
                label: selectedLabel.trim(), camera_name: cameraName.trim() || 'Manual upload',
                notes: notes.trim() || null, observed_at: observedAt ? new Date(observedAt).toISOString() : null,
                latitude: hasLocation ? latitude : null,
                longitude: hasLocation ? longitude : null,
                location_source: hasLocation ? (locationSource === 'image_metadata' ? 'image_metadata' : 'manual_pin') : locationSource,
            });
            draft = { ...draft, status: 'saved', saved_event_id: saved.event_id };
            sessionStorage.removeItem('manual_observation_draft');
            toastStore.success($_('manual_observation.saved.toast', { default: 'Observation added' }));
        } catch (error) {
            errorMessage = error instanceof Error ? error.message : $_('manual_observation.errors.save', { default: 'The observation could not be saved.' });
        } finally {
            saving = false;
        }
    }

    onMount(() => {
        void fetchClassifierLabels().then((result) => speciesLabels = result.labels).catch(() => undefined);
        const remembered = sessionStorage.getItem('manual_observation_draft');
        if (remembered) {
            void fetchManualObservation(remembered).then((value) => {
                applyDraft(value);
                selectedLabel = value.predictions[0]?.label ?? '';
                schedulePoll();
            }).catch(() => sessionStorage.removeItem('manual_observation_draft'));
        }
    });

    onDestroy(() => {
        clearPoll();
        if (localPreviewUrl) URL.revokeObjectURL(localPreviewUrl);
    });
</script>

<section class="overflow-hidden rounded-[1.75rem] border border-slate-200/80 bg-white/80 shadow-sm dark:border-slate-700/60 dark:bg-slate-900/55">
    <div class="relative border-b border-slate-200/80 bg-gradient-to-r from-brand-50 via-white to-accent-50 px-5 py-5 dark:border-slate-700/60 dark:from-brand-950/40 dark:via-slate-900 dark:to-accent-950/30 sm:px-7">
        <div class="absolute inset-y-0 right-0 w-2/5 bg-[radial-gradient(circle_at_70%_30%,rgba(20,184,166,0.14),transparent_62%)]" aria-hidden="true"></div>
        <div class="relative flex items-start gap-4">
            <div class="grid h-11 w-11 shrink-0 place-items-center rounded-2xl bg-gradient-to-br from-brand-500 to-accent-600 text-white shadow-sm">
                <svg class="h-6 w-6" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" aria-hidden="true"><path stroke-linecap="round" stroke-linejoin="round" d="M12 16V4m0 0L8 8m4-4 4 4M5 14v4a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2v-4" /></svg>
            </div>
            <div class="min-w-0">
                <p class="text-xs font-bold uppercase tracking-[0.16em] text-brand-700 dark:text-brand-300">{$_('manual_observation.eyebrow', { default: 'Field record' })}</p>
                <h2 class="mt-1 text-lg font-bold text-slate-900 dark:text-white">{$_('manual_observation.intro_title', { default: 'Turn a photo or clip into a verified observation' })}</h2>
                <p class="mt-1 max-w-2xl text-sm leading-6 text-slate-600 dark:text-slate-300">{$_('manual_observation.intro_body', { default: 'YA-WAMF uses the same model, crop selection, and video consensus as live detections. Nothing is added until you review it.' })}</p>
            </div>
        </div>
    </div>

    <div class="grid lg:grid-cols-[16rem_minmax(0,1fr)]">
        <nav aria-label={$_('manual_observation.progress_label', { default: 'Observation progress' })} class="border-b border-slate-200/80 bg-slate-50/70 px-5 py-5 dark:border-slate-700/60 dark:bg-slate-950/25 lg:border-b-0 lg:border-r lg:px-6 lg:py-7">
            <ol class="grid grid-cols-4 lg:block">
                {#each steps as item, index}
                    <li class="relative min-w-0 lg:pb-8 last:lg:pb-0">
                        {#if index < steps.length - 1}
                            <div class="absolute left-[calc(50%+1.25rem)] right-[calc(-50%+1.25rem)] top-4 h-px bg-slate-200 dark:bg-slate-700 lg:left-4 lg:right-auto lg:top-9 lg:h-[calc(100%-1rem)] lg:w-px" class:bg-brand-400={stage > item.number} aria-hidden="true"></div>
                        {/if}
                        <div class="relative flex flex-col items-center gap-2 text-center lg:flex-row lg:items-start lg:gap-3 lg:text-left">
                            <div class="grid h-8 w-8 shrink-0 place-items-center rounded-full border text-xs font-bold transition-colors {stage > item.number ? 'border-brand-500 bg-brand-500 text-white' : stage === item.number ? 'border-brand-500 bg-white text-brand-700 ring-4 ring-brand-100 dark:bg-slate-900 dark:text-brand-300 dark:ring-brand-900/50' : 'border-slate-300 bg-white text-slate-400 dark:border-slate-600 dark:bg-slate-900 dark:text-slate-500'}">
                                {#if stage > item.number}<svg class="h-4 w-4" viewBox="0 0 20 20" fill="none" stroke="currentColor" stroke-width="2.2" aria-hidden="true"><path stroke-linecap="round" stroke-linejoin="round" d="m5 10 3 3 7-7" /></svg>{:else}{item.number}{/if}
                            </div>
                            <div class="min-w-0 pt-0.5">
                                <div class="truncate text-xs font-bold sm:text-sm {stage === item.number ? 'text-brand-800 dark:text-brand-200' : 'text-slate-700 dark:text-slate-300'}">{item.title}</div>
                                <div class="mt-0.5 hidden text-xs leading-5 text-slate-500 dark:text-slate-400 lg:block">{item.detail}</div>
                            </div>
                        </div>
                    </li>
                {/each}
            </ol>
        </nav>

        <div class="min-h-[34rem] px-5 py-6 sm:px-7 sm:py-8">
            {#if errorMessage}
                <div role="alert" class="mb-5 flex items-start gap-3 rounded-xl border border-rose-200 bg-rose-50 px-4 py-3 text-sm text-rose-800 dark:border-rose-900/50 dark:bg-rose-950/30 dark:text-rose-200">
                    <svg class="mt-0.5 h-5 w-5 shrink-0" viewBox="0 0 20 20" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true"><path stroke-linecap="round" stroke-linejoin="round" d="M10 7v3m0 3h.01M8.6 3.4 2.8 14a2 2 0 0 0 1.8 3h10.8a2 2 0 0 0 1.8-3L11.4 3.4a1.6 1.6 0 0 0-2.8 0Z" /></svg>
                    <span>{errorMessage}</span>
                </div>
            {/if}

            {#if stage === 1}
                <div class="mx-auto max-w-2xl">
                    <h3 class="text-xl font-bold text-slate-900 dark:text-white">{$_('manual_observation.upload.title', { default: 'Choose the clearest original' })}</h3>
                    <p class="mt-2 text-sm leading-6 text-slate-600 dark:text-slate-300">{$_('manual_observation.upload.help', { default: 'Use the full-resolution file. The classifier will compare the full frame and any useful crop automatically.' })}</p>
                    <button type="button" onclick={() => fileInput?.click()} ondragover={(event) => { event.preventDefault(); dragActive = true; }} ondragleave={() => dragActive = false} ondrop={handleDrop} class="focus-ring mt-6 flex min-h-64 w-full flex-col items-center justify-center overflow-hidden rounded-2xl border-2 border-dashed transition {dragActive ? 'border-brand-500 bg-brand-50 dark:bg-brand-950/30' : 'border-slate-300 bg-slate-50/60 hover:border-brand-400 hover:bg-brand-50/50 dark:border-slate-700 dark:bg-slate-950/20 dark:hover:border-brand-600'}">
                        {#if selectedFile && localPreviewUrl}
                            {#if selectedFile.type.startsWith('image/')}
                                <img src={localPreviewUrl} alt="" class="h-52 w-full object-contain p-3" />
                            {:else}
                                <video src={localPreviewUrl} class="h-52 w-full object-contain p-3" muted preload="metadata"></video>
                            {/if}
                            <div class="w-full border-t border-slate-200/80 bg-white/80 px-4 py-3 text-left dark:border-slate-700/60 dark:bg-slate-900/75">
                                <div class="truncate text-sm font-semibold text-slate-800 dark:text-slate-100">{selectedFile.name}</div>
                                <div class="text-xs text-slate-500 dark:text-slate-400">{(selectedFile.size / 1024 / 1024).toFixed(1)} MB · {$_('manual_observation.upload.change', { default: 'Choose a different file' })}</div>
                            </div>
                        {:else}
                            <div class="grid h-14 w-14 place-items-center rounded-2xl bg-brand-100 text-brand-700 dark:bg-brand-900/50 dark:text-brand-300"><svg class="h-7 w-7" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" aria-hidden="true"><path stroke-linecap="round" stroke-linejoin="round" d="M12 16V4m0 0L8 8m4-4 4 4M5 14v4a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2v-4" /></svg></div>
                            <div class="mt-4 text-sm font-bold text-slate-800 dark:text-slate-100">{$_('manual_observation.upload.drop', { default: 'Drop media here or choose a file' })}</div>
                            <div class="mt-1 px-6 text-xs leading-5 text-slate-500 dark:text-slate-400">{$_('manual_observation.upload.formats', { default: 'JPEG, PNG or WebP up to 25 MB · MP4, MOV or WebM up to 250 MB and 3 minutes' })}</div>
                        {/if}
                    </button>
                    <input bind:this={fileInput} class="sr-only" type="file" aria-label={$_('manual_observation.upload.title', { default: 'Choose a photo or video' })} accept="image/jpeg,image/png,image/webp,video/mp4,video/quicktime,video/webm" onchange={(event) => setFile(event.currentTarget.files?.[0] ?? null)} />
                    <div class="mt-6 flex justify-end"><button class="btn btn-primary px-5 py-2.5" disabled={!selectedFile || uploading} onclick={beginAnalysis}>{uploading ? $_('manual_observation.upload.uploading', { default: 'Securing upload…' }) : $_('manual_observation.upload.analyse', { default: 'Analyse media' })}<svg class="h-4 w-4" viewBox="0 0 20 20" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true"><path stroke-linecap="round" stroke-linejoin="round" d="m7 4 6 6-6 6" /></svg></button></div>
                </div>
            {:else if stage === 2}
                <div class="mx-auto max-w-3xl">
                    <div class="grid gap-6 md:grid-cols-[minmax(0,1.1fr)_minmax(16rem,.9fr)] md:items-center">
                        <div class="relative overflow-hidden rounded-2xl bg-slate-950 aspect-video"><img src={previewUrl ?? ''} alt={$_('manual_observation.analysis.preview_alt', { default: 'Uploaded observation preview' })} class="h-full w-full object-contain" /><div class="absolute inset-x-0 bottom-0 bg-gradient-to-t from-black/75 to-transparent px-4 pb-3 pt-10 text-xs font-semibold text-white/90">{draft?.original_filename}</div></div>
                        <div>
                            <p class="text-xs font-bold uppercase tracking-[0.16em] text-brand-700 dark:text-brand-300">{draft?.media_type === 'video' ? $_('manual_observation.analysis.video', { default: 'Temporal analysis' }) : $_('manual_observation.analysis.image', { default: 'Image analysis' })}</p>
                            <h3 class="mt-2 text-xl font-bold text-slate-900 dark:text-white">{draft?.status === 'failed' ? $_('manual_observation.analysis.failed_title', { default: 'Analysis needs another try' }) : $_('manual_observation.analysis.title', { default: 'Finding the strongest evidence' })}</h3>
                            {#if draft?.status === 'failed'}
                                <p class="mt-2 text-sm leading-6 text-slate-600 dark:text-slate-300">{draft.error_message ?? $_('manual_observation.analysis.failed_body', { default: 'The original is safe. Retry the analysis without uploading it again.' })}</p>
                                <div class="mt-5 flex flex-wrap gap-3"><button class="btn btn-primary px-4 py-2.5" onclick={retryAnalysis}>{$_('manual_observation.analysis.retry', { default: 'Retry analysis' })}</button><button class="btn btn-ghost px-4 py-2.5" onclick={startOver}>{$_('manual_observation.start_over', { default: 'Start over' })}</button></div>
                            {:else}
                                <p class="mt-2 text-sm leading-6 text-slate-600 dark:text-slate-300">{draft?.progress_message ?? $_('manual_observation.analysis.body', { default: 'Comparing the full frame with useful crops and ranking the strongest video frames.' })}</p>
                                <div class="mt-6" aria-live="polite"><div class="flex items-center justify-between text-xs font-semibold text-slate-600 dark:text-slate-300"><span>{$_('manual_observation.analysis.progress', { default: 'Analysis progress' })}</span><span class="tabular-nums">{progress}%</span></div><div class="mt-2 h-2 overflow-hidden rounded-full bg-slate-200 dark:bg-slate-700"><div class="h-full rounded-full bg-gradient-to-r from-brand-500 to-accent-500 transition-[width] duration-500" style={`width:${Math.max(4, progress)}%`}></div></div></div>
                            {/if}
                        </div>
                    </div>
                </div>
            {:else if stage === 3}
                <div class="grid gap-7 xl:grid-cols-[minmax(17rem,.8fr)_minmax(0,1.2fr)]">
                    <div><div class="relative overflow-hidden rounded-2xl bg-slate-950 aspect-[4/3]"><img src={previewUrl ?? ''} alt={$_('manual_observation.review.preview_alt', { default: 'Evidence selected for review' })} class="h-full w-full object-contain" /><div class="absolute left-3 top-3 rounded-full border border-white/20 bg-black/55 px-3 py-1.5 text-xs font-bold text-white backdrop-blur">{sourceLabel}</div></div><div class="mt-3 grid grid-cols-2 gap-x-4 gap-y-2 text-xs"><div><span class="text-slate-500 dark:text-slate-400">{$_('manual_observation.evidence.model', { default: 'Model' })}</span><div class="mt-0.5 truncate font-semibold text-slate-800 dark:text-slate-100">{topPrediction?.model_name ?? topPrediction?.model_id ?? '—'}</div></div><div><span class="text-slate-500 dark:text-slate-400">{$_('manual_observation.evidence.provider', { default: 'Provider' })}</span><div class="mt-0.5 truncate font-semibold text-slate-800 dark:text-slate-100">{topPrediction?.inference_provider ?? topPrediction?.inference_backend ?? '—'}</div></div></div></div>
                    <div>
                        <h3 class="text-xl font-bold text-slate-900 dark:text-white">{$_('manual_observation.review.title', { default: 'Does this look right?' })}</h3>
                        <p class="mt-2 text-sm leading-6 text-slate-600 dark:text-slate-300">{$_('manual_observation.review.body', { default: 'Choose a suggestion or correct it before this becomes part of your observation history.' })}</p>
                        <fieldset class="mt-5 space-y-2"><legend class="sr-only">{$_('manual_observation.review.candidates', { default: 'Classification candidates' })}</legend>{#each (draft?.predictions ?? []).slice(0, 4) as prediction, index}<label class="flex cursor-pointer items-center gap-3 rounded-xl border px-3.5 py-3 transition {selectedLabel === prediction.label ? 'border-brand-400 bg-brand-50/70 dark:border-brand-600 dark:bg-brand-950/30' : 'border-slate-200 hover:border-slate-300 dark:border-slate-700 dark:hover:border-slate-600'}"><input type="radio" class="h-4 w-4 accent-teal-600" name="candidate" value={prediction.label} bind:group={selectedLabel} /><span class="min-w-0 flex-1"><span class="block truncate text-sm font-semibold text-slate-800 dark:text-slate-100">{predictionPrimaryName(prediction)}</span>{#if predictionSecondaryName(prediction)}<span class="mt-0.5 block truncate text-xs italic text-slate-500 dark:text-slate-400">{predictionSecondaryName(prediction)}</span>{/if}</span><span class="text-xs font-bold tabular-nums {index === 0 ? 'text-brand-700 dark:text-brand-300' : 'text-slate-500 dark:text-slate-400'}">{Math.round(prediction.score * 100)}%</span></label>{/each}</fieldset>
                        <label class="mt-4 block"><span class="text-xs font-bold uppercase tracking-wider text-slate-500 dark:text-slate-400">{$_('manual_observation.review.species', { default: 'Confirmed species' })}</span><input class="input-base mt-2 min-h-11" list="manual-species-labels" bind:value={selectedLabel} autocomplete="off" /><datalist id="manual-species-labels">{#each speciesLabels as label}<option value={label}></option>{/each}</datalist></label>
                        <div class="mt-4 grid gap-4 sm:grid-cols-2"><label><span class="text-xs font-bold text-slate-600 dark:text-slate-300">{$_('manual_observation.review.when', { default: 'Observed at' })}</span><input class="input-base mt-1.5 min-h-11" type="datetime-local" bind:value={observedAt} /></label><label><span class="text-xs font-bold text-slate-600 dark:text-slate-300">{$_('manual_observation.review.location', { default: 'Camera or place name' })}</span><input class="input-base mt-1.5 min-h-11" bind:value={cameraName} maxlength="100" /></label></div>
                        <section class="mt-5 border-t border-slate-200 pt-5 dark:border-slate-700" aria-labelledby="manual-observation-location-title">
                            <div class="flex flex-wrap items-start justify-between gap-3">
                                <div>
                                    <h4 id="manual-observation-location-title" class="text-sm font-bold text-slate-800 dark:text-slate-100">{$_('manual_observation.location.title', { default: 'Sighting location' })}</h4>
                                    <p class="mt-1 text-xs leading-5 text-slate-500 dark:text-slate-400">{locationSource === 'image_metadata' ? $_('manual_observation.location.extracted', { default: 'Location found in the image metadata. Check the pin and adjust it if needed.' }) : locationSource === 'manual_pin' ? $_('manual_observation.location.manual', { default: 'This pin was placed or adjusted manually. Check it before saving.' }) : $_('manual_observation.location.missing', { default: 'No embedded location was found. Place a pin if you know where the sighting was made.' })}</p>
                                </div>
                                {#if locationSource === 'image_metadata'}<span class="rounded-full bg-accent-50 px-2.5 py-1 text-[10px] font-bold text-accent-700 dark:bg-accent-950/40 dark:text-accent-300">{$_('manual_observation.location.from_image', { default: 'From image metadata' })}</span>{/if}
                            </div>
                            <div class="mt-4"><LocationPicker {latitude} {longitude} center={defaultMapCenter} onchange={chooseLocation} /></div>
                            <div class="mt-4 grid gap-3 sm:grid-cols-2">
                                <label><span class="text-xs font-bold text-slate-600 dark:text-slate-300">{$_('manual_observation.location.latitude', { default: 'Latitude' })}</span><input class="input-base mt-1.5 min-h-11" type="number" min="-90" max="90" step="0.000001" value={latitude ?? ''} oninput={(event) => updateCoordinate('latitude', event.currentTarget.value)} /></label>
                                <label><span class="text-xs font-bold text-slate-600 dark:text-slate-300">{$_('manual_observation.location.longitude', { default: 'Longitude' })}</span><input class="input-base mt-1.5 min-h-11" type="number" min="-180" max="180" step="0.000001" value={longitude ?? ''} oninput={(event) => updateCoordinate('longitude', event.currentTarget.value)} /></label>
                            </div>
                            {#if locationIncomplete}<p role="alert" class="mt-2 text-xs font-semibold text-rose-600 dark:text-rose-300">{$_('manual_observation.location.incomplete', { default: 'Enter both latitude and longitude, or clear the location.' })}</p>{:else if locationOutOfRange}<p role="alert" class="mt-2 text-xs font-semibold text-rose-600 dark:text-rose-300">{$_('manual_observation.location.invalid', { default: 'Latitude must be −90 to 90 and longitude −180 to 180.' })}</p>{/if}
                            {#if hasLocation}<button type="button" class="btn btn-ghost mt-2 min-h-11 px-3 py-2" onclick={clearLocation}>{$_('manual_observation.location.clear', { default: 'Clear location' })}</button>{/if}
                        </section>
                        <label class="mt-4 block"><span class="text-xs font-bold text-slate-600 dark:text-slate-300">{$_('manual_observation.review.notes', { default: 'Notes (optional)' })}</span><textarea class="input-base mt-1.5 min-h-20 resize-y" bind:value={notes} maxlength="1000"></textarea></label>
                        <div class="mt-6 flex flex-wrap items-center justify-between gap-3"><button class="btn btn-ghost min-h-11 px-3 py-2.5" onclick={startOver}>{$_('manual_observation.start_over', { default: 'Start over' })}</button><button class="btn btn-primary min-h-11 px-5 py-2.5" disabled={!selectedLabel.trim() || saving || locationIncomplete || locationOutOfRange} onclick={saveObservation}>{saving ? $_('manual_observation.review.saving', { default: 'Saving…' }) : $_('manual_observation.review.save', { default: 'Add observation' })}</button></div>
                    </div>
                </div>
            {:else}
                <div class="mx-auto flex max-w-xl flex-col items-center py-10 text-center"><div class="grid h-16 w-16 place-items-center rounded-full bg-accent-100 text-accent-700 ring-8 ring-accent-50 dark:bg-accent-900/50 dark:text-accent-300 dark:ring-accent-950/40"><svg class="h-8 w-8" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true"><path stroke-linecap="round" stroke-linejoin="round" d="m5 12 4 4L19 6" /></svg></div><p class="mt-6 text-xs font-bold uppercase tracking-[0.16em] text-accent-700 dark:text-accent-300">{$_('manual_observation.saved.eyebrow', { default: 'Field record complete' })}</p><h3 class="mt-2 text-2xl font-bold text-slate-900 dark:text-white">{$_('manual_observation.saved.title', { default: 'Observation added' })}</h3><p class="mt-2 text-sm leading-6 text-slate-600 dark:text-slate-300">{$_('manual_observation.saved.body', { default: 'The original media, classification evidence, and your confirmed species are now safely linked.' })}</p><div class="mt-7 flex flex-wrap justify-center gap-3"><button class="btn btn-primary px-5 py-2.5" onclick={() => onNavigate(`/events?event=${encodeURIComponent(draft?.saved_event_id ?? '')}`)}>{$_('manual_observation.saved.view', { default: 'View detection' })}</button><button class="btn btn-secondary px-5 py-2.5" onclick={startOver}>{$_('manual_observation.saved.another', { default: 'Add another' })}</button></div></div>
            {/if}
        </div>
    </div>
</section>
