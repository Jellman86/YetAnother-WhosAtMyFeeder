import { describe, expect, it } from 'vitest';
import detectionRowSource from './DetectionRow.svelte?raw';
import eventsPageSource from '../pages/Events.svelte?raw';
import appearanceSource from './settings/AppearanceSettings.svelte?raw';

/**
 * #270: "The explorer section tends to get crowded fast, the cards there are
 * very big... What I am interested is comparing the visiting times. So I can
 * scroll the list fast to get to the time I want."
 */
describe('the Explorer list row', () => {
    it('leads with the time, in a column whose digits line up', () => {
        // The alignment is the whole point: it is what makes scrolling for a
        // time work. A proportional font would defeat it.
        expect(detectionRowSource).toMatch(/grid-cols-\[3\.25rem_/);
        const timeBlock = detectionRowSource.match(/font-display[^"]*tabular-nums[^"]*"[\s\S]{0,140}formatTime/);
        expect(timeBlock, 'the first column should be the time, tabular').not.toBeNull();
    });

    it('flags a detection needing a person with all three signals', () => {
        // Never colour alone: a wash, a rule and a worded reason.
        expect(detectionRowSource).toContain('from-accent-500');
        expect(detectionRowSource).toContain('bg-accent-500');
        expect(detectionRowSource).toContain('events.row_below_threshold');
    });

    it('takes what needs a person from the owner threshold, not a literal', () => {
        // The dashboard's review queue and field log already answer this
        // question; a second rule here would flag a different set of rows.
        expect(detectionRowSource).toContain("import { needsReview }");
        expect(detectionRowSource).toContain('classification_threshold');
        expect(detectionRowSource).not.toMatch(/needsAttention = \$derived\(\(detection\.score/);
    });

    it('keeps the whole row a control, and the touch floor', () => {
        expect(detectionRowSource).toMatch(/absolute inset-0[^"]*z-0/);
        expect(detectionRowSource).toContain('focus-visible:ring-brand-500');
        expect(detectionRowSource).toMatch(/h-11 w-11/);
    });

    it('shows a placeholder until the snapshot loads, so no alt text spills', () => {
        // A 44px tile rendering a broken image shows its alt text instead.
        expect(detectionRowSource).toContain('imageLoaded');
        expect(detectionRowSource).toMatch(/onload=\{\(\) => \(imageLoaded = true\)\}/);
        expect(detectionRowSource).toContain('overflow-hidden');
    });
});

describe('choosing the Explorer layout', () => {
    it('defaults to cards so nobody upgrades into a different Explorer', () => {
        expect(eventsPageSource).toContain("settingsStore.settings?.appearance_explorer_view ?? 'cards'");
    });

    it('renders rows only when list is chosen', () => {
        expect(eventsPageSource).toContain("{:else if explorerView === 'list'}");
        expect(eventsPageSource).toContain('<DetectionRow');
        expect(eventsPageSource).toContain('<DetectionCard');
    });

    it('is offered in appearance settings beside the other display choices', () => {
        expect(appearanceSource).toContain('settings.explorer_view.label');
        expect(appearanceSource).toContain("value: 'cards'");
        expect(appearanceSource).toContain("value: 'list'");
    });
});
