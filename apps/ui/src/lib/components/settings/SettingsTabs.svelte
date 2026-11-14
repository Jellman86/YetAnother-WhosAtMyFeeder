<script lang="ts">
    import { _ } from "svelte-i18n";
    import { toAppPath } from "../../app/url-base";
    import { setupWizardStore } from "../../stores/setup_wizard.svelte";
    import type { SettingsTab } from "../../settings/settings-route";

    interface SettingsTabItem {
        id: SettingsTab;
        label: string;
    }

    interface SettingsTabGroup {
        id: 'pipeline' | 'intelligence' | 'operations' | 'interface';
        label: string;
        tabs: SettingsTabItem[];
    }

    interface Props {
        activeTab: string;
        ontabchange: (tab: SettingsTab) => void;
        debugUiEnabled?: boolean;
        /** Tabs holding unsaved changes; each is marked in the list with a worded dot. */
        unsavedTabs?: readonly SettingsTab[];
        /** The id of the element the skip link moves focus to. */
        contentId: string;
    }

    let { activeTab, ontabchange, debugUiEnabled = false, unsavedTabs = [], contentId }: Props = $props();

    const groups = $derived<SettingsTabGroup[]>([
        {
            id: "pipeline",
            label: $_("settings.tabs.groups.pipeline", { default: "Feeder pipeline" }),
            tabs: [
                { id: "connection", label: $_("settings.tabs.connection") },
                { id: "detection", label: $_("settings.tabs.detection") }
            ]
        },
        {
            id: "intelligence",
            label: $_("settings.tabs.groups.intelligence", { default: "Intelligence & sharing" }),
            tabs: [
                { id: "integrations", label: $_("settings.tabs.integrations") },
                { id: "ai", label: $_("settings.tabs.ai", { default: "AI" }) },
                { id: "notifications", label: $_("settings.tabs.notifications") }
            ]
        },
        {
            id: "operations",
            label: $_("settings.tabs.groups.operations", { default: "Operations" }),
            tabs: [
                { id: "health", label: $_("settings.tabs.health") },
                { id: "security", label: $_("settings.tabs.security") },
                { id: "data", label: $_("settings.tabs.data") },
                { id: "beta", label: $_("settings.tabs.beta", { default: "Beta features" }) },
                ...(debugUiEnabled ? [{ id: "debug" as const, label: $_("settings.tabs.debug") }] : [])
            ]
        },
        {
            id: "interface",
            label: $_("settings.tabs.groups.interface", { default: "Interface" }),
            tabs: [
                { id: "appearance", label: $_("settings.tabs.appearance") },
                { id: "accessibility", label: $_("settings.tabs.accessibility") }
            ]
        }
    ]);

    const unsavedLabel = $derived($_("settings.tabs.unsaved", { default: "unsaved" }));

    function settingsHref(tab: SettingsTab): string {
        return toAppPath(`/settings/${tab}`);
    }

    function handleLinkClick(event: MouseEvent, tab: SettingsTab): void {
        if (event.button !== 0 || event.metaKey || event.ctrlKey || event.shiftKey || event.altKey) return;
        event.preventDefault();
        if (tab !== activeTab) ontabchange(tab);
    }

    function skipToContent(event: MouseEvent): void {
        event.preventDefault();
        document.getElementById(contentId)?.focus();
    }

    function openSetupWizard(): void {
        setupWizardStore.open('rerun');
    }
</script>

<a
    href="#{contentId}"
    onclick={skipToContent}
    class="sr-only focus:not-sr-only focus:absolute focus:z-40 focus:rounded-lg focus:bg-surface focus:px-3 focus:py-2 focus:text-sm focus:font-semibold focus:text-brand-700 focus:ring-2 focus:ring-brand-500 dark:focus:text-brand-300"
    data-settings-skip-link
>{$_('settings.tabs.skip_to_content', { default: 'Skip to the settings' })}</a>

