<script lang="ts">
    import { _ } from 'svelte-i18n';
    import SettingsCard from './_primitives/SettingsCard.svelte';
    import SettingsRow from './_primitives/SettingsRow.svelte';
    import SettingsInput from './_primitives/SettingsInput.svelte';
    import SettingsSegmented from './_primitives/SettingsSegmented.svelte';
    import Map from '../Map.svelte';
    import { reverseGeocode } from '../../api/geocoding';

    // The feeder's place: the weather recorded with each visit, nearby eBird sightings, the range
    // filter, a location-aware model and observations sent to iNaturalist all start from it.
    let {
        locationAuto = $bindable(true),
        locationLat = $bindable<number | null>(null),
        locationLon = $bindable<number | null>(null),
        locationState = $bindable(''),
        locationCountry = $bindable(''),
        savedLocation = null
    }: {
        locationAuto: boolean;
        locationLat: number | null;
        locationLon: number | null;
        locationState: string;
        locationCountry: string;
        /** The saved coordinates. A place looked up for them is shown, never written into the draft. */
        savedLocation?: { latitude: number | null; longitude: number | null } | null;
    } = $props();

    let mapPoint = $derived<[number, number] | null>(
        typeof locationLat === 'number' && typeof locationLon === 'number' && Number.isFinite(locationLat) && Number.isFinite(locationLon)
            ? [locationLat, locationLon]
            : null
    );

    let geocodeLoading = $state(false);
    let geocodePlace = $state<string | null>(null);
    let geocodeError = $state<string | null>(null);
    let geocodeKey = $state<string | null>(null);

    $effect(() => {
        if (!mapPoint) {
            geocodePlace = null;
            geocodeError = null;
            geocodeKey = null;
            return;
        }
        const [lat, lon] = mapPoint;
        const key = `${lat.toFixed(2)},${lon.toFixed(2)}`;
        // The region of the saved point is already saved; only a moved pin brings a new one.
        const pinMoved = !savedLocation || savedLocation.latitude !== lat || savedLocation.longitude !== lon;
        if (key === geocodeKey) return;
        geocodeKey = key;
        geocodeLoading = true;
        geocodeError = null;
        reverseGeocode(lat, lon)
            .then((result) => {
                if (geocodeKey !== key) return;
                geocodePlace = result.place_guess
                    || [result.state, result.country].filter(Boolean).join(', ')
                    || null;
                if (!pinMoved) return;
                if (result.state) locationState = result.state;
                if (result.country) locationCountry = result.country;
            })
            .catch((error) => {
                if (geocodeKey !== key) return;
                geocodeError = error instanceof Error ? error.message : 'Lookup failed';
            })
            .finally(() => {
                if (geocodeKey === key) geocodeLoading = false;
            });
    });
</script>

<SettingsCard
    title={$_('settings.location.card_title', { default: 'Your feeder\u2019s location' })}
    description={$_('settings.location.card_desc', { default: 'The weather recorded with each visit, nearby eBird sightings, the range filter and observations sent to iNaturalist all start from here.' })}
>
    <SettingsRow
        labelId="setting-location-mode"
        label={$_('settings.location.mode_title', { default: 'Location source' })}
        description={$_('settings.location.mode_help', { default: 'Auto-detect uses your IP/timezone. Manual lets you pin exact coordinates for weather, eBird hotspots, and observation submissions.' })}
        layout="stacked"
    >
        <SettingsSegmented
            value={locationAuto ? 'auto' : 'manual'}
            layout="card"
            columns={2}
            labelledBy="setting-location-mode"
            onchange={(v) => (locationAuto = v === 'auto')}
            options={[
                {
                    value: 'auto',
                    label: $_('settings.location.mode_auto', { default: 'Auto-detect' }),
                    sub: $_('settings.location.mode_auto_sub', { default: 'Resolved from your network' })
                },
                {
                    value: 'manual',
                    label: $_('settings.location.mode_manual', { default: 'Manual entry' }),
                    sub: $_('settings.location.mode_manual_sub', { default: 'Pin exact latitude and longitude' })
                }
            ]}
        />
    </SettingsRow>

    {#if !locationAuto}
        <div class="space-y-4">
            <SettingsRow
                labelId="setting-location-lat"
                label={$_('settings.location.latitude')}
                layout="stacked"
            >
                <SettingsInput
                    id="location-lat"
                    field="location_latitude"
                    type="number"
                    value={locationLat ?? ''}
                    ariaLabel={$_('settings.location.latitude')}
                    oninput={(v) => (locationLat = v === '' ? null : Number(v))}
                />
            </SettingsRow>
            <SettingsRow
                labelId="setting-location-lon"
                label={$_('settings.location.longitude')}
                layout="stacked"
            >
                <SettingsInput
                    id="location-lon"
                    field="location_longitude"
                    type="number"
                    value={locationLon ?? ''}
                    ariaLabel={$_('settings.location.longitude')}
                    oninput={(v) => (locationLon = v === '' ? null : Number(v))}
                />
            </SettingsRow>
        </div>
    {/if}

    {#if mapPoint}
        <div class="flex items-center gap-2 text-xs">
            <span class="shrink-0 text-sm font-semibold text-ink">{$_('settings.location.resolved_label', { default: 'Resolved' })}</span>
            {#if geocodeLoading}
                <span class="text-muted">{$_('settings.location.resolving', { default: 'Looking up…' })}</span>
            {:else if geocodeError}
                <span class="text-status-fail">{$_('settings.location.resolve_error', { default: 'Lookup failed' })}</span>
            {:else if geocodePlace}
                <span class="truncate text-ink">{geocodePlace}</span>
            {:else}
                <span class="text-muted">{$_('settings.location.resolve_empty', { default: 'No place name available for these coordinates' })}</span>
            {/if}
        </div>
    {/if}

    <SettingsRow
        labelId="setting-location-map"
        label={$_('settings.location.map_title', { default: 'Map preview' })}
        description={mapPoint
            ? $_('settings.location.map_help', { default: 'Showing the location currently configured for weather, hotspots, and observations.' })
            : $_('settings.location.map_empty', { default: 'No coordinates configured yet. Set a latitude and longitude (or enable auto-detect) to see the map.' })}
        layout="stacked"
    >
        <div class="h-64 w-full overflow-hidden rounded-2xl border border-line-soft">
            {#if mapPoint}
                {#key `${mapPoint[0]},${mapPoint[1]}`}
                    <Map userLocation={mapPoint} center={mapPoint} zoom={11} />
                {/key}
            {:else}
                <div class="flex h-full w-full items-center justify-center bg-surface-sunken text-xs italic text-muted">
                    {$_('settings.location.map_empty', { default: 'No coordinates configured yet.' })}
                </div>
            {/if}
        </div>
    </SettingsRow>
</SettingsCard>
