<script lang="ts">
    import { locale, _ } from 'svelte-i18n';
    import { onMount } from 'svelte';
    import { setAppLocale } from '../i18n';

    const languageNames: Record<string, string> = {
        en: 'English',
        es: 'Español',
        fr: 'Français',
        de: 'Deutsch',
        ja: '日本語',
        zh: '中文',
        ru: 'Русский',
        pt: 'Português',
        it: 'Italiano'
    };

    let showDropdown = $state(false);
    let { dropUp = false, compact = false }: { dropUp?: boolean; compact?: boolean } = $props();
    const menuId = 'language-selector-menu';
    let currentLocaleValue = $state('en'); // Local state for locale value
    let languageChanging = $state(false);
    let languageError = $state(false);

    onMount(() => {
        return locale.subscribe(value => {
            currentLocaleValue = typeof value === 'string' && value ? value : 'en';
        });
    });

    async function setLanguage(lang: string): Promise<void> {
        if (languageChanging) return;
        languageChanging = true;
        languageError = false;
        const changed = await setAppLocale(lang);
        languageChanging = false;
        languageError = !changed;
        if (changed) showDropdown = false;
    }
</script>

<div class="relative">
    <button
        onclick={() => showDropdown = !showDropdown}
        class={compact
            ? 'btn btn-ghost min-h-11 min-w-11 p-2.5 rounded-xl hover:bg-surface-raised text-muted transition-all duration-200 focus-ring'
            : 'btn btn-ghost min-h-11 min-w-11 flex items-center gap-2 px-3 py-2 rounded-xl hover:bg-surface-raised text-muted transition-all duration-200 focus-ring'}
        aria-label={languageNames[currentLocaleValue || 'en'] || 'English'}
        title={compact ? (languageNames[currentLocaleValue || 'en'] || 'English') : undefined}
        aria-haspopup="menu"
        aria-expanded={showDropdown}
        aria-controls={menuId}
    >
        <svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M3 5h12M9 3v2m1.048 9.5A18.022 18.022 0 016.412 9m6.088 9h7M11 21l5-10 5 10M12.751 5C11.783 10.77 8.07 15.61 3 18.129" />
        </svg>
        {#if !compact}
            <span class="text-xs font-bold">{languageNames[currentLocaleValue || 'en'] || 'English'}</span>
        {/if}
    </button>

    {#if showDropdown}
        <div 
            class="absolute {compact ? 'left-0' : 'right-0'} w-48 bg-surface rounded-2xl shadow-2xl border border-line z-60 overflow-hidden animate-in fade-in zoom-in-95 {dropUp ? 'bottom-full mb-2' : 'mt-2'}"
            onclick={(e) => e.stopPropagation()}
            onkeydown={(e) => {
                if (e.key === 'Escape') showDropdown = false;
                e.stopPropagation();
            }}
            role="menu"
            tabindex="-1"
            id={menuId}
        >
            <div class="p-2 space-y-1">
                {#each Object.entries(languageNames) as [code, name]}
                    <button
                        onclick={() => setLanguage(code)}
                        disabled={languageChanging}
                        role="menuitemradio"
                        aria-checked={currentLocaleValue === code}
                        class="btn min-h-11 min-w-11 w-full justify-between px-4 py-2.5 text-left text-sm font-bold rounded-xl transition-all
                               {currentLocaleValue === code
                                   ? 'bg-accent text-accent-fg'
                                   : 'text-muted hover:bg-surface-raised'}"
                    >
                        <span>{name}</span>
                        {#if currentLocaleValue === code}
                            <svg class="h-4 w-4 shrink-0" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true" data-language-check>
                                <path d="M3.5 8.5l3 3 6-7" />
                            </svg>
                        {/if}
                    </button>
                {/each}
                {#if languageError}
                    <p class="px-3 py-2 text-xs font-medium leading-5 text-status-attention" role="alert">
                        {$_('common.language_load_error', { default: 'That language could not be loaded. Check your connection and try again.' })}
                    </p>
                {/if}
            </div>
        </div>
        <!-- Backdrop to close dropdown -->
        <button 
            class="fixed inset-0 z-55 cursor-default bg-transparent w-full h-full border-none" 
            onclick={() => showDropdown = false}
            aria-label={$_('nav.close_language_selector', { default: 'Close language selector' })}
        ></button>
    {/if}
</div>
