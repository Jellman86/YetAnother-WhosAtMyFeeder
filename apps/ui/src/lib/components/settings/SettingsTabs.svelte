<script lang="ts">
    import { _ } from "svelte-i18n";

    interface Props {
        activeTab: string;
        ontabchange: (tab: any) => void;
        debugUiEnabled?: boolean;
    }

    let { activeTab, ontabchange, debugUiEnabled = false }: Props = $props();

    const tabs = $derived([
        { id: "connection", label: $_("settings.tabs.connection"), icon: "🔗" },
        { id: "detection", label: $_("settings.tabs.detection"), icon: "🎯" },
        { id: "notifications", label: $_("settings.tabs.notifications"), icon: "🔔" },
        { id: "integrations", label: $_("settings.tabs.integrations"), icon: "🔌" },
        { id: "enrichment", label: $_("settings.tabs.enrichment"), icon: "✨" },
        { id: "ai", label: $_("settings.tabs.ai", { default: 'AI' }), icon: "🤖" },
        { id: "security", label: $_("settings.tabs.security"), icon: "🔐" },
        { id: "data", label: $_("settings.tabs.data"), icon: "💾" },
        { id: "appearance", label: $_("settings.tabs.appearance"), icon: "🎨" },
        { id: "accessibility", label: $_("settings.tabs.accessibility"), icon: "♿" },
        ...(debugUiEnabled ? [{ id: "debug", label: $_("settings.tabs.debug"), icon: "🧪" }] : [])
    ]);
</script>

<!-- Mobile (<md): collapse the wrapping tab strip into a single select to stop
     it from spilling onto two or three lines on small screens. -->
<div class="md:hidden">
    <label for="settings-tab-select" class="sr-only">{$_('settings.tabs.connection')}</label>
    <select
        id="settings-tab-select"
        value={activeTab}
        onchange={(e) => ontabchange((e.currentTarget as HTMLSelectElement).value)}
        class="w-full px-4 py-3 rounded-2xl border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-900 text-slate-900 dark:text-white font-bold text-sm focus:ring-2 focus:ring-teal-500 outline-none"
    >
        {#each tabs as tab}
            <option value={tab.id}>{tab.icon}  {tab.label}</option>
        {/each}
    </select>
</div>

<!-- Desktop (>=md): the existing horizontal pill strip. -->
<nav
    class="hidden md:flex card-base flex-wrap justify-center md:justify-start gap-2 p-1 rounded-2xl w-full"
    aria-label="Settings tabs"
>
    {#each tabs as tab}
        <button
            type="button"
            onclick={() => ontabchange(tab.id)}
            aria-pressed={activeTab === tab.id}
            class="group flex items-center justify-center gap-2 px-4 py-3 rounded-xl text-sm font-bold transition-all duration-200
                   {activeTab === tab.id
                ? 'bg-white dark:bg-slate-800 text-teal-600 dark:text-teal-400 shadow-sm ring-1 ring-slate-200/50 dark:ring-slate-700/50'
                : 'text-slate-500 dark:text-slate-400 hover:text-slate-900 dark:hover:text-white hover:bg-slate-200/50 dark:hover:bg-slate-800/50'}"
            title={tab.label}
        >
            <span class="text-lg opacity-80 group-hover:scale-110 transition-transform duration-200" aria-hidden="true">
                {tab.icon}
            </span>
            <span>{tab.label}</span>
            {#if activeTab === tab.id}
                <div class="ml-auto w-1.5 h-1.5 rounded-full bg-teal-500 animate-pulse" aria-hidden="true"></div>
            {/if}
        </button>
    {/each}
</nav>
