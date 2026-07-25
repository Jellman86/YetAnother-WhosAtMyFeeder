<script lang="ts">
    import { onMount } from 'svelte';
    import { themeStore } from '../stores/theme.svelte';
    import { layoutStore } from '../stores/layout.svelte';
    import { authStore } from '../stores/auth.svelte';
    import { updateStatusStore } from '../stores/update_status.svelte';
    import { _ } from 'svelte-i18n';
    import BrandMark from './BrandMark.svelte';
    import LanguageSelector from './LanguageSelector.svelte';

    onMount(() => {
        updateStatusStore.load();
    });

    let { currentRoute, onNavigate, mobileSidebarOpen = false, onMobileClose, status } = $props<{
        currentRoute: string;
        onNavigate: (path: string) => void;
        mobileSidebarOpen?: boolean;
        onMobileClose?: () => void;
        status?: import('svelte').Snippet;
    }>();

    let collapsed = $derived(layoutStore.sidebarCollapsed);
    let accountInitial = $derived((authStore.username?.trim().slice(0, 1) || 'Y').toUpperCase());

    type NavSection = 'observe' | 'manage';

    type NavItem = {
        path: string;
        label: string;
        icon: string;
        section: NavSection;
        requiresAuth?: boolean;
    };

    type NavGroup = {
        id: NavSection;
        label: string;
        items: NavItem[];
    };

    const allNavItems = $derived.by((): NavItem[] => ([
        { path: '/', label: $_('nav.dashboard'), icon: 'M3 12l2-2m0 0l7-7 7 7M5 10v10a1 1 0 001 1h3m10-11l2 2m-2-2v10a1 1 0 01-1 1h-3m-6 0a1 1 0 001-1v-4a1 1 0 011-1h2a1 1 0 011 1v4a1 1 0 001 1m-6 0h6', section: 'observe' },
        { path: '/events', label: $_('nav.explorer'), icon: 'M4 6h16M4 10h16M4 14h16M4 18h16', section: 'observe' },
        { path: '/species', label: $_('nav.leaderboard'), icon: 'M9 19v-6a2 2 0 00-2-2H5a2 2 0 00-2 2v6a2 2 0 002 2h2a2 2 0 002-2zm0 0V9a2 2 0 012-2h2a2 2 0 012 2v10m-6 0a2 2 0 002 2h2a2 2 0 002-2m0 0V5a2 2 0 012-2h2a2 2 0 012 2v14a2 2 0 01-2 2h-2a2 2 0 01-2-2z', section: 'observe' },
        { path: '/settings', label: $_('nav.settings'), icon: 'M10.325 4.317c.426-1.756 2.924-1.756 3.35 0a1.724 1.724 0 002.573 1.066c1.543-.94 3.31.826 2.37 2.37a1.724 1.724 0 001.065 2.572c1.756.426 1.756 2.924 0 3.35a1.724 1.724 0 00-1.066 2.573c.94 1.543-.826 3.31-2.37 2.37a1.724 1.724 0 00-2.572 1.065c-.426 1.756-2.924 1.756-3.35 0a1.724 1.724 0 00-2.573-1.066c-1.543.94-3.31-.826-2.37-2.37a1.724 1.724 0 00-1.065-2.572c-1.756-.426-1.756-2.924 0-3.35a1.724 1.724 0 001.066-2.573c-.94-1.543.826-3.31 2.37-2.37.996.608 2.296.07 2.572-1.065z M15 12a3 3 0 11-6 0 3 3 0 016 0z', section: 'manage', requiresAuth: true },
        { path: '/about', label: $_('nav.about'), icon: 'M13 16h-1v-4h-1m1-4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z', section: 'manage' },
    ]));

    const navSections = $derived.by((): NavGroup[] => {
        const visibleItems = allNavItems.filter(item => !item.requiresAuth || authStore.showSettings);
        return [
            { id: 'observe', label: $_('nav.observe'), items: visibleItems.filter(item => item.section === 'observe') },
            { id: 'manage', label: $_('nav.manage'), items: visibleItems.filter(item => item.section === 'manage') },
        ];
    });

    function navigateAndClose(path: string): void {
        onNavigate(path);
        onMobileClose?.();
    }

    function handleNavClick(item: NavItem): void {
        navigateAndClose(item.path);
    }

    function isRouteActive(item: NavItem): boolean {
        if (item.path === '/') {
            return currentRoute === '/';
        }
        return currentRoute.startsWith(item.path);
    }
