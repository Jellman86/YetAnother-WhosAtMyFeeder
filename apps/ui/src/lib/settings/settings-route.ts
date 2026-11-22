/**
 * Settings is organised by the owner's task: seven sections, each holding the parts that one task
 * needs. A part is a group of settings with an address of its own inside its section. No name is
 * both a section and a part, so an address never means two things; a name Settings used before
 * (a former tab, or a section since renamed) still lands on what it held.
 */
export type SettingsSection = 'cameras' | 'identification' | 'integrations' | 'notifications' | 'access' | 'storage' | 'display';

export type SettingsPart =
    | 'connection'
    | 'location'
    | 'detection'
    | 'models'
    | 'beta'
    | 'birdnet'
    | 'weather'
    | 'networks'
    | 'ai'
    | 'enrichment'
    | 'rules'
    | 'channels'
    | 'garden-alerts'
    | 'security'
    | 'telemetry'
    | 'data'
    | 'maintenance'
    | 'appearance'
    | 'accessibility';

/** Every section, in the order the navigation lists them. */
export const SETTINGS_SECTION_ORDER: readonly SettingsSection[] = [
    'cameras',
    'identification',
    'integrations',
    'notifications',
    'access',
    'storage',
    'display'
];

/** The parts each section shows, top to bottom. */
export const SETTINGS_SECTION_PARTS: Readonly<Record<SettingsSection, readonly SettingsPart[]>> = {
    cameras: ['connection', 'location'],
    identification: ['detection', 'models', 'beta'],
    integrations: ['birdnet', 'weather', 'networks', 'ai', 'enrichment'],
    notifications: ['rules', 'channels', 'garden-alerts'],
    access: ['security', 'telemetry'],
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

// Addresses older than the parts, and the part that now shows what they held. Debug held two model
// settings, now in Models. The Notifications and Integrations tabs are sections of those names now.
// Health is a page of its own (`/system-health`), redirected by the app.
const RETIRED_TABS: Readonly<Record<string, SettingsPart>> = { debug: 'models' };

// Sections since renamed. Alerts is Notifications. Sharing & integrations was split: what it held
// first, sign-in and guest access, is Access & privacy, and an anchor says which of its former
// parts an older link meant.
const RETIRED_SECTIONS: Readonly<Record<string, SettingsSection>> = { alerts: 'notifications', sharing: 'access' };

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
/**
 * Where the upkeep jobs (batch analysis among them) are shown: their cards in Storage & upkeep, under
 * More options, which this route opens. A job notification kept from before the cards moved opens
 * them here too, as its route is written again whenever the job reports.
 */
export const MAINTENANCE_JOBS_ROUTE = '/settings/maintenance';

export function settingsPartPath(part: SettingsPart): string {
    return settingsSectionPath(settingsSectionOfPart(part), part);
}

/** A route without its fragment and query, which the navigation may carry. */
function routePath(route: string): string {
    return route.replace(/[?#].*$/, '');
}

/** The fragment a route carries, without its `#`. */
function routeAnchor(route: string): string {
    return /#([^?]*)/.exec(route)?.[1] ?? '';
}

/** Where a name Settings has ever used in an address leads, or null for a name it never used. */
function placeNamed(name: string): { section: SettingsSection; part?: SettingsPart } | null {
    if (isSettingsSection(name)) return { section: name };
    const part = partNamed(name);
    return part ? { section: settingsSectionOfPart(part), part } : null;
}

/**
 * Where `/settings/<slug>` leads with an anchor. A renamed section follows its anchor, since its
 * former parts are in more than one section now; any other name is its own place, keeping an
 * anchor that names one of its parts.
 */
function placeOf(slug: string, anchor: string): { section: SettingsSection; part?: SettingsPart } | null {
    const retired = RETIRED_SECTIONS[slug];
    if (retired) return placeNamed(anchor) ?? { section: retired };
    const place = placeNamed(slug);
    if (!place || place.part) return place;
    return { section: place.section, part: settingsPartFromAnchor(place.section, anchor) ?? undefined };
}

/** The section a route shows. A former address shows the section that holds what it named. */
export function settingsSectionFromRoute(route: string | undefined): SettingsSection {
    if (!route) return 'cameras';
    const match = /^\/settings\/([^/]+)/.exec(routePath(route));
    if (!match) return 'cameras';
    return placeOf(match[1], routeAnchor(route))?.section ?? 'cameras';
}

/** The part an anchor names inside a section, or null when it names none of that section's parts. */
export function settingsPartFromAnchor(section: SettingsSection, anchor: string): SettingsPart | null {
    const part = partNamed(anchor.replace(/^#/, ''));
    return part && settingsSectionOfPart(part) === section ? part : null;
}

/**
 * The canonical `/settings/<section>` address for a pathname and hash, or null when the pathname is
 * already canonical (or outside Settings), so a caller can do nothing in the steady state. A former
 * tab's address returns its section with the part as the anchor; a renamed section's returns the
 * section that now holds what its anchor names. Older Health addresses return the Health page,
 * outside Settings.
 *
 * Older links used `/settings#<tab>`; an unknown name steers back to the first section so the visible
 * section and the address agree.
 */
export function canonicalSettingsPath(pathname: string, hash: string): string | null {
    const path = routePath(pathname);
    if (!path.startsWith('/settings')) return null;
    const anchor = hash.replace(/^#/, '');

    // Health left Settings for a page of its own; its older tab, hash and errors addresses open it.
    if (/^\/settings\/(health|errors)(\/|$)/.test(path)) return HEALTH_PAGE_PATH;
    if ((path === '/settings' || path === '/settings/') && HEALTH_HASHES.has(anchor)) return HEALTH_PAGE_PATH;

    if (path === '/settings/' || path === '/settings') {
        const place = placeNamed(anchor) ?? (RETIRED_SECTIONS[anchor] ? { section: RETIRED_SECTIONS[anchor] } : null);
        return place ? settingsSectionPath(place.section, place.part) : settingsSectionPath('cameras');
    }

    const match = /^\/settings\/([^/]+)\/?$/.exec(path);
    // A deeper sub-path such as /settings/data/foo is left alone.
    if (!match) return null;
    const slug = match[1];
    // A canonical section address stands whatever its fragment: the page reads the part from it.
    if (isSettingsSection(slug) && settingsSectionPath(slug) === path) return null;
    const place = placeOf(slug, anchor);
    return place ? settingsSectionPath(place.section, place.part) : settingsSectionPath('cameras');
}
