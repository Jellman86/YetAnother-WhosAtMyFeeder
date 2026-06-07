import { describe, expect, it } from 'vitest';
import recentAudioSource from './RecentAudio.svelte?raw';

describe('RecentAudio dashboard widget layout', () => {
    it('requests enough detections to fill the dashboard card', () => {
        expect(recentAudioSource).toContain('const RECENT_AUDIO_LIMIT = 10;');
        expect(recentAudioSource).toContain('fetchRecentAudio(RECENT_AUDIO_LIMIT)');
        expect(recentAudioSource).not.toContain('fetchRecentAudio(5)');
    });

    it('renders spectrograms as images instead of CSS backgrounds', () => {
        expect(recentAudioSource).toContain('src={spec}');
        expect(recentAudioSource).toContain('object-cover');
        expect(recentAudioSource).not.toContain('background-image: url');
    });
});