</script>

{#if mobileSidebarOpen}
    <div
        role="button"
        tabindex="0"
        class="fixed inset-0 z-40 bg-black/50 transition-opacity duration-300 md:hidden"
        onclick={onMobileClose}
        onkeydown={(event) => event.key === 'Enter' || event.key === 'Escape' ? onMobileClose?.() : null}
        aria-label={$_('nav.close_menu', { default: 'Close menu' })}
    ></div>
{/if}

<aside
    class="fixed left-0 top-0 z-50 flex h-full flex-col border-r border-slate-200/80 bg-white/95 shadow-xl backdrop-blur-xl transition-all duration-300 dark:border-slate-700/60 dark:bg-slate-900/95 {collapsed ? 'w-20' : 'w-64'} {mobileSidebarOpen ? 'translate-x-0' : '-translate-x-full md:translate-x-0'}"
>
    <div
        data-sidebar-brand
        class="relative flex w-full flex-col items-center text-center gap-3 border-b border-slate-200/80 px-4 py-5 dark:border-slate-700/60"
    >
        <button
            class="focus-ring -m-1 flex flex-col items-center gap-3 rounded-xl p-1"
            onclick={() => navigateAndClose('/')}
        >
            <BrandMark
                alt={$_('app.title')}
                sizes={collapsed ? '40px' : '64px'}
                class="flex-shrink-0 transition-all duration-300 {collapsed ? 'h-10 w-10' : 'h-16 w-16'}"
            />
            {#if !collapsed}
                <div class="flex flex-col items-center overflow-hidden">
                    <h1 class="text-gradient truncate text-sm font-bold leading-tight">
                        {$_('app.logo_title')}
                    </h1>
                    <span class="truncate text-xs font-semibold text-slate-600 dark:text-slate-300">
                        {$_('app.logo_subtitle')}
                    </span>
                </div>
            {/if}
        </button>
    </div>

    <nav class="min-h-0 flex-1 overflow-y-auto px-3 py-4" aria-label={$_('nav.navigation', { default: 'Primary navigation' })}>
        {#each navSections as section, sectionIndex}
            <div data-sidebar-section={section.id} class={sectionIndex === 0 ? '' : 'mt-5'}>
                {#if !collapsed}
                    <div class="px-3 pb-2 text-[0.625rem] font-bold uppercase tracking-[0.14em] text-slate-400 dark:text-slate-500">
                        {section.label}
                    </div>
                {/if}
                <div class="space-y-1">
                    {#each section.items as item}
                        <button
                            class="sidebar-nav {collapsed ? 'justify-center px-0' : ''}"
                            class:sidebar-nav-active={isRouteActive(item)}
                            class:sidebar-nav-inactive={!isRouteActive(item)}
                            onclick={() => handleNavClick(item)}
                            title={collapsed ? item.label : ''}
                            aria-label={item.label}
                            aria-current={isRouteActive(item) ? 'page' : undefined}
                        >
                            <svg xmlns="http://www.w3.org/2000/svg" class="h-5 w-5 flex-shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2" aria-hidden="true">
                                <path stroke-linecap="round" stroke-linejoin="round" d={item.icon} />
                            </svg>
                            {#if !collapsed}
                                <span class="truncate text-sm">{item.label}</span>
                            {/if}
                        </button>
                    {/each}
                </div>
            </div>
        {/each}
    </nav>

    {#if !collapsed}
        <div data-sidebar-status class="shrink-0 border-t border-slate-200/80 p-3 dark:border-slate-700/60">
            <div class="rounded-xl border border-slate-200/80 bg-slate-50/90 p-3 shadow-sm dark:border-slate-700/70 dark:bg-slate-800/55">
                <div class="mb-2 flex items-center justify-between gap-2">
                    <span class="text-[0.625rem] font-bold uppercase tracking-[0.14em] text-slate-500 dark:text-slate-400">
                        {$_('status.title')}
                    </span>
                </div>
                {@render status?.()}
            </div>
        </div>
    {/if}

    <div class="shrink-0 border-t border-slate-200/80 p-3 dark:border-slate-700/60">
        {#if !collapsed}
            {#if authStore.isAuthenticated}
                <div data-sidebar-account class="flex min-w-0 items-center gap-2 rounded-xl border border-slate-200/80 bg-slate-50/90 p-2 dark:border-slate-700/70 dark:bg-slate-800/55">
                    <div class="grid h-8 w-8 flex-shrink-0 place-items-center rounded-lg bg-brand-100 text-xs font-bold text-brand-700 dark:bg-brand-900/50 dark:text-brand-300">
                        {accountInitial}
                    </div>
                    <div class="min-w-0 flex-1">
                        <div class="truncate text-xs font-semibold text-slate-800 dark:text-slate-100">{authStore.username}</div>
                        <div class="truncate text-[0.625rem] text-slate-500 dark:text-slate-400">{$_('app.title')}</div>
                    </div>
                    <button
                        class="focus-ring rounded-lg p-2 text-slate-400 transition hover:bg-red-50 hover:text-red-600 dark:text-slate-500 dark:hover:bg-red-900/30 dark:hover:text-red-400"
                        onclick={() => authStore.logout()}
                        title={$_('auth.logout')}
                        aria-label={$_('auth.logout')}
                    >
                        <svg xmlns="http://www.w3.org/2000/svg" class="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2" aria-hidden="true">
                            <path stroke-linecap="round" stroke-linejoin="round" d="M17 16l4-4m0 0l-4-4m4 4H7m6 4v1a3 3 0 01-3 3H6a3 3 0 01-3-3V7a3 3 0 013-3h4a3 3 0 013 3v1" />
                        </svg>
                    </button>
                </div>
            {:else if authStore.isGuest}
                <div data-sidebar-account class="flex min-w-0 items-center gap-2 rounded-xl border border-slate-200/80 bg-slate-50/90 p-2 dark:border-slate-700/70 dark:bg-slate-800/55">
                    <div class="grid h-8 w-8 flex-shrink-0 place-items-center rounded-lg bg-indigo-100 text-indigo-700 dark:bg-indigo-900/40 dark:text-indigo-300">
                        <svg xmlns="http://www.w3.org/2000/svg" class="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2" aria-hidden="true">
                            <path stroke-linecap="round" stroke-linejoin="round" d="M15 12a3 3 0 11-6 0 3 3 0 016 0z" />
                            <path stroke-linecap="round" stroke-linejoin="round" d="M2.458 12C3.732 7.943 7.523 5 12 5c4.478 0 8.268 2.943 9.542 7-1.274 4.057-5.064 7-9.542 7-4.477 0-8.268-2.943-9.542-7z" />
                        </svg>
                    </div>
                    <div class="min-w-0 flex-1 truncate text-xs font-semibold text-slate-700 dark:text-slate-200">
                        {$_('auth.public_view')}
                    </div>
                    <button
                        class="focus-ring rounded-lg p-2 text-slate-400 transition hover:bg-accent-50 hover:text-accent-700 dark:text-slate-500 dark:hover:bg-accent-900/30 dark:hover:text-accent-300"
                        onclick={() => authStore.requestLogin()}
                        title={$_('auth.login')}
                        aria-label={$_('auth.login')}
                    >
                        <svg xmlns="http://www.w3.org/2000/svg" class="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2" aria-hidden="true">
                            <path stroke-linecap="round" stroke-linejoin="round" d="M11 16l-4-4m0 0l4-4m-4 4h14m-5 4v1a3 3 0 01-3 3H6a3 3 0 01-3-3V7a3 3 0 013-3h7a3 3 0 013 3v1" />
                        </svg>
                    </button>
                </div>
            {/if}
        {:else}
            {#if authStore.isAuthenticated}
                <button
                    class="sidebar-nav sidebar-nav-inactive justify-center px-0 hover:text-red-600 dark:hover:text-red-400"
                    onclick={() => authStore.logout()}
                    title={$_('auth.logout')}
                    aria-label={$_('auth.logout')}
                >
                    <svg xmlns="http://www.w3.org/2000/svg" class="h-5 w-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2" aria-hidden="true">
                        <path stroke-linecap="round" stroke-linejoin="round" d="M17 16l4-4m0 0l-4-4m4 4H7m6 4v1a3 3 0 01-3 3H6a3 3 0 01-3-3V7a3 3 0 013-3h4a3 3 0 013 3v1" />
                    </svg>
                </button>
            {:else if authStore.isGuest}
                <button
                    class="sidebar-nav sidebar-nav-inactive justify-center px-0"
                    onclick={() => authStore.requestLogin()}
                    title={$_('auth.login')}
                    aria-label={$_('auth.login')}
                >
                    <svg xmlns="http://www.w3.org/2000/svg" class="h-5 w-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2" aria-hidden="true">
                        <path stroke-linecap="round" stroke-linejoin="round" d="M11 16l-4-4m0 0l4-4m-4 4h14m-5 4v1a3 3 0 01-3 3H6a3 3 0 01-3-3V7a3 3 0 013-3h7a3 3 0 013 3v1" />
                    </svg>
                </button>
            {/if}
        {/if}
    </div>

    <div class="shrink-0 border-t border-slate-200/80 p-3 dark:border-slate-700/60">
        <div class="flex items-center {collapsed ? 'flex-col gap-1' : 'justify-around gap-1'}">
            <LanguageSelector dropUp compact />
            <button
                class="focus-ring rounded-xl p-2.5 text-slate-500 transition-all duration-200 hover:bg-slate-100 dark:text-slate-400 dark:hover:bg-slate-800"
                onclick={() => themeStore.toggle()}
                title={themeStore.isDark ? $_('theme.switch_light') : $_('theme.switch_dark')}
                aria-label={themeStore.isDark ? $_('theme.switch_light') : $_('theme.switch_dark')}
            >
                {#if themeStore.isDark}
                    <svg xmlns="http://www.w3.org/2000/svg" class="h-5 w-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2" aria-hidden="true">
                        <path stroke-linecap="round" stroke-linejoin="round" d="M12 3v1m0 16v1m9-9h-1M4 12H3m15.364 6.364l-.707-.707M6.343 6.343l-.707-.707m12.728 0l-.707.707M6.343 17.657l-.707.707M16 12a4 4 0 11-8 0 4 4 0 018 0z" />
                    </svg>
                {:else}
                    <svg xmlns="http://www.w3.org/2000/svg" class="h-5 w-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2" aria-hidden="true">
                        <path stroke-linecap="round" stroke-linejoin="round" d="M20.354 15.354A9 9 0 018.646 3.646 9.003 9.003 0 0012 21a9.003 9.003 0 008.354-5.646z" />
                    </svg>
                {/if}
            </button>
            <button
                class="focus-ring rounded-xl p-2.5 text-slate-500 transition-all duration-200 hover:bg-slate-100 dark:text-slate-400 dark:hover:bg-slate-800"
                onclick={() => layoutStore.toggleSidebar()}
                title={collapsed ? $_('nav.expand_sidebar') : $_('nav.collapse_sidebar')}
                aria-label={collapsed ? $_('nav.expand_sidebar') : $_('nav.collapse_sidebar')}
            >
                <svg xmlns="http://www.w3.org/2000/svg" class="h-5 w-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2" aria-hidden="true">
                    {#if collapsed}
                        <path stroke-linecap="round" stroke-linejoin="round" d="M13 5l7 7-7 7M5 5l7 7-7 7" />
                    {:else}
                        <path stroke-linecap="round" stroke-linejoin="round" d="M11 19l-7-7 7-7m8 14l-7-7 7-7" />
                    {/if}
                </svg>
            </button>
        </div>
    </div>
</aside>
