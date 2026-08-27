import { describe, expect, it } from 'vitest';

import errorsSource from './Errors.svelte?raw';
import fieldLogSource from '../components/FieldLog.svelte?raw';
import filteredPreviewSource from '../components/FilteredFramePreview.svelte?raw';

/**
 * Structural intent for the Health page timeline, per layout-patterns §7.
 * These assert the decisions that are easy to undo by accident, not the markup.
 */

describe('health page timeline', () => {
    it('reuses Field log rather than growing a second timeline idiom', () => {
        expect(errorsSource).toContain("import FieldLog from '../components/FieldLog.svelte'");
        expect(errorsSource).toContain('data-health-timeline');
        expect(errorsSource).toMatch(/<FieldLog[\s\S]*?rows=\{timelineRows\}/);
    });

    it('windows visits to the same slice of time the counters describe', () => {
        // §1.1: a header saying one thing while cards count another is broken.
        expect(errorsSource).toContain('instanceWindowMs');
        expect(errorsSource).toMatch(/withinDeskWindow\(\s*detectionsStore\.detections,\s*Date\.now\(\),\s*instanceWindow\s*\)/);
        expect(errorsSource).toContain('errors_activity_no_window');
    });

    it('groups frames into visits before showing them', () => {
        // §1.2: users see birds, not frames.
        expect(errorsSource).toContain('groupDetectionsIntoVisits');
        expect(errorsSource).toContain('reviewThreshold');
    });

    it('keeps subsystem detail available rather than deleting it', () => {
        expect(errorsSource).toContain('data-subsystem-detail');
        expect(errorsSource).toContain('errors_subsystems_title');
    });

    it('states the remainder from the pipeline total, not from the rows shown', () => {
        expect(errorsSource).toContain('hiddenEventCount');
    });
});

describe('the health verdict', () => {
    it('colours the whole card, not just a pill on a neutral ground', () => {
        expect(errorsSource).toContain('heroToneClass');
        expect(errorsSource).toMatch(/<div class="rounded-3xl border p-6 \{heroToneClass\(/);
    });

    it('is green when healthy and amber only when something wants a person', () => {
        const fn = errorsSource.slice(
            errorsSource.indexOf('function heroToneClass'),
            errorsSource.indexOf('function toneClass')
        );
        const healthy = fn.slice(fn.indexOf("'ok', 'healthy', 'normal'"), fn.indexOf("'degraded'"));
        expect(healthy).toContain('emerald');
        const degraded = fn.slice(fn.indexOf("'degraded'"), fn.indexOf("'critical'"));
        expect(degraded).toContain('amber-');
        // accent-* is emerald in the classic theme, which would paint degraded green.
        expect(degraded).not.toContain('accent-');
    });

    it('leaves a state it has not measured in slate rather than claiming health', () => {
        // The fallback branch is what an unknown status hits, and it must not be green.
        const fn = errorsSource.slice(
            errorsSource.indexOf('function heroToneClass'),
            errorsSource.indexOf('function toneClass')
        );
        const fallback = fn.slice(fn.lastIndexOf('return '));
        expect(fallback).toContain('slate');
        expect(fallback).not.toContain('emerald');
    });

    it('keeps export plumbing out of the health reading', () => {
        expect(errorsSource).not.toContain("errors_health_snapshots', { default: 'Health Snapshots' }");
        expect(errorsSource).not.toContain('backend events\n');
    });
});

describe('filtered rows', () => {
    it('are rendered by Field log as their own kind', () => {
        expect(fieldLogSource).toContain("row.kind === 'filtered'");
        expect(fieldLogSource).toContain('data-row-kind="filtered"');
    });

    it('never borrow the amber that means a person is needed', () => {
        // §1.3: amber is reserved for outstanding work. A rejected frame wants nothing.
        const filteredBlock = fieldLogSource.slice(
            fieldLogSource.indexOf("row.kind === 'filtered'"),
            fieldLogSource.indexOf('{:else}', fieldLogSource.indexOf("row.kind === 'filtered'"))
        );
        expect(filteredBlock).not.toMatch(/accent-\d/);
        expect(filteredBlock).toContain('data-needs-review="false"');
    });

    it('state their reason in words rather than by colour alone', () => {
        expect(fieldLogSource).toContain('jobs.errors_drop_reason_row.');
    });

    it('leave the dashboard untouched by defaulting rows from visits', () => {
        expect(fieldLogSource).toMatch(/rows \?\? visits\.map/);
    });
});

describe('filtered frame preview', () => {
    it('honours the hover pop-out contract', () => {
        // §4: hover alone fails WCAG 2.2 AA.
        expect(filteredPreviewSource).toContain('onmouseenter');
        expect(filteredPreviewSource).toContain('onfocusin');
        expect(filteredPreviewSource).toContain('CLOSE_GRACE_MS = 120');
        expect(filteredPreviewSource).toContain("event.key === 'Escape'");
        expect(filteredPreviewSource).toContain('aria-expanded');
        expect(filteredPreviewSource).toContain('focus-ring');
        expect(filteredPreviewSource).toContain('motion-safe:');
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
