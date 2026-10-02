import { describe, expect, it } from 'vitest';
import recentAudioSource from './RecentAudio.svelte?raw';

describe('RecentAudio dashboard widget layout', () => {
    it('summarises what was heard and links onward to the call-by-call history', () => {
        // Only the latest call is fetched; the raw feed lives on the audio history page.
        expect(recentAudioSource).toContain('const RECENT_AUDIO_LIMIT = 1;');
        expect(recentAudioSource).toContain('fetchRecentAudio(RECENT_AUDIO_LIMIT, signal)');
        expect(recentAudioSource).toContain('data-dashboard-most-heard');
        expect(recentAudioSource).toContain('data-dashboard-latest-call');
        expect(recentAudioSource).toContain("onNavigate?.('/audio')");
        expect(recentAudioSource).toMatch(/data-audio-history-action[^>]+rounded-full/);
    });

    it('explains a microphone that matched no visit without raising it as work', () => {
        // Amber is for what needs a person; this is context.
        expect(recentAudioSource).toContain('data-dashboard-no-match');
        expect(recentAudioSource).not.toContain('accent-');
        expect(recentAudioSource).not.toContain('amber-');
    });

    it('serializes background refreshes and stops them with the component lifecycle', () => {
        expect(recentAudioSource).toContain('scheduleAudioPoll();');
        expect(recentAudioSource).toContain('scheduleSummaryPoll();');
        expect(recentAudioSource).toContain('if (!document.hidden)');
        expect(recentAudioSource).not.toContain('setInterval(loadAudio');
        expect(recentAudioSource).not.toContain('setInterval(loadSummary');
        expect(recentAudioSource).toContain('audioLoader.dispose();');
        expect(recentAudioSource).toContain('summaryLoader.dispose();');
    });
});
