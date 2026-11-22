import { describe, expect, it } from 'vitest';
import before from './settings-reachability.before.json';
import { analyseSettings, type ControlPath } from './settings-reachability.analysis';
import { canonicalSettingsPath, settingsSectionFromRoute, settingsSectionOfPart, type SettingsPart, type SettingsSection } from './settings-route';
import { settingsFieldPart, settingsFieldSection } from './settings-fields';

// Settings as it was before it was organised by task, frozen in settings-reachability.before.json
// from the twelve-tab page on dev:
// - every control the page could render, at any depth, with the tab that rendered it and the
//   saved-settings payload entries it wrote (settings-reachability.analysis.ts follows each one
//   through every binding and callback up to the host's payload);
// - every literal element id, with the tab that rendered it;
// - the tab that showed each saved field.
// This proves each is still reachable, and still saves, from the section its tab moved to.
// Something moved on purpose is named in MOVED, so nothing is lost or renamed silently.
//
// The frozen controls and ids were written by running analyseSettings() over a checkout of dev at
// dd5c1fa3f, the last twelve-tab page. They are never regenerated from a later page: a change that
// moves or retires something on purpose names it in MOVED instead.

interface Frozen {
    controls: ControlPath[];
    ids: Record<string, string[]>;
    savedFields: Record<string, string>;
}
const frozen = before as unknown as Frozen;

/**
 * Fields and element ids shown somewhere else on purpose, with the part that now shows them. A
 * control without an id has moved when every field it saves has.
 */
const MOVED: Readonly<Record<string, SettingsPart>> = {
    // BirdNET-Go is an external service like the others, so it has its own part in Integrations.
    birdnet_enabled: 'birdnet',
    birdnet_url: 'birdnet',
    birdnet_external_url: 'birdnet',
    audio_topic: 'birdnet',
    audio_buffer_hours: 'birdnet',
    audio_correlation_window_seconds: 'birdnet',
    camera_audio_mapping: 'birdnet',
    'birdnet-url': 'birdnet',
    'birdnet-external-url': 'birdnet',
    'audio-topic': 'birdnet',
    'integrations-birdnet-advanced': 'birdnet',
    'audio-buffer': 'birdnet',
    'correlation-window': 'birdnet',
    'birdnet-source-options': 'birdnet',
    // Units are how numbers read, so they are set in Display with the rest of how YA-WAMF looks.
    location_weather_unit_system: 'appearance',
    'weather-unit-system': 'appearance',
    // The feeder's location is a fact about the feeder, so it is set with the cameras; telemetry is
    // what leaves the install, so it is set in Access & privacy beside who can open it.
    'location-lat': 'location',
    'location-lon': 'location',
    location_automatic: 'location',
    location_country: 'location',
    location_latitude: 'location',
    location_longitude: 'location',
    location_state: 'location',
    telemetry_enabled: 'telemetry',
    telemetry_health_enabled: 'telemetry',
    // Garden's automatic naming and its threshold sit in the naming card, beside the birds' threshold.
    garden_automatic_naming: 'detection',
    garden_naming_threshold: 'detection',
    'garden-naming-threshold': 'detection',
    // Garden's alerts send through the bird alert channels, so they are set in Notifications.
    garden_notifications_enabled: 'garden-alerts',
    garden_notifications_use_bird_channels: 'garden-alerts',
    garden_notification_channels: 'garden-alerts',
    garden_notifications_include_photo: 'garden-alerts',
    'garden-section-alerts': 'garden-alerts'
};

/**
 * Controls that save nothing and have no id (a test or an action button), moved on purpose: by the
 * part they left and the part that now shows them.
 */
const MOVED_ACTIONS: ReadonlyArray<{ what: string; from: SettingsSection; to: SettingsSection }> = [
    // The AI usage dashboard's buttons were on the AI tab's own page; AI is a part of Integrations now.
];

/**
 * Controls that still render, but whose effect on a saved field now runs through a module the
 * analysis does not read (it follows Svelte files). Each names the file that still renders it.
 */
