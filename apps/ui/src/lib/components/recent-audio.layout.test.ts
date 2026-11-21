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
        // A kit button like every other on the desk, not a pill (round 4).
        expect(recentAudioSource).toMatch(/data-audio-history-action[^>]*class="btn btn-secondary/);
        expect(recentAudioSource).not.toMatch(/data-audio-history-action[^>]+rounded-full/);
    });

    it('names the species heard and leaves the call totals to the day bar', () => {
        expect(recentAudioSource).toContain("$_('dashboard.desk.species_heard'");
        expect(recentAudioSource).toContain('data-dashboard-species-heard');
        expect(recentAudioSource).not.toContain('dashboard.day_bar.calls_heard');
        expect(recentAudioSource).not.toContain('dashboard.day_bar.cross_confirmed');
        expect(recentAudioSource).not.toContain('{matchedCalls.toLocaleString()}');
    });

    it('explains a microphone that matched no visit without raising it as work', () => {
        // Amber is for what needs a person; this is context.
        expect(recentAudioSource).toContain('data-dashboard-no-match');
        expect(recentAudioSource).not.toMatch(/\baccent-\d/);
        expect(recentAudioSource).not.toContain('amber-');
    });

    it('serializes background refreshes and stops them with the component lifecycle', () => {
        // Serial reads, the hidden-tab pause, following the live stream and the stop are the shared
        // reading's, tested with timers in app/live-reading.test.ts; here the card is only required to
        // use it, to pass on announced calls, and to stop it.
        expect(recentAudioSource).toContain('latestCallReading = startLiveReading({');
        expect(recentAudioSource).toContain('live: () => followsLiveStream,');
        expect(recentAudioSource).toContain('latestCallReading?.changed();');
        expect(recentAudioSource).toContain('latestCallReading?.stop();');
        expect(recentAudioSource).not.toContain('setInterval(loadAudio');
        expect(recentAudioSource).toContain('audioLoader.dispose();');
    });

    it('shows the window summary the Dashboard read for the day bar instead of reading it again', () => {
        expect(recentAudioSource).not.toContain('fetchAudioSummary');
        expect(recentAudioSource).toContain('summary: AudioSummaryResponse | null;');
        expect(recentAudioSource).toContain('{#if (loading || summaryLoading) && !summary}');
    });
});
