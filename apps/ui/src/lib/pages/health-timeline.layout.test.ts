import { describe, expect, it } from 'vitest';

import errorsSource from './Errors.svelte?raw';
import settingsSource from './Settings.svelte?raw';
import timelineSource from '../components/HealthActivityTimeline.svelte?raw';
import filteredPreviewSource from '../components/FilteredFramePreview.svelte?raw';

/**
 * Structural intent for the Health page timeline, per layout-patterns §7.
 * These assert the decisions that are easy to undo by accident, not the markup.
 */

describe('health page timeline', () => {
    it('uses an operational activity timeline rather than duplicating the Dashboard field log', () => {
        expect(errorsSource).toContain("import HealthActivityTimeline from '../components/HealthActivityTimeline.svelte'");
        expect(errorsSource).toContain('data-health-timeline');
        expect(errorsSource).toMatch(/<HealthActivityTimeline[\s\S]*?rows=\{timelineRows\}/);
        expect(timelineSource).toContain('data-health-activity-timeline');
        expect(timelineSource).toContain("jobs.errors_activity_recorded");
        expect(timelineSource).toContain("jobs.errors_activity_filtered");
        expect(timelineSource).toContain("jobs.errors_activity_fault");
    });

    it('routes View record through the app navigator instead of writing a dead hash URL', () => {
        expect(errorsSource).toContain('onNavigate?: (path: string) => void');
        expect(errorsSource).toContain("onNavigate?.(`/events?event=${encodeURIComponent(eventId)}`)");
        expect(errorsSource).not.toContain('window.location.hash');
        expect(settingsSource).toContain('<Errors {onNavigate} />');
        expect(timelineSource).toContain("jobs.errors_activity_view_record");
    });

    it('windows visits to the same slice of time the counters describe', () => {
        // §1.1: a header saying one thing while cards count another is broken.
        expect(errorsSource).toContain('instanceWindowMs');
        expect(errorsSource).toContain('const window = { startTime: started, endTime: new Date().toISOString() }');
        expect(errorsSource).toContain('errors_activity_no_window');
    });

    it('groups frames into visits before showing them', () => {
        // §1.2: users see birds, not frames.
        expect(errorsSource).toContain('fromServerVisit(visit, window)');
        expect(errorsSource).toContain('fetchVisits');
    });

    it('keeps subsystem detail available rather than deleting it', () => {
        expect(errorsSource).toContain('data-subsystem-detail');
        expect(errorsSource).toContain('errors_subsystems_title');
    });

    it('states the remainder from the pipeline total, not from the rows shown', () => {
        expect(errorsSource).toContain('representedEventCount');
        expect(errorsSource).toContain('hiddenEventCount');
    });
});

