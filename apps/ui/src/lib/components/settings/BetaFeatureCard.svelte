<script lang="ts">
    /**
     * One beta feature on Settings → Beta features: its name, what it does, its switch and a status
     * line in words. Its settings appear only while it is on; while it is off the card says what
     * off means. The switch stages a change in the page's draft like every other setting, so
     * nothing takes effect until Save changes.
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

<!-- Shaped like every Settings section: the heading, its description, status and switch above one
     card of the feature's settings. -->
<article class="min-w-0 space-y-3" aria-labelledby={nameId} data-beta-feature={id}>
    <header class="flex items-start justify-between gap-4 pl-1 pr-5 md:pr-6">
        <div class="min-w-0 space-y-1">
            <h2 id={nameId} class="text-lg font-semibold text-slate-900 dark:text-white">{name}</h2>
            <p class="max-w-prose text-sm text-slate-600 dark:text-slate-400">
                {description}
                {#if learnMoreHref}
                    <a href={learnMoreHref} target="_blank" rel="noopener noreferrer" class="focus-ring font-medium text-brand-700 underline underline-offset-2 hover:text-brand-800 dark:text-brand-300 dark:hover:text-brand-200">
                        {$_('settings.beta.learn_more', { default: 'Learn more' })}
                    </a>
                {/if}
            </p>
            <p class="flex items-center gap-2 pt-1 text-sm font-medium text-slate-800 dark:text-slate-100" aria-live="polite" data-beta-status={attention ? 'attention' : 'calm'}>
                {#if attention}<span class="attention-dot" aria-hidden="true"></span>{/if}
                <span class="min-w-0 wrap-break-word">{status}</span>
            </p>
        </div>
        <div class="flex min-h-11 shrink-0 items-center">
            <SettingsToggle checked={enabled} labelledBy={nameId} srLabel={name} onchange={ontoggle} />
        </div>
    </header>
    <div class="card-base settings-section-body" data-beta-feature-body={enabled ? 'on' : 'off'}>
        {#if enabled}
            {@render children()}
        {:else}
            <div>{@render off()}</div>
        {/if}
    </div>
</article>
