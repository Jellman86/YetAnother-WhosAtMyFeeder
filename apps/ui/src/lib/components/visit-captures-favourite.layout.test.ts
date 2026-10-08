import { describe, expect, it } from 'vitest';
import explorerList from './VisitCaptures.svelte?raw';
import fieldLogList from './FieldLogVisitRow.svelte?raw';

/**
 * A visit's capture list said which capture was the visit photo but not which were favourites,
 * so a favourite in a stack could not be found again (#481). Both lists name it in words,
 * with the label the record already uses for a favourite.
 */
describe('a visit capture list names its favourites', () => {
    for (const [name, source] of [['Explorer', explorerList], ['field log', fieldLogList]] as const) {
        it(`in the ${name} list`, () => {
            expect(source).toContain("if (facts.favorite)");
            expect(source).toContain("$_('detection.favorite_label_active', { default: 'Favorited' })");
        });
    }
});
