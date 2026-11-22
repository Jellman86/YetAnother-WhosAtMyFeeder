/**
 * What an integration's group says about itself, in words. YA-WAMF keeps no test result and measures
 * none of these services in the background, so the line never says "connected": it says whether the
 * service is on, what it still needs, and what the last test on this visit found.
 */
export interface ServiceTest {
    passed: boolean;
    /** The reason the test gave when it failed. */
    message: string;
    /** Milliseconds since the epoch, when the test finished. */
    at: number;
    /** The values the test ran with, so an edit after it retires the result. */
    signature: string;
}

export type ServiceState =
    | { kind: 'off' }
    | { kind: 'not_set_up'; missing: string }
    | { kind: 'not_tested' }
    | { kind: 'no_test' }
    | { kind: 'passed'; at: number }
    | { kind: 'failed'; at: number; reason: string };

export interface ServiceReading {
    enabled: boolean;
    /** What the service still needs before it can work, already worded; null when nothing is missing. */
    missing: string | null;
    /** The values a test would run with now. */
    signature: string;
    /** The last test on this visit; undefined for a service that has no test. */
    test?: ServiceTest | null;
}

/** The state a group shows. Off wins, then what is missing, then a test that still describes the page. */
export function serviceState({ enabled, missing, signature, test }: ServiceReading): ServiceState {
    if (!enabled) return { kind: 'off' };
    if (missing) return { kind: 'not_set_up', missing };
    if (test === undefined) return { kind: 'no_test' };
    if (!test || test.signature !== signature) return { kind: 'not_tested' };
    return test.passed ? { kind: 'passed', at: test.at } : { kind: 'failed', at: test.at, reason: test.message };
}

type Translate = (key: string, options?: { values?: Record<string, string>; default?: string }) => string;

/** The state as a sentence. `time` words a moment the way the page words times. */
export function serviceStateText(state: ServiceState, translate: Translate, time: (at: number) => string): string {
    switch (state.kind) {
        case 'off':
            return translate('settings.integrations.state.off', { default: 'Off.' });
        case 'not_set_up':
            return translate('settings.integrations.state.not_set_up', { values: { missing: state.missing }, default: 'On, but not set up: {missing}.' });
        case 'no_test':
            return translate('settings.integrations.state.no_test', { default: 'On and set up. It has no connection test.' });
        case 'not_tested':
            return translate('settings.integrations.state.not_tested', { default: 'On and set up. Not tested yet; test results aren\u2019t kept between visits.' });
        case 'passed':
            return translate('settings.integrations.state.passed', { values: { time: time(state.at) }, default: 'On. The test passed at {time}.' });
        case 'failed':
            return translate('settings.integrations.state.failed', { values: { time: time(state.at), reason: state.reason }, default: 'On, but the test failed at {time}: {reason}' });
    }
}