describe('the health verdict', () => {
    it('colours the whole card, not just a pill on a neutral ground', () => {
        expect(errorsSource).toContain('heroToneClass');
        expect(errorsSource).toMatch(/<div class="[^"]*rounded-2xl border px-5 py-4 \{heroToneClass\(/);
        // The verdict opens the System card rather than sitting in a second card of its own.
        expect(errorsSource.indexOf('{#snippet status()}')).toBeLessThan(errorsSource.indexOf('{heroToneClass('));
    });

    it('takes every tone from the one status helper, so running work is never amber', () => {
        // NT-04: running work was amber here while Notifications says a job in flight needs
        // nobody, and healthy was emerald in the verdict but brand on the cards. The mapping
        // itself is unit-tested in utils/status-tone.test.ts.
        expect(errorsSource).toContain("from '../utils/status-tone'");
        expect(errorsSource).toContain('STATUS_SURFACE[statusTone(value)]');
        expect(errorsSource).toContain('STATUS_PILL[statusTone(value)]');
        expect(errorsSource).not.toMatch(/emerald-|amber-|accent-/);
    });

    it('prints statuses in translated sentence case, keeping the raw word in a title', () => {
        expect(errorsSource).toContain('statusLabelKey(value)');
        expect(errorsSource).toContain('{statusLabel(overallStatus())}');
        expect(errorsSource).toContain('title={overallStatus()}');
        expect(errorsSource).not.toMatch(/text-xs font-bold uppercase tracking-(widest|wider|\[0\.2em\])[^"`]*"?>?\s*\{(overallStatus|incident\.status|event\.severity)/);
        expect(errorsSource).not.toContain('tracking-[0.18em]');
        // English fallbacks no longer leak into other languages.
        expect(errorsSource).not.toContain("fallback = 'Unknown'");
        expect(errorsSource).not.toContain("last_reconnect_reason, 'None')");
    });

    it('keeps export plumbing out of the health reading', () => {
        expect(errorsSource).not.toContain("errors_health_snapshots', { default: 'Health Snapshots' }");
        expect(errorsSource).not.toContain('backend events\n');
    });
});

describe('filtered rows', () => {
    it('are rendered by the health timeline as their own kind', () => {
        expect(timelineSource).toContain("isFault ? 'fault' : 'filtered'");
        expect(timelineSource).toContain("data-row-kind={isFault ? 'fault' : 'filtered'}");
    });

    it('never borrow the amber that means a person is needed', () => {
        // §1.3: amber is reserved for outstanding work. A rejected frame wants nothing.
        expect(timelineSource).toContain("'border-l-slate-300 bg-slate-50/55");
        expect(timelineSource).not.toContain('data-needs-review="true"');
    });

    it('state their reason in words rather than by colour alone', () => {
        expect(timelineSource).toContain('jobs.errors_drop_reason_row.');
    });

    it('keeps fault drops visible and distinct from expected filtering', () => {
        expect(timelineSource).toContain("row.kind === 'fault'");
        expect(timelineSource).toContain("data-row-kind={isFault ? 'fault' : 'filtered'}");
        expect(timelineSource).toContain('border-l-rose-400');
    });

    it('states each outcome once instead of repeating status at the end of the row', () => {
        expect(timelineSource).not.toContain("jobs.errors_activity_recorded_short");
        expect(timelineSource).not.toContain("jobs.errors_activity_no_record");
        expect(timelineSource).not.toContain("jobs.errors_activity_not_saved");
    });
});

describe('filtered frame preview', () => {
    it('honours the hover pop-out contract', () => {
        // §4: hover alone fails WCAG 2.2 AA.
        expect(filteredPreviewSource).toContain('onpointerenter');
        expect(filteredPreviewSource).toContain('onfocusin');
        expect(filteredPreviewSource).toContain('CLOSE_GRACE_MS = 120');
        expect(filteredPreviewSource).toContain("event.key === 'Escape'");
        expect(filteredPreviewSource).toContain('aria-expanded');
        expect(filteredPreviewSource).toContain('focus-ring');
        expect(filteredPreviewSource).toContain('motion-reduce:animate-none');
        expect(filteredPreviewSource).toContain('show();');
    });

    it('portals the panel out of the clipped timeline card and keeps it on screen', () => {
        expect(filteredPreviewSource).toContain("import { portal } from '../utils/portal'");
        expect(filteredPreviewSource).toContain('use:portal');
        expect(filteredPreviewSource).toContain("class=\"fixed z-[70]");
        expect(filteredPreviewSource).toContain('getBoundingClientRect()');
        expect(filteredPreviewSource).toContain("window.addEventListener('scroll', follow, true)");
        expect(filteredPreviewSource).toContain('max-w-[calc(100vw-16px)]');
    });

    it('degrades a rotated-away frame to a placeholder of the same size', () => {
        // §1.5: media must never leave a hole that shifts the row.
        expect(filteredPreviewSource).toContain('onerror');
        expect(filteredPreviewSource).toContain('errors_filtered_frame_gone');
        expect(filteredPreviewSource).toMatch(/failed[\s\S]*?h-9 w-9/);
    });

    it('meets the touch target floor', () => {
        expect(filteredPreviewSource).toContain('min-h-11');
    });
});
