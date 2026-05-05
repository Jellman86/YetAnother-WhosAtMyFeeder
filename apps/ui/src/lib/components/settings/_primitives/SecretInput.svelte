<script lang="ts">
    import { _ } from 'svelte-i18n';

    interface Props {
        id: string;
        value: string;
        saved: boolean;
        ariaLabel?: string;
        autocomplete?: string;
        // 'password' masks input. 'text' is for non-secret-but-still-saved
        // fields like OAuth client IDs that we still want to show 'Saved' on
        // for visual consistency with secrets.
        type?: 'password' | 'text';
        // Placeholder shown when no value is saved; defaults to a generic
        // 'Enter value' string.
        emptyPlaceholder?: string;
        oninput?: (next: string) => void;
    }

    let {
        id,
        value,
        saved,
        ariaLabel,
        autocomplete = 'off',
        type = 'password',
        emptyPlaceholder,
        oninput,
    }: Props = $props();

    // When a secret is saved we visually gray the input out, show the shared
    // 'Saved' tick badge inside the field, and use the redaction placeholder
    // so users can see something is stored without exposing it. Once the user
    // starts typing a replacement the badge disappears and the input goes back
    // to normal styling — the parent doesn't need to clear `saved` itself, the
    // primitive handles the visual contract via `effectivelySaved`.
    const effectivelySaved = $derived(saved && (value ?? '') === '');
</script>

<div class="relative">
    <input
        {id}
        {type}
        autocomplete={autocomplete as any}
        aria-label={ariaLabel}
        value={value as any}
        placeholder={effectivelySaved ? '***REDACTED***' : emptyPlaceholder}
        oninput={(e) => oninput?.((e.currentTarget as HTMLInputElement).value)}
        class="w-full px-4 py-3 pr-24 rounded-2xl border font-bold text-sm focus:ring-2 focus:ring-teal-500 outline-none transition-all
               {effectivelySaved
                 ? 'border-slate-200 dark:border-slate-700/60 bg-slate-100/70 dark:bg-slate-800/60 text-slate-500 dark:text-slate-400 placeholder-slate-400 dark:placeholder-slate-500'
                 : 'border-slate-200 dark:border-slate-700 bg-slate-50 dark:bg-slate-900/50 text-slate-900 dark:text-white placeholder-slate-400'}"
    />
    {#if effectivelySaved}
        <span
            class="pointer-events-none absolute inset-y-0 right-3 flex items-center"
            aria-hidden="false"
        >
            <span
                class="inline-flex items-center gap-1 rounded-full border border-emerald-200/80 bg-emerald-50 px-2 py-0.5 text-[9px] font-black uppercase tracking-widest text-emerald-700 dark:border-emerald-500/40 dark:bg-emerald-900/20 dark:text-emerald-300"
            >
                <svg class="h-2.5 w-2.5" fill="none" stroke="currentColor" viewBox="0 0 24 24" aria-hidden="true">
                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="3" d="M5 13l4 4L19 7" />
                </svg>
                {$_('common.saved')}
            </span>
        </span>
    {/if}
</div>
