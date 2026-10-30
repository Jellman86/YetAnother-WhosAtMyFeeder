import { describe, expect, it } from 'vitest';

import dashboard from '../pages/Dashboard.svelte?raw';
import events from '../pages/Events.svelte?raw';
import about from '../pages/About.svelte?raw';
import species from '../pages/Species.svelte?raw';
import audioHistory from '../pages/AudioHistory.svelte?raw';
import detectionModal from './DetectionModal.svelte?raw';
import reviewQueueModal from './ReviewQueueModal.svelte?raw';
import lazyDialogs from './lazy-dialogs.ts?raw';

const pages = { Dashboard: dashboard, Events: events, About: about, Species: species, AudioHistory: audioHistory };
const dialogs = ['DetectionModal', 'SpeciesDetailModal', 'GardenCaptureModal', 'VideoPlayer', 'ReviewQueueModal'];

describe('dialogs load on first open', () => {
    it.each(Object.entries(pages))('%s imports no record dialog or player up front', (_name, source) => {
        for (const dialog of dialogs) expect(source).not.toMatch(new RegExp(`import ${dialog} from`));
        expect(source).toContain("import LazyModal from '../components/LazyModal.svelte'");
    });

    it('imports each dialog through one shared, retryable loader', () => {
        for (const dialog of dialogs) expect(lazyDialogs).toContain(`lazyComponent(() => import('./${dialog}.svelte'))`);
    });

    it('renders AI text without putting markdown-it in the record dialog', () => {
        expect(detectionModal).not.toContain("from '../utils/markdown'");
        expect(detectionModal).toContain('<MarkdownText text={aiAnalysis} />');
    });
});

describe('classifier labels', () => {
    it.each(Object.entries(pages))('%s never reads the 10,000-name label list itself', (_name, source) => {
        expect(source).not.toContain('fetchClassifierLabels');
        expect(source).not.toMatch(/\bclassifierLabels\b/);
    });

    it('are read by the record dialog only when its species search fails', () => {
        expect(detectionModal).not.toContain('classifierLabels:');
        expect(detectionModal).toContain("classifierLabelsStore.searchFallback('', 20)");
        expect(detectionModal).toContain('if (!hasOwnerDetectionActions || !showTagDropdown) return;');
    });

    it('are not a prop of the review queue, which searches the catalogue', () => {
        expect(reviewQueueModal).not.toMatch(/^\s+labels\??: /m);
        expect(reviewQueueModal).not.toMatch(/let \{[^}]*\blabels\b/);
    });
});
