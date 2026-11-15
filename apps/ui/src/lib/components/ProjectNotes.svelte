<script lang="ts">
    import { _, json } from 'svelte-i18n';

    /**
     * A bird fact, kept on About and off the pages people work in. It changes only when asked,
     * so nothing moves while it is read.
     */
    const birdFacts = $derived((($json('project_notes.bird_facts') as string[] | undefined) ?? []).filter(Boolean));
    let factIndex = $state(0);
    const currentFact = $derived(birdFacts.length > 0 ? (birdFacts[factIndex % birdFacts.length] ?? '') : '');
</script>

{#if currentFact}
    <section class="card-base space-y-2 p-6" aria-labelledby="about-project-notes-heading" data-project-notes>
        <h2 id="about-project-notes-heading" class="font-display text-xl font-bold text-slate-900 dark:text-white">
            {$_('project_notes.did_you_know', { default: 'Did you know?' })}
        </h2>
        <p class="max-w-prose text-sm leading-6 text-slate-700 dark:text-slate-300" aria-live="polite" data-project-notes-fact>{currentFact}</p>
        {#if birdFacts.length > 1}
            <button
                type="button"
                class="btn btn-ghost -ml-3 min-h-11 px-3 text-xs"
                onclick={() => { factIndex = (factIndex + 1) % birdFacts.length; }}
                data-project-notes-another
            >
                {$_('project_notes.another_fact', { default: 'Show another fact' })}
            </button>
        {/if}
    </section>
{/if}
