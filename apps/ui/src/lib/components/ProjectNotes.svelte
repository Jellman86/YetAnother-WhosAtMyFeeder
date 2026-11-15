<script lang="ts">
    import { _, json } from 'svelte-i18n';

    /**
     * The project's own voice, kept on About and off the pages people work in: how it was
     * built, and a bird fact. The fact changes only when asked, so nothing moves while it is read.
     */
    const birdFacts = $derived((($json('project_notes.bird_facts') as string[] | undefined) ?? []).filter(Boolean));
    let factIndex = $state(0);
    const currentFact = $derived(birdFacts.length > 0 ? (birdFacts[factIndex % birdFacts.length] ?? '') : '');
</script>

<section class="card-base space-y-3 p-6" aria-labelledby="about-project-notes-heading" data-project-notes>
    <h2 id="about-project-notes-heading" class="font-display text-xl font-bold text-slate-900 dark:text-white">
        {$_('project_notes.title', { default: 'About this project' })}
    </h2>
    <p class="max-w-prose text-sm leading-6 text-slate-700 dark:text-slate-300" data-project-notes-built>
        {$_('project_notes.built_with_ai', { default: 'Built with AI assistance, and a lot of trial and error' })}
    </p>
    {#if currentFact}
        <div class="max-w-prose border-t border-line-soft pt-3">
            <h3 class="text-sm font-bold text-slate-900 dark:text-white">{$_('project_notes.did_you_know', { default: 'Did you know?' })}</h3>
            <p class="mt-1 text-sm leading-6 text-slate-700 dark:text-slate-300" aria-live="polite" data-project-notes-fact>{currentFact}</p>
            {#if birdFacts.length > 1}
                <button
                    type="button"
                    class="btn btn-secondary mt-3 min-h-11 px-3 text-xs"
                    onclick={() => { factIndex = (factIndex + 1) % birdFacts.length; }}
                    data-project-notes-another
                >
                    {$_('project_notes.another_fact', { default: 'Show another fact' })}
                </button>
            {/if}
        </div>
    {/if}
</section>
