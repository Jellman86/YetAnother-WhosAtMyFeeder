<script lang="ts">
    import { APP_ICON_192_URL } from '../assets';

    export let onToggleMenu: () => void = () => undefined;
    export let onToggleTheme: () => void = () => undefined;
    export let theme: string = 'light';
    export let appTitle: string = '';
    export let toggleMenuLabel: string = 'Toggle menu';
    export let switchThemeLabel: string = 'Switch theme';
</script>

<div class="md:hidden sticky top-0 z-40 bg-white/90 dark:bg-slate-900/90 backdrop-blur-xl border-b border-slate-200/80 dark:border-slate-700/50 h-[var(--app-chrome-height,4rem)] flex items-center px-4 justify-between">
    <button
        class="p-2 -ml-2 text-slate-500 hover:bg-slate-100 dark:hover:bg-slate-800 rounded-lg transition-colors"
        onclick={onToggleMenu}
        aria-label={toggleMenuLabel}
    >
        <svg xmlns="http://www.w3.org/2000/svg" class="h-6 w-6" fill="none" viewBox="0 0 24 24" stroke="currentColor">
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 6h16M4 12h16M4 18h16" />
        </svg>
        <span class="sr-only">{toggleMenuLabel}</span>
    </button>
    <div class="flex items-center gap-2">
        <div class="w-7 h-7 flex items-center justify-center overflow-hidden">
            <img src={APP_ICON_192_URL} alt={appTitle} class="w-full h-full object-contain bg-transparent" />
        </div>
        <span class="text-sm font-bold text-gradient">{appTitle}</span>
    </div>
    <button
        class="p-2 rounded-lg hover:bg-slate-100 dark:hover:bg-slate-800 text-slate-500 dark:text-slate-400 transition-colors"
        onclick={onToggleTheme}
        aria-label={switchThemeLabel}
    >
        {#if theme === 'dark'}
            <svg xmlns="http://www.w3.org/2000/svg" class="h-5 w-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2">
                <path stroke-linecap="round" stroke-linejoin="round" d="M12 3v1m0 16v1m9-9h-1M4 12H3m15.364 6.364l-.707-.707M6.343 6.343l-.707-.707m12.728 0l-.707.707M6.343 17.657l-.707.707M16 12a4 4 0 11-8 0 4 4 0 018 0z" />
            </svg>
        {:else}
            <svg xmlns="http://www.w3.org/2000/svg" class="h-5 w-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2">
                <path stroke-linecap="round" stroke-linejoin="round" d="M20.354 15.354A9 9 0 018.646 3.646 9.003 9.003 0 0012 21a9.003 9.003 0 008.354-5.646z" />
            </svg>
        {/if}
    </button>
</div>
