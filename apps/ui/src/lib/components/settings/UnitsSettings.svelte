<script lang="ts">
    import { _ } from 'svelte-i18n';
    import SettingsCard from './_primitives/SettingsCard.svelte';
    import SettingsRow from './_primitives/SettingsRow.svelte';
    import SettingsSelect from './_primitives/SettingsSelect.svelte';
    import type { WeatherUnitSystem } from '../../utils/weather-units';

    // One unit system for temperature, wind, rain and distances. It is saved with the settings, so
    // everyone who opens this install reads the same units.
    let { locationWeatherUnitSystem = $bindable<WeatherUnitSystem>('metric') }: { locationWeatherUnitSystem: WeatherUnitSystem } = $props();
</script>

<SettingsCard
    level={3}
    title={$_('settings.units.title', { default: 'Units' })}
    description={$_('settings.units.desc', { default: 'For everyone who opens this install, not only this device.' })}
>
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
            onchange={(v) => (locationWeatherUnitSystem = v as WeatherUnitSystem)}
        />
    </SettingsRow>
</SettingsCard>
