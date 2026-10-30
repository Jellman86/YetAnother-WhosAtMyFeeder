<script lang="ts">
    import LazyModal from '../src/lib/components/LazyModal.svelte';
    import { lazyComponent } from '../src/lib/app/lazy-component';

    // ?fail=1 refuses the first import, as a dropped chunk request would; ?delay=ms holds every import.
    const params = new URLSearchParams(location.search);
    let failuresLeft = Number(params.get('fail') ?? 0);
    const delay = Number(params.get('delay') ?? 0);
    let imports = $state(0);
    const loadStub = lazyComponent(async () => {
        imports += 1;
        await new Promise((resolve) => setTimeout(resolve, delay));
        if (failuresLeft > 0) {
            failuresLeft -= 1;
            throw new TypeError('Failed to fetch dynamically imported module');
        }
        return import('./LazyDialogStub.svelte');
    });
    let open = $state(false);
</script>

<main class="p-4">
    <button class="btn btn-primary" onclick={() => (open = true)}>Open record</button>
    <p data-imports>{imports}</p>
</main>

{#if open}
    <LazyModal loader={loadStub} onclose={() => (open = false)}>
        {#snippet children(Stub)}
            <Stub name="Record" onclose={() => (open = false)} />
        {/snippet}
    </LazyModal>
{/if}