const THROUGH_MODULES: ReadonlyArray<{ section: SettingsSection; entry: string; starts: ReadonlyArray<{ file: string; button: string }> }> = [
    {
        section: 'identification',
        entry: 'inference_provider',
        // Hardware's "Check devices for every installed model" and the bird finder's "Check devices"
        // start the shared check in settings/device-check.svelte.ts, which reloads the runtime and so
        // may save a new provider. Each button is named by the handler that starts the check.
        starts: [
            { file: '../components/settings/HardwareSettings.svelte', button: '<button type="button" onclick={() => deviceCheck.run()}' },
            { file: '../pages/models/FinderDevicePanel.svelte', button: '<button type="button" onclick={oncheck}' }
        ]
    }
];

/** The part a frozen control is shown by now: by its id, else by the fields it saves, else its tab's. */
function movedPart(control: ControlPath): SettingsPart | undefined {
    if (control.id && MOVED[control.id]) return MOVED[control.id];
    const moved = control.entries.map((entry) => MOVED[entry]);
    return moved.length > 0 && moved.every((part) => part === moved[0]) ? moved[0] : undefined;
}

const HOST = '../pages/Settings.svelte';
const sources = import.meta.glob<string>(['../components/**/*.svelte', '../pages/**/*.svelte', '../components/settings/sections/part-loaders.ts'], {
    query: '?raw',
    import: 'default',
    eager: true
});
const current = analyseSettings(sources, HOST);

/**
 * Where each of the twelve tabs went: the section that holds what it held, and the address its own
 * address now opens. The Integrations and Notifications tabs became sections of those names.
 */
const FORMER_TABS: Readonly<Record<string, { section: SettingsSection; address: string }>> = {
    connection: { section: 'cameras', address: '/settings/cameras#connection' },
    detection: { section: 'identification', address: '/settings/identification#detection' },
    models: { section: 'identification', address: '/settings/identification#models' },
    beta: { section: 'identification', address: '/settings/identification#beta' },
    integrations: { section: 'integrations', address: '/settings/integrations' },
    ai: { section: 'integrations', address: '/settings/integrations#ai' },
    notifications: { section: 'notifications', address: '/settings/notifications' },
    security: { section: 'access', address: '/settings/access#security' },
    data: { section: 'storage', address: '/settings/storage#data' },
    maintenance: { section: 'storage', address: '/settings/storage#maintenance' },
    appearance: { section: 'display', address: '/settings/display#appearance' },
    accessibility: { section: 'display', address: '/settings/display#accessibility' }
};

/** The section a former tab now lives in, unless what it held moved on purpose. */
function sectionOf(area: string, moved?: SettingsPart): SettingsSection {
    return moved ? settingsSectionOfPart(moved) : FORMER_TABS[area].section;
}

/** How many controls write each payload entry in each section; `(no setting)` for none. */
function countBySectionAndEntry(controls: readonly ControlPath[], areaToSection: (control: ControlPath, area: string) => string): Map<string, number> {
    const counts = new Map<string, number>();
    for (const control of controls) {
        // A control two former tabs both rendered (a shared dialog) counts once in their section.
        for (const section of new Set(control.areas.map((area) => areaToSection(control, area)))) {
            for (const entry of control.entries.length > 0 ? control.entries : ['(no setting)']) {
                const key = `${section} | ${entry}`;
                counts.set(key, (counts.get(key) ?? 0) + 1);
            }
        }
    }
    return counts;
}

describe('the frozen twelve-tab page', () => {
    it('holds enough to prove something: controls at every depth, ids, and every saved field', () => {
        expect(frozen.controls.length).toBeGreaterThan(150);
        // Descendant controls a flat listing missed are in it.
        expect(frozen.controls.find((control) => control.id === 'range-filter-level')?.entries).toEqual(['range_filter_region_level']);
        expect(frozen.controls.find((control) => control.id === 'recording-frame-delay')?.entries).toEqual(['recording_frame_delay_seconds']);
        expect(Object.keys(frozen.ids).length).toBeGreaterThan(180);
        expect(Object.keys(frozen.savedFields).length).toBeGreaterThan(190);
    });

    it('found a control writing every payload entry the page could edit', () => {
        const written = new Set(frozen.controls.flatMap((control) => control.entries));
        // 168 of the 172 payload entries. No control wrote the other four on dev: the media cache's
        // own retention days, the place a pin lookup fills in (state, country), and the species
        // information sources, which Integrations only summarised.
        expect(written.size).toBe(168);
        for (const unwritten of ['media_cache_retention_days', 'location_state', 'location_country', '...enrichmentSection.encodePatch(enrichmentDraft)']) {
            expect(written.has(unwritten), unwritten).toBe(false);
        }
    });
});

