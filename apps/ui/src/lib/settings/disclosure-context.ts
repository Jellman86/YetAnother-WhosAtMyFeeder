import { getContext, setContext } from 'svelte';

const DISCLOSURES = Symbol('settings-disclosures');

/**
 * Which closed cards and Advanced sections are open, held by the Settings page so it outlives a
 * tab being left and reopened, and so the page can open the ones holding a refused field.
 * `isOpen` is undefined for a disclosure nobody has opened or closed yet.
 */
export interface SettingsDisclosures {
    isOpen(id: string): boolean | undefined;
    setOpen(id: string, open: boolean): void;
}

export function provideSettingsDisclosures(disclosures: SettingsDisclosures): void {
    setContext(DISCLOSURES, disclosures);
}

export function settingsDisclosures(): SettingsDisclosures | undefined {
    return getContext<SettingsDisclosures | undefined>(DISCLOSURES);
}
