type WeatherUnitSystem = 'metric' | 'imperial' | 'british';

interface CurrentLocationSettings {
    latitude: number | null;
    longitude: number | null;
    state: string;
    country: string;
    automatic: boolean;
    weatherUnitSystem: WeatherUnitSystem;
}

interface StoredLocationSettings {
    location_latitude?: number | null;
    location_longitude?: number | null;
    location_state?: string | null;
    location_country?: string | null;
    location_automatic?: boolean;
    location_weather_unit_system?: string;
    location_temperature_unit?: string;
}

function normalizeText(value?: string | null): string {
    return value ?? '';
}

export function locationSettingsDirty(input: {
    current: CurrentLocationSettings;
    stored: StoredLocationSettings;
}): boolean {
    const { current, stored } = input;
    const storedWeatherUnitSystem =
        (stored.location_weather_unit_system as WeatherUnitSystem | undefined) ??
        (stored.location_temperature_unit === 'fahrenheit' ? 'imperial' : 'metric');

    return (
        current.latitude !== (stored.location_latitude ?? null) ||
        current.longitude !== (stored.location_longitude ?? null) ||
        current.state !== normalizeText(stored.location_state) ||
        current.country !== normalizeText(stored.location_country) ||
        current.automatic !== (stored.location_automatic ?? true) ||
        current.weatherUnitSystem !== storedWeatherUnitSystem
    );
}
