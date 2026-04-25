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
        expect(detectionModalSource).toContain("detection.has_frigate_event === false");
        expect(detectionModalSource).toContain("detection.video_classification_error === 'event_not_found'");
        expect(detectionModalSource).toContain('FRIGATE_MISSING_DOCS_URL');
        expect(detectionModalSource).toContain('src={FRIGATE_LOGO_URL}');
        expect(detectionModalSource).toContain("$_('detection.upstream_missing.compact_label'");
        expect(detectionModalSource).toContain("$_('detection.upstream_missing.learn_more'");
        expect(detectionModalSource).toContain("$_('detection.upstream_missing.last_checked'");
        expect(detectionModalSource).not.toContain('rounded-2xl border border-orange-200 bg-orange-50/90 p-4');
    });

    it('does not also show the severe video failure card for missing-event failures', () => {
        expect(detectionModalSource).toContain('suppressVideoFailureForMissingEvent');
        expect(detectionModalSource).toContain("detection.video_classification_status === 'failed' && !suppressVideoFailureForMissingEvent");
        expect(detectionModalSource).toContain('hasFrigateMediaIssue(detection) && !missingEventMetadataGone');
    });
});
