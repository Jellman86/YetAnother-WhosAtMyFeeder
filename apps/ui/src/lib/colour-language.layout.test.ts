import { describe, expect, it } from 'vitest';
import detectionCard from './components/DetectionCard.svelte?raw';
import detectionRow from './components/DetectionRow.svelte?raw';
import detectionModal from './components/DetectionModal.svelte?raw';
import gardenExplorerCard from './components/GardenExplorerCard.svelte?raw';
import gardenExplorerRow from './components/GardenExplorerRow.svelte?raw';
import gardenCaptureModal from './components/GardenCaptureModal.svelte?raw';
import fieldLogGardenRow from './components/FieldLogGardenRow.svelte?raw';
import fieldLogVisitRow from './components/FieldLogVisitRow.svelte?raw';
import visitCaptures from './components/VisitCaptures.svelte?raw';
import healthActivityTimeline from './components/HealthActivityTimeline.svelte?raw';
import reviewQueueModal from './components/ReviewQueueModal.svelte?raw';
import reviewQueueCard from './components/ReviewQueueCard.svelte?raw';
import dayBar from './components/DayBar.svelte?raw';
import toast from './components/Toast.svelte?raw';
import notifications from './pages/Notifications.svelte?raw';
import errors from './pages/Errors.svelte?raw';
import audioHistory from './pages/AudioHistory.svelte?raw';
import scoreTone from './utils/score-tone.ts?raw';
import statusTone from './utils/status-tone.ts?raw';

const svelteSources = import.meta.glob(['./**/*.svelte', '../App.svelte'], {
    eager: true,
    query: '?raw',
    import: 'default'
}) as Record<string, string>;

/**
 * layout-patterns.md §1.3: amber is reserved for "this needs a person", green means confirmed,
 * brand means normal emphasis, and `accent-*` is a brand colour that the classic theme paints
 * emerald and bluetit paints amber. A score or a state drawn in `accent-*` therefore changes
 * meaning with the theme: one score was three colours across Cards, List and the record
 * (EXP-02), and "needs a person" was green in classic (DB-02). Score and state code uses
 * `attention-*`, `brand-*` and `success-*` only.
 */
const SCORE_AND_STATE_CODE: Record<string, string> = {
    'DetectionCard.svelte': detectionCard,
    'DetectionRow.svelte': detectionRow,
    'GardenExplorerCard.svelte': gardenExplorerCard,
    'GardenExplorerRow.svelte': gardenExplorerRow,
    'GardenCaptureModal.svelte': gardenCaptureModal,
    'FieldLogGardenRow.svelte': fieldLogGardenRow,
    'FieldLogVisitRow.svelte': fieldLogVisitRow,
    'VisitCaptures.svelte': visitCaptures,
    'HealthActivityTimeline.svelte': healthActivityTimeline,
    'ReviewQueueModal.svelte': reviewQueueModal,
    'ReviewQueueCard.svelte': reviewQueueCard,
    'DayBar.svelte': dayBar,
    'Toast.svelte': toast,
    'Notifications.svelte': notifications,
    'Errors.svelte': errors,
    'AudioHistory.svelte': audioHistory,
    'score-tone.ts': scoreTone,
    'status-tone.ts': statusTone
};

/** A theme-accent colour utility (`bg-accent-500`), not the CSS `accent-color` utility (`accent-brand-600`). */
const THEME_ACCENT = /\baccent-\d/;

