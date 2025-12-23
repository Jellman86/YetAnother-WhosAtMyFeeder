import { writable, derived } from 'svelte/store';

export type Theme = 'light' | 'dark' | 'system';

function getIsDark(theme: Theme): boolean {
    if (typeof window === 'undefined') return false;
    return theme === 'dark' ||
        (theme === 'system' && window.matchMedia('(prefers-color-scheme: dark)').matches);
}

function applyTheme(theme: Theme) {
    if (typeof document === 'undefined') return;
    const isDark = getIsDark(theme);
    document.documentElement.classList.toggle('dark', isDark);
}

function createThemeStore() {
    const stored = (typeof localStorage !== 'undefined'
        ? localStorage.getItem('theme') as Theme | null
        : null) || 'system';

    const { subscribe, set, update } = writable<Theme>(stored);

    return {
        subscribe,
        set: (value: Theme) => {
            if (typeof localStorage !== 'undefined') {
                localStorage.setItem('theme', value);
            }
            set(value);
            applyTheme(value);
        },
        toggle: () => {
            update(current => {
                // Toggle based on current visual state, not preference
                const currentlyDark = getIsDark(current);
                const newTheme: Theme = currentlyDark ? 'light' : 'dark';
                if (typeof localStorage !== 'undefined') {
                    localStorage.setItem('theme', newTheme);
                }
                applyTheme(newTheme);
                return newTheme;
            });
        },
        init: () => {
            applyTheme(stored);
            // Listen for system preference changes
            if (typeof window !== 'undefined') {
                window.matchMedia('(prefers-color-scheme: dark)').addEventListener('change', (e) => {
                    update(current => {
                        if (current === 'system') {
                            applyTheme('system');
                        }
                        return current;
                    });
                });
            }
        }
    };
}

export const theme = createThemeStore();

// Derived store that tells us if dark mode is currently active
export const isDark = derived(theme, ($theme) => getIsDark($theme));