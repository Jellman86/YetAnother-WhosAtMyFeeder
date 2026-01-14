<script lang="ts">
    import { _ } from "svelte-i18n";

    interface Props {
        activeTab: string;
        ontabchange: (tab: string) => void;
    }

    let { activeTab, ontabchange }: Props = $props();

    const tabs = $derived([
        { id: "connection", label: $_("settings.tabs.connection"), icon: "🔗" },
        { id: "detection", label: $_("settings.tabs.detection"), icon: "🎯" },
        {
            id: "notifications",
            label: $_("settings.tabs.notifications"),
            icon: "🔔",
        },
        {
            id: "integrations",
            label: $_("settings.tabs.integrations"),
            icon: "🔌",
        },
        { id: "data", label: $_("settings.tabs.data"), icon: "💾" },
        { id: "appearance", label: $_("settings.tabs.appearance"), icon: "🎨" },
        {
            id: "accessibility",
            label: $_("settings.tabs.accessibility"),
            icon: "♿",
        },
    ]);
</script>

<nav class="md:w-64 flex-shrink-0">
    <!-- Mobile: Horizontal Scroll -->
    <!-- Desktop: Vertical List -->
    <div
        class="flex md:flex-col gap-1 md:gap-2 p-1.5 md:p-0 
               bg-slate-100 md:bg-transparent dark:bg-slate-800/50 md:dark:bg-transparent 
               rounded-xl md:rounded-none 
               border border-slate-200/50 md:border-none dark:border-slate-700/50 
               overflow-x-auto md:overflow-visible min-w-min md:min-w-0"
    >
        {#each tabs as tab}
            <button
                onclick={() => ontabchange(tab.id)}
                class="group flex items-center gap-3 px-4 py-3 rounded-xl text-sm font-bold transition-all duration-200 whitespace-nowrap
                       {activeTab === tab.id
                    ? 'bg-white dark:bg-slate-800 text-teal-600 dark:text-teal-400 shadow-sm md:shadow-md ring-1 ring-slate-200/50 dark:ring-slate-700/50'
                    : 'text-slate-500 dark:text-slate-400 hover:text-slate-900 dark:hover:text-white hover:bg-slate-200/50 dark:hover:bg-slate-800/50'}"
            >
                <span class="text-lg opacity-80 group-hover:scale-110 transition-transform duration-200"
                    >{tab.icon}</span
                >
                <span>{tab.label}</span>
                {#if activeTab === tab.id}
                    <div
                        class="hidden md:block ml-auto w-1.5 h-1.5 rounded-full bg-teal-500 animate-pulse"
                    ></div>
                {/if}
            </button>
        {/each}
    </div>
</nav>

<style>
</style>
