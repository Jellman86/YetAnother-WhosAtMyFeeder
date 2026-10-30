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
