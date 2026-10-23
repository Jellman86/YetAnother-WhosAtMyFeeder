<script lang="ts">
    /**
     * Garden's own models, downloaded only when the owner asks. The Garden API answers only while
     * the saved beta switch is on, so status waits for Apply rather than guessing. A download
     * installs a verified file and nothing else: it saves no settings, activates no bird model and
     * starts no checks.
     */
    import { _ } from 'svelte-i18n';
    import {
        fetchGardenIdentification,
        fetchGardenMotion,
        installGardenModel,
        installGardenMotion,
        type GardenIdentificationStatus,
        type GardenMotionStatus
    } from '../../api/garden';
    import { settingsStore } from '../../stores/settings.svelte';
    import {
        formatModelSize,
        gardenModelRows,
        gardenSetupBlock,
        type GardenModelRole,
        type GardenModelRow
    } from '../../utils/garden-models';

    interface Props {
        motionCameras: string[];
    }

    let { motionCameras }: Props = $props();

    const savedEnabled = $derived(settingsStore.settings?.beta_garden_animals === true);
    let identification = $state.raw<GardenIdentificationStatus | null>(null);
    let motion = $state.raw<GardenMotionStatus | null>(null);
    let loading = $state(false);
    let loadError = $state<string | null>(null);
    let downloading = $state<GardenModelRole | null>(null);
    let rowErrors = $state<Partial<Record<GardenModelRole, string>>>({});
    let rowDone = $state<Partial<Record<GardenModelRole, boolean>>>({});
    let generation = 0;

    const rows = $derived(gardenModelRows(identification, motion, motionCameras));
    const block = $derived(gardenSetupBlock(identification, downloading));

    async function refresh(signal?: AbortSignal): Promise<void> {
        const request = ++generation;
        loading = true;
        loadError = null;
        const [identificationResult, motionResult] = await Promise.allSettled([
            fetchGardenIdentification(signal ?? new AbortController().signal),
            fetchGardenMotion(signal ?? new AbortController().signal)
        ]);
        if (request !== generation || signal?.aborted) return;
        identification = identificationResult.status === 'fulfilled' ? identificationResult.value : null;
        motion = motionResult.status === 'fulfilled' ? motionResult.value : null;
        const failure = [identificationResult, motionResult].find(result => result.status === 'rejected');
        loadError = failure?.status !== 'rejected'
            ? null
            : failure.reason instanceof Error && failure.reason.message
                ? failure.reason.message
                : $_('garden.model_status_unavailable', { default: 'Model status unavailable. Refresh to try again.' });
        loading = false;
    }

    $effect(() => {
        if (!savedEnabled) return;
        const controller = new AbortController();
        void refresh(controller.signal);
        return () => {
            controller.abort();
            generation += 1;
        };
    });

    async function download(row: GardenModelRow): Promise<void> {
        if (block !== null) return;
        downloading = row.role;
        rowErrors = { ...rowErrors, [row.role]: undefined };
        rowDone = { ...rowDone, [row.role]: false };
        try {
            if (row.install.kind === 'motion') motion = await installGardenMotion();
            else identification = await installGardenModel(row.install.variant);
            rowDone = { ...rowDone, [row.role]: true };
        } catch (failure) {
            rowErrors = {
                ...rowErrors,
                [row.role]: failure instanceof Error && failure.message
                    ? failure.message
                    : $_('settings.beta.garden_model_download_failed', { default: 'The download could not be verified. Nothing was changed. Try again.' })
            };
        } finally {
            downloading = null;
        }
        await refresh();
    }

    function modelName(role: GardenModelRole): string {
        if (role === 'automatic_check') return $_('settings.beta.garden_model_check', { default: 'Automatic check model' });
        if (role === 'species_suggestions') return $_('settings.beta.garden_model_suggestions', { default: 'Species suggestion model' });
        return $_('settings.beta.garden_model_motion', { default: 'Motion detector' });
    }

    function modelSource(role: GardenModelRole): string {
        if (role === 'automatic_check') return $_('garden.model_crop', { default: 'SpeciesNet 4.0.3a · Tracked crop' });
        if (role === 'species_suggestions') return $_('garden.model_whole', { default: 'SpeciesNet 4.0.3b · Whole image' });
        return $_('settings.beta.garden_model_motion_source', { default: 'MegaDetector v1000 Cedar' });
    }

    function modelPurpose(role: GardenModelRole): string {
        if (role === 'automatic_check') return $_('settings.beta.garden_model_check_help', { default: 'Checks every new capture, dismisses bird-only or empty photos and names confident animals. If it is missing, the first automatic check downloads it.' });
        if (role === 'species_suggestions') return $_('settings.beta.garden_model_suggestions_help', { default: 'Used when you choose Suggest species on a confirmed animal. Not needed for automatic checks.' });
        return $_('settings.beta.garden_model_motion_help', { default: 'Finds animals in retained motion footage for cameras with motion photos turned on. Not needed for Frigate animal events.' });
    }

    function stateLabel(row: GardenModelRow): string {
        if (row.state === 'ready') return $_('settings.beta.garden_model_ready', { default: 'Downloaded' });
        if (row.state === 'missing') return $_('settings.beta.garden_model_missing', { default: 'Not downloaded' });
        if (row.state === 'unavailable') return $_('settings.beta.garden_model_unavailable', { default: 'Unavailable' });
        return $_('settings.beta.garden_model_unknown', { default: 'Status unknown' });
    }

    function blockReason(value: NonNullable<typeof block>): string {
        if (value === 'downloading') return $_('settings.beta.garden_models_one_at_a_time', { default: 'One download runs at a time.' });
        if (value === 'busy') return $_('settings.beta.garden_models_busy', { default: 'Garden is busy with a check, scan or download. Refresh the status in a minute.' });
        if (value === 'error') return $_('settings.beta.garden_models_error', { default: 'Garden work is stopped until the application restarts.' });
        return $_('settings.beta.garden_models_status_needed', { default: 'Downloads are available once the model status loads.' });
    }
