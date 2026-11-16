import { describe, expect, it } from 'vitest';
import detectionCardSource from './DetectionCard.svelte?raw';
import detectionModalSource from './DetectionModal.svelte?raw';

describe('upstream missing detection UI', () => {
    it('surfaces missing Frigate state on detection cards', () => {
        expect(detectionCardSource).toContain("detection.frigate_status === 'missing'");
        expect(detectionCardSource).toContain("$_('detection.upstream_missing.card_label'");
        expect(detectionCardSource).toContain("$_('detection.upstream_missing.card_title'");
    });

    it('surfaces missing Frigate details in the detection modal', () => {
        expect(detectionModalSource).toContain("detection.frigate_status === 'missing'");
        // "Gone" comes from the reading, never from a failed check: Frigate being down is not an absence.
        expect(detectionModalSource).not.toContain('has_frigate_event === false');
        expect(detectionModalSource).toContain("frigateReading === 'gone'");
        expect(detectionModalSource).toContain('frigateEventNotice(frigateReading, $_)');
        expect(detectionModalSource).toContain('videoStatusNoticeVisible');
        expect(detectionModalSource).toContain('missingEventNoticeVisible');
        expect(detectionModalSource).toContain('FRIGATE_MISSING_DOCS_URL');
        expect(detectionModalSource).toContain("$_('detection.upstream_missing.learn_more'");
        expect(detectionModalSource).toContain("$_('detection.upstream_missing.last_checked'");
        expect(detectionModalSource).not.toContain("$_('detection.upstream_missing.card_title'");
        expect(detectionModalSource).not.toContain('rounded-2xl border border-orange-200 bg-orange-50/90 p-4');
        expect(detectionModalSource).not.toContain("$_('detection.upstream_missing.compact_label'");
    });

    it('does not also show the severe video failure card for missing-event failures', () => {
        expect(detectionModalSource).toContain('videoStatusNoticeTone');
        expect(detectionModalSource).toContain('videoStatusShowTechnicalDetails');
        expect(detectionModalSource).toContain('The standalone "Video Analysis Failed" red card has been folded');
        expect(detectionModalSource).not.toContain("detection.video_classification_status === 'failed' && !suppressVideoFailureForMissingEvent");
        expect(detectionModalSource).not.toContain('suppressVideoFailureForMissingEvent');
        expect(detectionModalSource).toContain('hasFrigateMediaIssue(detection) && !missingEventMetadataGone');
    });

    it('offers technical details only for a recorded error or diagnostics', () => {
        expect(detectionModalSource).not.toContain('videoFailureInsight.causes.length === 0 && videoFailureInsight.checks.length === 0');
        expect(detectionModalSource).toContain("Boolean((detection.video_classification_error || '').trim()) || Boolean(videoClassificationDiagnostics)");
    });
});
