<script lang="ts">
    import { _ } from 'svelte-i18n';
    import SettingsCard from './_primitives/SettingsCard.svelte';

    // Deleting data, last in Storage & upkeep and outside More options: one block per action,
    // narrowest reach first, each consequence beside its own button. Every action asks first.
    let {
        clearingFeedback,
        clearingFavorites,
        resettingDatabase,
        handleClearFeedback,
        handleClearFavorites,
        handleResetDatabase
    }: {
        clearingFeedback: boolean;
        clearingFavorites: boolean;
        resettingDatabase: boolean;
        handleClearFeedback: () => Promise<void>;
        handleClearFavorites: () => Promise<void>;
        handleResetDatabase: () => Promise<void>;
    } = $props();

    const buttonDangerOutlineClass = 'btn btn-danger min-h-11 px-4 py-3';
    const buttonDangerSolidClass = 'btn btn-danger-solid min-h-11 px-4 py-3';
</script>

{#snippet spinner()}
    <svg class="h-4 w-4 animate-spin" fill="none" viewBox="0 0 24 24" aria-hidden="true">
        <circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4"></circle>
        <path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
    </svg>
{/snippet}

<SettingsCard
    id="data-danger"
    title={$_('settings.danger.title')}
    description={$_('settings.danger.subtitle')}
>
    <!-- One block per action, narrowest reach first, each consequence beside its own button. -->
    <ul class="@container divide-y divide-line-soft" data-danger-actions>
        <li class="flex flex-col gap-3 p-4 @xl:flex-row @xl:items-center @xl:justify-between @xl:gap-6" data-danger-action="feedback">
            <div class="min-w-0 space-y-1">
                <h3 class="text-sm font-semibold text-strong">{$_('settings.danger.feedback_title', { default: 'Personalization data' })}</h3>
                <p id="danger-feedback-consequence" class="text-xs leading-snug text-muted">
                    {$_('settings.danger.clear_feedback_desc', { default: 'Clearing personalization feedback will delete all manual tag corrections the AI uses to adjust confidence scores. This will revert the classifier to its baseline accuracy.' })}
                    {$_('settings.danger.clear_feedback_hint', { default: 'This does not delete detections or media. Re-ranking will begin learning again as you make new manual corrections.' })}
                </p>
            </div>
            <button
                type="button"
                onclick={handleClearFeedback}
                disabled={clearingFeedback}
                aria-describedby="danger-feedback-consequence"
                class="shrink-0 {buttonDangerOutlineClass}"
            >
                {#if clearingFeedback}{@render spinner()}{/if}
                {clearingFeedback ? $_('settings.danger.clearing_feedback', { default: 'Clearing...' }) : $_('settings.danger.clear_feedback_button', { default: 'Clear Personalization Data' })}
            </button>
        </li>
        <li class="flex flex-col gap-3 p-4 @xl:flex-row @xl:items-center @xl:justify-between @xl:gap-6" data-danger-action="favorites">
            <div class="min-w-0 space-y-1">
                <h3 class="text-sm font-semibold text-strong">{$_('settings.danger.favorites_title', { default: 'Favourites' })}</h3>
                <p id="danger-favorites-consequence" class="text-xs leading-snug text-muted">{$_('settings.data.clear_favorites_desc')}</p>
            </div>
            <button
                type="button"
                onclick={handleClearFavorites}
                disabled={clearingFavorites}
                aria-describedby="danger-favorites-consequence"
                class="shrink-0 {buttonDangerOutlineClass}"
            >
                {#if clearingFavorites}{@render spinner()}{/if}
                {clearingFavorites ? $_('settings.data.cleaning') : $_('settings.data.clear_favorites_button')}
            </button>
        </li>
        <li class="flex flex-col gap-3 p-4 @xl:flex-row @xl:items-center @xl:justify-between @xl:gap-6" data-danger-action="reset">
            <div class="min-w-0 space-y-1">
                <h3 class="text-sm font-semibold text-strong">{$_('settings.danger.reset_title', { default: 'Database and media cache' })}</h3>
                <p id="danger-reset-consequence" class="text-xs leading-snug text-muted">{$_('settings.danger.reset_desc')}</p>
            </div>
            <button
                type="button"
                onclick={handleResetDatabase}
                disabled={resettingDatabase}
                aria-describedby="danger-reset-consequence"
                class="shrink-0 {buttonDangerSolidClass}"
            >
                {#if resettingDatabase}{@render spinner()}{/if}
                {resettingDatabase ? $_('settings.danger.resetting') : $_('settings.danger.reset_button')}
            </button>
        </li>
    </ul>
</SettingsCard>
