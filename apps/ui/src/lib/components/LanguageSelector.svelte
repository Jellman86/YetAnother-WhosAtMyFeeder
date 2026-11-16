<script lang="ts">
    import { locale, _ } from 'svelte-i18n';
    import { onMount, tick } from 'svelte';
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
    const uid = $props.id();
    const menuId = `language-selector-menu-${uid}`;
    let trigger: HTMLButtonElement | undefined = $state();
    let menu: HTMLDivElement | undefined = $state();
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
        if (changed) close({ refocus: true });
    }

    /*
     * A menu button (WAI-ARIA APG): opening moves focus to the checked language, the arrows move
     * through the list with wrap, Home and End reach its ends, Enter or Space chooses, Escape closes
     * with focus back on the button, and Tab closes and moves on.
     */
    function items(): HTMLElement[] {
        return menu ? [...menu.querySelectorAll<HTMLElement>('[role="menuitemradio"]')] : [];
    }

    async function open(): Promise<void> {
        showDropdown = true;
        await tick();
        const list = items();
        (list.find((item) => item.getAttribute('aria-checked') === 'true') ?? list[0])?.focus();
    }

    function close({ refocus }: { refocus: boolean }): void {
        showDropdown = false;
        if (refocus) trigger?.focus();
    }

    function onTriggerKeydown(event: KeyboardEvent): void {
        if (event.key === 'ArrowDown' || event.key === 'ArrowUp') {
            event.preventDefault();
            void open();
        }
    }

    function onMenuKeydown(event: KeyboardEvent): void {
        const list = items();
        const at = list.indexOf(document.activeElement as HTMLElement);
        const move = (index: number) => list[(index + list.length) % list.length]?.focus();
        switch (event.key) {
            case 'ArrowDown':
                event.preventDefault();
                move(at + 1);
                break;
            case 'ArrowUp':
                event.preventDefault();
                move(at - 1);
                break;
            case 'Home':
                event.preventDefault();
                move(0);
                break;
            case 'End':
                event.preventDefault();
                move(list.length - 1);
                break;
            case 'Escape':
                event.preventDefault();
                close({ refocus: true });
                break;
            case 'Tab':
                // Focus moves on as Tab would take it; the menu just closes behind it.
                close({ refocus: false });
                break;
        }
        event.stopPropagation();
    }
</script>

<div class="relative">
    <button
        bind:this={trigger}
        onclick={() => (showDropdown ? close({ refocus: false }) : void open())}
        onkeydown={onTriggerKeydown}
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
            bind:this={menu}
            onclick={(e) => e.stopPropagation()}
            onkeydown={onMenuKeydown}
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
                        tabindex="-1"
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
        <!-- A pointer's way out. Keyboard users close with Escape or Tab, so it takes no tab stop. -->
        <button
            class="fixed inset-0 z-55 cursor-default bg-transparent w-full h-full border-none"
            tabindex="-1"
            onclick={() => close({ refocus: false })}
            aria-label={$_('nav.close_language_selector', { default: 'Close language selector' })}
        ></button>
    {/if}
</div>
