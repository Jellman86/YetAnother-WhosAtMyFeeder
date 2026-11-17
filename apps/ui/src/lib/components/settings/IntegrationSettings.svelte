<script lang="ts">
    import { _ } from 'svelte-i18n';
    import { locationTogglePresentation } from '../../settings/location-toggle';
    import SecretInput from './_primitives/SecretInput.svelte';
    import SettingsCard from './_primitives/SettingsCard.svelte';
    import SettingsRow from './_primitives/SettingsRow.svelte';
    import SettingsToggle from './_primitives/SettingsToggle.svelte';
    import SettingsInput from './_primitives/SettingsInput.svelte';
    import SettingsSelect from './_primitives/SettingsSelect.svelte';
    import AdvancedSection from './_primitives/AdvancedSection.svelte';
    import Map from '../Map.svelte';
    import SettingsSegmented from './_primitives/SettingsSegmented.svelte';
    import { reverseGeocode } from '../../api/geocoding';
    import DiagnosticDialog from '../DiagnosticDialog.svelte';
    import { runSequentialDiagnostic, type DiagnosticStage, type DiagnosticResult, type DiagnosticStep } from '../../utils/diagnostic-runner';
    import { illuminanceStepOutcome, isHomeAssistantEntityId, type IlluminanceStepText } from '../../utils/illuminance';
    import { testBirdWeather, testHaWeather } from '../../api/maintenance';
    import type { WeatherUnitSystem } from '../../utils/weather-units';
    import {
        ebirdRadiusFromDisplayValue,
        ebirdRadiusToDisplayValue,
        getEbirdRadiusBounds
    } from '../../utils/ebird-radius';

    let {
        birdweatherEnabled = $bindable(false),
        birdweatherStationToken = $bindable(''),
        haWeatherEnabled = $bindable(false),
        haWeatherBaseUrl = $bindable(''),
        haWeatherAccessToken = $bindable(''),
        haWeatherAccessTokenSaved = $bindable(false),
        haWeatherEntity = $bindable(''),
        haWeatherTemperatureEntity = $bindable(''),
        haWeatherWindSpeedEntity = $bindable(''),
        haWeatherWindDirectionEntity = $bindable(''),
        haWeatherCloudCoverEntity = $bindable(''),
        haWeatherPrecipitationEntity = $bindable(''),
        haWeatherRainEntity = $bindable(''),
        haWeatherSnowfallEntity = $bindable(''),
        haWeatherIlluminanceEntity = $bindable(''),
        ebirdEnabled = $bindable(false),
        ebirdApiKey = $bindable(''),
        ebirdApiKeySaved = $bindable(false),
        ebirdDefaultRadiusKm = $bindable(25),
        weatherUnitSystem = 'metric',
        ebirdDefaultDaysBack = $bindable(14),
        ebirdMaxResults = $bindable(25),
        ebirdLocale = $bindable('en'),
        inaturalistEnabled = $bindable(false),
        inaturalistClientId = $bindable(''),
        inaturalistClientSecret = $bindable(''),
        inaturalistClientIdSaved = $bindable(false),
        inaturalistClientSecretSaved = $bindable(false),
        inaturalistDefaultLat = $bindable<number | null>(null),
        inaturalistDefaultLon = $bindable<number | null>(null),
        inaturalistDefaultPlace = $bindable(''),
        inaturalistConnectedUser = $bindable(null),
        locationAuto = $bindable(true),
        locationLat = $bindable<number | null>(null),
        locationLon = $bindable<number | null>(null),
        locationState = $bindable(''),
        locationCountry = $bindable(''),
        locationWeatherUnitSystem = $bindable<'metric' | 'imperial' | 'british'>('metric'),
        prepareInaturalistOAuth,
        initiateInaturalistOAuth,
        disconnectInaturalistOAuth,
        refreshInaturalistStatus,
        exportEbirdCsv,
        birdweatherStationTokenSaved = $bindable(false),
        onActionFeedback = (_type: 'success' | 'error', _text: string) => {},
        savedLocation = null
    }: {
        birdweatherEnabled: boolean;
        birdweatherStationToken: string;
        haWeatherEnabled: boolean;
        haWeatherBaseUrl: string;
        haWeatherAccessToken: string;
        haWeatherAccessTokenSaved: boolean;
        haWeatherEntity: string;
        haWeatherTemperatureEntity: string;
        haWeatherWindSpeedEntity: string;
        haWeatherWindDirectionEntity: string;
        haWeatherCloudCoverEntity: string;
        haWeatherPrecipitationEntity: string;
        haWeatherRainEntity: string;
        haWeatherSnowfallEntity: string;
        haWeatherIlluminanceEntity: string;
        ebirdEnabled: boolean;
        ebirdApiKey: string;
        ebirdApiKeySaved: boolean;
        ebirdDefaultRadiusKm: number;
        weatherUnitSystem?: WeatherUnitSystem;
        ebirdDefaultDaysBack: number;
        ebirdMaxResults: number;
        ebirdLocale: string;
        inaturalistEnabled: boolean;
        inaturalistClientId: string;
        inaturalistClientSecret: string;
        inaturalistClientIdSaved: boolean;
        inaturalistClientSecretSaved: boolean;
        inaturalistDefaultLat: number | null;
        inaturalistDefaultLon: number | null;
        inaturalistDefaultPlace: string;
        inaturalistConnectedUser: string | null;
        locationAuto: boolean;
        locationLat: number | null;
        locationLon: number | null;
        locationState: string;
        locationCountry: string;
        locationWeatherUnitSystem: 'metric' | 'imperial' | 'british';
        prepareInaturalistOAuth: () => Promise<void>;
        initiateInaturalistOAuth: () => Promise<{ authorization_url: string }>;
        disconnectInaturalistOAuth: () => Promise<{ status: string }>;
        refreshInaturalistStatus: () => Promise<void>;
        exportEbirdCsv: (range?: { from?: string; to?: string }) => Promise<void>;
        birdweatherStationTokenSaved: boolean;
        onActionFeedback: (type: 'success' | 'error', text: string) => void;
        /** The saved coordinates. A place looked up for them is shown, never written into the draft. */
        savedLocation?: { latitude: number | null; longitude: number | null } | null;
    } = $props();

    // The radius is stored in kilometres because that is what eBird's API accepts.
    // Only the field the owner reads and edits changes with their unit preference,
    // so opening settings and saving without touching it cannot move the value.
    const ebirdRadiusBounds = $derived(getEbirdRadiusBounds(weatherUnitSystem));
    const ebirdRadiusDisplayValue = $derived(
        ebirdRadiusToDisplayValue(ebirdDefaultRadiusKm, weatherUnitSystem)
    );
    const ebirdRadiusUnitLabel = $derived(
        weatherUnitSystem === 'metric'
            ? $_('common.unit_km', { default: 'km' })
            : $_('common.unit_mi', { default: 'mi' })
    );
    const ebirdRadiusHelp = $derived(
        $_('settings.integrations.ebird.radius_help', {
            values: {
                min: ebirdRadiusBounds.min,
                max: ebirdRadiusBounds.max,
                unit: ebirdRadiusUnitLabel
            },
            default: 'eBird accepts {min} to {max} {unit}.'
        })
    );

    // An empty or half-typed field leaves the saved radius alone rather than
    // collapsing it to zero, so clearing the box to retype it is not destructive.
    function updateEbirdRadius(entered: string): void {
        const parsed = Number(entered.trim());
        const storedKm = ebirdRadiusFromDisplayValue(
            entered.trim() === '' || Number.isNaN(parsed) ? null : parsed,
            weatherUnitSystem
        );
        if (storedKm === null) return;
        ebirdDefaultRadiusKm = storedKm;
    }

    let inatConnecting = $state(false);
    let inatRefreshing = $state(false);
    let inatDisconnecting = $state(false);
    let exportingEbirdCsv = $state(false);
    let ebirdExportEverything = $state(true);
    let ebirdExportFrom = $state('');
    let ebirdExportTo = $state('');
    let ebirdExportRangeError = $state('');

    function actionErrorMessage(error: unknown) {
        if (error instanceof Error && error.message.trim().length > 0) return error.message;
        return 'Action failed';
    }

    // Connection tests use the shared DiagnosticDialog + runSequentialDiagnostic
    // (see docs/standards/diagnostics-and-dialogs.md). Each stage runs a real check
    // and reports its own outcome, so the progress a user sees is always honest.

    let bwTestOpen = $state(false);
    let bwRunning = $state(false);
    let bwStages = $state<DiagnosticStage[]>([]);
    let bwResult = $state<DiagnosticResult | null>(null);
    let bwRunId = $state(0);

    let hawTestOpen = $state(false);
    let hawRunning = $state(false);
    let hawStages = $state<DiagnosticStage[]>([]);
    let hawResult = $state<DiagnosticResult | null>(null);
    let hawRunId = $state(0);


    async function runBirdWeatherDiagnostic(): Promise<void> {
        bwTestOpen = true;
        bwRunning = true;
        bwResult = null;
        bwRunId += 1;
        bwResult = await runSequentialDiagnostic(
            [
                { id: 'station', label: $_('settings.integrations.birdweather.stage_station', { default: 'BirdWeather station token' }), run: () => testBirdWeather(birdweatherStationToken || undefined) }
            ],
            (stages) => (bwStages = stages)
        );
        bwRunning = false;
    }

    const haWeatherNamesWeather = $derived(
        [
            haWeatherEntity,
            haWeatherTemperatureEntity,
            haWeatherWindSpeedEntity,
            haWeatherWindDirectionEntity,
            haWeatherCloudCoverEntity,
            haWeatherPrecipitationEntity,
            haWeatherRainEntity,
            haWeatherSnowfallEntity
        ].some((entity) => entity.trim() !== '')
    );
    const illuminanceEntityInvalid = $derived(
        haWeatherIlluminanceEntity.trim() !== '' && !isHomeAssistantEntityId(haWeatherIlluminanceEntity)
    );

    async function runHaWeatherDiagnostic(): Promise<void> {
        hawTestOpen = true;
        hawRunning = true;
        hawResult = null;
        hawRunId += 1;
        const illuminanceEntity = haWeatherIlluminanceEntity.trim();
        // The weather check is left out only when a light sensor is all that is named.
        const steps: DiagnosticStep[] = haWeatherNamesWeather || !illuminanceEntity
            ? [
                {
                    id: 'readings',
                    label: $_('settings.integrations.ha_weather.stage_fetch', { default: 'Live readings from Home Assistant' }),
                    run: async () => {
                        const result = await testHaWeather({
                            baseUrl: haWeatherBaseUrl || undefined,
                            accessToken: haWeatherAccessToken || undefined,
                            weatherEntity: haWeatherEntity || undefined,
                            scope: 'weather'
                        });
                        return { status: result.status, message: result.message };
                    }
                }
            ]
            : [];
        // The light sensor is its own check with its own request, so the dialog can
        // show the measured value or the reason there is none.
        if (illuminanceEntity) {
            steps.push({
                id: 'illuminance',
                label: $_('settings.integrations.ha_weather.stage_illuminance', { default: 'Light level from the illuminance entity' }),
                run: async () => {
                    const result = await testHaWeather({
                        baseUrl: haWeatherBaseUrl || undefined,
                        accessToken: haWeatherAccessToken || undefined,
                        illuminanceEntity: haWeatherIlluminanceEntity.trim(),
                        scope: 'illuminance'
                    });
                    return illuminanceStepOutcome(result.illuminance, illuminanceStepText());
                }
            });
        }
        hawResult = await runSequentialDiagnostic(steps, (stages) => (hawStages = stages));
        hawRunning = false;
    }

    function illuminanceStepText(): IlluminanceStepText {
        return {
            measured: (values) => $_('settings.integrations.ha_weather.illuminance_measured', { values, default: '{reading} measured by {entity}.' }),
            missing: {
                invalid_entity_id: (values) => $_('settings.integrations.ha_weather.illuminance_invalid_entity_id', { values, default: '{entity} is not a Home Assistant entity id. Use one such as sensor.feeder_illuminance.' }),
                unreachable: (values) => $_('settings.integrations.ha_weather.illuminance_unreachable', { values, default: 'Home Assistant did not return {entity}. Check the entity id, the URL and the token.' }),
                not_illuminance: (values) => $_('settings.integrations.ha_weather.illuminance_not_illuminance', { values, default: '{entity} is not an illuminance sensor. Choose a sensor with the illuminance device class or the unit lx.' }),
                unavailable: (values) => $_('settings.integrations.ha_weather.illuminance_unavailable', { values, default: '{entity} is unknown or unavailable in Home Assistant right now. Detections record no light level until it answers.' }),
                not_numeric: (values) => $_('settings.integrations.ha_weather.illuminance_not_numeric', { values, default: '{entity} did not report a number, so no light level is recorded.' }),
                out_of_range: (values) => $_('settings.integrations.ha_weather.illuminance_out_of_range', { values, default: '{entity} reported a value outside 0 to 200,000 lx, so it is not recorded.' })
            },
            noAnswer: $_('settings.integrations.ha_weather.illuminance_no_answer', { default: 'The test returned no light reading.' })
        };
    }

    async function connectInaturalist(): Promise<void> {
        // Open while the click still owns browser activation. Waiting for a save
        // before window.open causes legitimate OAuth popups to be blocked.
        const popup = window.open('', 'yawamf-inaturalist-oauth', 'width=600,height=700');
        if (!popup) {
            onActionFeedback(
                'error',
                $_('settings.integrations.inaturalist.popup_blocked', {
                    default: 'The sign-in window was blocked. Allow popups for this site and try again.'
                })
            );
            return;
        }

        popup.opener = null;
        try {
            inatConnecting = true;
            await prepareInaturalistOAuth();
            const response = await initiateInaturalistOAuth();
            popup.location.replace(response.authorization_url);
            popup.focus();
            onActionFeedback('success', $_('settings.integrations.inaturalist.connect'));
        } catch (error) {
            popup.close();
            onActionFeedback('error', actionErrorMessage(error));
        } finally {
            inatConnecting = false;
        }
    }

    // An empty iNaturalist default follows the feeder location when an observation is sent, so the
    // fields show that location as their placeholder rather than copying it into the draft.
    const inatLatPlaceholder = $derived(typeof locationLat === 'number' ? String(locationLat) : undefined);
    const inatLonPlaceholder = $derived(typeof locationLon === 'number' ? String(locationLon) : undefined);


    $effect(() => {
        if (ebirdExportEverything) {
            ebirdExportRangeError = '';
            return;
        }
        if (ebirdExportFrom && ebirdExportTo && ebirdExportFrom > ebirdExportTo) {
            ebirdExportRangeError = $_('settings.integrations.ebird.export_range_error');
            return;
        }
        ebirdExportRangeError = '';
    });

    function setEbirdExportEverything(next: boolean) {
        ebirdExportEverything = next;
        if (ebirdExportEverything) {
            ebirdExportFrom = '';
            ebirdExportTo = '';
            ebirdExportRangeError = '';
        }
    }

    let locationToggle = $derived(locationTogglePresentation(locationAuto));
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

    const buttonPrimaryClass = 'btn btn-primary min-h-11 px-4 py-3';
    const buttonSecondaryClass = 'btn btn-secondary min-h-11 px-6 py-3';
