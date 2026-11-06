<script lang="ts">
    import Pagination from '../src/lib/components/Pagination.svelte';
    import AccountStep from '../src/lib/components/setup/AccountStep.svelte';

    // Real kit components with nothing behind them: sizes, not behaviour, are under test here.
    let page = $state(2);
    let size = $state(24);
</script>

<main class="space-y-8 p-4">
    <Pagination currentPage={page} totalPages={5} totalItems={110} itemsPerPage={size} onPageChange={(next) => (page = next)} onPageSizeChange={(next) => (size = next)} />
    <section data-kit-account>
        <AccountStep />
    </section>
</main>
