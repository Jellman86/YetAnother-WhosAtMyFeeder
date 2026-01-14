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

<nav
    class="flex md:flex-col gap-2 p-1 md:p-0
           overflow-x-auto md:overflow-visible
           bg-slate-100/50 dark:bg-slate-800/50 md:bg-transparent md:dark:bg-transparent
           rounded-2xl md:rounded-none
           border border-slate-200/50 dark:border-slate-700/50 md:border-none
           w-full scrollbar-hide"
>
    {#each tabs as tab}
        <button
            onclick={() => ontabchange(tab.id)}
            class="group flex items-center gap-3 px-4 py-3 rounded-xl text-sm font-bold transition-all duration-200 whitespace-nowrap flex-shrink-0 md:w-full text-left
                   {activeTab === tab.id
                ? 'bg-white dark:bg-slate-800 text-teal-600 dark:text-teal-400 shadow-sm md:shadow-md ring-1 ring-slate-200/50 dark:ring-slate-700/50'
                : 'text-slate-500 dark:text-slate-400 hover:text-slate-900 dark:hover:text-white hover:bg-slate-200/50 dark:hover:bg-slate-800/50'}"
        >
            <span
                class="text-lg opacity-80 group-hover:scale-110 transition-transform duration-200"
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
</nav>

<style>
    /* Hide scrollbar for Chrome, Safari and Opera */
    .scrollbar-hide::-webkit-scrollbar {
        display: none;
    }
    /* Hide scrollbar for IE, Edge and Firefox */
    .scrollbar-hide {
        -ms-overflow-style: none; /* IE and Edge */
        scrollbar-width: none; /* Firefox */
    }
</style>
