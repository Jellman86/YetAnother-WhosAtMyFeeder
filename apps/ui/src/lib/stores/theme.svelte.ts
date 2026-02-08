export type Theme = 'light' | 'dark' | 'system';
export type FontTheme = 'default' | 'clean' | 'studio' | 'classic' | 'compact';

function getIsDark(theme: Theme): boolean {
    if (typeof window === 'undefined') return false;
    return theme === 'dark' ||
        (theme === 'system' && window.matchMedia('(prefers-color-scheme: dark)').matches);
}

function syncThemeColorMeta() {
    if (typeof document === 'undefined') return;
    const meta = document.querySelector('meta[name="theme-color"]') as HTMLMetaElement | null;
    if (!meta) return;

    // Use the actual themed background so this also tracks high-contrast mode.
    const bg = getComputedStyle(document.documentElement).backgroundColor;
    if (bg) meta.content = bg;
}

function applyTheme(theme: Theme) {
    if (typeof document === 'undefined') return;
    const isDark = getIsDark(theme);
    document.documentElement.classList.toggle('dark', isDark);

    // After class changes apply, sync the browser UI color (mobile/PWA).
    requestAnimationFrame(syncThemeColorMeta);
}

function applyFontTheme(fontTheme: FontTheme) {
    if (typeof document === 'undefined') return;
    switch (fontTheme) {
        case 'clean':
            document.documentElement.style.setProperty('--font-body', "'Manrope', 'Segoe UI', system-ui, -apple-system, sans-serif");
            document.documentElement.style.setProperty('--font-display', "'Sora', 'Manrope', sans-serif");
            break;
        case 'studio':
            document.documentElement.style.setProperty('--font-body', "'Sora', 'Segoe UI', system-ui, -apple-system, sans-serif");
            document.documentElement.style.setProperty('--font-display', "'Bricolage Grotesque', 'Sora', sans-serif");
            break;
        case 'classic':
            document.documentElement.style.setProperty('--font-body', "'Source Serif 4', 'Georgia', serif");
            document.documentElement.style.setProperty('--font-display', "'Playfair Display', 'Source Serif 4', serif");
            break;
        case 'compact':
            document.documentElement.style.setProperty('--font-body', "'Instrument Sans', 'Segoe UI', system-ui, -apple-system, sans-serif");
            document.documentElement.style.setProperty('--font-display', "'Sora', 'Instrument Sans', sans-serif");
            break;
        default:
            document.documentElement.style.setProperty('--font-body', "'Instrument Sans', 'Segoe UI', system-ui, -apple-system, sans-serif");
            document.documentElement.style.setProperty('--font-display', "'Bricolage Grotesque', 'Instrument Sans', sans-serif");
            break;
    }
}

class ThemeStore {
    currentTheme = $state<Theme>('system');
    currentFontTheme = $state<FontTheme>('classic');
    private mediaQueryList: MediaQueryList | null = null;

    constructor() {
        // Initialize from localStorage
        if (typeof localStorage !== 'undefined') {
            const stored = localStorage.getItem('theme') as Theme | null;
            if (stored) {
                this.currentTheme = stored;
            }
            const storedFont = localStorage.getItem('font_theme') as FontTheme | null;
            if (storedFont) {
                this.currentFontTheme = storedFont;
            }
        }

        // Apply theme immediately
        applyTheme(this.currentTheme);
        applyFontTheme(this.currentFontTheme);

        // Use $effect.root() to create effect context outside components
        $effect.root(() => {
            // Sync to localStorage on changes
            if (typeof localStorage !== 'undefined') {
                $effect(() => {
                    localStorage.setItem('theme', this.currentTheme);
                    applyTheme(this.currentTheme);
                });
                $effect(() => {
                    localStorage.setItem('font_theme', this.currentFontTheme);
                    applyFontTheme(this.currentFontTheme);
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

    get fontTheme(): FontTheme {
        return this.currentFontTheme;
    }

    setTheme(value: Theme) {
        this.currentTheme = value;
    }

    setFontTheme(value: FontTheme) {
        this.currentFontTheme = value;
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

export const fontTheme = {
    subscribe: (fn: (value: FontTheme) => void) => {
        return $effect.root(() => {
            $effect(() => {
                fn(themeStore.fontTheme);
            });
            return () => {};
        });
    },
    set: (value: FontTheme) => themeStore.setFontTheme(value)
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
