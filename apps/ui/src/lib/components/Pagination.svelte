<script lang="ts">
    import { _ } from 'svelte-i18n';

    interface Props {
        currentPage: number;
        totalPages: number;
        totalItems: number;
        itemsPerPage: number;
        onPageChange: (page: number) => void;
        onPageSizeChange?: (size: number) => void;
        pageSizeOptions?: number[];
    }

    let {
        currentPage,
        totalPages,
        totalItems,
        itemsPerPage,
        onPageChange,
        onPageSizeChange,
        pageSizeOptions = [12, 24, 48]
    }: Props = $props();

    // Calculate display range
    let startItem = $derived((currentPage - 1) * itemsPerPage + 1);
    let endItem = $derived(Math.min(currentPage * itemsPerPage, totalItems));

    // Generate page numbers to display
    let pageNumbers = $derived(() => {
        const pages: (number | 'ellipsis')[] = [];
        const maxVisible = 7;

        if (totalPages <= maxVisible) {
            // Show all pages
            for (let i = 1; i <= totalPages; i++) pages.push(i);
        } else {
            // Always show first page
            pages.push(1);

            if (currentPage > 3) {
                pages.push('ellipsis');
            }

            // Show pages around current
            const start = Math.max(2, currentPage - 1);
            const end = Math.min(totalPages - 1, currentPage + 1);

            for (let i = start; i <= end; i++) {
                if (!pages.includes(i)) pages.push(i);
            }

            if (currentPage < totalPages - 2) {
                pages.push('ellipsis');
            }

            // Always show last page
            if (!pages.includes(totalPages)) pages.push(totalPages);
        }

        return pages;
    });

    function goToPage(page: number) {
        if (page >= 1 && page <= totalPages && page !== currentPage) {
            onPageChange(page);
        }
    }
</script>

{#if totalPages > 0}
    <div class="flex flex-col sm:flex-row items-center justify-between gap-4 py-4">
        <!-- Items info and page size selector -->
        <div class="flex items-center gap-4 text-sm text-slate-600 dark:text-slate-400">
            <span>
                Showing <span class="font-medium text-slate-900 dark:text-white">{startItem}</span>
                - <span class="font-medium text-slate-900 dark:text-white">{endItem}</span>
                of <span class="font-medium text-slate-900 dark:text-white">{totalItems.toLocaleString()}</span>
            </span>

            {#if onPageSizeChange}
                <div class="flex items-center gap-2">
                    <label for="page-size-selector">{$_('pagination.page_size_label', { default: 'Show:' })}</label>
                    <select
                        id="page-size-selector"
                        value={itemsPerPage}
                        onchange={(e) => onPageSizeChange?.(Number(e.currentTarget.value))}
                        aria-label={$_('pagination.page_size_aria', { default: 'Items per page' })}
                        class="px-2 py-1 rounded-md border border-slate-300 dark:border-slate-600
                               bg-white dark:bg-slate-800 text-slate-900 dark:text-white text-sm
                               focus:ring-2 focus:ring-teal-500 focus:border-transparent"
                    >
                        {#each pageSizeOptions as size}
                            <option value={size}>{size}</option>
                        {/each}
                    </select>
                </div>
            {/if}
        </div>

        <!-- Page navigation -->
        <nav class="flex items-center gap-1" aria-label={$_('pagination.navigation', { default: 'Pagination' })}>
            <!-- Previous button -->
            <button
                onclick={() => goToPage(currentPage - 1)}
                disabled={currentPage === 1}
                class="p-2 rounded-lg text-slate-600 dark:text-slate-400
                       hover:bg-slate-100 dark:hover:bg-slate-800 transition-colors
                       disabled:opacity-40 disabled:cursor-not-allowed disabled:hover:bg-transparent"
                aria-label={$_('pagination.previous_page', { default: 'Previous page' })}
            >
                <svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M15 19l-7-7 7-7" />
                </svg>
            </button>

            <!-- Page numbers -->
            {#each pageNumbers() as page}
                {#if page === 'ellipsis'}
                    <span class="px-2 text-slate-400 dark:text-slate-500">...</span>
                {:else}
                    <button
                        onclick={() => goToPage(page)}
                        class="min-w-[2.5rem] h-10 px-3 rounded-lg text-sm font-medium transition-colors
                               {page === currentPage
                                   ? 'bg-teal-500 text-white shadow-sm'
                                   : 'text-slate-600 dark:text-slate-400 hover:bg-slate-100 dark:hover:bg-slate-800'}"
                        aria-current={page === currentPage ? 'page' : undefined}
                        aria-label={$_('pagination.page_number', { values: { number: page }, default: `Page ${page}` })}
                    >
                        {page}
                    </button>
                {/if}
            {/each}

            <!-- Next button -->
            <button
                onclick={() => goToPage(currentPage + 1)}
                disabled={currentPage === totalPages}
                class="p-2 rounded-lg text-slate-600 dark:text-slate-400
                       hover:bg-slate-100 dark:hover:bg-slate-800 transition-colors
                       disabled:opacity-40 disabled:cursor-not-allowed disabled:hover:bg-transparent"
                aria-label={$_('pagination.next_page', { default: 'Next page' })}
            >
                <svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 5l7 7-7 7" />
                </svg>
            </button>
        </nav>
    </div>
{/if}