</script>


<div class="space-y-8">
    <SettingsCard title={$_('settings.integrations.inaturalist.title')} description={$_('settings.integrations.inaturalist.toggle_label')} titleId="integration-inaturalist-title">
        <!-- The card's own switch, named by its title, so the title is not repeated as a row below it. -->
        {#snippet actions()}
            <SettingsToggle
                checked={inaturalistEnabled}
                labelledBy="integration-inaturalist-title"
                srLabel={$_('settings.integrations.inaturalist.title')}
                onchange={(v) => (inaturalistEnabled = v)}
            />
        {/snippet}

        {#if inaturalistEnabled}
        <SettingsRow
            labelId="setting-inat-client-id"
            label={$_('settings.integrations.inaturalist.client_id')}
            layout="stacked"
        >
            <SecretInput
                id="inat-client-id"
                type="text"
                value={inaturalistClientId}
                saved={inaturalistClientIdSaved}
                emptyPlaceholder={$_('settings.integrations.inaturalist.client_id_placeholder')}
                ariaLabel={$_('settings.integrations.inaturalist.client_id_label')}
                oninput={(v) => (inaturalistClientId = v)}
            />
        </SettingsRow>

        <SettingsRow
            labelId="setting-inat-client-secret"
            label={$_('settings.integrations.inaturalist.client_secret')}
            layout="stacked"
        >
            <SecretInput
                id="inat-client-secret"
                value={inaturalistClientSecret}
                saved={inaturalistClientSecretSaved}
                emptyPlaceholder={$_('settings.integrations.inaturalist.client_secret_placeholder')}
                ariaLabel={$_('settings.integrations.inaturalist.client_secret_label')}
                oninput={(v) => (inaturalistClientSecret = v)}
            />
        </SettingsRow>

        <div class="border-t border-line-soft pt-4 space-y-3">
            <p class="text-xs text-slate-700 dark:text-slate-200">{$_('settings.integrations.inaturalist.oauth_desc')}</p>
            <p class="text-xs text-slate-600 dark:text-slate-400 font-semibold">{$_('settings.integrations.inaturalist.app_owner_note')}</p>
            <div class="flex flex-wrap gap-2">
                <button
                    type="button"
                    onclick={connectInaturalist}
                    aria-label={$_('settings.integrations.inaturalist.connect_label')}
                    disabled={inatConnecting || inatRefreshing || inatDisconnecting}
                    class="flex-1 min-w-[150px] {buttonPrimaryClass}"
                >
                    {inatConnecting ? $_('common.testing') : $_('settings.integrations.inaturalist.connect')}
                </button>
                <button
                    type="button"
                    onclick={async () => {
                        try {
                            inatRefreshing = true;
                            await refreshInaturalistStatus();
                            onActionFeedback('success', $_('settings.integrations.inaturalist.refresh'));
                        } catch (error) {
                            onActionFeedback('error', actionErrorMessage(error));
                        } finally {
                            inatRefreshing = false;
                        }
                    }}
                    aria-label={$_('settings.integrations.inaturalist.refresh_label')}
                    disabled={inatRefreshing || inatConnecting || inatDisconnecting}
                    class="flex-1 min-w-[150px] {buttonSecondaryClass}"
                >
                    {inatRefreshing ? $_('common.testing') : $_('settings.integrations.inaturalist.refresh')}
                </button>
            </div>
            {#if inaturalistConnectedUser}
                <div class="flex items-center justify-between gap-2 p-3 bg-success-50 dark:bg-success-900/20 rounded-xl">
                    <span class="text-sm text-success-700 dark:text-success-300">{$_('settings.integrations.inaturalist.connected', { values: { user: inaturalistConnectedUser } })}</span>
                    <button
                        type="button"
                        onclick={async () => {
                            try {
                                inatDisconnecting = true;
                                await disconnectInaturalistOAuth();
                                await refreshInaturalistStatus();
                                onActionFeedback('success', $_('settings.integrations.inaturalist.disconnect'));
                            } catch (error) {
                                onActionFeedback('error', actionErrorMessage(error));
                            } finally {
                                inatDisconnecting = false;
                            }
                        }}
                        aria-label={$_('settings.integrations.inaturalist.disconnect_label')}
                        disabled={inatDisconnecting}
                        class="text-xs text-rose-700 dark:text-rose-400 hover:underline"
                    >
                        {inatDisconnecting ? $_('common.testing') : $_('settings.integrations.inaturalist.disconnect')}
                    </button>
                </div>
            {/if}
        </div>

        <AdvancedSection
            id="integrations-inat-advanced"
            title={$_('settings.integrations.inaturalist.advanced_title', { default: 'Default location' })}
        >
            <div class="space-y-4">
                <SettingsRow
                    labelId="setting-inat-lat"
                    label={$_('settings.integrations.inaturalist.default_latitude')}
                    layout="stacked"
                >
                    <SettingsInput
                        id="inat-lat"
                        field="inaturalist_default_latitude"
                        type="number"
                        step={0.0001}
                        value={inaturalistDefaultLat ?? ''}
                        ariaLabel={$_('settings.integrations.inaturalist.default_latitude_label')}
                        placeholder={inatLatPlaceholder}
                        oninput={(v) => { inaturalistDefaultLat = v === '' ? null : Number(v); }}
                    />
                </SettingsRow>
                <SettingsRow
                    labelId="setting-inat-lon"
                    label={$_('settings.integrations.inaturalist.default_longitude')}
                    layout="stacked"
                >
                    <SettingsInput
                        id="inat-lon"
                        field="inaturalist_default_longitude"
                        type="number"
                        step={0.0001}
                        value={inaturalistDefaultLon ?? ''}
                        ariaLabel={$_('settings.integrations.inaturalist.default_longitude_label')}
                        placeholder={inatLonPlaceholder}
                        oninput={(v) => { inaturalistDefaultLon = v === '' ? null : Number(v); }}
                    />
                </SettingsRow>
            </div>
            <SettingsRow
                labelId="setting-inat-place"
                label={$_('settings.integrations.inaturalist.default_place_guess')}
                layout="stacked"
            >
                <SettingsInput
                    id="inat-place"
                    field="inaturalist_default_place_guess"
                    type="text"
                    value={inaturalistDefaultPlace}
                    placeholder={$_('settings.integrations.inaturalist.default_place_guess_placeholder')}
                    ariaLabel={$_('settings.integrations.inaturalist.default_place_guess_label')}
                    oninput={(v) => { inaturalistDefaultPlace = v; }}
                />
            </SettingsRow>
        </AdvancedSection>
        {/if}
    </SettingsCard>

    <SettingsCard title={$_('settings.integrations.ebird.title')} description={$_('settings.integrations.ebird.toggle_label')} titleId="integration-ebird-title">
        <!-- The card's own switch, named by its title, so the title is not repeated as a row below it. -->
        {#snippet actions()}
            <SettingsToggle
                checked={ebirdEnabled}
                labelledBy="integration-ebird-title"
                srLabel={$_('settings.integrations.ebird.title')}
                onchange={(v) => (ebirdEnabled = v)}
            />
        {/snippet}

        {#if ebirdEnabled}
        <SettingsRow
            labelId="setting-ebird-api-key"
            label={$_('settings.integrations.ebird.api_key')}
            description={$_('settings.integrations.ebird.api_key_desc')}
            layout="stacked"
        >
            <SecretInput
                id="ebird-api-key"
                value={ebirdApiKey}
                saved={ebirdApiKeySaved}
                emptyPlaceholder={$_('settings.integrations.ebird.api_key_placeholder')}
                ariaLabel={$_('settings.integrations.ebird.api_key_label')}
                oninput={(v) => (ebirdApiKey = v)}
            />
        </SettingsRow>

        <SettingsRow
            labelId="setting-ebird-export-mode"
            label={$_('settings.integrations.ebird.export_everything')}
            description={$_('settings.integrations.ebird.export_everything_help')}
        >
            <SettingsToggle
                checked={ebirdExportEverything}
                labelledBy="setting-ebird-export-mode"
                srLabel={$_('settings.integrations.ebird.export_everything_label')}
                onchange={(v) => setEbirdExportEverything(v)}
            />
        </SettingsRow>

        <div class="space-y-4">
            <SettingsRow
                labelId="setting-ebird-export-from"
                label={$_('settings.integrations.ebird.export_from')}
                layout="stacked"
            >
                <input
                    id="ebird-export-from"
                    type="date"
                    bind:value={ebirdExportFrom}
                    disabled={ebirdExportEverything}
                    aria-label={$_('settings.integrations.ebird.export_from_label')}
                    class="input-base w-full disabled:cursor-not-allowed disabled:opacity-50"
                />
            </SettingsRow>
            <SettingsRow
                labelId="setting-ebird-export-to"
                label={$_('settings.integrations.ebird.export_to')}
                layout="stacked"
            >
                <input
                    id="ebird-export-to"
                    type="date"
                    bind:value={ebirdExportTo}
                    disabled={ebirdExportEverything}
                    aria-label={$_('settings.integrations.ebird.export_to_label')}
                    class="input-base w-full disabled:cursor-not-allowed disabled:opacity-50"
                />
            </SettingsRow>
        </div>
        <p class="text-xs text-slate-600 dark:text-slate-400 ">{$_('settings.integrations.ebird.export_range_help')}</p>
        {#if ebirdExportRangeError}
            <p class="text-xs text-rose-700 dark:text-rose-300 font-bold">{ebirdExportRangeError}</p>
        {/if}
        <button
            type="button"
            onclick={async () => {
                try {
                    exportingEbirdCsv = true;
                    await exportEbirdCsv({
                        from: ebirdExportEverything ? undefined : ebirdExportFrom || undefined,
                        to: ebirdExportEverything ? undefined : ebirdExportTo || undefined
                    });
                    onActionFeedback('success', $_('settings.integrations.ebird.export_csv'));
                } catch (e) {
                    onActionFeedback('error', $_('settings.integrations.ebird.export_csv_error'));
                } finally {
                    exportingEbirdCsv = false;
                }
            }}
            disabled={exportingEbirdCsv || !!ebirdExportRangeError}
            class="w-full sm:w-auto {buttonPrimaryClass}"
        >
            {exportingEbirdCsv ? $_('common.testing') : $_('settings.integrations.ebird.export_csv')}
        </button>
        <p class="text-xs text-slate-600 dark:text-slate-400 text-center">{$_('settings.integrations.ebird.export_csv_desc')}</p>

        <AdvancedSection
            id="integrations-ebird-advanced"
            title={$_('settings.integrations.ebird.advanced_title', { default: 'Hotspot search defaults' })}
        >
            <div class="space-y-4">
                <SettingsRow
                    labelId="setting-ebird-radius"
                    label={$_('settings.integrations.ebird.radius', {
                        values: { unit: ebirdRadiusUnitLabel }
                    })}
                    description={ebirdRadiusHelp}
                    layout="stacked"
                >
                    <SettingsInput
                        id="ebird-radius"
                        field="ebird_default_radius_km"
                        type="number"
                        min={ebirdRadiusBounds.min}
                        max={ebirdRadiusBounds.max}
                        value={ebirdRadiusDisplayValue}
                        ariaLabel={$_('settings.integrations.ebird.radius', {
                            values: { unit: ebirdRadiusUnitLabel }
                        })}
                        oninput={(v) => updateEbirdRadius(v)}
                    />
                </SettingsRow>
                <SettingsRow
                    labelId="setting-ebird-days"
                    label={$_('settings.integrations.ebird.days_back')}
                    layout="stacked"
                >
                    <SettingsInput
                        id="ebird-days"
                        field="ebird_default_days_back"
                        type="number"
                        min={1}
                        max={30}
                        value={ebirdDefaultDaysBack}
                        ariaLabel={$_('settings.integrations.ebird.days_back')}
                        oninput={(v) => (ebirdDefaultDaysBack = Number(v) || 0)}
                    />
                </SettingsRow>
                <SettingsRow
                    labelId="setting-ebird-max-results"
                    label={$_('settings.integrations.ebird.max_results')}
                    layout="stacked"
                >
                    <SettingsInput
                        id="ebird-max-results"
                        field="ebird_max_results"
                        type="number"
                        min={1}
                        max={200}
                        value={ebirdMaxResults}
                        ariaLabel={$_('settings.integrations.ebird.max_results')}
                        oninput={(v) => (ebirdMaxResults = Number(v) || 0)}
                    />
                </SettingsRow>
                <SettingsRow
                    labelId="setting-ebird-locale"
                    label={$_('settings.integrations.ebird.locale')}
                    layout="stacked"
                >
                    <SettingsInput
                        id="ebird-locale"
                        field="ebird_locale"
                        type="text"
                        value={ebirdLocale}
                        ariaLabel={$_('settings.integrations.ebird.locale')}
                        oninput={(v) => (ebirdLocale = v)}
                    />
                </SettingsRow>
            </div>
        </AdvancedSection>
        {/if}
    </SettingsCard>

    <SettingsCard title={$_('settings.integrations.birdweather.title')} description={$_('settings.integrations.birdweather.toggle_label')} titleId="integration-birdweather-title">
        <!-- The card's own switch, named by its title, so the title is not repeated as a row below it. -->
        {#snippet actions()}
            <SettingsToggle
                checked={birdweatherEnabled}
                labelledBy="integration-birdweather-title"
                srLabel={$_('settings.integrations.birdweather.title')}
                onchange={(v) => (birdweatherEnabled = v)}
            />
        {/snippet}

        {#if birdweatherEnabled}
        <SettingsRow
            labelId="setting-birdweather-token"
            label={$_('settings.integrations.birdweather.token')}
            description={$_('settings.integrations.birdweather.token_desc')}
            layout="stacked"
        >
            <SecretInput
                id="birdweather-token"
                value={birdweatherStationToken}
                saved={birdweatherStationTokenSaved}
                emptyPlaceholder={$_('settings.integrations.birdweather.token_placeholder')}
                ariaLabel={$_('settings.integrations.birdweather.token_label')}
                oninput={(v) => (birdweatherStationToken = v)}
            />
        </SettingsRow>

        <button
            type="button"
            onclick={runBirdWeatherDiagnostic}
            disabled={bwRunning || (!birdweatherStationToken && !birdweatherStationTokenSaved)}
            aria-label={$_('settings.integrations.birdweather.test_button')}
            class="w-full sm:w-auto {buttonPrimaryClass}"
        >
            {bwRunning ? $_('settings.integrations.birdweather.test_loading') : $_('settings.integrations.birdweather.test_button')}
        </button>
        {/if}
    </SettingsCard>

    <SettingsCard title={$_('settings.integrations.ha_weather.title', { default: 'Home Assistant weather' })} description={$_('settings.integrations.ha_weather.toggle_label', { default: 'Record the weather from your own sensors instead of the forecast API. A sensor that cannot answer reads as unknown, never as a forecast.' })} titleId="integration-ha-weather-title">
        <!-- The card's own switch, named by its title, so the title is not repeated as a row below it. -->
        {#snippet actions()}
            <SettingsToggle
                checked={haWeatherEnabled}
                labelledBy="integration-ha-weather-title"
                srLabel={$_('settings.integrations.ha_weather.title', { default: 'Home Assistant weather' })}
                onchange={(v) => (haWeatherEnabled = v)}
            />
        {/snippet}

        {#if haWeatherEnabled}
        <SettingsRow
            labelId="setting-ha-weather-url"
            label={$_('settings.integrations.ha_weather.base_url', { default: 'Home Assistant URL' })}
            description={$_('settings.integrations.ha_weather.base_url_desc', { default: 'The address this server can reach, e.g. http://homeassistant.local:8123' })}
            layout="stacked"
        >
            <SettingsInput
                id="ha-weather-url"
                field="ha_weather_base_url"
                type="text"
                value={haWeatherBaseUrl}
                ariaLabel={$_('settings.integrations.ha_weather.base_url', { default: 'Home Assistant URL' })}
                oninput={(v) => (haWeatherBaseUrl = v)}
            />
        </SettingsRow>
        <SettingsRow
            labelId="setting-ha-weather-token"
            label={$_('settings.integrations.ha_weather.token', { default: 'Long-lived access token' })}
            description={$_('settings.integrations.ha_weather.token_desc', { default: 'Created in Home Assistant under your profile, Security, Long-lived access tokens.' })}
            layout="stacked"
        >
            <SecretInput
                id="ha-weather-token"
                value={haWeatherAccessToken}
                saved={haWeatherAccessTokenSaved}
                emptyPlaceholder={$_('settings.integrations.ha_weather.token_placeholder', { default: 'Paste a long-lived access token' })}
                ariaLabel={$_('settings.integrations.ha_weather.token', { default: 'Long-lived access token' })}
                oninput={(v) => (haWeatherAccessToken = v)}
            />
        </SettingsRow>
        <SettingsRow
            labelId="setting-ha-weather-entity"
            label={$_('settings.integrations.ha_weather.entity', { default: 'Weather entity' })}
            description={$_('settings.integrations.ha_weather.entity_desc', { default: 'The general source, e.g. weather.home. Leave empty to rely on sensor overrides alone.' })}
            layout="stacked"
        >
            <SettingsInput
                id="ha-weather-entity"
                field="ha_weather_entity"
                type="text"
                value={haWeatherEntity}
                ariaLabel={$_('settings.integrations.ha_weather.entity', { default: 'Weather entity' })}
                oninput={(v) => (haWeatherEntity = v)}
            />
        </SettingsRow>

        <SettingsRow
            labelId="setting-ha-weather-illuminance"
            label={$_('settings.integrations.ha_weather.illuminance', { default: 'Illuminance entity' })}
            description={$_('settings.integrations.ha_weather.illuminance_desc', { default: 'Optional. A light sensor that reports lx, e.g. sensor.feeder_illuminance. Its reading is stored with each new detection. When it cannot answer, no light level is stored.' })}
            descriptionId="setting-ha-weather-illuminance-desc"
            layout="stacked"
        >
            <SettingsInput
                id="ha-weather-illuminance"
                field="ha_weather_illuminance_entity"
                type="text"
                value={haWeatherIlluminanceEntity}
                ariaLabel={$_('settings.integrations.ha_weather.illuminance', { default: 'Illuminance entity' })}
                describedBy={illuminanceEntityInvalid ? 'ha-weather-illuminance-error setting-ha-weather-illuminance-desc' : 'setting-ha-weather-illuminance-desc'}
                invalid={illuminanceEntityInvalid}
                oninput={(v) => (haWeatherIlluminanceEntity = v)}
            />
            {#if illuminanceEntityInvalid}
                <p id="ha-weather-illuminance-error" class="mt-2 text-xs font-semibold text-rose-700 dark:text-rose-300">
                    {$_('settings.integrations.ha_weather.illuminance_invalid', { default: 'This is not an entity id. Use the id Home Assistant shows for the sensor, such as sensor.feeder_illuminance.' })}
                </p>
            {/if}
        </SettingsRow>

        <AdvancedSection
            title={$_('settings.integrations.ha_weather.overrides', { default: 'Per-reading sensor overrides' })}
            description={$_('settings.integrations.ha_weather.overrides_desc', { default: 'A sensor named here outranks the weather entity for its one reading. When it cannot answer, that reading is unknown.' })}
        >
            <div class="space-y-3">
                {#each [
                    { id: 'temperature', label: $_('settings.integrations.ha_weather.override_temperature', { default: 'Temperature sensor' }), get: () => haWeatherTemperatureEntity, set: (v: string) => (haWeatherTemperatureEntity = v) },
                    { id: 'wind-speed', label: $_('settings.integrations.ha_weather.override_wind_speed', { default: 'Wind speed sensor' }), get: () => haWeatherWindSpeedEntity, set: (v: string) => (haWeatherWindSpeedEntity = v) },
                    { id: 'wind-direction', label: $_('settings.integrations.ha_weather.override_wind_direction', { default: 'Wind direction sensor' }), get: () => haWeatherWindDirectionEntity, set: (v: string) => (haWeatherWindDirectionEntity = v) },
                    { id: 'cloud-cover', label: $_('settings.integrations.ha_weather.override_cloud_cover', { default: 'Cloud cover sensor' }), get: () => haWeatherCloudCoverEntity, set: (v: string) => (haWeatherCloudCoverEntity = v) },
                    { id: 'precipitation', label: $_('settings.integrations.ha_weather.override_precipitation', { default: 'Precipitation sensor' }), get: () => haWeatherPrecipitationEntity, set: (v: string) => (haWeatherPrecipitationEntity = v) },
                    { id: 'rain', label: $_('settings.integrations.ha_weather.override_rain', { default: 'Rain sensor' }), get: () => haWeatherRainEntity, set: (v: string) => (haWeatherRainEntity = v) },
                    { id: 'snowfall', label: $_('settings.integrations.ha_weather.override_snowfall', { default: 'Snowfall sensor' }), get: () => haWeatherSnowfallEntity, set: (v: string) => (haWeatherSnowfallEntity = v) }
                ] as override (override.id)}
                    <SettingsRow labelId={'setting-ha-weather-' + override.id} label={override.label} layout="stacked">
                        <SettingsInput
                            id={'ha-weather-' + override.id}
                            type="text"
                            value={override.get()}
                            ariaLabel={override.label}
                            oninput={override.set}
                        />
                    </SettingsRow>
                {/each}
            </div>
        </AdvancedSection>

        <button
            type="button"
            onclick={runHaWeatherDiagnostic}
            disabled={hawRunning || !haWeatherBaseUrl || (!haWeatherAccessToken && !haWeatherAccessTokenSaved)}
            aria-label={$_('settings.integrations.ha_weather.test_button', { default: 'Fetch a live reading' })}
            class="w-full sm:w-auto {buttonPrimaryClass}"
        >
            {hawRunning ? $_('settings.integrations.ha_weather.test_loading', { default: 'Fetching…' }) : $_('settings.integrations.ha_weather.test_button', { default: 'Fetch a live reading' })}
        </button>
        {/if}
    </SettingsCard>

    <div>
        <SettingsCard
            title={$_('settings.location.title')}
            description={$_('settings.location.desc')}
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
                    <span class="text-sm font-semibold text-slate-700 shrink-0 dark:text-slate-200">{$_('settings.location.resolved_label', { default: 'Resolved' })}</span>
                    {#if geocodeLoading}
                        <span class="text-slate-600 dark:text-slate-400 ">{$_('settings.location.resolving', { default: 'Looking up…' })}</span>
                    {:else if geocodeError}
                        <span class="text-rose-700 dark:text-rose-300 font-bold">{$_('settings.location.resolve_error', { default: 'Lookup failed' })}</span>
                    {:else if geocodePlace}
                        <span class="font-bold text-slate-700 dark:text-slate-200 truncate">{geocodePlace}</span>
                    {:else}
                        <span class="text-slate-600 dark:text-slate-400 ">{$_('settings.location.resolve_empty', { default: 'No place name available for these coordinates' })}</span>
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
                <div class="h-64 w-full rounded-2xl overflow-hidden border border-slate-200 dark:border-slate-700">
                    {#if mapPoint}
                        {#key `${mapPoint[0]},${mapPoint[1]}`}
                            <Map userLocation={mapPoint} center={mapPoint} zoom={11} />
                        {/key}
                    {:else}
                        <div class="w-full h-full flex items-center justify-center bg-slate-50 dark:bg-slate-900/40 text-xs font-bold text-slate-600 dark:text-slate-400 italic">
                            {$_('settings.location.map_empty', { default: 'No coordinates configured yet.' })}
                        </div>
                    {/if}
                </div>
            </SettingsRow>

            <SettingsRow
                labelId="setting-weather-units"
                label={$_('settings.location.weather_unit_system')}
                description={$_('settings.location.weather_unit_system_desc')}
                layout="stacked"
            >
                <SettingsSelect
                    id="weather-unit-system"
                    value={locationWeatherUnitSystem}
                    ariaLabel={$_('settings.location.weather_unit_system')}
                    options={[
                        { value: 'metric', label: $_('settings.location.metric') },
                        { value: 'imperial', label: $_('settings.location.imperial') },
                        { value: 'british', label: $_('settings.location.british') }
                    ]}
                    onchange={(v) => (locationWeatherUnitSystem = v as 'metric' | 'imperial' | 'british')}
                />
            </SettingsRow>
        </SettingsCard>
    </div>
</div>

{#if bwTestOpen}
    <DiagnosticDialog
        title={$_('settings.integrations.birdweather.test_title', { default: 'BirdWeather connection test' })}
        subtitle={$_('settings.integrations.birdweather.test_subtitle', { default: 'Checks that your station token is accepted by BirdWeather.' })}
        stages={bwStages}
        busy={bwRunning}
        result={bwResult}
        runId={bwRunId}
        retryLabel={$_('settings.integrations.birdweather.test_button')}
        onClose={() => (bwTestOpen = false)}
        onRetry={runBirdWeatherDiagnostic}
    />
{/if}

{#if hawTestOpen}
    <DiagnosticDialog
        title={$_('settings.integrations.ha_weather.test_title', { default: 'Home Assistant weather test' })}
        subtitle={$_('settings.integrations.ha_weather.test_subtitle', { default: 'Fetches the current readings your detections would record.' })}
        stages={hawStages}
        busy={hawRunning}
        result={hawResult}
        runId={hawRunId}
        retryLabel={$_('settings.integrations.ha_weather.test_button', { default: 'Fetch a live reading' })}
        onClose={() => (hawTestOpen = false)}
        onRetry={runHaWeatherDiagnostic}
    />
{/if}
