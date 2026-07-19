<script lang="ts">
    import { _ } from "svelte-i18n";
    import { toAppPath } from "../../app/url-base";

    type SettingsTab = 'connection' | 'detection' | 'notifications' | 'health' | 'enrichment'
        | 'ai' | 'data' | 'appearance' | 'accessibility' | 'security' | 'debug' | 'integrations';

    interface SettingsTabItem {
        id: SettingsTab;
        label: string;
        iconPath: string;
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
    }

    let { activeTab, ontabchange, debugUiEnabled = false }: Props = $props();

    const groups = $derived<SettingsTabGroup[]>([
        {
            id: "pipeline",
            label: $_("settings.tabs.groups.pipeline", { default: "Feeder pipeline" }),
            tabs: [
                { id: "connection", label: $_("settings.tabs.connection"), iconPath: "M13.5 6H18a3 3 0 0 1 3 3v6a3 3 0 0 1-3 3h-4.5M10.5 18H6a3 3 0 0 1-3-3V9a3 3 0 0 1 3-3h4.5M8 12h8" },
                { id: "detection", label: $_("settings.tabs.detection"), iconPath: "M12 3v3m0 12v3M3 12h3m12 0h3M7.05 7.05l2.12 2.12m5.66 5.66 2.12 2.12m0-9.9-2.12 2.12m-5.66 5.66-2.12 2.12M15 12a3 3 0 1 1-6 0 3 3 0 0 1 6 0Z" }
            ]
        },
        {
            id: "intelligence",
            label: $_("settings.tabs.groups.intelligence", { default: "Intelligence & sharing" }),
            tabs: [
                { id: "integrations", label: $_("settings.tabs.integrations"), iconPath: "M8 3v4m8-4v4M6 7h12v3a6 6 0 0 1-6 6v5m-3 0h6" },
                { id: "enrichment", label: $_("settings.tabs.enrichment"), iconPath: "m12 3 1.4 4.1 4.1 1.4-4.1 1.4L12 14l-1.4-4.1-4.1-1.4 4.1-1.4L12 3Zm6.5 11 .7 2.1 2.1.7-2.1.7-.7 2.1-.7-2.1-2.1-.7 2.1-.7.7-2.1Z" },
                { id: "ai", label: $_("settings.tabs.ai", { default: "AI" }), iconPath: "M9 3v3m6-3v3M9 18v3m6-3v3M3 9h3m-3 6h3m12-6h3m-3 6h3M7 7h10v10H7V7Zm3 3h4v4h-4v-4Z" },
                { id: "notifications", label: $_("settings.tabs.notifications"), iconPath: "M18 8a6 6 0 0 0-12 0c0 7-3 7-3 9h18c0-2-3-2-3-9ZM10 21h4" }
            ]
        },
        {
            id: "operations",
            label: $_("settings.tabs.groups.operations", { default: "Operations" }),
            tabs: [
                { id: "health", label: $_("settings.tabs.health"), iconPath: "M3 12h4l2-5 4 10 2-5h6M12 21C7 18 4 14.5 4 10a4 4 0 0 1 7-2.65A4 4 0 0 1 18 10c0 .7-.08 1.36-.24 2" },
                { id: "security", label: $_("settings.tabs.security"), iconPath: "m12 3 7 3v5c0 4.6-2.8 8-7 10-4.2-2-7-5.4-7-10V6l7-3Zm-3 9 2 2 4-4" },
                { id: "data", label: $_("settings.tabs.data"), iconPath: "M19 6c0 1.66-3.13 3-7 3S5 7.66 5 6s3.13-3 7-3 7 1.34 7 3Zm0 0v6c0 1.66-3.13 3-7 3s-7-1.34-7-3V6m14 6v6c0 1.66-3.13 3-7 3s-7-1.34-7-3v-6" },
                ...(debugUiEnabled
                    ? [{ id: "debug" as const, label: $_("settings.tabs.debug"), iconPath: "M9 3h6m-5 0v5l-5 9a2 2 0 0 0 1.74 3h10.52A2 2 0 0 0 19 17l-5-9V3m-6 11h8" }]
                    : [])
            ]
        },
        {
            id: "interface",
            label: $_("settings.tabs.groups.interface", { default: "Interface" }),
            tabs: [
                { id: "appearance", label: $_("settings.tabs.appearance"), iconPath: "M12 3v2m0 14v2M3 12h2m14 0h2M5.64 5.64l1.42 1.42m9.88 9.88 1.42 1.42m0-12.72-1.42 1.42M7.06 16.94l-1.42 1.42M16 12a4 4 0 1 1-8 0 4 4 0 0 1 8 0Z" },
                { id: "accessibility", label: $_("settings.tabs.accessibility"), iconPath: "M12 6a2 2 0 1 0 0-4 2 2 0 0 0 0 4ZM4 9h16m-8 0v12m0-7-4 7m4-7 4 7" }
            ]
        }
    ]);

    function settingsHref(tab: SettingsTab): string {
        return toAppPath(`/settings/${tab}`);
    }

    function handleLinkClick(event: MouseEvent, tab: SettingsTab): void {
        if (
            event.button !== 0
            || event.metaKey
            || event.ctrlKey
            || event.shiftKey
            || event.altKey
        ) {
            return;
        }

        event.preventDefault();
        if (tab !== activeTab) ontabchange(tab);
    }
