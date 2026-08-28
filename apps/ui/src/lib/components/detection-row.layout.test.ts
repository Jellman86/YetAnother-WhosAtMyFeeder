import { describe, expect, it } from 'vitest';
import detectionRowSource from './DetectionRow.svelte?raw';
import previewSource from './DetectionPreview.svelte?raw';
import eventsPageSource from '../pages/Events.svelte?raw';
import appearanceSource from './settings/AppearanceSettings.svelte?raw';
import filtersSource from './ExplorerFilters.svelte?raw';
import storeSource from '../stores/explorer_view.svelte.ts?raw';
import authStoreSource from '../stores/auth.svelte.ts?raw';

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

    it('keeps the favourite flag the card shows', () => {
        // Dropping it would mean a favourited detection is unmarked in one view
        // and marked in the other.
        expect(detectionRowSource).toContain('isFavorite');
        expect(detectionRowSource).toContain("detection.favorite");
    });

    it('lets the camera name give way before a status word does', () => {
        // On a narrow row something has to go. The status words are why a row
        // is worth reading; the camera is the least of it.
        expect(detectionRowSource).toMatch(/shrink-0 text-accent-700/);
        expect(detectionRowSource).toMatch(/shrink-0 text-brand-600/);
        expect(detectionRowSource).toContain('min-w-0 truncate">{detection.camera_name}');
    });

    it('tells one row from another by voice, not just by sight', () => {
        // Every row announcing "Open Dunnock" is no use in a list of Dunnocks.
        expect(detectionRowSource).toContain('rowSubject');
        expect(detectionRowSource).toMatch(/rowSubject = \$derived\(`\$\{primaryName\}, \$\{formatTime/);
    });

    it('cannot spill alt text from a broken snapshot', () => {
        // The row no longer loads its own image. DetectionPreview owns it, and
        // holds the guarantee more firmly than the row did: the thumbnail is
        // decorative (`alt=""`), so there is no text to spill even before
        // `onerror` fires, and a failure swaps in an explicit placeholder.
        expect(detectionRowSource).toContain('<DetectionPreview');
        expect(previewSource).toContain('alt=""');
        expect(previewSource).toContain('onerror={() => markFailed(frame.frigate_event)}');
        expect(previewSource).toContain('failed.has(frame.frigate_event)');
    });
});

describe('choosing the Explorer layout', () => {
    it('defaults to cards so nobody upgrades into a different Explorer', () => {
        // The device's own choice wins where there is one; otherwise the install
        // default; and cards when the install has said nothing either.
        expect(eventsPageSource).toContain(
            'explorerViewStore.resolve(settingsStore.settings?.appearance_explorer_view ?? authStore.explorerView)'
        );
        expect(storeSource).toContain("this.override ?? (installDefault === 'list' ? 'list' : 'cards')");
    });

    it('reaches a guest, who is refused the settings it would otherwise come from', () => {
        // `/api/settings` is owner-only, so for a guest `settingsStore.settings`
        // stays null and the install default would never arrive: the setting
        // would be inert on exactly the installs that have visitors. It travels
        // on the public status payload instead, as the date and time formats do.
        expect(authStoreSource).toContain("this.explorerView = status.appearance_explorer_view");
        expect(authStoreSource).toMatch(/explorerView = \$state<'cards' \| 'list'>\('cards'\)/);
    });

    it('renders rows only when list is chosen', () => {
        expect(eventsPageSource).toContain("{:else if explorerView === 'list'}");
        expect(eventsPageSource).toContain('<DetectionRow');
        expect(eventsPageSource).toContain('<DetectionCard');
    });

    it('can also be switched from the Explorer itself', () => {
        // Settings is where you set the default; the toggle is where you are
        // when you decide the cards are too big to scroll.
        expect(filtersSource).toContain('data-explorer-view-toggle');
        expect(filtersSource).toContain('aria-pressed={view === option.value}');
        expect(eventsPageSource).toContain('explorerViewStore.set(next)');
    });

    it('is offered in appearance settings beside the other display choices', () => {
        expect(appearanceSource).toContain('settings.explorer_view.label');
        expect(appearanceSource).toContain("value: 'cards'");
        expect(appearanceSource).toContain("value: 'list'");
    });
});
