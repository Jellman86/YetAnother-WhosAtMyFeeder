import { describe, expect, it } from 'vitest';
import before from './settings-reachability.before.json';
import { analyseSettings, type ControlPath } from './settings-reachability.analysis';
import { canonicalSettingsPath, settingsPartPath, settingsSectionFromRoute, settingsSectionOfPart, type SettingsPart, type SettingsSection } from './settings-route';
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
    savedFields: Record<string, SettingsPart>;
}
const frozen = before as unknown as Frozen;

/** Controls, ids or fields shown somewhere else on purpose, with the part that now shows them. */
const MOVED: Readonly<Record<string, SettingsPart>> = {};

const HOST = '../pages/Settings.svelte';
const sources = import.meta.glob<string>(['../components/**/*.svelte', '../pages/**/*.svelte', '../components/settings/sections/part-loaders.ts'], {
    query: '?raw',
    import: 'default',
    eager: true
});
const current = analyseSettings(sources, HOST);

const FORMER_TABS: readonly SettingsPart[] = ['connection', 'detection', 'models', 'integrations', 'ai', 'notifications', 'security', 'data', 'maintenance', 'beta', 'appearance', 'accessibility'];

/** The section a former tab, or a frozen area name, now lives in. */
function sectionOf(area: string, key?: string): SettingsSection {
    const moved = key ? MOVED[key] : undefined;
    return settingsSectionOfPart(moved ?? (area as SettingsPart));
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
    it.each(FORMER_TABS)('%s: its address opens the section that holds it, at its place', (part) => {
        const section = settingsSectionOfPart(part);
        expect(canonicalSettingsPath(`/settings/${part}`, '')).toBe(settingsPartPath(part));
        expect(canonicalSettingsPath('/settings', part)).toBe(settingsPartPath(part));
        expect(settingsSectionFromRoute(`/settings/${part}`)).toBe(section);
        expect(settingsPartPath(part)).toBe(`/settings/${section}#${part}`);
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
                const section = sectionOf(area, control.id);
                if (!sections.has(section)) problems.push(`${control.id}: not rendered in ${section}`);
            }
            const entries = new Set(now.flatMap((candidate) => candidate.entries));
            for (const entry of control.entries) if (!entries.has(entry)) problems.push(`${control.id}: no longer saves ${entry}`);
        }
        expect(problems).toEqual([]);
    });

    it('is matched, with or without an id: no section has fewer controls saving a setting than its tabs had', () => {
        const was = countBySectionAndEntry(frozen.controls, (control, area) => sectionOf(area, control.id ?? undefined));
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
                const section = sectionOf(area, id);
                if (!now.includes(section)) problems.push(`${id}: not rendered in ${section}`);
            }
        }
        expect(problems).toEqual([]);
    });
});

describe('every saved setting', () => {
    it.each(Object.entries(frozen.savedFields))('%s is shown by the section its former tab moved to', (field, formerPart) => {
        const part = MOVED[field] ?? formerPart;
        expect(settingsFieldPart(field)).toBe(part);
        expect(settingsFieldSection(field)).toBe(settingsSectionOfPart(part));
    });
});
