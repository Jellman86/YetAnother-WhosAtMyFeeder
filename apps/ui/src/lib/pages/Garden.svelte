<script lang="ts">
    import { onDestroy, onMount } from 'svelte';
    import { _ } from 'svelte-i18n';
    import { fetchGarden, reviewGarden, reviewGardenBatch, fetchGardenIdentification, installGardenModel, identifyGarden, reviewGardenIdentification, type GardenCapture, type GardenIdentificationStatus, type GardenIdentifyRequest } from '../api/garden';
    import { withAuthParams } from '../api/core';
    import { pageRefreshAction } from '../stores/page_refresh_action.svelte';
    import { fetchGardenMotion, installGardenMotion, type GardenMotionStatus } from '../api/garden';
    import { gardenPhotoOutline } from '../utils/garden-photo';
    import { gardenThresholdStep } from '../utils/garden-threshold';
    import { groupGardenReview, type GardenReviewGroup } from '../utils/garden-review-groups';
    import { updateSettings } from '../api/settings';
    import { toastStore } from '../stores/toast.svelte';
    import { checkGardenPhoto, type GardenPhotoCheck } from '../api/garden';
    import GardenPhotoCheckDialog from '../components/GardenPhotoCheckDialog.svelte';

    let { onNavigate }: { onNavigate: (path: string) => void } = $props();
    let status = $state<GardenCapture['status']>('pending');
    let items = $state.raw<GardenCapture[]>([]);
    let total = $state(0);
    const pageSize = $derived(status === 'pending' ? 128 : 8);
    const groups = $derived(groupGardenReview(items));
    let photoIndexes = $state<Record<string, number>>({});
    let undoIds = $state.raw<string[]>([]);
    let batchResult = $state<{ action: 'dismiss' | 'restore'; updated: number; skipped: number } | null>(null);
    let offset = $state(0);
    let loading = $state(true);
    let saving = $state<string | null>(null);
    let error = $state<string | null>(null);
    let loadedImages = $state<Record<string, readonly [number, number]>>({});
    let failedImages = $state<Record<string, boolean>>({});
    let identification = $state.raw<GardenIdentificationStatus | null>(null);
    let motion = $state.raw<GardenMotionStatus | null>(null);
    let motionConfidence = $state(0.5);
    let variant = $state<NonNullable<GardenIdentifyRequest['variant']>>('4.0.3b');
    let provider = $state<NonNullable<GardenIdentifyRequest['provider']>>('cpu');
    const selectedModel = $derived(identification?.models.find(model => model.variant === variant));
    const canIdentify = $derived(Boolean(identification?.catalogue_ready && identification.country && !identification.error && selectedModel?.installed && !identification.busy));
    const canCheckPhoto = $derived(Boolean(identification?.catalogue_ready && !identification.error && !identification.busy && identification.models.some(model => model.variant === '4.0.3a' && model.installed)));
    let photoCheckTarget = $state.raw<GardenCapture | null>(null);
    let photoAssessment = $state.raw<GardenPhotoCheck | null>(null);
    let photoCheckBusy = $state(false);
    let photoCheckError = $state<string | null>(null);
    let photoCheckRun = $state(0);
    let photoCheckController: AbortController | null = null;
    let controller: AbortController | null = null;
    let generation = 0;
    let destroyed = false;
    let unregisterRefresh: (() => void) | undefined;
    const views = $derived([
        { id: 'pending' as const, name: $_('garden.pending', { default: 'Needs review' }) },
        { id: 'confirmed' as const, name: $_('garden.confirmed', { default: 'Confirmed animals' }) },
        { id: 'dismissed' as const, name: $_('garden.dismissed', { default: 'Dismissed' }) }
    ]);

    function photoLoaded(id: string, event: Event): void {
        const image = event.currentTarget;
        if (!(image instanceof HTMLImageElement) || image.naturalWidth <= 0 || image.naturalHeight <= 0) return;
        loadedImages = { ...loadedImages, [id]: [image.naturalWidth, image.naturalHeight] };
    }

    function clearPhotoCheck(): void {
        photoCheckRun++;
        photoCheckController?.abort();
        photoCheckController = null;
        photoCheckTarget = null;
        photoAssessment = null;
        photoCheckError = null;
        photoCheckBusy = false;
    }

    function selectPhoto(group: GardenReviewGroup, index: number): void {
        clearPhotoCheck();
        photoIndexes = { ...photoIndexes, [group.id]: index };
    }

    async function checkPhoto(item: GardenCapture): Promise<void> {
        if (!canCheckPhoto || !item.motion_source || item.status !== 'pending' || !loadedImages[item.id] || failedImages[item.id]) return;
        clearPhotoCheck();
        const run = photoCheckRun;
        const selectedProvider = provider;
        const imageHash = item.motion_source.image_sha256;
        const box = JSON.stringify(item.motion_source.box_xywh);
        const dimensions = JSON.stringify(loadedImages[item.id]);
        const requestController = new AbortController();
        photoCheckController = requestController;
        photoCheckTarget = item;
        photoCheckBusy = true;
        try {
            const result = await checkGardenPhoto(item.id, { image_sha256: imageHash, provider: selectedProvider }, requestController.signal);
            if (destroyed || run !== photoCheckRun || requestController.signal.aborted || provider !== selectedProvider) return;
            if (result.capture_id !== item.id || result.image_sha256 !== imageHash || result.provider !== selectedProvider || result.variant !== '4.0.3a' || JSON.stringify(result.box_xywh) !== box || JSON.stringify(result.frame_size) !== dimensions) {
                throw new Error($_('garden.check_changed', { default: 'The photo check does not match the displayed photo. Refresh before trying again.' }));
            }
            photoAssessment = result;
        } catch (failure) {
            if (!destroyed && run === photoCheckRun && !requestController.signal.aborted) photoCheckError = failure instanceof Error ? failure.message : $_('garden.check_unavailable', { default: 'Photo check unavailable. Review the photo yourself.' });
        } finally {
            if (!destroyed && run === photoCheckRun) photoCheckBusy = false;
        }
    }

    async function load(): Promise<void> {
        clearPhotoCheck();
        const request = ++generation;
        controller?.abort();
        controller = new AbortController();
        loading = true;
        error = null;
        items = [];
        loadedImages = {};
        failedImages = {};
        photoIndexes = {};
        try {
            const result = await fetchGarden(status, offset, controller.signal);
            if (destroyed || request !== generation) return;
            items = result.items;
            total = result.total;
            try {
                const modelStatus = await fetchGardenIdentification(controller.signal);
                if (!destroyed && request === generation) identification = modelStatus;
            } catch {
                if (!destroyed && request === generation) identification = null;
            }
            if (destroyed || request !== generation) return;
            try {
                const motionStatus = await fetchGardenMotion(controller.signal);
                if (!destroyed && request === generation) {
                    motion = motionStatus;
                    motionConfidence = motionStatus.animal_confidence ?? 0.5;
                }
            } catch {
                if (!destroyed && request === generation) motion = null;
            }
            if (destroyed || request !== generation) return;
            if (offset > 0 && items.length === 0) {
                offset = Math.max(0, offset - pageSize);
                await load();
            }
        } catch (failure) {
            if (destroyed || request !== generation || controller.signal.aborted) return;
            error = failure instanceof Error ? failure.message : $_('garden.load_error', { default: 'Could not load garden captures. Refresh to try again.' });
        } finally {
            if (!destroyed && request === generation) loading = false;
        }
    }

    async function selectView(next: GardenCapture['status']): Promise<void> {
        status = next;
        offset = 0;
        await load();
    }

    async function review(item: GardenCapture, action: 'confirm' | 'dismiss' | 'restore'): Promise<void> {
        if (saving) return;
        clearPhotoCheck();
        const group = groups.find(group => group.items.some(photo => photo.id === item.id));
        const index = group?.items.findIndex(photo => photo.id === item.id) ?? -1;
        const nextPhotoId = group?.items[index + 1]?.id ?? group?.items[index - 1]?.id;
        const hasOtherPendingPhotos = Boolean(group && group.items.length > 1);
        saving = item.id;
        error = null;
        try {
            await reviewGarden(item.id, action);
            if (destroyed) return;
            const message = action === 'confirm'
                ? $_('garden.photo_confirmed', { default: 'Photo confirmed.' })
                : action === 'dismiss'
                    ? $_('garden.photo_dismissed', { default: 'Photo dismissed.' })
                    : $_('garden.photo_restored', { default: 'Photo returned to review.' });
            toastStore.success(hasOtherPendingPhotos
                ? `${message} ${$_('garden.group_remaining', { default: 'Other photos in this group still need review.' })}`
                : message);
            await load();
            if (!destroyed && nextPhotoId) {
                const nextGroup = groupGardenReview(items).find(group => group.items.some(photo => photo.id === nextPhotoId));
                if (nextGroup) photoIndexes = { ...photoIndexes, [nextGroup.id]: nextGroup.items.findIndex(photo => photo.id === nextPhotoId) };
            }
        } catch (failure) {
            if (!destroyed) {
                error = failure instanceof Error ? failure.message : $_('garden.save_error', { default: 'Could not save your review. Try again.' });
                toastStore.error(error);
            }
        } finally {
            if (!destroyed) saving = null;
        }
    }

    async function reviewGroup(group: GardenReviewGroup | null): Promise<void> {
        if (saving) return;
        clearPhotoCheck();
        const ids = group ? group.items.map(item => item.id) : undoIds;
        if (ids.length === 0) return;
        const action = group ? 'dismiss' : 'restore';
        saving = group?.id ?? 'undo';
        error = null;
        try {
            const result = await reviewGardenBatch(ids, action);
            if (destroyed) return;
            undoIds = action === 'dismiss' ? result.updated_ids : [];
            batchResult = { action, updated: result.updated_ids.length, skipped: result.skipped_count };
            const message = action === 'dismiss'
                ? $_('garden.batch_dismissed', { default: '{count} photos dismissed.', values: { count: result.updated_ids.length } })
                : $_('garden.batch_restored', { default: '{count} photos returned to review.', values: { count: result.updated_ids.length } });
            if (result.skipped_count > 0) {
                toastStore.warning(`${message} ${$_('garden.batch_skipped', { default: '{count} photos were unchanged because their review or availability changed.', values: { count: result.skipped_count } })}`);
            } else toastStore.success(message);
            await load();
        } catch (failure) {
            if (!destroyed) {
                error = failure instanceof Error ? failure.message : $_('garden.save_error', { default: 'Could not save your review. Try again.' });
                toastStore.error(error);
            }
        } finally {
            if (!destroyed) saving = null;
        }
    }

    async function speciesAction(item: GardenCapture, action: 'identify' | 'accept' | 'dismiss'): Promise<void> {
        if (saving) return;
        saving = item.id;
        error = null;
        try {
            if (action === 'identify') await identifyGarden(item.id, { variant, provider });
            else await reviewGardenIdentification(item.id, action);
            if (!destroyed) await load();
        } catch (failure) {
            if (!destroyed) error = failure instanceof Error ? failure.message : $_('garden.save_error', { default: 'Could not save your review. Try again.' });
        } finally {
            if (!destroyed) saving = null;
        }
    }

    async function downloadModel(): Promise<void> {
        if (saving) return;
        saving = 'model';
        error = null;
        try {
            const result = await installGardenModel(variant);
            if (!destroyed) identification = result;
        } catch (failure) {
            if (!destroyed) error = failure instanceof Error ? failure.message : $_('garden.model_error', { default: 'Could not download the garden model. Try again.' });
        } finally {
            if (!destroyed) saving = null;
        }
    }

    async function downloadMotionDetector(): Promise<void> {
        if (saving) return;
        saving = 'motion-model';
        error = null;
        try {
            const result = await installGardenMotion();
            if (!destroyed) motion = result;
        } catch (failure) {
            if (!destroyed) error = failure instanceof Error ? failure.message : $_('garden.model_error', { default: 'Could not download the garden model. Try again.' });
        } finally {
            if (!destroyed) saving = null;
        }
    }

    async function saveMotionConfidence(): Promise<void> {
        if (saving || !Number.isFinite(motionConfidence) || motionConfidence < 0.5 || motionConfidence > 0.95) return;
        saving = 'confidence';
        error = null;
        try {
            await updateSettings({ garden_motion_confidence: motionConfidence });
            if (!destroyed) await load();
        } catch (failure) {
            if (!destroyed) error = failure instanceof Error ? failure.message : $_('garden.save_error', { default: 'Could not save your review. Try again.' });
        } finally {
            if (!destroyed) saving = null;
        }
    }

    onMount(() => {
        unregisterRefresh = pageRefreshAction.register(load);
        void load();
    });
    onDestroy(() => {
        destroyed = true;
        clearPhotoCheck();
        generation += 1;
        controller?.abort();
        unregisterRefresh?.();
    });
