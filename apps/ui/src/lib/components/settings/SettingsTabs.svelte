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
        /** Tabs holding unsaved changes; each is marked in the list with a worded dot. */
        unsavedTabs?: readonly SettingsTab[];
        /** Tabs holding a value the last save refused; each needs a fix before saving again. */
        refusedTabs?: readonly SettingsTab[];
        /** The id of the element the skip link moves focus to. */
        contentId: string;
    }

    let { activeTab, ontabchange, unsavedTabs = [], refusedTabs = [], contentId }: Props = $props();

    const groups = $derived<SettingsTabGroup[]>([
        {
            id: "pipeline",
            label: $_("settings.tabs.groups.pipeline", { default: "Feeder pipeline" }),
            tabs: [
                { id: "connection", label: $_("settings.tabs.connection") },
                { id: "detection", label: $_("settings.tabs.detection") },
                { id: "models", label: $_("settings.tabs.models", { default: "Models" }) }
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
                { id: "security", label: $_("settings.tabs.security") },
                { id: "data", label: $_("settings.tabs.data") },
                { id: "maintenance", label: $_("settings.tabs.maintenance", { default: "Maintenance" }) },
                { id: "beta", label: $_("settings.tabs.beta", { default: "Beta features" }) }
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
    const refusedLabel = $derived($_("settings.tabs.refused", { default: "needs a fix" }));

    // The phone picker is a native list, so each tab's state is said in words after its name.
    function optionText(tab: SettingsTabItem): string {
        if (refusedTabs.includes(tab.id)) return `${tab.label} (${refusedLabel})`;
        if (unsavedTabs.includes(tab.id)) return `${tab.label} (${unsavedLabel})`;
        return tab.label;
    }

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
    class="sr-only focus:not-sr-only focus:absolute focus:z-40 focus:rounded-lg focus:bg-surface focus:px-3 focus:py-2 focus:text-sm focus:font-semibold focus:text-brand-700 focus:ring-2 focus:ring-focus dark:focus:text-brand-300"
    data-settings-skip-link
>{$_('settings.tabs.skip_to_content', { default: 'Skip to the settings' })}</a>

<!-- Phones, narrow windows and enlarged text: one select that names the current section, and the wizard beside it. -->
<div class="flex flex-wrap items-end gap-3 @4xl:hidden" data-settings-compact-navigation>
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
                        <option value={tab.id}>{optionText(tab)}</option>
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
<span id="settings-tab-refused-note" class="sr-only">{$_('settings.tabs.refused_note', { default: 'Has a value the last save refused' })}</span>

<!-- Room for it (56rem, so it scales with the text): a compact rail beside the settings, so they start at the top of the page. -->
<nav data-settings-navigation class="hidden @4xl:block" aria-label={$_('settings.tabs.navigation_label', { default: 'Settings sections' })}>
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
                                aria-describedby={refusedTabs.includes(tab.id) ? 'settings-tab-refused-note' : unsavedTabs.includes(tab.id) ? 'settings-tab-unsaved-note' : undefined}
                                class="sidebar-nav flex-wrap {current ? 'sidebar-nav-active' : 'sidebar-nav-inactive'}"
                            >
                                <!-- The name keeps its own width, so at a larger text size or in the reading font
                                     the status drops to a second line rather than being written over it. -->
                                <span class="flex-auto wrap-break-word">{tab.label}</span>
                                {#if refusedTabs.includes(tab.id)}
                                    <span class="text-xs font-semibold text-red-700 dark:text-red-300" aria-hidden="true" data-tab-refused>{refusedLabel}</span>
                                {:else if unsavedTabs.includes(tab.id)}
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