<!-- Phones and narrow windows: one select that names the current section, and the wizard beside it. -->
<div class="flex flex-wrap items-end gap-3 lg:hidden" data-settings-compact-navigation>
    <div class="min-w-0 flex-1 basis-48">
        <label for="settings-tab-select" class="mb-1.5 block text-sm font-semibold text-slate-700 dark:text-slate-200">{$_('settings.tabs.section_label', { default: 'Settings section' })}</label>
        <select
            id="settings-tab-select"
            value={activeTab}
            onchange={(e) => ontabchange((e.currentTarget as HTMLSelectElement).value as SettingsTab)}
            class="select-base w-full"
        >
            {#each groups as group (group.id)}
                <optgroup label={group.label}>
                    {#each group.tabs as tab (tab.id)}
                        <option value={tab.id}>{unsavedTabs.includes(tab.id) ? `${tab.label} (${unsavedLabel})` : tab.label}</option>
                    {/each}
                </optgroup>
            {/each}
        </select>
    </div>
    <button type="button" data-setup-wizard-action class="btn btn-secondary min-h-11 px-4" onclick={openSetupWizard} aria-haspopup="dialog">
        {$_('nav.setup_wizard')}
    </button>
</div>

<!-- The word beside a section's name is visible; this says the same to a screen reader without
     changing the link's name. -->
<span id="settings-tab-unsaved-note" class="sr-only">{$_('settings.tabs.unsaved_note', { default: 'Has unsaved changes' })}</span>

<!-- Wide screens: a compact rail beside the settings, so they start at the top of the page. -->
<nav data-settings-navigation class="hidden lg:block" aria-label={$_('settings.tabs.navigation_label', { default: 'Settings sections' })}>
    <div class="space-y-5">
        {#each groups as group (group.id)}
            <div>
                <h2 id="settings-group-{group.id}" class="px-3 pb-1 text-sm font-semibold text-slate-900 dark:text-white">{group.label}</h2>
                <ul class="space-y-0.5" aria-labelledby="settings-group-{group.id}">
                    {#each group.tabs as tab (tab.id)}
                        {@const current = activeTab === tab.id}
                        <li>
                            <a
                                href={settingsHref(tab.id)}
                                onclick={(event) => handleLinkClick(event, tab.id)}
                                aria-current={current ? 'page' : undefined}
                                aria-describedby={unsavedTabs.includes(tab.id) ? 'settings-tab-unsaved-note' : undefined}
                                class="flex min-h-10 items-center gap-2 rounded-lg border-l-2 px-3 py-2 text-sm transition-colors focus-visible:outline-hidden focus-visible:ring-2 focus-visible:ring-brand-500
                                       {current
                                    ? 'border-brand-600 bg-brand-50 font-semibold text-slate-900 dark:border-brand-400 dark:bg-brand-950/60 dark:text-white'
                                    : 'border-transparent font-medium text-slate-600 hover:bg-surface-raised hover:text-slate-900 dark:text-slate-300 dark:hover:text-white'}"
                            >
                                <span class="min-w-0 flex-1">{tab.label}</span>
                                {#if unsavedTabs.includes(tab.id)}
                                    <span class="flex items-center gap-1 text-xs font-semibold text-slate-600 dark:text-slate-300" aria-hidden="true" data-tab-unsaved>
                                        <span class="h-1.5 w-1.5 rounded-full bg-brand-600 dark:bg-brand-400" aria-hidden="true"></span>
                                        {unsavedLabel}
                                    </span>
                                {/if}
                            </a>
                        </li>
                    {/each}
                </ul>
            </div>
        {/each}
        <div class="border-t border-line-soft px-1 pt-4">
            <button type="button" data-setup-wizard-action class="btn btn-secondary min-h-11 w-full px-4" onclick={openSetupWizard} aria-haspopup="dialog">
                {$_('nav.setup_wizard')}
            </button>
        </div>
    </div>
</nav>
