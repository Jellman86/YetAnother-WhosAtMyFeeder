<script lang="ts">
    interface Props {
        activeTab: string;
        ontabchange: (tab: string) => void;
    }

    let { activeTab, ontabchange }: Props = $props();

    const tabs = [
        { id: 'connection', label: 'Connection', icon: '🔗' },
        { id: 'detection', label: 'Detection', icon: '🎯' },
        { id: 'integrations', label: 'Integrations', icon: '🔌' },
        { id: 'data', label: 'Data', icon: '💾' },
        { id: 'appearance', label: 'Appearance', icon: '🎨' },
    ];
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
