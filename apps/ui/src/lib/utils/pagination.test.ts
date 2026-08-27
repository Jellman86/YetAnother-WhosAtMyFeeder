import { describe, expect, it } from 'vitest';

import { paginateItems } from './pagination';

describe('paginateItems', () => {
    const items = Array.from({ length: 45 }, (_, index) => index + 1);

    it('returns one bounded page and its honest range', () => {
        expect(paginateItems(items, 2, 20)).toEqual({
            items: items.slice(20, 40),
            page: 2,
            pageSize: 20,
            totalItems: 45,
            totalPages: 3,
            startItem: 21,
            endItem: 40
        });
    });

    it('clamps a stale page when live history shrinks', () => {
        const page = paginateItems(items.slice(0, 8), 4, 20);
        expect(page.page).toBe(1);
        expect(page.items).toEqual(items.slice(0, 8));
    });

    it('returns an empty first page for an empty history', () => {
        expect(paginateItems([], 9, 0)).toEqual({
            items: [],
            page: 1,
            pageSize: 1,
            totalItems: 0,
            totalPages: 0,
            startItem: 0,
            endItem: 0
        });
    });
});
