import { authStore } from '../stores/auth.svelte';
import { settingsStore } from '../stores/settings.svelte';
import { formatDistance, resolveWeatherUnitSystem } from './weather-units';

type Translate = (id: string, options: { default: string }) => string;

/**
 * A distance stored in kilometres, written in the units the owner chose.
 *
 * Reads the owner's settings, or the public unit choice a visitor is given, so a
 * caller inside `$derived` updates when either changes.
 */
export function displayDistance(valueKm: number, translate: Translate): string {
    const system = resolveWeatherUnitSystem(
        settingsStore.settings?.location_weather_unit_system ?? authStore.locationWeatherUnitSystem,
        settingsStore.settings?.location_temperature_unit ?? authStore.locationTemperatureUnit
    );
    return formatDistance(valueKm, system, {
        metric: translate('common.unit_km', { default: 'km' }),
        imperial: translate('common.unit_mi', { default: 'mi' })
    });
}
