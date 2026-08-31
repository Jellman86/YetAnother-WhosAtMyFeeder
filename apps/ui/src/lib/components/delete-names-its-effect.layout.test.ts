import { describe, expect, it } from 'vitest';
import en from '../i18n/locales/en.json';

describe('the delete control names its own effect (#256)', () => {
    // A destructive action is the worst place to be vague: the old wording
    // never said whether it removed the identification or the whole visit,
    // nor that the media goes with it, nor that hiding is the reversible way.
    it('says what leaves, that it is permanent, and what the alternative is', () => {
        const actions = (en as unknown as Record<string, Record<string, string>>).actions;
        expect(actions.delete_detection.toLowerCase()).toContain('permanently');
        expect(actions.confirm_delete).toContain('whole');
        expect(actions.confirm_delete.toLowerCase()).toContain('permanently');
        expect(actions.confirm_delete.toLowerCase()).toContain('media');
        expect(actions.confirm_delete.toLowerCase()).toContain('hiding');
    });
});
