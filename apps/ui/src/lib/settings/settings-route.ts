/**
 * Settings is organised by the owner's task: six sections, each holding the parts that one task
 * needs. A part is what was a tab of its own before Settings was organised by task; its name is
 * kept as the anchor inside its section, so an older `/settings/<tab>` address still lands on it.
 */
export type SettingsSection = 'cameras' | 'identification' | 'alerts' | 'sharing' | 'storage' | 'display';

export type SettingsPart =
    | 'connection'
    | 'detection'
    | 'models'
    | 'beta'
    | 'notifications'
    | 'integrations'
    | 'ai'
    | 'security'
    | 'data'
    | 'maintenance'
    | 'appearance'
    | 'accessibility';

/** Every section, in the order the navigation lists them. */
export const SETTINGS_SECTION_ORDER: readonly SettingsSection[] = [
    'cameras',
    'identification',
    'alerts',
    'sharing',
    'storage',
    'display'
];

/** The parts each section shows, top to bottom. */
export const SETTINGS_SECTION_PARTS: Readonly<Record<SettingsSection, readonly SettingsPart[]>> = {
    cameras: ['connection'],
    identification: ['detection', 'models', 'beta'],
    alerts: ['notifications'],
    sharing: ['integrations', 'ai', 'security'],
    storage: ['data', 'maintenance'],
    display: ['appearance', 'accessibility']
};

/** Every part, in navigation order. */
export const SETTINGS_PART_ORDER: readonly SettingsPart[] = SETTINGS_SECTION_ORDER.flatMap(
    (section) => SETTINGS_SECTION_PARTS[section]
);

const SECTION_OF_PART: Readonly<Record<SettingsPart, SettingsSection>> = Object.fromEntries(
    SETTINGS_SECTION_ORDER.flatMap((section) => SETTINGS_SECTION_PARTS[section].map((part) => [part, section]))
) as Record<SettingsPart, SettingsSection>;

// Addresses older than the tabs, and the part that now shows what they held. Species information
// sources were their own tab; they are summarised at the end of Integrations. Debug held two
// model settings, now in Models. Health is a page of its own (`/system-health`), redirected by the app.
const RETIRED_TABS: Readonly<Record<string, SettingsPart>> = { enrichment: 'integrations', debug: 'models' };

/** The Health page's address. Not `/health`: the backend answers that path itself. */
const HEALTH_PAGE_PATH = '/system-health';
const HEALTH_HASHES: ReadonlySet<string> = new Set(['health', 'errors']);

function isSettingsSection(value: string): value is SettingsSection {
    return (SETTINGS_SECTION_ORDER as readonly string[]).includes(value);
}

function isSettingsPart(value: string): value is SettingsPart {
    return (SETTINGS_PART_ORDER as readonly string[]).includes(value);
}

/** The part a former tab name, current or retired, now names; null for anything else. */
function partNamed(name: string): SettingsPart | null {
    const part = RETIRED_TABS[name] ?? name;
    return isSettingsPart(part) ? part : null;
}

/** The section that shows a part. */
export function settingsSectionOfPart(part: SettingsPart): SettingsSection {
    return SECTION_OF_PART[part];
}

/** The address of a section, or of one part inside it. */
export function settingsSectionPath(section: SettingsSection, part?: SettingsPart): string {
    return part ? `/settings/${section}#${part}` : `/settings/${section}`;
}

/** The address that opens a part: its section, at the part. */
export function settingsPartPath(part: SettingsPart): string {
    return settingsSectionPath(settingsSectionOfPart(part), part);
}

/** A route without its fragment and query, which the navigation may carry. */
function routePath(route: string): string {
    return route.replace(/[?#].*$/, '');
}

/** The section a route shows. A former tab's address shows the section that holds it. */
export function settingsSectionFromRoute(route: string | undefined): SettingsSection {
    if (!route) return 'cameras';
    const match = /^\/settings\/([^/]+)/.exec(routePath(route));
    if (!match) return 'cameras';
    const slug = match[1];
    if (isSettingsSection(slug)) return slug;
    const part = partNamed(slug);
    return part ? settingsSectionOfPart(part) : 'cameras';
}

/** The part an anchor names inside a section, or null when it names none of that section's parts. */
export function settingsPartFromAnchor(section: SettingsSection, anchor: string): SettingsPart | null {
    const part = partNamed(anchor.replace(/^#/, ''));
    return part && settingsSectionOfPart(part) === section ? part : null;
}

/**
 * The canonical `/settings/<section>` address for a pathname and hash, or null when the pathname is
 * already canonical (or outside Settings), so a caller can do nothing in the steady state. A former
 * tab's address returns its section with the part as the anchor. Older Health addresses return the
 * Health page, outside Settings.
 *
 * Older links used `/settings#<tab>`; an unknown name steers back to the first section so the visible
 * section and the address agree.
 */
export function canonicalSettingsPath(pathname: string, hash: string): string | null {
    const path = routePath(pathname);
    if (!path.startsWith('/settings')) return null;

    // Health left Settings for a page of its own; its older tab, hash and errors addresses open it.
    if (/^\/settings\/(health|errors)(\/|$)/.test(path)) return HEALTH_PAGE_PATH;
    if ((path === '/settings' || path === '/settings/') && HEALTH_HASHES.has(hash)) return HEALTH_PAGE_PATH;

    if (path === '/settings/' || path === '/settings') {
        if (isSettingsSection(hash)) return settingsSectionPath(hash);
        const part = partNamed(hash);
        return part ? settingsPartPath(part) : settingsSectionPath('cameras');
    }

    const match = /^\/settings\/([^/]+)\/?$/.exec(path);
    // A deeper sub-path such as /settings/data/foo is left alone.
    if (!match) return null;
    const slug = match[1];
    if (isSettingsSection(slug)) {
        const canonical = settingsSectionPath(slug);
        return canonical === path ? null : canonical;
    }
    const part = partNamed(slug);
    return part ? settingsPartPath(part) : settingsSectionPath('cameras');
}