</script>

<div class="space-y-5" data-garden-history>
    <div class="card-base p-4 space-y-2">
        <p class="eyebrow">{$_('garden.review_only', { default: 'Owner review prototype' })}</p>
        <p class="text-sm text-slate-600 dark:text-slate-400">{$_('garden.review_help', { default: 'Check the photo and confirm animal presence first. You can then request a species suggestion. Model scores can be confidently wrong; identification always needs your review.' })}</p>
        <p class="text-xs text-slate-600 dark:text-slate-400">{$_('garden.retention_help', { default: 'Garden visits stay separate from bird totals and exports. Frigate event photos follow Frigate retention. Motion photos last up to three days; dismissed photos may make room for new captures sooner. Unconfirmed motion captures are removed on expiry.' })}</p>
        <details class="group" data-garden-motion>
            <summary class="min-h-11 list-none [&::-webkit-details-marker]:hidden cursor-pointer py-3 text-sm font-semibold focus-visible:ring-2 focus-visible:ring-brand"><span>{$_('garden.motion_title', { default: 'Motion collection' })}</span><span class="inline-block ml-2 transition-transform group-open:rotate-180" aria-hidden="true">⌄</span></summary>
            <div class="space-y-3 pt-2">
                <p class="text-xs text-slate-600 dark:text-slate-400">{$_('garden.motion_help', { default: 'Cedar proposes animals from short motion recordings, including wildlife Frigate did not track. Birds and objects can also be proposed. Every photo needs your review; no species is identified automatically.' })}</p>
                {#if !motion}
                    <p role="status" class="text-sm">{$_('garden.model_status_unavailable', { default: 'Model status unavailable. Refresh to try again.' })}</p>
                {:else}
                    <p role="status" class="text-sm">{motion.message}</p>
                    <label class="block space-y-1 text-sm">
                        <span>{$_('garden.confidence', { default: 'Animal proposal threshold' })}</span>
                        <input class="input-base w-full" type="number" min="0.5" max="0.95" step={gardenThresholdStep(motionConfidence, motion.animal_confidence)} bind:value={motionConfidence} disabled={saving !== null} />
                    </label>
                    <p class="text-xs text-slate-600 dark:text-slate-400">{$_('garden.confidence_help', { default: 'Higher values reduce proposals but can miss animals. Applies to new motion photos only; bird detection and person privacy checks are unchanged.' })}</p>
                    <button class="btn btn-secondary min-h-11 px-4 py-2 whitespace-normal" disabled={saving !== null || !Number.isFinite(motionConfidence) || motionConfidence < 0.5 || motionConfidence > 0.95 || motionConfidence === (motion.animal_confidence ?? 0.5)} onclick={saveMotionConfidence}>{$_('garden.confidence_save', { default: 'Save animal threshold' })}</button>
                    <p class="text-xs text-slate-600 dark:text-slate-400">{$_('garden.motion_limits', { default: 'CPU only · At least {seconds}s between scans · Up to {limit} photos · {days}-day photo retention', values: { seconds: motion.interval_seconds, limit: motion.photo_limit, days: motion.photo_retention_days } })}</p>
                    {#if motion.queue_limit !== undefined && motion.catchup_seconds !== undefined}
                        <p class="text-xs text-slate-600 dark:text-slate-400">{$_('garden.motion_coverage', { default: 'Up to {limit} short windows queued per camera from the last {minutes} minutes. Birds and camera pressure pause collection; brief visits can be missed.', values: { limit: motion.queue_limit, minutes: motion.catchup_seconds / 60 } })}</p>
                    {/if}
                    {#if motion.queue_camera && motion.queue_checked_at}
                        <p class="text-xs break-words">{$_('garden.motion_queue', { default: '{camera}: {count} windows waiting when checked at {time}. More may be available at the queue limit.', values: { camera: motion.queue_camera, count: motion.queued_windows, time: new Date(motion.queue_checked_at).toLocaleString() } })}</p>
                    {/if}
                    {#if motion.last_scan_at}<p class="text-xs">{$_('garden.motion_last_scan', { default: 'Last scan: {time}', values: { time: new Date(motion.last_scan_at).toLocaleString() } })}</p>{/if}
                    {#if !motion.installed}
                        <button class="btn btn-secondary min-h-11 px-4 py-2 whitespace-normal" disabled={saving !== null || motion.busy || !motion.catalogue_ready} onclick={downloadMotionDetector}>{saving === 'motion-model' ? $_('garden.downloading', { default: 'Downloading and verifying…' }) : $_('garden.motion_download', { default: 'Download Cedar detector (101 MB)' })}</button>
                    {/if}
                    <button class="btn btn-secondary min-h-11 px-4 py-2" onclick={() => onNavigate('/settings/connection')}>{$_('garden.camera_settings', { default: 'Camera settings' })}</button>
                {/if}
            </div>
        </details>
        <details class="group">
            <summary class="min-h-11 list-none [&::-webkit-details-marker]:hidden cursor-pointer py-3 text-sm font-semibold focus-visible:ring-2 focus-visible:ring-brand"><span>{$_('garden.species_settings', { default: 'Species suggestions' })}</span><span class="inline-block ml-2 transition-transform group-open:rotate-180" aria-hidden="true">⌄</span></summary>
            <div class="space-y-3 pt-2">
                <p class="text-xs text-slate-600 dark:text-slate-400">{$_('garden.species_help', { default: 'SpeciesNet runs only when you ask. Bird inference takes priority and can interrupt it. No automatic identification or notifications are enabled.' })}</p>
                {#if !identification}
                    <p role="status" class="text-sm">{$_('garden.model_status_unavailable', { default: 'Model status unavailable. Refresh to try again.' })}</p>
                {:else if identification.error}
                    <p role="alert" class="text-sm">{identification.error}</p>
                {:else if !identification.catalogue_ready}
                    <p role="status" class="text-sm">{$_('garden.catalogue_unavailable', { default: 'Garden species data is unavailable. Check the application startup diagnostics.' })}</p>
                {:else}
                    <div class="grid gap-3 sm:grid-cols-2">
                        <label class="space-y-1 text-sm"><span>{$_('garden.model', { default: 'Garden model' })}</span>
                            <select class="select-base w-full" bind:value={variant} disabled={saving !== null}>
                                <option value="4.0.3b">{$_('garden.model_whole', { default: 'SpeciesNet 4.0.3b · Whole image' })}</option>
                                <option value="4.0.3a">{$_('garden.model_crop', { default: 'SpeciesNet 4.0.3a · Tracked crop' })}</option>
                            </select>
                        </label>
                        <label class="space-y-1 text-sm"><span>{$_('garden.provider', { default: 'Run garden model on' })}</span>
                            <select class="select-base w-full" bind:value={provider} onchange={clearPhotoCheck} disabled={saving !== null}>
                                <option value="cpu">CPU</option><option value="intel_cpu">Intel CPU</option><option value="intel_gpu">Intel GPU</option><option value="intel_npu">Intel NPU</option><option value="cuda">NVIDIA GPU</option>
                            </select>
                        </label>
                    </div>
                    <p class="text-xs text-slate-600 dark:text-slate-400">{$_('garden.country', { default: 'Country filter: {country}', values: { country: identification.country ?? $_('garden.country_missing', { default: 'Set a recognised country or ISO code in Settings → Location' }) } })}</p>
                    {#if selectedModel?.installed}
                        <p class="text-xs">{$_('garden.model_downloaded', { default: 'Model downloaded. The checksum and selected provider are checked on each identification; unavailable hardware does not fall back to CPU.' })}</p>
                    {:else}
                        <button class="btn btn-secondary min-h-11 px-4 py-2 whitespace-normal" disabled={saving !== null || identification.busy} onclick={downloadModel}>{saving === 'model' ? $_('garden.downloading', { default: 'Downloading and verifying…' }) : $_('garden.download_model', { default: 'Download selected model (224 MB)' })}</button>
                    {/if}
                {/if}
            </div>
        </details>
    </div>
    <div class="flex flex-wrap items-center justify-between gap-3">
        <div class="flex flex-wrap gap-2" role="group" aria-label={$_('garden.views', { default: 'Garden review views' })}>
            {#each views as view}
                <button class="tab-button min-h-11 {status === view.id ? 'tab-button-active' : 'tab-button-inactive'}" aria-pressed={status === view.id} disabled={saving !== null} onclick={() => selectView(view.id)}>{view.name}</button>
            {/each}
        </div>
        <button class="btn btn-secondary min-h-11 px-4 py-2" disabled={loading || saving !== null} onclick={load}>{$_('garden.refresh', { default: 'Refresh' })}</button>
    </div>
    {#if error}
        <div class="rounded-xl border border-line bg-surface-raised p-4 text-sm" role="alert">{error}</div>
    {/if}
    {#if batchResult}
        <div class="card-base p-4 space-y-2" role="status">
            <p class="text-sm">{batchResult.action === 'dismiss'
                ? $_('garden.batch_dismissed', { default: '{count} photos dismissed.', values: { count: batchResult.updated } })
                : $_('garden.batch_restored', { default: '{count} photos returned to review.', values: { count: batchResult.updated } })}</p>
            {#if batchResult.skipped > 0}<p class="text-xs">{$_('garden.batch_skipped', { default: '{count} photos were unchanged because their review or availability changed.', values: { count: batchResult.skipped } })}</p>{/if}
            {#if undoIds.length > 0}
                <p class="text-xs text-slate-600 dark:text-slate-400">{$_('garden.batch_undo_help', { default: 'Undo is available while photos remain. Dismissed photos may make room for new captures.' })}</p>
                <button class="btn btn-secondary min-h-11 px-4 py-2 whitespace-normal" disabled={saving !== null} onclick={() => reviewGroup(null)}>{$_('garden.batch_undo', { default: 'Undo group dismissal' })}</button>
            {/if}
        </div>
    {/if}
    <div aria-live="polite" aria-busy={loading}>
        {#if loading}
            <p class="p-6 text-sm text-slate-600 dark:text-slate-400" role="status">{$_('garden.loading', { default: 'Loading garden captures…' })}</p>
        {:else if !error && items.length === 0}
            <div class="card-base space-y-3 p-6">
                <h2 class="font-semibold">{$_('garden.empty', { default: 'No captures in this view' })}</h2>
                <p class="text-sm text-slate-600 dark:text-slate-400">{$_('garden.empty_help', { default: 'Enable Garden animals for a camera in Settings. Completed animal events will appear here for review; birds keep their existing Feeder or Nest role.' })}</p>
                <button class="btn btn-secondary min-h-11 px-4 py-2" onclick={() => onNavigate('/settings/connection')}>{$_('garden.camera_settings', { default: 'Camera settings' })}</button>
            </div>
        {:else}
            <div class="space-y-4">
                {#each groups as group (group.id)}
                    {@const photoIndex = Math.min(photoIndexes[group.id] ?? 0, group.items.length - 1)}
                    {@const item = group.items[photoIndex]}
                    {@const outline = gardenPhotoOutline(item, loadedImages[item.id])}
                    <article class="card-base overflow-hidden md:grid md:grid-cols-3" aria-label={item.camera}>
                        <div class="relative aspect-video min-w-0 bg-surface-raised md:col-span-2">
                            {#if item.snapshot_url && !failedImages[item.id]}
                                <img class="absolute inset-0 h-full w-full object-contain" src={withAuthParams(item.snapshot_url)}
                                    alt={$_('garden.photo_alt', { default: 'Animal capture from {camera}', values: { camera: item.camera } })}
                                    loading="lazy" onload={(event) => photoLoaded(item.id, event)}
                                    onerror={() => failedImages = { ...failedImages, [item.id]: true }} />
                                {#if outline}
                                    {@const box = outline.box}
                                    {@const size = outline.size}
                                    <svg class="pointer-events-none absolute inset-0 h-full w-full text-amber-400" viewBox={`0 0 ${size[0]} ${size[1]}`} preserveAspectRatio="xMidYMid meet" aria-hidden="true" data-garden-presence={outline.kind === 'presence' ? '' : undefined} data-garden-input={outline.kind === 'identification' ? '' : undefined}>
                                        <rect x={box[0] * size[0]} y={box[1] * size[1]} width={box[2] * size[0]} height={box[3] * size[1]} fill="none" stroke="black" stroke-width="4" vector-effect="non-scaling-stroke" />
                                        <rect x={box[0] * size[0]} y={box[1] * size[1]} width={box[2] * size[0]} height={box[3] * size[1]} fill="none" stroke="currentColor" stroke-width="2" vector-effect="non-scaling-stroke" />
                                    </svg>
                                {/if}
                            {:else}
                                <p class="absolute inset-0 flex items-center justify-center p-4 text-center text-sm text-slate-600 dark:text-slate-400">{$_('garden.snapshot_unavailable', { default: 'Snapshot unavailable' })}</p>
                            {/if}
                        </div>
                        <div class="min-w-0 space-y-4 p-4">
                            <div class="space-y-1">
                                <h2 class="break-words font-semibold">{item.camera}</h2>
                                {#if group.items.length > 1}
                                    <p class="font-semibold text-sm">{$_('garden.group_count', { default: '{count} photos around the same position', values: { count: group.items.length } })}</p>
                                    <p class="text-xs text-slate-600 dark:text-slate-400">{$_('garden.group_help', { default: 'Position does not identify an animal. This group can contain different visitors.' })}</p>
                                    <p class="text-xs">{new Date(group.items[group.items.length - 1].observed_at).toLocaleString()} · {new Date(group.items[0].observed_at).toLocaleString()}</p>
                                    <div class="flex flex-wrap items-center gap-2">
                                        <button class="btn btn-secondary min-h-11 px-3 py-2 whitespace-normal" disabled={saving !== null || photoIndex === 0} onclick={() => selectPhoto(group, photoIndex - 1)}>{$_('garden.previous_photo', { default: 'Previous photo' })}</button>
                                        <span class="text-xs">{$_('garden.photo_count', { default: 'Photo {index} of {count}', values: { index: photoIndex + 1, count: group.items.length } })}</span>
                                        <button class="btn btn-secondary min-h-11 px-3 py-2 whitespace-normal" disabled={saving !== null || photoIndex + 1 >= group.items.length} onclick={() => selectPhoto(group, photoIndex + 1)}>{$_('garden.next_photo', { default: 'Next photo' })}</button>
                                    </div>
                                {/if}
                                <time class="block text-xs text-slate-600 dark:text-slate-400" datetime={item.observed_at}>{new Date(item.observed_at).toLocaleString()}</time>
                                <p class="break-words text-sm">{item.source_kind === 'motion' ? $_('garden.motion_source', { default: 'Candidate from retained motion footage' }) : $_('garden.frigate_suggested', { default: 'Frigate suggested: {label}', values: { label: item.frigate_label } })}</p>
                                {#if outline?.kind === 'presence' && !failedImages[item.id]}
                                    <p class="text-xs text-slate-600 dark:text-slate-400">{$_('garden.presence_box', { default: 'Box: MegaDetector Cedar candidate. Check the photo before confirming.' })}</p>
                                {/if}
                                <p class="text-xs text-slate-600 dark:text-slate-400">{views.find(view => view.id === item.status)?.name}</p>
                                {#if item.identification && item.identification.review !== 'dismissed'}
                                    {#if item.identification.outcome === 'suggestion'}
                                        <p class="break-words font-semibold">{item.identification.name}</p>
                                        <p class="text-xs text-slate-600 dark:text-slate-400">{item.identification.review === 'accepted' ? $_('garden.identification_confirmed', { default: 'Identification confirmed by you' }) : $_('garden.identification_needs_review', { default: 'Suggested identification · Needs your review' })}</p>
                                        {#if item.identification.rank !== 'species'}<p class="text-xs">{$_('garden.group_only', { default: 'Animal group only; species is unresolved.' })}</p>{/if}
                                        <p class="text-xs">{$_('garden.model_score', { default: 'Model score: {score}%', values: { score: ((item.identification.score ?? 0) * 100).toFixed(1) } })}</p>
                                    {:else}
                                        <p class="text-sm">{$_('garden.identification_unknown', { default: 'No reliable identification. Leave this animal unidentified or try another model.' })}</p>
                                    {/if}
                                    <p class="text-xs text-slate-600 dark:text-slate-400">{item.identification.variant} · {item.identification.devices.join(', ')} · {item.identification.country} · {item.identification.input_kind === 'tracked_crop' ? $_('garden.tracked_crop', { default: 'Tracked snapshot crop' }) : $_('garden.whole_image', { default: 'Whole image with model border trim' })}</p>
                                {/if}
                            </div>
                            <div class="flex flex-col gap-2">
                                {#if group.items.length > 1}
                                    <p class="text-sm font-semibold">{$_('garden.single_photo_help', { default: 'Review this photo' })}</p>
                                {/if}
                                {#if item.status === 'pending'}
                                    {#if item.motion_source}
                                        <button class="btn btn-secondary min-h-11 px-4 py-2 whitespace-normal" disabled={saving !== null || !canCheckPhoto || !loadedImages[item.id] || failedImages[item.id]} onclick={() => checkPhoto(item)}>{$_('garden.check_photo', { default: 'Check photo' })}</button>
                                        {#if !canCheckPhoto}<p class="text-xs text-slate-600 dark:text-slate-400">{$_('garden.check_setup', { default: 'Open Species suggestions to download the tracked-crop model and choose a provider. Photo checks do not need a country.' })}</p>{/if}
                                    {/if}
                                    <button class="btn btn-primary min-h-11 px-4 py-2 whitespace-normal" disabled={saving !== null || (!loadedImages[item.id] || failedImages[item.id])} onclick={() => review(item, 'confirm')}>{$_('garden.confirm', { default: 'Confirm animal present' })}</button>
                                {/if}
                                {#if item.status === 'confirmed'}
                                    {#if item.identification?.review === 'accepted'}
                                        <button class="btn btn-secondary min-h-11 px-4 py-2 whitespace-normal" disabled={saving !== null} onclick={() => speciesAction(item, 'dismiss')}>{$_('garden.discard_identification', { default: 'Discard identification' })}</button>
                                    {:else}
                                        <button class="btn btn-secondary min-h-11 px-4 py-2 whitespace-normal" disabled={saving !== null || (!loadedImages[item.id] || failedImages[item.id]) || !canIdentify} onclick={() => speciesAction(item, 'identify')}>{saving === item.id ? $_('garden.working', { default: 'Working…' }) : $_('garden.suggest_species', { default: 'Suggest species' })}</button>
                                        {#if !canIdentify}<p class="text-xs text-slate-600 dark:text-slate-400">{$_('garden.setup_needed', { default: 'Open Species suggestions above to check the model, country and availability.' })}</p>{/if}
                                        {#if item.identification?.outcome === 'suggestion' && item.identification.review === 'unreviewed'}
                                            <button class="btn btn-primary min-h-11 px-4 py-2 whitespace-normal" disabled={saving !== null || (!loadedImages[item.id] || failedImages[item.id])} onclick={() => speciesAction(item, 'accept')}>{$_('garden.accept_identification', { default: 'Confirm identification' })}</button>
                                            <button class="btn btn-secondary min-h-11 px-4 py-2 whitespace-normal" disabled={saving !== null} onclick={() => speciesAction(item, 'dismiss')}>{$_('garden.dismiss_suggestion', { default: 'Dismiss suggestion' })}</button>
                                        {/if}
                                    {/if}
                                {/if}
                                {#if item.status !== 'dismissed'}
                                    <button class="btn btn-secondary min-h-11 px-4 py-2 whitespace-normal" disabled={saving !== null} onclick={() => review(item, 'dismiss')}>{$_('garden.dismiss', { default: 'Dismiss capture' })}</button>
                                {:else}
                                    <button class="btn btn-secondary min-h-11 px-4 py-2 whitespace-normal" disabled={saving !== null || !item.snapshot_url} onclick={() => review(item, 'restore')}>{$_('garden.restore', { default: 'Return to review' })}</button>
                                    {#if !item.snapshot_url}
                                        <p class="text-xs text-slate-600 dark:text-slate-400">{$_('garden.photo_restore_unavailable', { default: 'Photo unavailable. It cannot return to review.' })}</p>
                                    {/if}
                                {/if}
                                {#if group.items.length > 1}
                                    <div class="space-y-2 border-t border-line-soft pt-3" data-garden-stack-review>
                                        <p class="text-sm font-semibold">{$_('garden.group_review', { default: 'Review this stack' })}</p>
                                        <p class="text-xs text-slate-600 dark:text-slate-400">{$_('garden.group_dismiss_help', { default: 'Confirm any animal photos first, then dismiss the remaining photos in this stack. Confirmed photos are kept; future captures are unaffected.' })}</p>
                                        <button class="btn btn-secondary min-h-11 w-full px-4 py-2 whitespace-normal" disabled={saving !== null} onclick={() => reviewGroup(group)}>{$_('garden.group_dismiss', { default: 'Dismiss remaining {count} photos', values: { count: group.items.length } })}</button>
                                    </div>
                                {/if}
                            </div>
                        </div>
                    </article>
                {/each}
            </div>
        {/if}
    </div>
    {#if !loading && !error && total > 0}
        <div class="flex flex-wrap items-center justify-between gap-3">
            <button class="btn btn-secondary min-h-11 px-4 py-2" disabled={offset === 0 || saving !== null} onclick={() => { offset = Math.max(0, offset - pageSize); void load(); }}>{$_('garden.previous', { default: 'Previous' })}</button>
            <p class="text-xs text-slate-600 dark:text-slate-400">{status === 'pending'
                ? $_('garden.review_page_count', { default: 'Photos {start}–{end} of {total} · {cards, plural, one {# review card} other {# review cards}}', values: { start: offset + 1, end: offset + items.length, total, cards: groups.length } })
                : $_('garden.page_count', { default: '{start}–{end} of {total}', values: { start: offset + 1, end: Math.min(offset + pageSize, total), total } })}</p>
            <button class="btn btn-secondary min-h-11 px-4 py-2" disabled={offset + pageSize >= total || saving !== null} onclick={() => { offset += pageSize; void load(); }}>{$_('garden.next', { default: 'Next' })}</button>
        </div>
    {/if}
</div>

{#if photoCheckTarget}
    <GardenPhotoCheckDialog capture={photoCheckTarget} assessment={photoAssessment} busy={photoCheckBusy} error={photoCheckError} runId={photoCheckRun} size={loadedImages[photoCheckTarget.id]} onClose={clearPhotoCheck} />
{/if}
