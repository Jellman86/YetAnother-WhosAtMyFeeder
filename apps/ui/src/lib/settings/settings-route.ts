export type SettingsTab =
    | 'connection'
    | 'detection'
    | 'models'
    | 'integrations'
    | 'ai'
    | 'notifications'
    | 'security'
    | 'data'
    | 'maintenance'
    | 'beta'
    | 'appearance'
    | 'accessibility';

/** Every Settings tab, in the order the navigation lists them. */
export const SETTINGS_TAB_ORDER: readonly SettingsTab[] = [
    'connection',
    'detection',
    'models',
    'integrations',
    'ai',
    'notifications',
    'security',
    'data',
    'maintenance',
    'beta',
    'appearance',
    'accessibility'
];

// Tabs that no longer exist, and the tab that now shows what they held. Species information
// sources were their own tab; they are summarised at the end of Integrations. Debug held two
// model settings, now in Models. Health is a page of its own (`/system-health`), redirected by the app.
const RETIRED_TABS: Readonly<Record<string, SettingsTab>> = { enrichment: 'integrations', debug: 'models' };

/** The Health page's address. Not `/health`: the backend answers that path itself. */
const HEALTH_PAGE_PATH = '/system-health';
const HEALTH_HASHES: ReadonlySet<string> = new Set(['health', 'errors']);

function isSettingsTab(value: string): value is SettingsTab {
    return (SETTINGS_TAB_ORDER as readonly string[]).includes(value);
}

export function settingsTabPath(tab: SettingsTab): string {
    return `/settings/${tab}`;
}

/** The tab a route shows. */
export function settingsTabFromRoute(route: string | undefined): SettingsTab {
    if (!route) return 'connection';
    const match = /^\/settings\/([^/]+)/.exec(route);
    if (!match) return 'connection';
    const slug = match[1];
    const tab = RETIRED_TABS[slug] ?? slug;
    return isSettingsTab(tab) ? tab : 'connection';
}

/**
 * The canonical `/settings/<tab>` address for a pathname and hash, or null when the pathname is
 * already canonical (or outside Settings), so a caller can do nothing in the steady state. Older
 * Health addresses return the Health page, outside Settings.
 *
 * Older links used `/settings#<tab>`; an unknown tab steers back to Connection so the visible tab
 * and the address agree.
 */
export function canonicalSettingsPath(pathname: string, hash: string): string | null {
    if (!pathname.startsWith('/settings')) return null;

    // Health left Settings for a page of its own; its older tab, hash and errors addresses open it.
    if (/^\/settings\/(health|errors)(\/|$)/.test(pathname)) return HEALTH_PAGE_PATH;
    if ((pathname === '/settings' || pathname === '/settings/') && HEALTH_HASHES.has(hash)) return HEALTH_PAGE_PATH;

    if (pathname === '/settings/' || pathname === '/settings') {
        const tab = RETIRED_TABS[hash] ?? hash;
        return isSettingsTab(tab) ? settingsTabPath(tab) : settingsTabPath('connection');
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
