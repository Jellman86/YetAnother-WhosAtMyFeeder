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

/** The saved location fields the draft would change, named as the save sends them. */
export function locationChangedFields(input: {
    current: CurrentLocationSettings;
    stored: StoredLocationSettings;
}): string[] {
    const { current, stored } = input;
    const storedWeatherUnitSystem =
        (stored.location_weather_unit_system as WeatherUnitSystem | undefined) ??
        (stored.location_temperature_unit === 'fahrenheit' ? 'imperial' : 'metric');
    const comparisons: Array<[string, boolean]> = [
        ['location_latitude', current.latitude !== (stored.location_latitude ?? null)],
        ['location_longitude', current.longitude !== (stored.location_longitude ?? null)],
        ['location_state', current.state !== normalizeText(stored.location_state)],
        ['location_country', current.country !== normalizeText(stored.location_country)],
        ['location_automatic', current.automatic !== (stored.location_automatic ?? true)],
        ['location_weather_unit_system', current.weatherUnitSystem !== storedWeatherUnitSystem]
    ];
    return comparisons.filter(([, changed]) => changed).map(([field]) => field);
}
