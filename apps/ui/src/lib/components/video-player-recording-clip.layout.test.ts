import { describe, expect, it } from 'vitest';
import videoPlayerSource from './VideoPlayer.svelte?raw';
import mediaApiSource from '../api/media.ts?raw';

describe('video player recording clip variant wiring', () => {
    it('adds a recording clip variant to the media API and player state', () => {
        expect(mediaApiSource).toContain('getRecordingClipUrl');
        expect(mediaApiSource).toContain('recording-clip.mp4');

        expect(videoPlayerSource).toContain("type ClipVariant = 'event' | 'recording'");
        expect(videoPlayerSource).toContain('selectedClipVariant');
        expect(videoPlayerSource).toContain('recordingClipAvailable');
        expect(videoPlayerSource).toContain('recordingClipFetched');
        expect(videoPlayerSource).toContain('initialRecordingClipFetched');
        expect(videoPlayerSource).toContain('getRecordingClipUrl');
        expect(videoPlayerSource).toContain("selectedClipVariant === 'recording' && !recordingClipFetched");
        expect(videoPlayerSource).toContain('!recordingClipFetched && recordingClipAvailable');
    });

    it('keeps persisted full visits on the canonical clip route and lets the mobile action row wrap', () => {
        expect(videoPlayerSource).toContain("selectedClipVariant === 'recording' && !recordingClipFetched ? getRecordingClipUrl(frigateEvent) : getClipUrl(frigateEvent)");
        expect(videoPlayerSource).toContain('recordingClipFetched = initialRecordingClipFetched');
        expect(videoPlayerSource).toContain('flex-wrap items-center justify-end gap-2');
    });
});
