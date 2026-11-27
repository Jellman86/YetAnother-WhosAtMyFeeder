<script lang="ts">
    /**
     * Another species seen in one capture of a visit. The visit keeps its own species' name; this
     * note is secondary, and it opens the capture that holds the other bird, so the owner can see the
     * evidence rather than take a name on trust. It says capture, never photo: a card's thumbnail is
     * usually a crop of one bird, so the other is in the capture's whole scene, not in that picture.
     */
    import { _, locale } from 'svelte-i18n';
    import type { Detection } from '../api';
    import { birdNames } from '../naming';
    import { settingsStore } from '../stores/settings.svelte';
    import { authStore } from '../stores/auth.svelte';
    import { formatTime } from '../utils/datetime';
    import type { CompanionSpecies } from '../utils/visit-captures';

    interface Props {
        companions: CompanionSpecies;
        onopen: (capture: Detection) => void;
        class?: string;
    }

    let { companions, onopen, class: className = '' }: Props = $props();

    const showCommon = $derived(settingsStore.settings?.display_common_names ?? authStore.displayCommonNames ?? true);
    const preferSci = $derived(settingsStore.settings?.scientific_name_primary ?? authStore.scientificNamePrimary ?? false);
    const names = $derived(
        new Intl.ListFormat($locale ?? 'en', { style: 'long', type: 'conjunction' }).format(
            companions.species.map((entry) => $birdNames(entry, showCommon, preferSci).primary)
        )
    );
    const note = $derived(
        companions.shown
            ? $_('events.also_in_this_capture', { values: { species: names }, default: 'Also in this capture: {species}' })
            : $_('events.also_in_one_capture', { values: { species: names }, default: 'Also in one capture: {species}' })
    );
    const captureTime = $derived(
        formatTime(companions.capture.detection_time, { hour: '2-digit', minute: '2-digit', second: '2-digit' })
    );
    const label = $derived(
        $_('events.also_in_capture_open', { values: { note, time: captureTime }, default: '{note}. Open the capture at {time}' })
    );
</script>

<button
    type="button"
    class="pointer-events-auto -ml-2 inline-flex min-h-11 max-w-full items-center gap-1.5 rounded-lg px-2 text-left text-xs font-semibold text-accent-ink transition-colors hover:bg-accent-soft focus-visible:outline-hidden focus-visible:ring-2 focus-visible:ring-focus {className}"
    aria-label={label}
    onclick={(event) => {
        event.stopPropagation();
        onopen(companions.capture);
    }}
    data-visit-companions={companions.capture.frigate_event}
>
    <svg class="h-3.5 w-3.5 shrink-0" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" aria-hidden="true">
        <path stroke-linecap="round" stroke-linejoin="round" d="M4 6h16v12H4z" />
        <path stroke-linecap="round" stroke-linejoin="round" d="m4 15 4-4 3 3 3-2 6 5" />
    </svg>
    <span class="min-w-0 wrap-break-word">{note}</span>
</button>
