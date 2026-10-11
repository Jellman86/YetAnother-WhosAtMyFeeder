<script lang="ts" generics="T extends string">
    interface Option {
        value: T;
        label: string;
        disabled?: boolean;
    }

    interface Props {
        id: string;
        value: T;
        options: Option[];
        ariaLabel?: string;
        ariaDescribedBy?: string;
        onchange: (next: T) => void;
        disabled?: boolean;
    }

    let { id, value, options, ariaLabel, ariaDescribedBy, onchange, disabled = false }: Props = $props();
</script>

<!-- Native menu-list styling in desktop WebKit discards padding and height (a 22px
     control), so the box is drawn here; the option picker stays native. Narrow
     screens use tighter padding so enlarged text keeps a visible value. -->
<div class="relative">
    <select
        {id}
        {value}
        {disabled}
        aria-label={ariaLabel}
        aria-describedby={ariaDescribedBy}
        onchange={(e) => onchange(e.currentTarget.value as T)}
        class="peer w-full min-h-11 appearance-none pl-2 pr-5 sm:pl-4 sm:pr-8 py-3 rounded-2xl border border-slate-200 dark:border-slate-700 bg-slate-50 dark:bg-slate-900/50 text-slate-900 dark:text-white font-bold text-sm focus:ring-2 focus:ring-brand-500 outline-none transition-all disabled:opacity-50 disabled:cursor-not-allowed"
    >
        {#each options as opt}
            <option value={opt.value} disabled={opt.disabled}>{opt.label}</option>
        {/each}
    </select>
    <svg
        class="pointer-events-none absolute right-1.5 sm:right-3 top-1/2 h-3 w-3 -translate-y-1/2 text-slate-500 dark:text-slate-400 peer-disabled:opacity-50"
        viewBox="0 0 20 20"
        fill="none"
        stroke="currentColor"
        stroke-width="2"
        stroke-linecap="round"
        stroke-linejoin="round"
        aria-hidden="true"
    >
        <path d="M5 7l5 6 5-6" />
    </svg>
</div>
