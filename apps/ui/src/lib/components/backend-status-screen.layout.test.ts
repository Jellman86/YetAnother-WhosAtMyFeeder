import { describe, expect, it } from 'vitest';
import source from './BackendStatusScreen.svelte?raw';

describe('BackendStatusScreen startup progress', () => {
    it('polls the real startup contract and does not invent percentage progress', () => {
        expect(source).toContain('fetchStartupStatus');
        expect(source).toContain("startupStatus?.status === 'starting'");
        expect(source).toContain('aria-valuenow={startupProgress}');
        expect(source).toContain("$_(`auth.startup_phase_${startupPhase}`");
        expect(source).toContain('startupStatusPollMs');
    });

    it('keeps genuine backend failures distinct from an active startup', () => {
        expect(source).toContain("startupStatus?.status === 'failed'");
        expect(source).toContain("role={showingUnavailable || startupFailed ? 'alert' : 'status'}");
        expect(source).toContain("mode === 'unavailable' && startupStatusChecked && !startupActive");
    });
});
