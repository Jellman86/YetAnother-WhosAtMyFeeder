export type Theme = 'light' | 'dark' | 'system';
export type FontTheme = 'default' | 'clean' | 'studio' | 'classic' | 'compact';
export type ColorTheme = 'default' | 'bluetit';
export type TextSize = 'smallest' | 'smaller' | 'standard' | 'large' | 'larger' | 'extra_large' | 'largest';

/**
 * How much each text size multiplies the automatic root size, which already grows on large displays.
 * Standard reads a step under the browser's own size: the app is dense, and at 100% a page of
 * small print fills a laptop screen. Large gives the browser's size back.
 */
export const TEXT_SIZE_SCALE: Record<TextSize, number> = {
    smallest: 0.75,
    smaller: 0.8125,
    standard: 0.875,
    large: 1,
    larger: 1.125,
    extra_large: 1.25,
    largest: 1.5
};

export function normalizeTextSize(value: unknown): TextSize {
    return typeof value === 'string' && Object.hasOwn(TEXT_SIZE_SCALE, value) ? (value as TextSize) : 'standard';
}

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

/**
 * High contrast is one black scheme, so it takes the dark variants whatever theme is chosen:
 * over the light theme every dark ink would otherwise sit on its black page.
 */
function applyTheme(theme: Theme, highContrast: boolean) {
    if (typeof document === 'undefined') return;
    const isDark = getIsDark(theme);
    document.documentElement.classList.toggle('dark', isDark || highContrast);

    // After class changes apply, sync the browser UI color (mobile/PWA).
    requestAnimationFrame(syncThemeColorMeta);
}

function applyColorTheme(colorTheme: ColorTheme) {
    if (typeof document === 'undefined') return;
    document.documentElement.classList.toggle('theme-bluetit', colorTheme === 'bluetit');
    requestAnimationFrame(syncThemeColorMeta);
}

function applyTextSize(textSize: TextSize) {
    if (typeof document === 'undefined') return;
    document.documentElement.style.setProperty('--text-scale', String(TEXT_SIZE_SCALE[textSize]));
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
    currentTheme = $state<Theme>('dark');
    currentFontTheme = $state<FontTheme>('classic');
    currentColorTheme = $state<ColorTheme>('bluetit');
    /** Kept on this device only: a wall display and a phone want different sizes. */
    currentTextSize = $state<TextSize>('standard');
    /** The install's high contrast choice (or its unsaved preview), set by the app shell. */
    private highContrast = $state(false);
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
            const storedColor = localStorage.getItem('color_theme') as ColorTheme | null;
            if (storedColor) {
                this.currentColorTheme = storedColor;
            }
            this.currentTextSize = normalizeTextSize(localStorage.getItem('text_size'));
        }

        // Apply theme immediately
        applyTheme(this.currentTheme, this.highContrast);
        applyFontTheme(this.currentFontTheme);
        applyColorTheme(this.currentColorTheme);
        applyTextSize(this.currentTextSize);

        // Use $effect.root() to create effect context outside components
        $effect.root(() => {
            // Sync to localStorage on changes
            if (typeof localStorage !== 'undefined') {
                $effect(() => {
                    localStorage.setItem('theme', this.currentTheme);
                    applyTheme(this.currentTheme, this.highContrast);
                });
                $effect(() => {
                    localStorage.setItem('font_theme', this.currentFontTheme);
                    applyFontTheme(this.currentFontTheme);
                });
                $effect(() => {
                    localStorage.setItem('color_theme', this.currentColorTheme);
                    applyColorTheme(this.currentColorTheme);
                });
                $effect(() => {
                    localStorage.setItem('text_size', this.currentTextSize);
                    applyTextSize(this.currentTextSize);
                });
            }

            // Listen for system preference changes
            if (typeof window !== 'undefined') {
                this.mediaQueryList = window.matchMedia('(prefers-color-scheme: dark)');

                const handleMediaChange = () => {
                    if (this.currentTheme === 'system') {
                        applyTheme('system', this.highContrast);
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

    /** Whether the page is drawn dark: the chosen theme, or high contrast over any theme. */
    get isDark(): boolean {
        return this.highContrast || getIsDark(this.currentTheme);
    }

    /** The reader's own theme choice, which the theme switch shows and high contrast leaves alone. */
    get prefersDark(): boolean {
        return getIsDark(this.currentTheme);
    }

    setHighContrast(value: boolean) {
        this.highContrast = value;
    }

    get fontTheme(): FontTheme {
        return this.currentFontTheme;
    }

    get colorTheme(): ColorTheme {
        return this.currentColorTheme;
    }

    setTheme(value: Theme) {
        this.currentTheme = value;
    }

    setFontTheme(value: FontTheme) {
        this.currentFontTheme = value;
    }

    setColorTheme(value: ColorTheme) {
        this.currentColorTheme = value;
    }

    get textSize(): TextSize {
        return this.currentTextSize;
    }

    setTextSize(value: TextSize) {
        this.currentTextSize = value;
    }

    toggle() {
        // Toggle based on current visual state, not preference
        const currentlyDark = getIsDark(this.currentTheme);
        this.currentTheme = currentlyDark ? 'light' : 'dark';
    }
}

// Singleton instance
export const themeStore = new ThemeStore();
