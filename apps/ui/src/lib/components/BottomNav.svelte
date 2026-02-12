<script lang="ts">
    import { _ } from 'svelte-i18n';

    let { currentRoute, onNavigate, navItems } = $props<{
        currentRoute: string;
        onNavigate: (path: string) => void;
        navItems: any[];
    }>();
</script>

<nav class="md:hidden fixed bottom-0 left-0 right-0 z-50 bg-white/90 dark:bg-slate-900/90 backdrop-blur-xl border-t border-slate-200/80 dark:border-slate-700/50 pb-safe shadow-[0_-4px_12px_rgba(0,0,0,0.05)]">
    <div class="flex items-center justify-around h-16 px-2">
        {#each navItems as item}
            <button
                onclick={() => onNavigate(item.path)}
                class="flex flex-col items-center justify-center gap-1 w-full h-full transition-colors
                       {currentRoute === item.path ? 'text-brand-600 dark:text-brand-400' : 'text-slate-500 dark:text-slate-400'}"
            >
                <div class="relative">
                    <svg xmlns="http://www.w3.org/2000/svg" class="h-6 w-6" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2">
                        <path stroke-linecap="round" stroke-linejoin="round" d={item.icon} />
                    </svg>
                    {#if currentRoute === item.path}
                        <div class="absolute -bottom-1 left-1/2 -translate-x-1/2 w-1 h-1 rounded-full bg-brand-500"></div>
                    {/if}
                </div>
                <span class="text-[10px] font-bold uppercase tracking-wider">{item.label}</span>
            </button>
        {/each}
    </div>
</nav>
