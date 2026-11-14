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
    // Species information sources used to be their own tab; they are summarised in Integrations.
    if (slug === 'enrichment') return 'integrations';
    return isSettingsTab(slug) ? slug : 'connection';
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
        return isSettingsTab(hash) ? settingsTabPath(hash) : settingsTabPath('connection');
    }

    if (pathname === '/settings/errors' || pathname.startsWith('/settings/errors/')) {
        return settingsTabPath('health');
    }
    if (pathname === '/settings/enrichment' || pathname === '/settings/enrichment/') {
        return settingsTabPath('integrations');
    }

    const match = /^\/settings\/([^/]+)\/?$/.exec(pathname);
    // A deeper sub-path such as /settings/data/foo is left alone.
    if (!match) return null;
    const slug = match[1];
    if (!isSettingsTab(slug)) return settingsTabPath('connection');
    const canonical = settingsTabPath(slug);
    return canonical === pathname ? null : canonical;
}
