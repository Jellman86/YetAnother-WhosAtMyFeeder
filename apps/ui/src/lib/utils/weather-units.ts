import type { TemperatureUnit } from './temperature';

export type WeatherUnitSystem = 'metric' | 'imperial';

type UnitLabels = {
    metric: string;
    imperial: string;
};

const DEFAULT_WIND_LABELS: UnitLabels = {
    metric: 'km/h',
    imperial: 'mph'
};

const DEFAULT_PRECIP_LABELS: UnitLabels = {
    metric: 'mm',
    imperial: 'in'
};

export function resolveWeatherUnitSystem(
    weatherUnitSystem?: string | null,
    legacyTemperatureUnit?: string | null
): WeatherUnitSystem {
    const normalizedSystem = String(weatherUnitSystem ?? '').trim().toLowerCase();
    if (normalizedSystem === 'metric' || normalizedSystem === 'imperial') {
        return normalizedSystem;
    }

    const normalizedLegacy = String(legacyTemperatureUnit ?? '').trim().toLowerCase();
    if (normalizedLegacy === 'fahrenheit') {
        return 'imperial';
    }
    return 'metric';
}

export function getTemperatureUnitForSystem(system: WeatherUnitSystem): TemperatureUnit {
    return system === 'imperial' ? 'fahrenheit' : 'celsius';
}

export function convertWindSpeed(speedKmh: number | null | undefined, system: WeatherUnitSystem): number | null {
    if (speedKmh === null || speedKmh === undefined || Number.isNaN(speedKmh)) {
        return null;
    }
    return system === 'imperial' ? speedKmh / 1.609344 : speedKmh;
}

export function convertPrecipitation(valueMm: number | null | undefined, system: WeatherUnitSystem): number | null {
    if (valueMm === null || valueMm === undefined || Number.isNaN(valueMm)) {
        return null;
    }
    return system === 'imperial' ? valueMm / 25.4 : valueMm;
}

export function formatWindSpeed(
    speedKmh: number | null | undefined,
    system: WeatherUnitSystem,
    labels: UnitLabels = DEFAULT_WIND_LABELS
): string {
    const converted = convertWindSpeed(speedKmh, system);
    if (converted === null) {
        return '';
    }
    const label = system === 'imperial' ? labels.imperial : labels.metric;
    return `${Math.round(converted)} ${label}`;
}

export function formatPrecipitation(
    valueMm: number | null | undefined,
    system: WeatherUnitSystem,
    labels: UnitLabels = DEFAULT_PRECIP_LABELS
): string {
    const converted = convertPrecipitation(valueMm, system);
    if (converted === null) {
        return '';
    }
    const label = system === 'imperial' ? labels.imperial : labels.metric;
    if (system === 'imperial') {
        if (converted < 0.1) return `${converted.toFixed(2)}${label}`;
        return `${converted.toFixed(1)}${label}`;
    }
    if (converted < 0.1) return `${converted.toFixed(2)}${label}`;
    if (converted < 1) return `${converted.toFixed(1)}${label}`;
    return `${converted.toFixed(0)}${label}`;
}
