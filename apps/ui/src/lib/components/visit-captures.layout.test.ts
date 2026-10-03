import { describe, expect, it } from 'vitest';
import visitCapturesSource from './VisitCaptures.svelte?raw';
import fieldLogSource from './FieldLog.svelte?raw';
import visitRowSource from './FieldLogVisitRow.svelte?raw';
import healthTimelineSource from './HealthActivityTimeline.svelte?raw';
import eventsSource from '../pages/Events.svelte?raw';

/**
 * A visit row and its captures are one object. The captures used to hang below the row as a
 * separate block of full detection rows, repeating the species, camera and day on every line,
 * behind a native disclosure that drew two markers. These hold the integrated shape.
 */
describe('visit captures read as part of their visit', () => {
    it('is a disclosure button that states its state, clears the touch floor and shows focus', () => {
        expect(visitCapturesSource).not.toContain('<details');
        expect(visitCapturesSource).not.toContain('<summary');
        expect(visitCapturesSource).toContain('aria-expanded={open}');
        expect(visitCapturesSource).toContain('aria-controls={panelId}');
        const marker = visitCapturesSource.indexOf('data-visit-captures-toggle');
        const toggle = visitCapturesSource.slice(visitCapturesSource.lastIndexOf('<button', marker), marker);
        // Both layouts' class strings sit in the one button tag; each clears the floor and shows focus.
        expect(toggle.match(/min-h-11/g)?.length).toBe(2);
        expect(toggle.match(/focus-visible:ring-2/g)?.length).toBe(2);
        expect(visitCapturesSource).toContain("{open ? 'rotate-180' : ''}");
    });

    it('offers no list for a single capture, which is already the row', () => {
        expect(visitCapturesSource).toContain('hasCaptureTimeline(visit)');
    });

    it('lists captures by time to the second without repeating the visit on every line', () => {
        expect(visitCapturesSource).not.toContain('DetectionRow');
        expect(visitCapturesSource).toContain("second: '2-digit'");
        expect(visitCapturesSource).toContain('captureFacts(capture, visit)');
        expect(visitCapturesSource).toContain('<DetectionPreview');
        expect(visitCapturesSource).toContain('visits.open_capture_at');
    });

    it('states progress, emptiness and failure in words', () => {
        expect(visitCapturesSource).toContain('visits.loaded_of_total');
        expect(visitCapturesSource).toContain('visits.captures_empty');
        expect(visitCapturesSource).toContain('role="alert"');
        expect(visitCapturesSource).toContain('aria-busy={loading}');
    });

    it('loads only when opened and reuses the page it already has', () => {
        // Reopening must not refetch: the membership key already invalidates stale pages.
        expect(visitCapturesSource).not.toContain('if (open) void load(true)');
        expect(visitCapturesSource).toContain('if (!open) return;');
    });

    it('opens a field log visit from its time, onto the same thread and columns', () => {
        // The time is the visit's handle; the captures are children of the row, not a block below it.
        expect(fieldLogSource).toContain('<FieldLogVisitRow');
        expect(fieldLogSource).not.toContain('VisitCaptures');
        expect(visitRowSource).toContain('data-field-log-time-toggle');
        expect(visitRowSource).toContain('aria-expanded={expanded}');
        expect(visitRowSource).toContain('aria-controls={listId}');
        expect(visitRowSource).toMatch(/data-field-log-time-toggle[\s\S]*min-h-11|min-h-11[\s\S]*data-field-log-time-toggle/);
        // One column template: a capture's time, node and score sit under its visit's.
        expect(visitRowSource).toContain('col-span-full grid grid-cols-subgrid');
        expect(fieldLogSource).toContain('{grid}');
        // Visit nodes are solid; capture nodes are hollow, the visit photo's filled, on a tinted stretch.
        expect(visitRowSource).toContain('data-field-log-capture-dot="capture"');
        expect(visitRowSource).toContain('data-field-log-capture-dot="shown"');
        expect(visitRowSource).toContain('new VisitCaptureList(');
        expect(visitRowSource).toContain("second: '2-digit'");
        expect(healthTimelineSource).toContain('layout="inline"');
    });

    it('states captures and the busiest capture as two numbers, and keeps a single capture plain', () => {
        expect(visitRowSource).toContain('data-field-log-captures');
        expect(visitRowSource).toContain('data-field-log-birds');
        expect(visitRowSource).not.toContain('×{');
        expect(visitRowSource).toContain('(server?.capture_count ?? 0) > 1');
    });

    it('keeps confirmed scores on the semantic success scale in the field log', () => {
        expect(fieldLogSource + visitRowSource).not.toContain('emerald');
        expect(visitRowSource).toContain('text-success-700 dark:text-success-300');
    });

    it('loads in the shape of real rows, states failure, and never animates under reduced motion', () => {
        expect(fieldLogSource).toContain('data-field-log-placeholder');
        expect(fieldLogSource).toContain('dashboard.field_log.unavailable');
        for (const source of [fieldLogSource, visitRowSource]) {
            expect(source.match(/animate-pulse/g)?.length).toBe(source.match(/animate-pulse motion-reduce:animate-none/g)?.length);
        }
    });

    it('closes Explorer cards and rows as a footer, without stretching neighbouring cards open', () => {
        expect(eventsSource).toContain('has-[[data-visit-captures-open]]:items-start');
        expect(eventsSource.match(/<VisitCaptures /g)?.length).toBe(2);
        expect(eventsSource).toContain('[&>[data-detection-row]]:border-b-0');
    });
});