describe('one colour language for score and state', () => {
    it('never paints a score or a state in the theme accent', () => {
        const offenders = Object.entries(SCORE_AND_STATE_CODE)
            .filter(([, source]) => THEME_ACCENT.test(source))
            .map(([name]) => name);
        expect(offenders).toEqual([]);
    });

    it("keeps the record's score block, inside the larger record, off the theme accent", () => {
        const start = detectionModal.indexOf("$_('detection.fact_species_match'");
        const block = detectionModal.slice(start, detectionModal.indexOf('data-record-score-bar', start) + 200);
        expect(start).toBeGreaterThan(0);
        expect(block).toContain('SCORE_FILL[scoreBand(detection.score)]');
        expect(block).not.toMatch(THEME_ACCENT);
        expect(block).not.toContain('emerald-');
    });

    it('takes every score band from the shared helper rather than its own thresholds', () => {
        const scoreViews = {
            'DetectionCard.svelte': detectionCard,
            'DetectionRow.svelte': detectionRow,
            'DetectionModal.svelte': detectionModal,
            'GardenExplorerCard.svelte': gardenExplorerCard,
            'GardenExplorerRow.svelte': gardenExplorerRow,
            'GardenCaptureModal.svelte': gardenCaptureModal,
            'FieldLogGardenRow.svelte': fieldLogGardenRow,
            'FieldLogVisitRow.svelte': fieldLogVisitRow,
            'VisitCaptures.svelte': visitCaptures,
            'HealthActivityTimeline.svelte': healthActivityTimeline,
            'ReviewQueueModal.svelte': reviewQueueModal,
            'AudioHistory.svelte': audioHistory
        };
        for (const [name, source] of Object.entries(scoreViews)) {
            expect(source, name).toContain("from '../utils/score-tone'");
            // The retired local band functions and the 90/70 card bands.
            expect(source, name).not.toMatch(/function (scoreTone|barTone|getConfidenceColor|getConfidenceBg)\(/);
            expect(source, name).not.toMatch(/score\s*>=\s*0\.9\b|score\s*>=\s*0\.7\b/);
        }
    });
});

describe('white text on a brand fill', () => {
    it('sits on brand-700 or darker, never brand-500 or brand-600 (KIT-02)', () => {
        // White on brand-500 is 2.49:1 in classic and 3.68:1 in bluetit; brand-600 is 3.74:1 in
        // classic. The kit's btn-primary already fills with brand-700 for this reason.
        const fill = /(?<![\w:/-])(?:hover:|focus:|group-hover:)?bg-brand-(?:500|600)(?![\w/-])/;
        const offenders: string[] = [];
        for (const [path, source] of Object.entries(svelteSources)) {
            for (const segment of source.split(/['"`]/)) {
                if (fill.test(segment) && /\btext-white\b/.test(segment)) offenders.push(`${path}: ${segment.trim().slice(0, 80)}`);
            }
        }
        expect(offenders).toEqual([]);
    });
});

/**
 * layout-patterns.md §1.3 names the whole palette: brand blue for normal emphasis and choice,
 * `success-*` for confirmed or healthy, `attention-*` for "this needs a person", rose (and the kit's
 * red danger buttons) for a failure, slate for everything else. Any other hue in component code is
 * either a second accent or decoration, and amber outside the attention scale reads as work waiting
 * on the owner when there is none. A component may only step outside the palette for a reason
 * written here.
 */
const OFF_PALETTE = /(?<![\w-])(?:[a-z0-9-]+:)*[a-z]+-(amber|accent|orange|yellow|cyan|indigo|violet|purple|teal|sky|blue|emerald|green|lime|pink|fuchsia)-\d{2,3}\b/g;

const PALETTE_EXCEPTIONS: Record<string, { families: string[]; reason: string }> = {
    'components/settings/AppearanceSettings.svelte': {
        families: ['blue', 'amber'],
        reason: "the colour-theme picker shows each theme's own two colours"
    },
    'components/DetectionCard.svelte': {
        families: ['orange'],
        reason: 'orange is the documented missing-upstream mark (§1): Frigate no longer has the media'
    },
    'components/DetectionRow.svelte': {
        families: ['orange'],
        reason: 'orange is the documented missing-upstream mark (§1): Frigate no longer has the media'
    },
    'components/settings/SystemHealthPanel.svelte': {
        families: ['amber', 'blue', 'teal', 'violet'],
        reason: 'categorical CPU-share series, chosen for colour-vision separation and always named; a series is not a state'
    },
    'components/SystemTelemetryGraph.svelte': {
        families: ['indigo'],
        reason: 'the accelerator line is a second chart series beside the brand CPU line, and is named beside its reading'
    },
    'pages/Species.svelte': {
        families: ['sky'],
        reason: 'the precipitation overlay draws rain as a sky band on the activity chart, and its legend matches it'
    }
};

/**
 * Work that needs a person lives in these components. Anything else that reaches for the attention
 * scale is claiming a person is needed where none is, so it has to say why here first.
 */
const ATTENTION_COMPONENTS: Record<string, string> = {
    // The review queue and everything that feeds it.
    'components/ReviewQueueCard.svelte': 'Needs your call: visits and species checks waiting on the owner',
    'components/ReviewQueueModal.svelte': 'the reason each queued visit needs a decision',
    'components/DayBar.svelte': 'days with visits still waiting for a decision',
    'components/FieldLogVisitRow.svelte': 'a visit below the naming threshold',
    'components/FieldLogGardenRow.svelte': 'a Garden capture waiting for review',
    'components/GardenExplorerCard.svelte': 'a Garden capture waiting for review',
    'components/GardenExplorerRow.svelte': 'a Garden capture waiting for review',
    'components/GardenCapturePreview.svelte': 'a Garden capture waiting for review',
    'components/GardenCaptureModal.svelte': 'a Garden capture waiting for review',
    'components/GardenVisitCaptures.svelte': 'a Garden capture waiting for review',
    'components/DetectionRow.svelte': 'a visit below the naming threshold',
    'components/SpeciesChecks.svelte': 'species the range check asks the owner to look at',
    'components/SpeciesCheckSheet.svelte': 'species the range check asks the owner to look at',
    'components/SpeciesDetailModal.svelte': 'an unidentified bird waiting for a decision, and an eBird warning',
    'pages/Species.svelte': 'species the range check flags as unlikely here',
    'components/DetectionModal.svelte': 'a video result held back until the owner confirms it',
    'pages/ManualObservation.svelte': 'an observation with no species chosen yet',
    // Something is wrong or degraded and only the owner can put it right.
    'components/Toast.svelte': 'warning toasts',
    'components/BackendStatusScreen.svelte': 'start-up that needs the owner',
    'components/CameraStatus.svelte': 'some cameras offline',
    'components/ConnectionStatus.svelte': 'the camera feed is down or degraded',
    'components/DiagnosticDialog.svelte': 'a diagnostic step that warned',
    'components/JobCircuitBanner.svelte': 'background work paused after repeated failures',
    'components/GlobalProgress.svelte': 'a job that is blocked',
    'components/LazyRoute.svelte': 'a page that could not load',
    'components/LanguageSelector.svelte': 'a language that could not load',
    'components/ProviderWarning.svelte': 'an accelerator that is not being used',
    'components/FamilyTreeDialog.svelte': 'part of the tree that could not load',
    'pages/Errors.svelte': 'subsystems that are degraded',
    'pages/Notifications.svelte': 'notifications and jobs that need the owner',
    'pages/AudioHistory.svelte': 'filters changed but not yet applied',
    'pages/ModelEvaluation.svelte': 'checks that did not match',
    'pages/models/ModelManager.svelte': 'an incomplete install that needs repair',
    // Settings and first run: a value that cannot work as set.
    'pages/Settings.svelte': 'the page is served without HTTPS',
    'components/settings/_primitives/SettingsPage.svelte': 'a save that conflicts with a newer change',
    'components/settings/_primitives/SettingsInput.svelte': 'a field in conflict',
    'components/settings/_primitives/FieldRefusal.svelte': 'a field in conflict',
    'components/settings/AuthenticationSettings.svelte': 'an access setting that leaves the instance exposed',
    'components/settings/CameraWatchRow.svelte': 'a camera Frigate does not know',
    'components/settings/ConnectionSettings.svelte': 'a camera list that could not be read',
    'components/settings/DataSettings.svelte': 'records due for deletion and repairs to review',
    'components/settings/DetectionSettings.svelte': 'a model or device setting that cannot run as chosen',
    'components/settings/DetectionStatusBand.svelte': 'a fallback model or device in use',
    'components/settings/GardenBetaSettings.svelte': 'a Garden step still to do',
    'components/settings/GardenNotificationSettings.svelte': 'Garden alerts that cannot be delivered',
    'components/settings/NotificationSettings.svelte': 'notifications with nowhere to go',
    'components/settings/RangeFilterSettings.svelte': 'a range filter that cannot run',
    'components/setup/WelcomeStep.svelte': 'a first-run problem',
    'components/setup/WizardShell.svelte': 'skipping setup',
    'components/setup/CamerasStep.svelte': 'a camera Frigate does not know',
    'components/setup/ConnectionStep.svelte': 'a connection test that failed',
    'components/setup/ModelStep.svelte': 'a model or device that cannot run as chosen',
    'components/setup/ReviewStep.svelte': 'a setup step that still needs attention'
};

function relative(path: string): string {
    return path.replace(/^\.\//, '').replace(/^\.\.\//, '');
}

describe('one palette across the app', () => {
    it('uses only brand, success, attention, rose, red and slate outside the named exceptions', () => {
        const offenders: string[] = [];
        for (const [path, source] of Object.entries(svelteSources)) {
            const file = relative(path);
            const allowed = PALETTE_EXCEPTIONS[file]?.families ?? [];
            const found = new Set([...source.matchAll(OFF_PALETTE)].map((match) => match[1]).filter((family) => !allowed.includes(family)));
            if (found.size) offenders.push(`${file}: ${[...found].sort().join(', ')}`);
        }
        expect(offenders).toEqual([]);
    });

    it('keeps every palette exception in use, so the list cannot rot', () => {
        for (const [file, { families }] of Object.entries(PALETTE_EXCEPTIONS)) {
            const source = Object.entries(svelteSources).find(([path]) => relative(path) === file)?.[1] ?? '';
            const found = new Set([...source.matchAll(OFF_PALETTE)].map((match) => match[1]));
            for (const family of families) expect(found.has(family), `${file} ${family}`).toBe(true);
        }
    });

    it('draws attention only where work waits on a person', () => {
        const offenders = Object.entries(svelteSources)
            .map(([path, source]) => [relative(path), source] as const)
            .filter(([file, source]) => /\battention-\d/.test(source) && !(file in ATTENTION_COMPONENTS))
            .map(([file]) => file);
        expect(offenders).toEqual([]);
    });

    it('keeps every attention entry in use', () => {
        for (const file of Object.keys(ATTENTION_COMPONENTS)) {
            const source = Object.entries(svelteSources).find(([path]) => relative(path) === file)?.[1] ?? '';
            expect(/\battention-\d/.test(source), file).toBe(true);
        }
    });
});

/**
 * A "·" between two facts is drawn by the shared Separator alone. It takes its parent's ink, which
 * already meets 4.5:1 wherever the text beside it does, rather than a lighter grey of its own
 * (slate-300 and slate-400 dots measured 1.5:1 to 2.6:1 on light panels), and is hidden from
 * screen readers, which would otherwise announce "dot" between every fact.
 */
describe('separator dots', () => {
    const DOT = /<span\b[^>]*>\s*(?:·|&middot;|\{'\s*·\s*'\})\s*<\/span>/;

    it('are drawn only by the shared Separator', () => {
        const offenders = Object.entries(svelteSources)
            .filter(([path, source]) => !path.endsWith('/Separator.svelte') && DOT.test(source))
            .map(([path]) => relative(path));
        expect(offenders).toEqual([]);
    });

    it('take the ink of the text they sit in and stay silent', () => {
        const separator = Object.entries(svelteSources).find(([path]) => path.endsWith('/Separator.svelte'))?.[1] ?? '';
        expect(separator).toContain('aria-hidden="true"');
        expect(separator).not.toMatch(/\btext-(?:slate|gray|brand|success|attention|rose|red)-\d/);
        expect(separator).not.toMatch(/\bopacity-\d/);
    });
});
