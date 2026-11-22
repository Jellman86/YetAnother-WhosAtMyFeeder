/**
 * The integration tests run during this visit to Settings, one result per service. A section's
 * code is unmounted when another section opens, so a result kept in its card would be forgotten on
 * the way back and the card would then say it was never tested. Held here, it lasts until the page
 * is reloaded, as the status column's results do; nothing is stored.
 */
import { untrack } from 'svelte';
import type { ServiceTest } from './service-state';

type TestedService = 'birdnet' | 'ha_weather' | 'birdweather' | 'ai';

class ServiceTests {
    results = $state<Partial<Record<TestedService, ServiceTest>>>({});

    /** Keeps a finished test, with the values it ran with so a later edit retires it. */
    record(service: TestedService, result: { passed: boolean; message: string }, signature: string, at: number = Date.now()): void {
        this.results = { ...untrack(() => this.results), [service]: { ...result, at, signature } };
    }

    /** The last test of a service on this visit, or null. */
    last(service: TestedService): ServiceTest | null {
        return this.results[service] ?? null;
    }
}

export const serviceTests = new ServiceTests();
