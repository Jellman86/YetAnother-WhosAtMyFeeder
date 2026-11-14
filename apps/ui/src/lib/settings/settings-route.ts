export type SettingsTab = 'connection' | 'detection' | 'notifications' | 'health' | 'ai' | 'data' | 'appearance' | 'accessibility' | 'security' | 'debug' | 'integrations' | 'beta';

/** Every Settings tab, in the order the navigation lists them. */
export const SETTINGS_TAB_ORDER: readonly SettingsTab[] = [
    'connection',
    'detection',
    'integrations',
    'ai',
    'notifications',
    'health',
    'security',
    'data',
    'beta',
    'debug',
    'appearance',
    'accessibility'
];

// Tabs that no longer exist, and the tab that now shows what they held. Species information
// sources were their own tab; they are summarised at the end of Integrations.
const RETIRED_TABS: Readonly<Record<string, SettingsTab>> = { enrichment: 'integrations' };

function isSettingsTab(value: string): value is SettingsTab {
    return (SETTINGS_TAB_ORDER as readonly string[]).includes(value);
}

export function settingsTabPath(tab: SettingsTab): string {
    return `/settings/${tab}`;
}

/** The tab a route shows. `/settings/errors` is the Health tab's older address. */
export function settingsTabFromRoute(route: string | undefined): SettingsTab {
    if (!route) return 'connection';
    const match = /^\/settings\/([^/]+)/.exec(route);
    if (!match) return 'connection';
    const slug = match[1];
    if (slug === 'errors') return 'health';
    const tab = RETIRED_TABS[slug] ?? slug;
    return isSettingsTab(tab) ? tab : 'connection';
}

/**
 * The canonical `/settings/<tab>` address for a pathname and hash, or null when the pathname is
 * already canonical (or outside Settings), so a caller can do nothing in the steady state.
 *
 * Older links used `/settings#<tab>` and `/settings/errors`; an unknown tab steers back to
 * Connection so the visible tab and the address agree.
 */
export function canonicalSettingsPath(pathname: string, hash: string): string | null {
    if (!pathname.startsWith('/settings')) return null;

    if (pathname === '/settings/' || pathname === '/settings') {
        const tab = RETIRED_TABS[hash] ?? hash;
        return isSettingsTab(tab) ? settingsTabPath(tab) : settingsTabPath('connection');
    }

    if (pathname === '/settings/errors' || pathname.startsWith('/settings/errors/')) {
        return settingsTabPath('health');
    }
    const retired = /^\/settings\/([^/]+)\/?$/.exec(pathname)?.[1];
    if (retired && RETIRED_TABS[retired]) return settingsTabPath(RETIRED_TABS[retired]);

    const match = /^\/settings\/([^/]+)\/?$/.exec(pathname);
    // A deeper sub-path such as /settings/data/foo is left alone.
    if (!match) return null;
    const slug = match[1];
    if (!isSettingsTab(slug)) return settingsTabPath('connection');
    const canonical = settingsTabPath(slug);
    return canonical === pathname ? null : canonical;
}
