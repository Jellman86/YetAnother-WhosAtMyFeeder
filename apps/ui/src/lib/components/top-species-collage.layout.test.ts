import { describe, expect, it } from 'vitest';

import collageSource from './TopSpeciesCollage.svelte?raw';
import leaderboardSource from '../pages/Species.svelte?raw';

describe('top species collage contract', () => {
    it('loads lightweight photographs from the selected leaderboard window', () => {
        expect(collageSource).toContain('collageDateQuery(span, windowStart, windowEnd)');
        expect(collageSource).toContain("fields: 'list'");
        expect(collageSource).toContain('startDate: dateQuery.startDate');
        expect(collageSource).toContain('endDate: dateQuery.endDate');
        expect(collageSource).toContain('signal: controller.signal');
        expect(collageSource).toContain('requestKey: null');
    });

    it('degrades broken media silently and fully respects reduced motion', () => {
        expect(collageSource).toContain('onerror={() => markPhotoUnavailable(photo.frigate_event)}');
        expect(collageSource).toContain('let reduceMotion = $state(false)');
        expect(collageSource).toContain('duration: reduceMotion ? 0 : FADE_MS');
        expect(collageSource).toContain('!reduceMotion && photos.length > TILES');
    });

    it('only uses feeder photographs for source modes they can support', () => {
        expect(leaderboardSource).toContain("sourceMode !== 'heard'");
        expect(leaderboardSource).toContain('sourceLeader.count > 0');
        expect(leaderboardSource).toContain('sourceMode={sourceMode}');
        expect(leaderboardSource).toContain('windowStart={leaderboardWindow?.start ?? null}');
        expect(leaderboardSource).toContain('windowEnd={leaderboardWindow?.end ?? null}');
        expect(collageSource).toContain("sourceMode === 'both'");
        expect(collageSource).toContain("$_('leaderboard.most_active'");
    });
});
