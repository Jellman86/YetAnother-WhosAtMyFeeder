<script lang="ts">
    import VisitFilm from '../src/lib/components/VisitFilm.svelte';
    let mounted = $state(true);
</script>

<button onclick={() => document.documentElement.classList.toggle('reduced-motion')}>Toggle reduced motion</button>
<button onclick={() => (mounted = !mounted)}>Toggle cards</button>
{#if mounted}
    <div class="grid grid-cols-2 gap-4">
        {#each [1, 2] as copy (copy)}
            <VisitFilm frigateEvent="visit-one" poster="/poster.svg" film={true} class="aspect-video" />
        {/each}
    </div>
{/if}
