<script lang="ts">
    import { locale, locales, _ } from 'svelte-i18n';
    import { get } from 'svelte/store';
    import { onMount, onDestroy } from 'svelte'; // Import onMount and onDestroy

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
    let { dropUp = false } = $props<{ dropUp?: boolean }>();
    const menuId = 'language-selector-menu';
    let currentLocaleValue = $state('en'); // Local state for locale value

    // Subscribe to the locale store manually
    let unsubscribeLocale: () => void;
    onMount(() => {
        unsubscribeLocale = locale.subscribe(value => {
            currentLocaleValue = typeof value === 'string' && value ? value : 'en';
        });

        // Load saved preference on mount
        const saved = localStorage.getItem('preferred-language');
        const available = get(locales);
        if (saved && typeof saved === 'string') {
            const normalized = saved.split(/[-_]/)[0].toLowerCase();
            if (available.includes(normalized)) {
                locale.set(normalized);
            }
        }
    });

    onDestroy(() => {
        if (unsubscribeLocale) {
            unsubscribeLocale();
        }
    });

    function setLanguage(lang: string) {
        locale.set(lang);
        localStorage.setItem('preferred-language', lang);
        showDropdown = false;
    }
</script>

<div class="relative">
    <button
        onclick={() => showDropdown = !showDropdown}
        class="flex items-center gap-2 px-3 py-2 rounded-xl hover:bg-slate-100 dark:hover:bg-slate-800 text-slate-600 dark:text-slate-300 transition-all duration-200 focus-ring"
        aria-label={languageNames[currentLocaleValue || 'en'] || 'English'}
        aria-haspopup="menu"
        aria-expanded={showDropdown}
        aria-controls={menuId}
    >
        <svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M3 5h12M9 3v2m1.048 9.5A18.022 18.022 0 016.412 9m6.088 9h7M11 21l5-10 5 10M12.751 5C11.783 10.77 8.07 15.61 3 18.129" />
        </svg>
        <span class="text-xs font-bold uppercase tracking-wider">{languageNames[currentLocaleValue || 'en'] || 'English'}</span>
    </button>

    {#if showDropdown}
        <div 
            class="absolute right-0 w-48 bg-white dark:bg-slate-800 rounded-2xl shadow-2xl border border-slate-200 dark:border-slate-700 z-[60] overflow-hidden animate-in fade-in zoom-in-95 {dropUp ? 'bottom-full mb-2' : 'mt-2'}"
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
                        role="menuitem"
                        class="w-full px-4 py-2.5 text-left text-sm font-bold rounded-xl transition-all
                               {currentLocaleValue === code 
                                   ? 'bg-brand-500 text-white' 
                                   : 'text-slate-600 dark:text-slate-300 hover:bg-slate-100 dark:hover:bg-slate-700'}"
                    >
                        {name}
                    </button>
                {/each}
            </div>
        </div>
        <!-- Backdrop to close dropdown -->
        <button 
            class="fixed inset-0 z-[55] cursor-default bg-transparent w-full h-full border-none" 
            onclick={() => showDropdown = false}
            aria-label="Close language selector"
        ></button>
    {/if}
</div>
