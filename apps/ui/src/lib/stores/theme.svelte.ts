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

class ThemeStore {
    currentTheme = $state<Theme>('system');
    private mediaQueryList: MediaQueryList | null = null;

    constructor() {
        // Initialize from localStorage
        if (typeof localStorage !== 'undefined') {
            const stored = localStorage.getItem('theme') as Theme | null;
            if (stored) {
                this.currentTheme = stored;
            }
        }

        // Apply theme immediately
        applyTheme(this.currentTheme);

        // Use $effect.root() to create effect context outside components
        $effect.root(() => {
            // Sync to localStorage on changes
            if (typeof localStorage !== 'undefined') {
                $effect(() => {
                    localStorage.setItem('theme', this.currentTheme);
                    applyTheme(this.currentTheme);
                });
            }

            // Listen for system preference changes
            if (typeof window !== 'undefined') {
                this.mediaQueryList = window.matchMedia('(prefers-color-scheme: dark)');

                const handleMediaChange = () => {
                    if (this.currentTheme === 'system') {
                        applyTheme('system');
                    }
                };

                this.mediaQueryList.addEventListener('change', handleMediaChange);

                // Cleanup
                $effect(() => {
                    return () => {
                        if (this.mediaQueryList) {
                            this.mediaQueryList.removeEventListener('change', handleMediaChange);
                        }
                    };
                });
            }
        });
    }

    get theme(): Theme {
        return this.currentTheme;
    }

    get isDark(): boolean {
        return getIsDark(this.currentTheme);
    }

    setTheme(value: Theme) {
        this.currentTheme = value;
    }

    toggle() {
        // Toggle based on current visual state, not preference
        const currentlyDark = getIsDark(this.currentTheme);
        this.currentTheme = currentlyDark ? 'light' : 'dark';
    }
}

// Singleton instance
export const themeStore = new ThemeStore();

// For backward compatibility with existing code
export const theme = {
    subscribe: (fn: (value: Theme) => void) => {
        return $effect.root(() => {
            $effect(() => {
                fn(themeStore.theme);
            });
            return () => {};
        });
    },
    set: (value: Theme) => themeStore.setTheme(value),
    toggle: () => themeStore.toggle(),
    init: () => {
        // No-op, initialization happens in constructor
    },
    cleanup: () => {
        // No-op, cleanup happens automatically via $effect
    }
};

export const isDark = {
    subscribe: (fn: (value: boolean) => void) => {
        return $effect.root(() => {
            $effect(() => {
                fn(themeStore.isDark);
            });
            return () => {};
        });
    }
};
