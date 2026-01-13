<script lang="ts">
    import { theme, isDark } from '../stores/theme';
    import { sidebarCollapsed } from '../stores/layout';
    import { _ } from 'svelte-i18n';

    let { currentRoute, onNavigate, mobileSidebarOpen = false, onMobileClose, status } = $props<{
        currentRoute: string;
        onNavigate: (path: string) => void;
        mobileSidebarOpen?: boolean;
        onMobileClose?: () => void;
        status?: import('svelte').Snippet;
    }>();

    let collapsed = $state(false);
    sidebarCollapsed.subscribe(value => {
        collapsed = value;
    });

    const navItems = $derived([
        { path: '/', label: $_('nav.dashboard'), icon: 'M3 12l2-2m0 0l7-7 7 7M5 10v10a1 1 0 001 1h3m10-11l2 2m-2-2v10a1 1 0 01-1 1h-3m-6 0a1 1 0 001-1v-4a1 1 0 011-1h2a1 1 0 011 1v4a1 1 0 001 1m-6 0h6' },
        { path: '/events', label: $_('nav.explorer'), icon: 'M4 6h16M4 10h16M4 14h16M4 18h16' },
        { path: '/species', label: $_('nav.leaderboard'), icon: 'M9 19v-6a2 2 0 00-2-2H5a2 2 0 00-2 2v6a2 2 0 002 2h2a2 2 0 002-2zm0 0V9a2 2 0 012-2h2a2 2 0 012 2v10m-6 0a2 2 0 002 2h2a2 2 0 002-2m0 0V5a2 2 0 012-2h2a2 2 0 012 2v14a2 2 0 01-2 2h-2a2 2 0 01-2-2z' },
        { path: '/settings', label: $_('nav.settings'), icon: 'M10.325 4.317c.426-1.756 2.924-1.756 3.35 0a1.724 1.724 0 002.573 1.066c1.543-.94 3.31.826 2.37 2.37a1.724 1.724 0 001.065 2.572c1.756.426 1.756 2.924 0 3.35a1.724 1.724 0 00-1.066 2.573c.94 1.543-.826 3.31-2.37 2.37a1.724 1.724 0 00-2.572 1.065c-.426 1.756-2.924 1.756-3.35 0a1.724 1.724 0 00-2.573-1.066c-1.543.94-3.31-.826-2.37-2.37a1.724 1.724 0 00-1.065-2.572c-1.756-.426-1.756-2.924 0-3.35a1.724 1.724 0 001.066-2.573c-.94-1.543.826-3.31 2.37-2.37.996.608 2.296.07 2.572-1.065z M15 12a3 3 0 11-6 0 3 3 0 016 0z' },
        { path: '/about', label: $_('nav.about'), icon: 'M13 16h-1v-4h-1m1-4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z' },
    ]);

    function handleNavClick(path: string) {
        onNavigate(path);
        // Close mobile sidebar after navigation
        if (onMobileClose) {
            onMobileClose();
        }
    }
</script>

