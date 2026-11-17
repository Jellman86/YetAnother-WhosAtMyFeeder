<script lang="ts">
    import { _ } from 'svelte-i18n';
    import { createInaturalistDraft, submitInaturalistObservation, type InaturalistDraft } from '../../api';
    import { settingsStore } from '../../stores/settings.svelte';
    import { formatDateTime } from '../../utils/datetime';
    import { getErrorMessage } from '../../utils/error-handling';

    /**
     * Sending one record to iNaturalist: a draft the backend prepares, the place and notes the owner
     * may correct, and one submit. The parent remounts it for each record, so a draft never carries
     * over to the next bird.
     */
    type Props = { eventId: string; connectedUser: string };

    let { eventId, connectedUser }: Props = $props();

    let open = $state(false);
    let loading = $state(false);
    let submitting = $state(false);
    let error = $state<string | null>(null);
    let draft = $state<InaturalistDraft | null>(null);
    let notes = $state('');
    let latitude = $state<number | null>(null);
    let longitude = $state<number | null>(null);
    let place = $state('');

    async function toggle(): Promise<void> {
        open = !open;
        if (!open || draft?.event_id === eventId) return;
        loading = true;
        error = null;
        try {
            draft = await createInaturalistDraft(eventId);
            notes = '';
            const defaults = settingsStore.settings;
            latitude = draft.latitude ?? defaults?.inaturalist_default_latitude ?? defaults?.location_latitude ?? null;
            longitude = draft.longitude ?? defaults?.inaturalist_default_longitude ?? defaults?.location_longitude ?? null;
            place = draft.place_guess ?? defaults?.inaturalist_default_place_guess ?? '';
        } catch (e) {
            error = getErrorMessage(e) || 'Failed to load iNaturalist draft';
        } finally {
            loading = false;
        }
    }

    async function submit(): Promise<void> {
        if (!draft) return;
        submitting = true;
        error = null;
        try {
            await submitInaturalistObservation({
                event_id: draft.event_id,
                notes: notes || undefined,
                latitude: latitude ?? undefined,
                longitude: longitude ?? undefined,
                place_guess: place || undefined
            });
            open = false;
            notes = '';
            latitude = draft.latitude ?? null;
            longitude = draft.longitude ?? null;
            place = draft.place_guess ?? '';
        } catch (e) {
            error = getErrorMessage(e) || 'Failed to submit to iNaturalist';
        } finally {
            submitting = false;
        }
    }
</script>

<section class="space-y-3 border-t border-line-soft pt-4" data-record-inaturalist>
    <div class="flex flex-wrap items-center justify-between gap-3">
        <div class="min-w-0">
            <h3 class="text-xs font-semibold text-strong">{$_('detection.inat.title')}</h3>
            <p class="text-xs text-muted">{$_('detection.inat.connected', { values: { user: connectedUser } })}</p>
        </div>
        <button type="button" onclick={toggle} class="btn btn-secondary min-h-11 px-3 text-xs" aria-label={$_('detection.inat.open_label')} aria-expanded={open}>
            {open ? $_('detection.inat.close') : $_('detection.inat.open')}
        </button>
    </div>

    {#if open}
        <div class="space-y-3">
            {#if loading}
                <p class="text-xs font-semibold text-muted" role="status">{$_('detection.inat.loading')}</p>
            {:else}
                {#if error}
                    <p class="text-xs font-semibold text-status-fail" role="alert">{error}</p>
                {/if}
                {#if draft}
                    <dl class="divide-y divide-line-soft border-y border-line-soft text-xs">
                        <div class="flex flex-wrap justify-between gap-x-3 py-2">
                            <dt class="text-muted">{$_('detection.inat.species')}</dt>
                            <dd class="font-semibold text-ink">{draft.species_guess}</dd>
                        </div>
                        <div class="flex flex-wrap justify-between gap-x-3 py-2">
                            <dt class="text-muted">{$_('detection.inat.observed')}</dt>
                            <dd class="font-semibold text-ink">{formatDateTime(draft.observed_on_string)}</dd>
                        </div>
                    </dl>
                    <div class="grid grid-cols-2 gap-3">
                        <div>
                            <label for="inat-lat" class="mb-1 block text-xs font-semibold text-muted">{$_('detection.inat.latitude')}</label>
                            <input id="inat-lat" type="number" step="0.0001" bind:value={latitude} class="input-base" />
                        </div>
                        <div>
                            <label for="inat-lon" class="mb-1 block text-xs font-semibold text-muted">{$_('detection.inat.longitude')}</label>
                            <input id="inat-lon" type="number" step="0.0001" bind:value={longitude} class="input-base" />
                        </div>
                    </div>
                    <div>
                        <label for="inat-place" class="mb-1 block text-xs font-semibold text-muted">{$_('detection.inat.place')}</label>
                        <input id="inat-place" type="text" bind:value={place} class="input-base" />
                    </div>
                    <div>
                        <label for="inat-notes" class="mb-1 block text-xs font-semibold text-muted">{$_('detection.inat.notes')}</label>
                        <textarea id="inat-notes" rows="3" bind:value={notes} class="input-base"></textarea>
                    </div>
                    <button type="button" onclick={submit} disabled={submitting} class="btn btn-primary min-h-11 w-full px-4 text-xs">
                        {submitting ? $_('detection.inat.submitting') : $_('detection.inat.submit')}
                    </button>
                {/if}
            {/if}
        </div>
    {/if}
</section>