describe('every former Settings tab', () => {
    it.each(Object.entries(FORMER_TABS))('%s: its address opens the section that holds it, at its place', (tab, { section, address }) => {
        // An address that is already canonical is left alone.
        expect(canonicalSettingsPath(`/settings/${tab}`, '') ?? `/settings/${tab}`).toBe(address);
        expect(canonicalSettingsPath('/settings', tab)).toBe(address);
        expect(settingsSectionFromRoute(`/settings/${tab}`)).toBe(section);
        expect(settingsSectionFromRoute(address)).toBe(section);
    });

    it('holds its place in the older Sharing & integrations and Alerts addresses too', () => {
        expect(canonicalSettingsPath('/settings/sharing', 'integrations')).toBe(FORMER_TABS.integrations.address);
        expect(canonicalSettingsPath('/settings/sharing', 'ai')).toBe(FORMER_TABS.ai.address);
        expect(canonicalSettingsPath('/settings/sharing', 'security')).toBe(FORMER_TABS.security.address);
        expect(canonicalSettingsPath('/settings/alerts', 'notifications')).toBe(FORMER_TABS.notifications.address);
    });
});

describe('every control the twelve tabs rendered', () => {
    it('that had an id is still rendered, by the section its tab moved to, and still saves what it saved', () => {
        const problems: string[] = [];
        for (const control of frozen.controls) {
            if (!control.id) continue;
            const now = current.controls.filter((candidate) => candidate.id === control.id);
            if (now.length === 0) {
                problems.push(`${control.id}: no longer rendered`);
                continue;
            }
            const sections = new Set(now.flatMap((candidate) => candidate.areas));
            for (const area of control.areas) {
                const section = sectionOf(area, movedPart(control));
                if (!sections.has(section)) problems.push(`${control.id}: not rendered in ${section}`);
            }
            const entries = new Set(now.flatMap((candidate) => candidate.entries));
            for (const entry of control.entries) if (!entries.has(entry)) problems.push(`${control.id}: no longer saves ${entry}`);
        }
        expect(problems).toEqual([]);
    });

    it('is matched, with or without an id: no section has fewer controls saving a setting than its tabs had', () => {
        const was = countBySectionAndEntry(frozen.controls, (control, area) => sectionOf(area, movedPart(control)));
        for (const { from, to } of MOVED_ACTIONS) {
            const left = `${from} | (no setting)`;
            const arrived = `${to} | (no setting)`;
            was.set(left, (was.get(left) ?? 0) - 1);
            was.set(arrived, (was.get(arrived) ?? 0) + 1);
        }
        for (const { section, entry, starts } of THROUGH_MODULES) {
            const key = `${section} | ${entry}`;
            was.set(key, (was.get(key) ?? 0) - starts.length);
            // Each button that starts the check is still in its file, and its file still renders in the section.
            for (const { file, button } of starts) {
                expect(sources[file], file).toContain(button);
                expect(current.controls.some((control) => control.file === file && control.areas.includes(section)), file).toBe(true);
            }
        }
        const now = countBySectionAndEntry(current.controls, (_control, area) => area);
        const fewer = [...was].filter(([key, count]) => (now.get(key) ?? 0) < count).map(([key, count]) => `${key}: ${count} -> ${now.get(key) ?? 0}`);
        expect(fewer).toEqual([]);
    });
});

describe('every element id the twelve tabs rendered', () => {
    it('is still rendered by the section its tab moved to', () => {
        const problems: string[] = [];
        for (const [id, areas] of Object.entries(frozen.ids)) {
            const now = current.ids[id];
            if (!now) {
                problems.push(`${id}: no longer rendered`);
                continue;
            }
            for (const area of areas) {
                const section = sectionOf(area, MOVED[id]);
                if (!now.includes(section)) problems.push(`${id}: not rendered in ${section}`);
            }
        }
        expect(problems).toEqual([]);
    });
});

describe('every saved setting', () => {
    it.each(Object.entries(frozen.savedFields))('%s is shown by the section its former tab moved to', (field, formerPart) => {
        // A field moved on purpose is held to its new part; any other to the section its tab became.
        const moved = MOVED[field];
        if (moved) expect(settingsFieldPart(field)).toBe(moved);
        expect(settingsFieldPart(field)).not.toBeNull();
        expect(settingsFieldSection(field)).toBe(sectionOf(formerPart, moved));
    });
});