<!-- Mobile backdrop overlay -->
{#if mobileSidebarOpen}
    <div
        role="button"
        tabindex="0"
        class="fixed inset-0 bg-black/50 z-40 md:hidden transition-opacity duration-300"
        onclick={onMobileClose}
        onkeydown={(e) => e.key === 'Enter' || e.key === 'Escape' ? onMobileClose?.() : null}
        aria-label="Close menu"
    ></div>
{/if}

<aside class="fixed left-0 top-0 h-full bg-white/90 dark:bg-slate-900/90 shadow-lg border-r border-slate-200/80 dark:border-slate-700/50 backdrop-blur-xl transition-all duration-300 flex flex-col {collapsed ? 'w-20' : 'w-64'}
    {mobileSidebarOpen ? 'translate-x-0 z-50' : '-translate-x-full md:translate-x-0 z-50'}">
    <!-- Logo and Collapse Button -->
    <div class="flex items-center justify-between p-4 border-b border-slate-200/80 dark:border-slate-700/50 h-16">
        {#if !collapsed}
            <button
                class="flex items-center gap-3 focus-ring rounded-lg p-1 -m-1"
                onclick={() => handleNavClick('/')}
            >
                <div class="w-9 h-9 rounded-xl bg-gradient-to-br from-brand-500 to-teal-400 flex items-center justify-center shadow-glow flex-shrink-0">
                    <span class="text-white text-lg">🐦</span>
                </div>
                <div class="flex flex-col overflow-hidden">
                    <h1 class="text-sm font-bold text-gradient leading-tight truncate">
                        {$_('app.logo_title')}
                    </h1>
                    <span class="text-xs font-semibold text-slate-600 dark:text-slate-300 truncate">
                        {$_('app.logo_subtitle')}
                    </span>
                </div>
            </button>
        {:else}
            <button
                class="w-full flex items-center justify-center focus-ring rounded-lg p-1"
                onclick={() => handleNavClick('/')}
            >
                <div class="w-9 h-9 rounded-xl bg-gradient-to-br from-brand-500 to-teal-400 flex items-center justify-center shadow-glow">
                    <span class="text-white text-lg">🐦</span>
                </div>
            </button>
        {/if}

        {#if !collapsed}
            <button
                class="p-2 rounded-lg hover:bg-slate-100 dark:hover:bg-slate-800 text-slate-500 dark:text-slate-400 transition-all duration-200 focus-ring"
                onclick={() => sidebarCollapsed.toggle()}
                title={$_('nav.collapse_sidebar')}
            >
                <svg xmlns="http://www.w3.org/2000/svg" class="h-5 w-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2">
                    <path stroke-linecap="round" stroke-linejoin="round" d="M11 19l-7-7 7-7m8 14l-7-7 7-7" />
                </svg>
            </button>
        {/if}
    </div>

    <!-- Navigation -->
    <nav class="flex-1 overflow-y-auto p-3 space-y-1">
        {#each navItems as item}
            <button
                class="w-full flex items-center gap-3 px-4 py-3 rounded-xl text-left font-medium transition-all duration-200 focus-ring
                       {currentRoute === item.path
                           ? 'bg-brand-50 dark:bg-brand-900/30 text-brand-700 dark:text-brand-300'
                           : 'text-slate-600 dark:text-slate-400 hover:bg-slate-100 dark:hover:bg-slate-800 hover:text-slate-900 dark:hover:text-white'}"
                onclick={() => handleNavClick(item.path)}
                title={collapsed ? item.label : ''}
            >
                <svg xmlns="http://www.w3.org/2000/svg" class="h-5 w-5 flex-shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2">
                    <path stroke-linecap="round" stroke-linejoin="round" d={item.icon} />
                </svg>
                {#if !collapsed}
                    <span class="text-sm">{item.label}</span>
                {/if}
            </button>
        {/each}
    </nav>

    <!-- Status Section -->
    {#if !collapsed}
        <div class="p-3 border-t border-slate-200/80 dark:border-slate-700/50">
            <div class="bg-slate-50 dark:bg-slate-800/50 rounded-xl p-3 space-y-2">
                {@render status?.()}
            </div>
        </div>
    {/if}

    <!-- Expand Button (collapsed state) -->
    {#if collapsed}
        <div class="p-3 border-t border-slate-200/80 dark:border-slate-700/50">
            <button
                class="w-full flex items-center justify-center p-3 rounded-xl hover:bg-slate-100 dark:hover:bg-slate-800 text-slate-500 dark:text-slate-400 transition-all duration-200 focus-ring"
                onclick={() => sidebarCollapsed.toggle()}
                title={$_('nav.expand_sidebar')}
            >
                <svg xmlns="http://www.w3.org/2000/svg" class="h-5 w-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2">
                    <path stroke-linecap="round" stroke-linejoin="round" d="M13 5l7 7-7 7M5 5l7 7-7 7" />
                </svg>
            </button>
        </div>
    {/if}

    <!-- Theme Toggle at Bottom -->
    <div class="p-3 border-t border-slate-200/80 dark:border-slate-700/50">
        <button
            class="w-full flex items-center gap-3 px-4 py-3 rounded-xl hover:bg-slate-100 dark:hover:bg-slate-800 text-slate-500 dark:text-slate-400 transition-all duration-200 focus-ring"
            onclick={() => theme.toggle()}
            title={collapsed ? ($isDark ? $_('theme.switch_light') : $_('theme.switch_dark')) : ''}
        >
            {#if $isDark}
                <svg xmlns="http://www.w3.org/2000/svg" class="h-5 w-5 flex-shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2">
                    <path stroke-linecap="round" stroke-linejoin="round" d="M12 3v1m0 16v1m9-9h-1M4 12H3m15.364 6.364l-.707-.707M6.343 6.343l-.707-.707m12.728 0l-.707.707M6.343 17.657l-.707.707M16 12a4 4 0 11-8 0 4 4 0 018 0z" />
                </svg>
            {:else}
                <svg xmlns="http://www.w3.org/2000/svg" class="h-5 w-5 flex-shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2">
                    <path stroke-linecap="round" stroke-linejoin="round" d="M20.354 15.354A9 9 0 018.646 3.646 9.003 9.003 0 0012 21a9.003 9.003 0 008.354-5.646z" />
                </svg>
            {/if}
            {#if !collapsed}
                <span class="text-sm font-medium">{$isDark ? $_('theme.light') : $_('theme.dark')}</span>
            {/if}
        </button>
    </div>
</aside>
