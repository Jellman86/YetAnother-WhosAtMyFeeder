import { getContext, setContext } from 'svelte';
import type { SettingsFieldError } from './field-errors';

const FIELD_ERRORS = Symbol('settings-field-errors');

/** Reads the standing refusal for a saved field, so the input that holds it can show it. */
export interface SettingsFieldErrorLookup {
    errorFor(field: string): SettingsFieldError | undefined;
}

/** Settings provides the lookup once; every input below it can then mark its own field. */
export function provideSettingsFieldErrors(lookup: SettingsFieldErrorLookup): void {
    setContext(FIELD_ERRORS, lookup);
}

export function settingsFieldErrorLookup(): SettingsFieldErrorLookup | undefined {
    return getContext<SettingsFieldErrorLookup | undefined>(FIELD_ERRORS);
}
