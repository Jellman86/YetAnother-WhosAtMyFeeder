import { expect, it } from 'vitest';
import dashboard from './Dashboard.svelte?raw';
import species from './Species.svelte?raw';
import detail from '../components/SpeciesDetailModal.svelte?raw';
import recentAudio from '../components/RecentAudio.svelte?raw';

it.each([dashboard, species, detail, recentAudio])('observes only new guest public history versions without remount refresh duplication', (source) => {
    expect(source).toContain('let handledPublicHistoryVersion = detectionsStore.publicHistoryVersion;');
    expect(source).toContain('if (version <= handledPublicHistoryVersion || !authStore.isGuest) return;');
});

it('clears dashboard observation summary before revalidation without clearing catalogue data', () => {
    expect(dashboard).toContain('summaryLoader.invalidate();');
    expect(dashboard).toContain('audioSummaryLoader.invalidate();');
});

it('clears visual/audio leaderboard rows, heatmaps and portraits before revalidation', () => {
    expect(species).toContain('species = [];\n            audioSpecies = [];');
    expect(species).toContain('activityHeatmap = null;');
    expect(species).toContain('speciesHeatmap = null;');
    expect(species).toContain('portraits = [];');
    expect(species).toContain('if (loadGeneration !== leaderboardLoadGeneration || controller.signal.aborted) return;');
});

it('revalidates local species records separately from reference/catalogue enrichment', () => {
    expect(detail).toContain('statsLoader.invalidate();');
    expect(detail).toContain('if (hadLocalRecord) onclose();');
    expect(detail).toContain('showVideo = false;');
    expect(detail).toContain('selectedSighting = null;');
    expect(detail).toContain('if (!observedLocalRecord && !statsPending) return;');
    expect(detail).toContain('if (destroyed || statsPending || version !== detectionsStore.publicHistoryVersion || !authStore.isGuest) return;');
});
