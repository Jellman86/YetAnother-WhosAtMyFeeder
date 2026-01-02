import { writable } from 'svelte/store';
import { fetchSettings, type Settings } from '../api';

function createSettingsStore() {
    const { subscribe, set } = writable<Settings | null>(null);

    return {
        subscribe,
        load: async () => {
            try {
                const s = await fetchSettings();
                set(s);
            } catch (e) {
                console.error('Failed to load settings store', e);
            }
        },
        set
    };
}

export const settingsStore = createSettingsStore();
