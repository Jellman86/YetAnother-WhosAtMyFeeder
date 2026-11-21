import { get } from 'svelte/store';
import { _ } from 'svelte-i18n';
import { announcer } from '../components/Announcer.svelte';
import { birdNames } from '../naming';
import { detectionsStore } from '../stores/detections.svelte';
import { settingsStore } from '../stores/settings.svelte';
import { createAnalysisAnnouncements, type AnalysisWords } from './analysis-announcements';

/** Speak card analyses once for the page, through the app's shared polite announcer. */
export function installAnalysisAnnouncements(): void {
    const say = (key: string, values: Record<string, string | number>, fallback: string): string =>
        get(_)(key, { values, default: fallback });
    const words = (): AnalysisWords => ({
        startedOne: (species) => say('detection.card_analysis.announce_started', { species }, 'Analysing {species}'),
        startedMany: (count) => say('detection.card_analysis.announce_started_count', { count }, '{count, plural, one {Analysing # visit} other {Analysing # visits}}'),
        finishedOne: (species) => say('detection.card_analysis.announce_finished', { species }, 'Analysis finished for {species}'),
        finishedMany: (count) => say('detection.card_analysis.announce_finished_count', { count }, '{count, plural, one {Analysis finished for # visit} other {Analysis finished for # visits}}')
    });
    // A visit the live list does not hold is said as a count ("1 visit"), never by a guessed name.
    const namesOf = (eventId: string): string | null => {
        const detection = detectionsStore.detections.find((item) => item.frigate_event === eventId);
        return detection ? get(birdNames)(detection, settingsStore.displayCommonNames, settingsStore.scientificNamePrimary).primary : null;
    };
    detectionsStore.setReclassificationListener(
        createAnalysisAnnouncements({ announce: (text) => announcer.announce(text), nameOf: namesOf, words })
    );
}