</script>

<section class="space-y-3" aria-labelledby="garden-beta-models" data-garden-models>
    <div class="space-y-1">
        <h4 id="garden-beta-models" class="text-sm font-semibold text-slate-900 dark:text-white">{$_('settings.beta.garden_models', { default: 'Garden models' })}</h4>
        <p class="text-xs text-slate-600 dark:text-slate-400">{$_('settings.beta.garden_models_help', { default: 'Garden uses its own models, separate from your bird model. A download only adds a verified file: it does not save these settings, change bird detection or start any checks.' })}</p>
    </div>

    {#if !savedEnabled}
        <p class="rounded-xl border border-dashed border-line-soft p-3 text-sm text-slate-600 dark:text-slate-300" role="status" data-garden-models-apply>
            {$_('settings.beta.garden_models_apply', { default: 'Choose Apply Settings to switch Garden on. Model status and downloads then appear here.' })}
        </p>
    {:else}
        {#if loading && !identification && !motion}
            <p class="text-sm text-slate-600 dark:text-slate-400" role="status">{$_('settings.beta.garden_models_loading', { default: 'Checking Garden models…' })}</p>
        {:else}
            {#if loadError !== null}
                <p class="rounded-xl border border-line-soft p-3 text-sm" role="alert">{loadError}</p>
            {/if}
            {#if identification?.error}
                <p class="rounded-xl border border-line-soft p-3 text-sm" role="alert">{identification.error}</p>
            {:else if identification && !identification.catalogue_ready}
                <p class="rounded-xl border border-line-soft p-3 text-sm" role="alert">{$_('garden.catalogue_unavailable', { default: 'Garden species data is unavailable. Check the application startup diagnostics.' })}</p>
            {/if}

            <ul class="space-y-2">
                {#each rows as row (row.role)}
                    {@const busyHere = downloading === row.role}
                    <li class="space-y-2 rounded-xl border border-line-soft bg-surface-raised/40 p-3" data-garden-model={row.role} aria-labelledby={`garden-model-${row.role}`}>
                        <div class="flex flex-wrap items-start justify-between gap-x-3 gap-y-1">
                            <div class="min-w-0 flex-1">
                                <p id={`garden-model-${row.role}`} class="break-words text-sm font-semibold text-slate-800 dark:text-slate-100">{modelName(row.role)}</p>
                                <p class="break-words text-xs text-slate-600 dark:text-slate-400">{modelSource(row.role)}{#if row.sizeBytes !== null}{' · '}{formatModelSize(row.sizeBytes)}{/if}</p>
                            </div>
                            <p class="max-w-full break-words text-xs font-semibold {row.state === 'missing' && row.requirement === 'required' ? 'text-amber-700 dark:text-amber-300' : 'text-slate-700 dark:text-slate-200'}" data-garden-model-state>
                                {row.requirement === 'required'
                                    ? $_('settings.beta.garden_model_required', { default: 'Required' })
                                    : $_('settings.beta.garden_model_optional', { default: 'Optional' })}
                                · {stateLabel(row)}
                            </p>
                        </div>
                        <p class="text-xs text-slate-600 dark:text-slate-400">{modelPurpose(row.role)}</p>
                        {#if busyHere}
                            <div class="space-y-1" role="status">
                                <progress class="h-1.5 w-full" aria-label={$_('settings.beta.garden_model_downloading_label', { values: { model: modelName(row.role) }, default: 'Downloading {model}' })}></progress>
                                <p class="text-xs">{$_('settings.beta.garden_model_downloading', { default: 'Downloading and verifying. This can take up to three minutes; you can keep editing settings.' })}</p>
                            </div>
                        {:else if row.state === 'missing'}
                            <button
                                type="button"
                                class="btn btn-secondary min-h-11 max-w-full px-3 py-2 whitespace-normal"
                                disabled={block !== null}
                                aria-describedby={block !== null ? 'garden-models-block' : undefined}
                                onclick={() => download(row)}
                            >
                                {rowErrors[row.role]
                                    ? $_('settings.beta.garden_model_retry', { default: 'Retry download' })
                                    : $_('settings.beta.garden_model_download', { values: { size: row.sizeBytes !== null ? formatModelSize(row.sizeBytes) : '' }, default: 'Download {size}' })}
                            </button>
                        {/if}
                        {#if rowErrors[row.role]}
                            <p class="text-xs" role="alert">{rowErrors[row.role]}</p>
                        {:else if rowDone[row.role] && row.state === 'ready'}
                            <p class="text-xs" role="status">{$_('settings.beta.garden_model_verified', { default: 'Downloaded and checksum verified.' })}</p>
                        {/if}
                    </li>
                {/each}
            </ul>

            {#if block !== null && block !== 'downloading' && rows.some(row => row.state === 'missing')}
                <p id="garden-models-block" class="text-xs text-slate-600 dark:text-slate-400" role="status">{blockReason(block)}</p>
            {:else if block === 'downloading'}
                <p id="garden-models-block" class="sr-only">{blockReason(block)}</p>
            {/if}

            {#if identification}
                <p class="text-xs text-slate-600 dark:text-slate-400" data-garden-country>
                    {identification.country
                        ? $_('settings.beta.garden_country', { values: { country: identification.country }, default: 'Animal names are filtered for {country}.' })
                        : $_('settings.beta.garden_country_missing', { default: 'Set a country in Settings → Location. Without one, animals are not named automatically and species suggestions are unavailable.' })}
                </p>
            {/if}
        {/if}

        <p class="text-xs text-slate-600 dark:text-slate-400">{$_('settings.beta.garden_models_limits', { default: 'Automatic checks and motion scans run on CPU, one at a time, while bird inference and cameras are idle. Each check loads its model in a separate process and releases the memory afterwards; memory use has not been measured for this beta. Other processors are only offered for checks you start on the Garden animals page, and fail rather than fall back to CPU.' })}</p>

        <button type="button" class="btn btn-ghost min-h-11 max-w-full px-3 py-2 whitespace-normal" disabled={loading || downloading !== null} onclick={() => refresh()}>
            {$_('settings.beta.garden_models_refresh', { default: 'Refresh model status' })}
        </button>
    {/if}
</section>
