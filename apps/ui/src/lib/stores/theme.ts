import { writable } from 'svelte/store';

export type Theme = 'light' | 'dark' | 'system';

function createThemeStore() {
    const stored = localStorage.getItem('theme') as Theme | null;
    const { subscribe, set } = writable<Theme>(stored || 'system');

    return {
        subscribe,
        set: (value: Theme) => {
            localStorage.setItem('theme', value);
            set(value);
            applyTheme(value);
        },
        init: () => {
             applyTheme(stored || 'system');
        }
    };
}

function applyTheme(theme: Theme) {
    const isDark = theme === 'dark' ||
        (theme === 'system' && window.matchMedia('(prefers-color-scheme: dark)').matches);
    
    if (isDark) {
        document.documentElement.classList.add('dark');
    } else {
        document.documentElement.classList.remove('dark');
    }
}

export const theme = createThemeStore();