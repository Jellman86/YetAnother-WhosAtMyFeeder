<script lang="ts">
    import { _ } from 'svelte-i18n';

    interface Props {
        activeTab: string;
        ontabchange: (tab: string) => void;
    }

    let { activeTab, ontabchange }: Props = $props();

<<<<<<< Updated upstream
    const tabs = $derived([
        { id: 'connection', label: $_('settings.tabs.connection'), icon: '🔗' },
        { id: 'detection', label: $_('settings.tabs.detection'), icon: '🎯' },
        { id: 'notifications', label: $_('settings.tabs.notifications'), icon: '🔔' },
        { id: 'integrations', label: $_('settings.tabs.integrations'), icon: '🔌' },
        { id: 'data', label: $_('settings.tabs.data'), icon: '💾' },
        { id: 'appearance', label: $_('settings.tabs.appearance'), icon: '🎨' },
        { id: 'accessibility', label: $_('settings.tabs.accessibility'), icon: '♿' },
    ]);
=======
    const tabs = [
        { id: 'connection', label: 'Connection', icon: '🔗' },
        { id: 'detection', label: 'Detection', icon: '🎯' },
        { id: 'notifications', label: 'Notifications', icon: '🔔' },
        { id: 'integrations', label: 'Integrations', icon: '🔌' },
        { id: 'data', label: 'Data', icon: '💾' },
        { id: 'appearance', label: 'Appearance', icon: '🎨' },
        { id: 'accessibility', label: 'Accessibility', icon: '♿' },
    ];
>>>>>>> Stashed changes
</script>

<div class="flex items-center gap-1 p-1.5 bg-slate-100 dark:bg-slate-800/50 rounded-xl border border-slate-200/50 dark:border-slate-700/50">
    {#each tabs as tab}
        <button
            onclick={() => ontabchange(tab.id)}
            class="tab-button {activeTab === tab.id ? 'tab-button-active' : 'tab-button-inactive'}"
        >
            <span class="text-base">{tab.icon}</span>
            <span class="hidden sm:inline">{tab.label}</span>
        </button>
    {/each}
</div>