</script>

<div class="rounded-2xl border border-slate-200/80 bg-gradient-to-r from-brand-50/70 via-accent-50/30 to-white p-3 dark:border-slate-700/80 dark:from-brand-950/30 dark:via-accent-950/10 dark:to-slate-900 md:hidden">
    <label for="settings-tab-select" class="mb-1.5 block px-1 text-xs font-semibold text-slate-500 dark:text-slate-400">{$_('settings.title')}</label>
    <select
        id="settings-tab-select"
        value={activeTab}
        onchange={(e) => ontabchange((e.currentTarget as HTMLSelectElement).value as SettingsTab)}
        class="select-base w-full"
    >
        {#each groups as group}
            <optgroup label={group.label}>
                {#each group.tabs as tab}
                    <option value={tab.id}>{tab.label}</option>
                {/each}
            </optgroup>
        {/each}
    </select>
</div>

<nav
    data-settings-navigation
    class="hidden w-full overflow-hidden rounded-2xl border border-slate-200/80 bg-white/80 dark:border-slate-700/80 dark:bg-slate-900/70 md:block"
    aria-label={$_('settings.title')}
>
    <div class="grid grid-cols-2 xl:grid-cols-4">
        {#each groups as group}
            <div class="min-w-0 border-slate-200/80 p-3 dark:border-slate-700/80 xl:p-4
                        {group.id === 'intelligence' ? 'border-l' : ''}
                        {group.id === 'operations' ? 'border-t xl:border-l xl:border-t-0' : ''}
                        {group.id === 'interface' ? 'border-l border-t xl:border-t-0' : ''}">
                <h2 class="px-2 pb-2 text-[11px] font-bold uppercase tracking-wider text-slate-400 dark:text-slate-500">
                    {group.label}
                </h2>
                <div class="space-y-0.5">
                    {#each group.tabs as tab}
                        <a
                            href={settingsHref(tab.id)}
                            onclick={(event) => handleLinkClick(event, tab.id)}
                            aria-current={activeTab === tab.id ? 'page' : undefined}
                            class="group flex min-h-11 items-center gap-2.5 rounded-lg px-2 py-2 text-left text-sm font-semibold transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-500 focus-visible:ring-offset-2 dark:focus-visible:ring-offset-slate-950
                                   {activeTab === tab.id
                                ? 'bg-brand-50 text-brand-800 dark:bg-brand-950/40 dark:text-brand-200'
                                : 'text-slate-600 hover:bg-slate-50 hover:text-slate-900 dark:text-slate-400 dark:hover:bg-slate-800/70 dark:hover:text-white'}"
                            title={tab.label}
                        >
                            <span
                                data-active-indicator
                                class="h-5 w-1 shrink-0 rounded-full {activeTab === tab.id ? 'bg-brand-500' : 'bg-transparent'}"
                                aria-hidden="true"
                            ></span>
                            <svg class="h-4 w-4 shrink-0 opacity-80" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
                                <path d={tab.iconPath} />
                            </svg>
                            <span class="min-w-0 flex-1">{tab.label}</span>
                        </a>
                    {/each}
                </div>
            </div>
        {/each}
    </div>
</nav>
