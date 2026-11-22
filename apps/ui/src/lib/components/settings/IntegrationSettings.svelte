<script lang="ts">
    import { _ } from 'svelte-i18n';
    import SecretInput from './_primitives/SecretInput.svelte';
    import SettingsCard from './_primitives/SettingsCard.svelte';
    import SettingsRow from './_primitives/SettingsRow.svelte';
    import SettingsToggle from './_primitives/SettingsToggle.svelte';
    import SettingsInput from './_primitives/SettingsInput.svelte';
    import AdvancedSection from './_primitives/AdvancedSection.svelte';
    import DiagnosticDialog from '../DiagnosticDialog.svelte';
    import { serviceState, serviceStateText } from '../../settings/service-state';
    import { formatTime } from '../../utils/datetime';
    import { serviceTests } from '../../settings/service-tests.svelte';
    import { runSequentialDiagnostic, type DiagnosticStage, type DiagnosticResult } from '../../utils/diagnostic-runner';
    import { testBirdWeather } from '../../api/maintenance';
    import type { WeatherUnitSystem } from '../../utils/weather-units';
    import {
        ebirdRadiusFromDisplayValue,
        ebirdRadiusToDisplayValue,
        getEbirdRadiusBounds
    } from '../../utils/ebird-radius';

    let {
        birdweatherEnabled = $bindable(false),
        birdweatherStationToken = $bindable(''),
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
        locationLat = null,
        locationLon = null,
        prepareInaturalistOAuth,
        initiateInaturalistOAuth,
        disconnectInaturalistOAuth,
        refreshInaturalistStatus,
        exportEbirdCsv,
        birdweatherStationTokenSaved = $bindable(false),
        onActionFeedback = (_type: 'success' | 'error', _text: string) => {}
    }: {
        birdweatherEnabled: boolean;
        birdweatherStationToken: string;
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
        locationLat: number | null;
        locationLon: number | null;
        prepareInaturalistOAuth: () => Promise<void>;
        initiateInaturalistOAuth: () => Promise<{ authorization_url: string }>;
        disconnectInaturalistOAuth: () => Promise<{ status: string }>;
        refreshInaturalistStatus: () => Promise<void>;
        exportEbirdCsv: (range?: { from?: string; to?: string }) => Promise<void>;
        birdweatherStationTokenSaved: boolean;
        onActionFeedback: (type: 'success' | 'error', text: string) => void;
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
        serviceTests.record('birdweather', { passed: bwResult.ok, message: bwResult.message }, bwSignature);
    }

    // Each group's state in words. A test describes the values it ran with, so an edit retires it.
    // Kept for the visit, so the result is still here after another section was opened.
    const bwTest = $derived(serviceTests.last('birdweather'));
    const bwSignature = $derived(birdweatherStationToken);
    const stateText = (reading: Parameters<typeof serviceState>[0]): string => serviceStateText(serviceState(reading), $_, formatTime);
    const birdweatherState = $derived(stateText({
        enabled: birdweatherEnabled,
        missing: birdweatherStationToken || birdweatherStationTokenSaved ? null : $_('settings.integrations.state.needs_station_token', { default: 'add your station token' }),
        signature: bwSignature,
        test: bwTest
    }));
    const ebirdState = $derived(stateText({
        enabled: ebirdEnabled,
        missing: ebirdApiKey || ebirdApiKeySaved ? null : $_('settings.integrations.state.needs_api_key', { default: 'add an API key' }),
        signature: ''
    }));
    // iNaturalist's own measure is the account it is signed in to, which the server reports.
    const inaturalistState = $derived(
        inaturalistEnabled && inaturalistConnectedUser
            ? $_('settings.integrations.state.inaturalist_connected', { values: { user: inaturalistConnectedUser }, default: 'On, signed in as {user}.' })
            : stateText({
                enabled: inaturalistEnabled,
                missing: (inaturalistClientId || inaturalistClientIdSaved) && (inaturalistClientSecret || inaturalistClientSecretSaved)
                    ? $_('settings.integrations.state.needs_inaturalist_sign_in', { default: 'connect your iNaturalist account below' })
                    : $_('settings.integrations.state.needs_inaturalist_app', { default: 'add the application ID and secret' }),
                signature: ''
            })
    );

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

    const buttonPrimaryClass = 'btn btn-primary min-h-11 px-4 py-3';
    const buttonSecondaryClass = 'btn btn-secondary min-h-11 px-6 py-3';
</script>


<div class="space-y-8">
    <SettingsCard id="settings-group-integrations-inaturalist" title={$_('settings.integrations.inaturalist.title')} description={$_('settings.integrations.inaturalist.toggle_label')} status={inaturalistState} titleId="integration-inaturalist-title">
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
            <p class="text-xs text-ink">{$_('settings.integrations.inaturalist.oauth_desc')}</p>
            <p class="text-xs font-semibold text-muted">{$_('settings.integrations.inaturalist.app_owner_note')}</p>
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
                <div class="flex items-center justify-between gap-2 rounded-xl bg-status-ok-soft p-3">
                    <span class="text-sm text-status-ok">{$_('settings.integrations.inaturalist.connected', { values: { user: inaturalistConnectedUser } })}</span>
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
                        class="text-xs text-status-fail hover:underline"
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

    <SettingsCard id="settings-group-integrations-ebird" title={$_('settings.integrations.ebird.title')} description={$_('settings.integrations.ebird.toggle_label')} status={ebirdState} titleId="integration-ebird-title">
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
        <p class="text-xs text-muted">{$_('settings.integrations.ebird.export_range_help')}</p>
        {#if ebirdExportRangeError}
            <p class="text-xs text-status-fail">{ebirdExportRangeError}</p>
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
        <p class="text-center text-xs text-muted">{$_('settings.integrations.ebird.export_csv_desc')}</p>

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

    <SettingsCard id="settings-group-integrations-birdweather" title={$_('settings.integrations.birdweather.title')} description={$_('settings.integrations.birdweather.toggle_label')} status={birdweatherState} titleId="integration-birdweather-title">
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
