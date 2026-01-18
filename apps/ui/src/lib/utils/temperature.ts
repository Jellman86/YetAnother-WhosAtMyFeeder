/**
 * Temperature conversion utilities
 *
 * All temperatures are stored in Celsius in the database.
 * These functions handle conversion to user's preferred unit for display.
 */

export type TemperatureUnit = 'celsius' | 'fahrenheit';

/**
 * Convert Celsius to Fahrenheit
 */
export function celsiusToFahrenheit(celsius: number): number {
    return (celsius * 9/5) + 32;
}

/**
 * Format temperature for display with conversion if needed
 *
 * @param tempCelsius - Temperature in Celsius (as stored in database)
 * @param preferredUnit - User's preferred temperature unit
 * @returns Formatted temperature string with unit symbol
 */
export function formatTemperature(
    tempCelsius: number | null | undefined,
    preferredUnit: TemperatureUnit = 'celsius'
): string {
    if (tempCelsius === null || tempCelsius === undefined) {
        return '';
    }

    if (preferredUnit === 'fahrenheit') {
        const fahrenheit = celsiusToFahrenheit(tempCelsius);
        return `${fahrenheit.toFixed(1)}°F`;
    }

    return `${tempCelsius.toFixed(1)}°C`;
}

/**
 * Get temperature unit symbol
 */
export function getTemperatureSymbol(unit: TemperatureUnit): string {
    return unit === 'fahrenheit' ? '°F' : '°C';
}
