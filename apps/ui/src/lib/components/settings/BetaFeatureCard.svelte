<script lang="ts">
    /**
     * One beta feature on Settings → Beta features: its name, what it does, its switch and a status
     * line in words. Its settings appear only while it is on; while it is off the card says what
     * off means. The switch stages a change in the page's draft like every other setting, so
     * nothing takes effect until Apply Settings.
     */
    import type { Snippet } from 'svelte';
    import { _ } from 'svelte-i18n';
    import SettingsToggle from './_primitives/SettingsToggle.svelte';

    interface Props {
        /** Stable key for ids and test hooks, such as `garden-animals`. */
        id: string;
        name: string;
        description: string;
        enabled: boolean;
        ontoggle: (next: boolean) => void;
        /** The status line, in words: "Off", "On · 2 cameras". */
        status: string;
        /** True only when something on the card needs the owner to act. */
        attention?: boolean;
        learnMoreHref?: string;
        /** What off means for this feature, shown while it is off. */
        off: Snippet;
        /** The feature's settings, shown while it is on. */
        children: Snippet;
    }

    let { id, name, description, enabled, ontoggle, status, attention = false, learnMoreHref, off, children }: Props = $props();

    const nameId = $derived(`beta-${id}-name`);
</script>

<article class="card-base min-w-0" aria-labelledby={nameId} data-beta-feature={id}>
    <header class="flex items-start justify-between gap-4 p-5 sm:p-6">
        <div class="min-w-0 space-y-1">
            <h4 id={nameId} class="font-display text-lg font-bold text-slate-900 dark:text-white">{name}</h4>
            <p class="text-sm text-slate-600 dark:text-slate-400">
                {description}
                {#if learnMoreHref}
                    <a href={learnMoreHref} target="_blank" rel="noopener noreferrer" class="font-semibold text-brand-700 underline underline-offset-2 hover:text-brand-800 focus-visible:outline-hidden focus-visible:ring-2 focus-visible:ring-brand-500 dark:text-brand-300 dark:hover:text-brand-200">
                        {$_('settings.beta.learn_more', { default: 'Learn more' })}
                    </a>
                {/if}
            </p>
            <p class="flex items-center gap-2 pt-1 text-sm font-semibold text-slate-800 dark:text-slate-100" aria-live="polite" data-beta-status={attention ? 'attention' : 'calm'}>
                {#if attention}<span class="attention-dot" aria-hidden="true"></span>{/if}
                <span class="min-w-0 wrap-break-word">{status}</span>
            </p>
        </div>
        <div class="flex min-h-11 shrink-0 items-center">
            <SettingsToggle checked={enabled} labelledBy={nameId} srLabel={name} onchange={ontoggle} />
        </div>
    </header>
    <div class="space-y-4 border-t border-line-soft px-5 pb-5 pt-4 sm:px-6 sm:pb-6" data-beta-feature-body={enabled ? 'on' : 'off'}>
        {#if enabled}
            {@render children()}
        {:else}
            {@render off()}
        {/if}
    </div>
</article>
