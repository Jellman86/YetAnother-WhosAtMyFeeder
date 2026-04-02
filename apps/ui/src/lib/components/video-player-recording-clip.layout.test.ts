import { describe, expect, it } from 'vitest';
import videoPlayerSource from './VideoPlayer.svelte?raw';
import mediaApiSource from '../api/media.ts?raw';

describe('video player canonical full-visit wiring', () => {
    it('keeps playback on the canonical clip route and uses full-visit state only for indicators', () => {
        expect(mediaApiSource).toContain('getRecordingClipUrl');
        expect(mediaApiSource).toContain('recording-clip.mp4');
        expect(mediaApiSource).not.toContain('clip_variant: options.clipVariant');

        expect(videoPlayerSource).toContain('initialFullVisitPromoted');
        expect(videoPlayerSource).toContain('fullVisitPromoted');
        expect(videoPlayerSource).toContain('const base = getClipUrl(frigateEvent);');
        expect(videoPlayerSource).toContain('getRecordingClipUrl');
        expect(videoPlayerSource).not.toContain("type ClipVariant = 'event' | 'recording'");
        expect(videoPlayerSource).not.toContain('selectedClipVariant');
        expect(videoPlayerSource).not.toContain('recordingClipAvailable');
        expect(videoPlayerSource).not.toContain('recordingClipFetched');
        expect(videoPlayerSource).not.toContain('initialClipVariant');
        expect(videoPlayerSource).not.toContain('initialRecordingClipFetched');
    });

    it('removes the playback toggle but keeps a full-visit badge and wrapping action row', () => {
        expect(videoPlayerSource).toContain("fullVisitPromoted\n            ? $_('video_player.full_visit_badge'");
        expect(videoPlayerSource).toContain('probeFullVisitPromotion');
        expect(videoPlayerSource).toContain('flex-wrap items-center justify-end gap-2');
        expect(videoPlayerSource).not.toContain("video_player.event_clip_toggle");
        expect(videoPlayerSource).not.toContain("video_player.full_visit_toggle");
    });
});
