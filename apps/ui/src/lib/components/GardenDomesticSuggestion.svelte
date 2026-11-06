<script lang="ts">
    /**
     * Asks once whether the owner keeps a domestic bird the models saw but the owner has not
     * declared. Nothing changes until they add it in Settings; "Not now" hides the question on
     * this device for that bird.
     */
    import { _ } from 'svelte-i18n';
    import { toAppPath } from '../app/url-base';
    import {
        dismissDomesticSuggestion,
        dismissedDomesticSuggestions,
        domesticBirdKind,
        type DomesticBirdKey
    } from '../utils/domestic-birds';

    let { bird }: { bird: DomesticBirdKey } = $props();

    const storage = typeof localStorage === 'undefined' ? null : localStorage;
    let dismissed = $state(dismissedDomesticSuggestions(storage));
    const kind = $derived(domesticBirdKind(bird, (id, options) => $_(id, options)));

    function notNow(): void {
        dismissDomesticSuggestion(storage, bird);
        dismissed = dismissedDomesticSuggestions(storage);
    }
</script>

{#if !dismissed.has(bird)}
    <div class="card-base space-y-2 p-3 text-sm text-slate-700 dark:text-slate-200" role="note" data-domestic-suggestion={bird}>
        <p>
            {$_('garden.domestic_birds.suggestion', {
                default: 'This looks like a domestic bird: {birds}. If you keep them, add them under Domestic birds you keep to record them as Garden animals, not wild birds.',
                values: { birds: kind }
            })}
        </p>
        <div class="flex flex-wrap gap-2">
            <a href={toAppPath('/settings/beta')} class="btn btn-secondary inline-flex min-h-11 items-center px-3 text-xs">
                {$_('garden.domestic_birds.suggestion_open', { default: 'Open Domestic birds you keep' })}
            </a>
            <button type="button" class="btn btn-ghost min-h-11 px-3 text-xs" onclick={notNow}>
                {$_('garden.domestic_birds.suggestion_dismiss', { default: 'Not now' })}
            </button>
        </div>
    </div>
{/if}
