<script lang="ts">
    import { trapFocus } from '../src/lib/utils/focus-trap';
    import { portal } from '../src/lib/utils/portal';
    let parentOpen = $state(false);
    let childOpen = $state(false);
    let openerVisible = $state(true);
    function focusScope(node: HTMLElement): { destroy: () => void } {
        return { destroy: trapFocus(node) };
    }
</script>

<main tabindex="-1" class="p-4">
    {#if openerVisible}<button class="btn btn-primary" onclick={() => parentOpen = true}>Open record</button>{/if}
    <button class="btn btn-secondary" onclick={() => parentOpen = false}>Navigate elsewhere</button>
</main>

{#if parentOpen}
    <div use:portal use:focusScope role="dialog" aria-label="Record" tabindex="-1" class="fixed inset-8 bg-white p-4"
        onkeydown={(event) => { if (event.key === 'Escape') { event.stopPropagation(); parentOpen = false; } }}>
        <button class="btn btn-secondary" onclick={() => parentOpen = false}>Close record</button>
        <button class="btn btn-secondary" onclick={() => childOpen = true}>Open confirmation</button>
        <button class="btn btn-secondary" onclick={() => { openerVisible = false; parentOpen = false; }}>Remove opener and close</button>
    </div>
{/if}

{#if childOpen}
    <div use:portal use:focusScope role="alertdialog" aria-label="Confirmation" tabindex="-1" class="fixed inset-12 bg-white p-4"
        onkeydown={(event) => { if (event.key === 'Escape') { event.stopPropagation(); childOpen = false; } }}>
        <button class="btn btn-secondary" onclick={() => childOpen = false}>Cancel confirmation</button>
        <button class="btn btn-secondary" onclick={() => parentOpen = false}>Close parent first</button>
    </div>
{/if}
