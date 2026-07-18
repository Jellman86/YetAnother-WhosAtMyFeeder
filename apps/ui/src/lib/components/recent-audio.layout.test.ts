import { describe, expect, it } from 'vitest';
import recentAudioSource from './RecentAudio.svelte?raw';

describe('RecentAudio dashboard widget layout', () => {
    it('keeps the dashboard preview concise and links onward to history', () => {
        expect(recentAudioSource).toContain('const RECENT_AUDIO_LIMIT = 4;');
        expect(recentAudioSource).toContain('fetchRecentAudio(RECENT_AUDIO_LIMIT, signal)');
        expect(recentAudioSource).toContain("onNavigate?.('/audio')");
        expect(recentAudioSource).toMatch(/data-audio-history-action[^>]+rounded-full/);
    });

    it('renders spectrograms as images instead of CSS backgrounds', () => {
        expect(recentAudioSource).toContain('src={spec}');
        expect(recentAudioSource).toContain('object-cover');
        expect(recentAudioSource).not.toContain('background-image: url');
    });

    it('serializes background refreshes and stops them with the component lifecycle', () => {
        expect(recentAudioSource).toContain('scheduleAudioPoll();');
        expect(recentAudioSource).toContain('scheduleSummaryPoll();');
        expect(recentAudioSource).toContain('if (!document.hidden)');
        expect(recentAudioSource).not.toContain('setInterval(loadAudio');
        expect(recentAudioSource).not.toContain('setInterval(loadSummary');
        expect(recentAudioSource).toContain('audioController?.abort();');
        expect(recentAudioSource).toContain('summaryController?.abort();');
    });
});
