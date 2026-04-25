<script lang="ts" generics="T extends string">
    interface Option {
        value: T;
        label: string;
        icon?: string;
        // Optional secondary line — used by font/colour pickers to show a
        // preview string under the main label.
        sub?: string;
        // Optional tertiary line — used for language hints on font themes.
        meta?: string;
        // Optional swatch class (e.g. "bg-teal-500") — used by colour theme.
        swatch?: string;
    }

    interface Props {
        value: T;
        options: Option[];
        onchange: (next: T) => void;
        ariaLabelTemplate: (label: string) => string;
        // Layout: 'tile' renders compact icon-stack tiles (theme: light/dark/system);
        // 'card' renders wider rows with sub/meta/swatch (font, colour, naming).
        layout?: 'tile' | 'card';
        // For 'card' layout the columns at >= sm.  Defaults to 2.
        columns?: 1 | 2 | 3;
    }

    let {
        value,
        options,
        onchange,
        ariaLabelTemplate,
        layout = 'tile',
        columns = 2
    }: Props = $props();

    const gridClass = $derived.by(() => {
        if (layout === 'tile') return 'grid grid-cols-3 gap-2';
        const colsClass = columns === 1
            ? 'grid-cols-1'
            : columns === 3
                ? 'grid-cols-1 sm:grid-cols-3'
                : 'grid-cols-1 sm:grid-cols-2';
        return `grid ${colsClass} gap-3`;
    });
</script>

<div class={gridClass}>
    {#each options as opt}
        {@const active = opt.value === value}
        <button
            type="button"
            onclick={() => onchange(opt.value)}
            aria-pressed={active}
            aria-label={ariaLabelTemplate(opt.label)}
            class="rounded-2xl border-2 transition-all duration-200 focus:outline-none focus:ring-2 focus:ring-teal-400
                   {layout === 'tile'
                        ? 'flex flex-col items-center gap-2 p-4'
                        : 'flex items-center gap-4 p-4 text-left'}
                   {active
                        ? 'bg-teal-500 border-teal-500 text-white shadow-lg shadow-teal-500/20'
                        : 'bg-white dark:bg-slate-900/50 border-slate-100 dark:border-slate-700/50 text-slate-700 dark:text-slate-200 hover:border-teal-500/30'}"
        >
            {#if layout === 'tile'}
                {#if opt.icon}
                    <span class="text-2xl" aria-hidden="true">{opt.icon}</span>
                {/if}
                <span class="text-[10px] font-black uppercase tracking-widest">{opt.label}</span>
            {:else}
                {#if opt.swatch}
                    <div class="w-10 h-10 rounded-xl {opt.swatch} shrink-0"></div>
                {:else if opt.icon}
                    <span class="text-2xl shrink-0" aria-hidden="true">{opt.icon}</span>
                {/if}
                <div class="flex-1 min-w-0">
                    <div class="text-sm font-black uppercase tracking-widest {active ? 'text-white' : 'text-slate-900 dark:text-white'}">
                        {opt.label}
                    </div>
                    {#if opt.sub}
                        <div class="text-xs font-medium mt-1 {active ? 'text-white/80' : 'text-slate-500 dark:text-slate-400'} truncate">
                            {opt.sub}
                        </div>
                    {/if}
                    {#if opt.meta}
                        <div class="text-[10px] font-semibold mt-1 {active ? 'text-white/70' : 'text-slate-400 dark:text-slate-500'}">
                            {opt.meta}
                        </div>
                    {/if}
                </div>
            {/if}
        </button>
    {/each}
</div>
