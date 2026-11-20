<script lang="ts">
    import { _ } from "svelte-i18n";
    import { toAppPath } from "../../app/url-base";
    import { setupWizardStore } from "../../stores/setup_wizard.svelte";
    import { SETTINGS_SECTION_ORDER, settingsSectionPath, type SettingsSection } from "../../settings/settings-route";
    import SettingsSearch, { type SettingsSearchLanding } from "./SettingsSearch.svelte";

    interface SettingsSectionItem {
        id: SettingsSection;
        label: string;
    }

    interface Props {
        activeSection: SettingsSection;
        onsectionchange: (section: SettingsSection) => void;
        /** Opens the setting a search result names; the search is left out without it. */
        onsearch?: (anchor: string) => Promise<SettingsSearchLanding>;
        /** Sections holding unsaved changes; each is marked in the list with a worded dot. */
        unsavedSections?: readonly SettingsSection[];
        /** Sections holding a value the last save refused; each needs a fix before saving again. */
        refusedSections?: readonly SettingsSection[];
        /** The id of the element the skip link moves focus to. */
        contentId: string;
    }

    let { activeSection, onsectionchange, onsearch, unsavedSections = [], refusedSections = [], contentId }: Props = $props();

    // Six sections, one per task an owner comes here to do, so they need no grouping.
    const sections = $derived<SettingsSectionItem[]>(
        SETTINGS_SECTION_ORDER.map((id) => ({ id, label: $_(`settings.sections.${id}`) }))
    );

    const unsavedLabel = $derived($_("settings.tabs.unsaved", { default: "unsaved" }));
    const refusedLabel = $derived($_("settings.tabs.refused", { default: "needs a fix" }));

    // The phone picker is a native list, so each section's state is said in words after its name.
    function optionText(section: SettingsSectionItem): string {
        if (refusedSections.includes(section.id)) return `${section.label} (${refusedLabel})`;
        if (unsavedSections.includes(section.id)) return `${section.label} (${unsavedLabel})`;
        return section.label;
    }

    function sectionHref(section: SettingsSection): string {
        return toAppPath(settingsSectionPath(section));
    }

    function handleLinkClick(event: MouseEvent, section: SettingsSection): void {
        if (event.button !== 0 || event.metaKey || event.ctrlKey || event.shiftKey || event.altKey) return;
        event.preventDefault();
        if (section !== activeSection) onsectionchange(section);
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
    class="sr-only focus:not-sr-only focus:absolute focus:z-40 focus:rounded-lg focus:bg-surface focus:px-3 focus:py-2 focus:text-sm focus:font-semibold focus:text-accent-ink focus:ring-2 focus:ring-focus"
    data-settings-skip-link
>{$_('settings.tabs.skip_to_content', { default: 'Skip to the settings' })}</a>

<!-- First in the navigation at every width: above the rail on a wide screen, above the section
     list on a phone. One box, so "/" always has one place to go. -->
{#if onsearch}
    <div class="mb-4">
        <SettingsSearch onchoose={onsearch} />
    </div>
{/if}

<!-- Phones, narrow windows and enlarged text: one select that names the current section, and the wizard beside it. -->
<div class="flex flex-wrap items-end gap-3 @2xl:hidden" data-settings-compact-navigation>
    <!-- Wide enough for the longest section name in every language; the wizard wraps below it on a phone. -->
    <div class="min-w-0 flex-1 basis-64">
        <label for="settings-tab-select" class="mb-1.5 block text-sm font-semibold text-ink">{$_('settings.tabs.section_label', { default: 'Settings section' })}</label>
        <select
            id="settings-tab-select"
            value={activeSection}
            onchange={(e) => onsectionchange((e.currentTarget as HTMLSelectElement).value as SettingsSection)}
            class="select-base w-full"
        >
            {#each sections as section (section.id)}
                <option value={section.id}>{optionText(section)}</option>
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

<!-- Room for it (42rem, so it scales with the text): a compact rail beside the settings, so they start at the top of the page. -->
<nav data-settings-navigation class="hidden @2xl:block" aria-label={$_('settings.tabs.navigation_label', { default: 'Settings sections' })}>
    <div class="space-y-5">
        <ul class="space-y-0.5">
            {#each sections as section (section.id)}
                {@const current = activeSection === section.id}
                <li>
                    <a
                        href={sectionHref(section.id)}
                        onclick={(event) => handleLinkClick(event, section.id)}
                        aria-current={current ? 'page' : undefined}
                        aria-describedby={refusedSections.includes(section.id) ? 'settings-tab-refused-note' : unsavedSections.includes(section.id) ? 'settings-tab-unsaved-note' : undefined}
                        class="sidebar-nav flex-wrap {current ? 'sidebar-nav-active' : 'sidebar-nav-inactive'}"
                    >
                        <!-- The name keeps its own width, so at a larger text size or in the reading font
                             the status drops to a second line rather than being written over it. -->
                        <span class="flex-auto wrap-break-word">{section.label}</span>
                        {#if refusedSections.includes(section.id)}
                            <span class="text-xs font-semibold text-status-fail" aria-hidden="true" data-tab-refused>{refusedLabel}</span>
                        {:else if unsavedSections.includes(section.id)}
                            <span class="flex items-center gap-1 text-xs font-semibold text-muted" aria-hidden="true" data-tab-unsaved>
                                <span class="h-1.5 w-1.5 rounded-full bg-accent" aria-hidden="true"></span>
                                {unsavedLabel}
                            </span>
                        {/if}
                    </a>
                </li>
            {/each}
        </ul>
        <div class="border-t border-line-soft px-1 pt-4">
            <button type="button" data-setup-wizard-action class="btn btn-secondary min-h-11 w-full px-4" onclick={openSetupWizard} aria-haspopup="dialog">
                {$_('nav.setup_wizard')}
            </button>
        </div>
    </div>
</nav>
