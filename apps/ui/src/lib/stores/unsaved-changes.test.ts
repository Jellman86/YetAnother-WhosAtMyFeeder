import { afterEach, describe, expect, it } from 'vitest';
import { confirmDialog } from './confirm_dialog.svelte';
import { unsavedChanges } from './unsaved-changes';

const warning = { title: 'Leave without saving?', message: 'Two changes in Connection are not saved.', confirmLabel: 'Leave without saving' };

describe('the unsaved-changes guard', () => {
    let release: (() => void) | null = null;
    afterEach(() => {
        release?.();
        release = null;
        confirmDialog.answer(false);
    });

    it('lets every navigation through while no page holds unsaved work', async () => {
        expect(unsavedChanges.warningFor('/')).toBeNull();
        await expect(unsavedChanges.allowLeaving('/')).resolves.toBe(true);
    });

    it('asks before leaving, and goes ahead only when the person agrees', async () => {
        release = unsavedChanges.hold((to) => (to.startsWith('/settings') ? null : warning));
        await expect(unsavedChanges.allowLeaving('/settings/detection')).resolves.toBe(true);

        const stay = unsavedChanges.allowLeaving('/');
        expect(confirmDialog.current?.title).toBe('Leave without saving?');
        confirmDialog.answer(false);
        await expect(stay).resolves.toBe(false);

        const leave = unsavedChanges.allowLeaving('/events');
        confirmDialog.answer(true);
        await expect(leave).resolves.toBe(true);
    });

    it('tells the page when the person chose to leave, so it can drop its draft', async () => {
        let left = 0;
        release = unsavedChanges.hold(() => warning, () => (left += 1));
        const stay = unsavedChanges.allowLeaving('/');
        confirmDialog.answer(false);
        await stay;
        expect(left).toBe(0);
        const leave = unsavedChanges.allowLeaving('/');
        confirmDialog.answer(true);
        await leave;
        expect(left).toBe(1);
    });

    it('stops asking once the page releases the guard', async () => {
        unsavedChanges.hold(() => warning)();
        await expect(unsavedChanges.allowLeaving('/')).resolves.toBe(true);
    });
});
