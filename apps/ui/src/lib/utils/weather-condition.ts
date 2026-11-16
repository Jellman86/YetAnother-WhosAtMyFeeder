/**
 * The weather a visit was recorded in is stored as the backend's English condition text
 * ("Rain", "Partly cloudy"). The vocabulary is closed, so each text maps to a message the page
 * translates; anything else is printed as stored rather than dropped.
 */
const CONDITION_KEYS: Readonly<Record<string, string>> = {
    'clear sky': 'clear_sky',
    clear: 'clear_sky',
    'partly cloudy': 'partly_cloudy',
    foggy: 'foggy',
    drizzle: 'drizzle',
    rain: 'rain',
    snow: 'snow',
    'rain showers': 'rain_showers',
    thunderstorm: 'thunderstorm',
    cloudy: 'cloudy',
    // Home Assistant's weather entity adds these three.
    hail: 'hail',
    windy: 'windy',
    exceptional: 'exceptional'
};

const CONDITION_DEFAULTS: Readonly<Record<string, string>> = {
    clear_sky: 'Clear sky',
    partly_cloudy: 'Partly cloudy',
    foggy: 'Foggy',
    drizzle: 'Drizzle',
    rain: 'Rain',
    snow: 'Snow',
    rain_showers: 'Rain showers',
    thunderstorm: 'Thunderstorm',
    cloudy: 'Cloudy',
    hail: 'Hail',
    windy: 'Windy',
    exceptional: 'Exceptional'
};

export interface WeatherConditionMessage {
    /** Null when the stored text is outside the known vocabulary; print `default` as it is. */
    key: string | null;
    default: string;
}

export function weatherConditionMessage(condition: string | null | undefined): WeatherConditionMessage | null {
    const stored = (condition ?? '').trim();
    // "Unknown" is the backend's word for no reading, and an unmeasured condition is left unsaid.
    if (!stored || stored.toLowerCase() === 'unknown') return null;
    const name = CONDITION_KEYS[stored.toLowerCase()];
    if (!name) return { key: null, default: stored };
    return { key: `common.weather_condition.${name}`, default: CONDITION_DEFAULTS[name] };
}

const COMPASS_POINTS = ['n', 'ne', 'e', 'se', 's', 'sw', 'w', 'nw'] as const;
export type CompassPoint = (typeof COMPASS_POINTS)[number];

/** The nearest of eight compass points to a bearing in degrees, as the suffix of `common.compass.*`. */
export function compassPointKey(degrees: number | null | undefined): CompassPoint | null {
    if (degrees === null || degrees === undefined || !Number.isFinite(degrees)) return null;
    const turned = ((degrees % 360) + 360) % 360;
    return COMPASS_POINTS[Math.round(turned / 45) % 8];
}
