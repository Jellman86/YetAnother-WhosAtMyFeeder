export interface PaginatedItems<T> {
    items: T[];
    page: number;
    pageSize: number;
    totalItems: number;
    totalPages: number;
    startItem: number;
    endItem: number;
}

export function paginateItems<T>(items: readonly T[], requestedPage: number, requestedPageSize: number): PaginatedItems<T> {
    const pageSize = Number.isFinite(requestedPageSize) ? Math.max(1, Math.floor(requestedPageSize)) : 1;
    const totalItems = items.length;
    const totalPages = totalItems === 0 ? 0 : Math.ceil(totalItems / pageSize);
    const normalizedPage = Number.isFinite(requestedPage) ? Math.max(1, Math.floor(requestedPage)) : 1;
    const page = totalPages === 0 ? 1 : Math.min(normalizedPage, totalPages);
    const offset = (page - 1) * pageSize;
    const pageItems = items.slice(offset, offset + pageSize);

    return {
        items: pageItems,
        page,
        pageSize,
        totalItems,
        totalPages,
        startItem: totalItems === 0 ? 0 : offset + 1,
        endItem: totalItems === 0 ? 0 : offset + pageItems.length
    };
}
