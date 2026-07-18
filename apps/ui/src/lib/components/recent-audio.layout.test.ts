import { describe, expect, it } from 'vitest';
import recentAudioSource from './RecentAudio.svelte?raw';

describe('RecentAudio dashboard widget layout', () => {
    it('keeps the dashboard preview concise and links onward to history', () => {
        expect(recentAudioSource).toContain('const RECENT_AUDIO_LIMIT = 4;');
        expect(recentAudioSource).toContain('fetchRecentAudio(RECENT_AUDIO_LIMIT)');
        expect(recentAudioSource).toContain("onNavigate?.('/audio')");
    });

    it('renders spectrograms as images instead of CSS backgrounds', () => {
        expect(recentAudioSource).toContain('src={spec}');
        expect(recentAudioSource).toContain('object-cover');
        expect(recentAudioSource).not.toContain('background-image: url');
    });
});
