<script lang="ts">
    import { _ } from 'svelte-i18n';
    import SecretInput from './_primitives/SecretInput.svelte';
    import SettingsCard from './_primitives/SettingsCard.svelte';
    import SettingsRow from './_primitives/SettingsRow.svelte';
    import SettingsToggle from './_primitives/SettingsToggle.svelte';
    import SettingsInput from './_primitives/SettingsInput.svelte';
    import AdvancedSection from './_primitives/AdvancedSection.svelte';
    import DiagnosticDialog from '../DiagnosticDialog.svelte';
    import { runSequentialDiagnostic, type DiagnosticStage, type DiagnosticResult, type DiagnosticStep } from '../../utils/diagnostic-runner';
    import { illuminanceStepOutcome, isHomeAssistantEntityId, type IlluminanceStepText } from '../../utils/illuminance';
    import { testHaWeather } from '../../api/maintenance';

    // Home Assistant weather: the readings recorded with each visit, from the owner's own sensors.
    let {
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
        haWeatherIlluminanceEntity = $bindable('')
    }: {
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
    } = $props();

    // The test uses the shared DiagnosticDialog (docs/standards/diagnostics-and-dialogs.md): each
    // stage runs a real check and reports its own outcome.
    let hawTestOpen = $state(false);
    let hawRunning = $state(false);
    let hawStages = $state<DiagnosticStage[]>([]);
    let hawResult = $state<DiagnosticResult | null>(null);
    let hawRunId = $state(0);

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
                unavailable: (values) => $_('settings.integrations.ha_weather.illuminance_unavailable', { values, default: '{entity} is unknown or unavailable in Home Assistant right now. Visits record no light level until it answers.' }),
                not_numeric: (values) => $_('settings.integrations.ha_weather.illuminance_not_numeric', { values, default: '{entity} did not report a number, so no light level is recorded.' }),
                out_of_range: (values) => $_('settings.integrations.ha_weather.illuminance_out_of_range', { values, default: '{entity} reported a value outside 0 to 200,000 lx, so it is not recorded.' })
            },
            noAnswer: $_('settings.integrations.ha_weather.illuminance_no_answer', { default: 'The test returned no light reading.' })
        };
    }
</script>

    <SettingsCard id="settings-group-integrations-ha-weather" nested title={$_('settings.integrations.ha_weather.title', { default: 'Home Assistant weather' })} description={$_('settings.integrations.ha_weather.toggle_label', { default: 'Record the weather from your own sensors instead of the forecast API. A sensor that cannot answer reads as unknown, never as a forecast.' })} titleId="integration-ha-weather-title">
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
            description={$_('settings.integrations.ha_weather.illuminance_desc', { default: 'Optional. A light sensor that reports lx, e.g. sensor.feeder_illuminance. Its reading is stored with each new visit. When it cannot answer, no light level is stored.' })}
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
                <p id="ha-weather-illuminance-error" class="mt-2 text-xs font-semibold text-status-fail">
                    {$_('settings.integrations.ha_weather.illuminance_invalid', { default: 'This is not an entity id. Use the id Home Assistant shows for the sensor, such as sensor.feeder_illuminance.' })}
                </p>
            {/if}
        </SettingsRow>

        <AdvancedSection
            id="integrations-ha-weather-overrides"
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
            class="btn btn-primary min-h-11 w-full px-4 py-3 sm:w-auto"
        >
            {hawRunning ? $_('settings.integrations.ha_weather.test_loading', { default: 'Fetching…' }) : $_('settings.integrations.ha_weather.test_button', { default: 'Fetch a live reading' })}
        </button>
        {/if}
    </SettingsCard>

{#if hawTestOpen}
    <DiagnosticDialog
        title={$_('settings.integrations.ha_weather.test_title', { default: 'Home Assistant weather test' })}
        subtitle={$_('settings.integrations.ha_weather.test_subtitle', { default: 'Fetches the current readings that would be stored with a visit.' })}
        stages={hawStages}
        busy={hawRunning}
        result={hawResult}
        runId={hawRunId}
        retryLabel={$_('settings.integrations.ha_weather.test_button', { default: 'Fetch a live reading' })}
        onClose={() => (hawTestOpen = false)}
        onRetry={runHaWeatherDiagnostic}
    />
{/if}
