import { describe, expect, it } from 'vitest';
import filtersSource from './ExplorerFilters.svelte?raw';
import paginationSource from './Pagination.svelte?raw';

/**
 * The Explorer's list is bracketed by two bars doing the same structural job:
 * the filters above it and the pagination below. They separated themselves
 * from the list two different ways — the filter bar with a hard rule top and
 * bottom on mobile, the pagination with nothing but space — so the top of the
 * list looked boxed in and the bottom did not.
 *
 * Space, in both cases. One answer to one question.
 */
describe('the bars above and below the Explorer list', () => {
    it('separate themselves by space, not by a rule', () => {
        expect(filtersSource).toContain('data-events-filter-bar');
        expect(filtersSource).not.toContain('border-y border-slate-200 py-3');
    });

    it('agree with each other, so the list is not boxed at one end only', () => {
        const barClasses = filtersSource.match(/<section\s+class="([^"]*)"/)?.[1] ?? '';
        const pagClasses = paginationSource.match(/data-pagination class="([^"]*)"/)?.[1] ?? '';
        const rule = (classes: string) => /\bborder-(y|t|b)\b/.test(classes);
        expect(rule(barClasses), 'filter bar rule').toBe(rule(pagClasses));
    });
});
