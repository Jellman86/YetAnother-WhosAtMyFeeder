<script lang="ts">
    import { pointerMayPrefetch } from '../app/route-prefetch';
    import { avatarStore } from '../stores/avatar.svelte';
    import { onMount } from 'svelte';
    import { themeStore } from '../stores/theme.svelte';
    import { layoutStore } from '../stores/layout.svelte';
    import { authStore } from '../stores/auth.svelte';
    import { settingsStore } from '../stores/settings.svelte';
    import { updateStatusStore } from '../stores/update_status.svelte';
    import { _ } from 'svelte-i18n';
    import BrandMark from './BrandMark.svelte';
    import LanguageSelector from './LanguageSelector.svelte';
    import SystemTelemetryGraph from './SystemTelemetryGraph.svelte';
    import { trapFocus } from '../utils/focus-trap';
    import { incidentWorkspaceStore } from '../stores/incident_workspace.svelte';
    import { systemStatusStore } from '../stores/system_status.svelte';
    import { healthAttention, openHealthItems } from '../utils/system-status';

    onMount(() => {
        updateStatusStore.load();
    });

    let { currentRoute, onNavigate, onPrefetch, isMobile = false, mobileSidebarOpen = false, onMobileClose, status }: {
        currentRoute: string;
        onNavigate: (path: string) => void;
        /** A link is hovered with a mouse or pen, or focused: its page's code can start loading ahead of the click. */
        onPrefetch?: (path: string) => void;
        /** On a phone the sidebar is a drawer over the page. */
        isMobile?: boolean;
        mobileSidebarOpen?: boolean;
        onMobileClose?: () => void;
        /** The status rows; the argument says whether the sidebar is the icon rail. */
        status?: import('svelte').Snippet<[boolean]>;
    } = $props();

    let asideEl = $state<HTMLElement | null>(null);
    const drawerOpen = $derived(isMobile && mobileSidebarOpen);
    // A closed drawer is only moved off screen, so without inert its controls would still
    // take keyboard focus and be read out, ahead of the page, while nobody can see them.
    const drawerClosed = $derived(isMobile && !mobileSidebarOpen);

    // An open drawer is modal: focus starts on the page you are on, stays inside until it
    // closes, and the trap returns it to the menu button that opened it.
    $effect(() => {
        if (!drawerOpen || !asideEl) return;
        const release = trapFocus(asideEl);
        asideEl.querySelector<HTMLElement>('nav [aria-current="page"]')?.focus({ preventScroll: true });
        return release;
    });

    function handleWindowKeydown(event: KeyboardEvent): void {
        if (!drawerOpen || event.key !== 'Escape' || event.defaultPrevented) return;
        event.preventDefault();
        onMobileClose?.();
    }

    // The icon rail is a desktop layout; a phone drawer always shows its labels.
    let collapsed = $derived(layoutStore.sidebarCollapsed && !isMobile);
    const health = $derived(healthAttention(
        authStore.showSettings
            ? openHealthItems(
                systemStatusStore.snapshot?.connections ?? incidentWorkspaceStore.workspacePayload?.connections ?? null,
                incidentWorkspaceStore.currentIssues.length
            )
            : null
    ));
    const issuesLabel = $derived(
        $_('status.issues_need_attention', {
            values: { count: health.count },
            default: '{count, plural, one {# issue needs attention} other {# issues need attention}}'
        })
    );
    // Said before the count, so the link is named "Health: 2 issues need attention".
    const healthLinkPrefix = $derived(`${$_('status.open_health', { default: 'Health' })}: `);
    const healthLinkName = $derived(
        health.needsAttention ? `${healthLinkPrefix}${issuesLabel}` : $_('status.open_health', { default: 'Health' })
    );

    function openHealth(event: MouseEvent): void {
        event.preventDefault();
        navigateAndClose('/system-health');
    }
    let accountInitial = $derived((authStore.username?.trim().slice(0, 1) || 'Y').toUpperCase());
    // The picture is fetched with the owner's credentials; a guest or signed-out viewer has none.
    $effect(() => {
        avatarStore.sync(authStore.isAuthenticated ? authStore.avatarVersion : null);
    });

    type NavSection = 'observe' | 'manage';

    type NavItem = {
        path: string;
        label: string;
        icon: string;
        section: NavSection;
        requiresAuth?: boolean;
        /** Left out while false: a page for a feature this installation does not have. */
        available?: boolean;
    };

    type NavGroup = {
        id: NavSection;
        label: string;
        items: NavItem[];
    };

    const audioHistoryAvailable = $derived(
        (settingsStore.settings?.birdnet_enabled ?? authStore.birdnetEnabled ?? false) && authStore.canViewAudio
    );

    const allNavItems = $derived.by((): NavItem[] => ([
        { path: '/', label: $_('nav.dashboard'), icon: 'M3 12l2-2m0 0l7-7 7 7M5 10v10a1 1 0 001 1h3m10-11l2 2m-2-2v10a1 1 0 01-1 1h-3m-6 0a1 1 0 001-1v-4a1 1 0 011-1h2a1 1 0 011 1v4a1 1 0 001 1m-6 0h6', section: 'observe' },
        { path: '/events', label: $_('nav.explorer'), icon: 'M4 6h16M4 10h16M4 14h16M4 18h16', section: 'observe' },
        { path: '/observations/new', label: $_('nav.add_observation', { default: 'Add observation' }), icon: 'M12 16V4m0 0L8 8m4-4 4 4M5 14v4a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2v-4', section: 'observe', requiresAuth: true },
        { path: '/species', label: $_('nav.leaderboard'), icon: 'M9 19v-6a2 2 0 00-2-2H5a2 2 0 00-2 2v6a2 2 0 002 2h2a2 2 0 002-2zm0 0V9a2 2 0 012-2h2a2 2 0 012 2v10m-6 0a2 2 0 002 2h2a2 2 0 002-2m0 0V5a2 2 0 012-2h2a2 2 0 012 2v14a2 2 0 01-2 2h-2a2 2 0 01-2-2z', section: 'observe' },
        // The listening history exists only where BirdNET-Go is connected and the reader may see it.
        { path: '/audio', label: $_('nav.audio_history', { default: 'Audio history' }), icon: 'M4 12v2m4-5v8m4-13v16m4-13v10m4-7v4', section: 'observe', available: audioHistoryAvailable },
        { path: '/settings', label: $_('nav.settings'), icon: 'M10.325 4.317c.426-1.756 2.924-1.756 3.35 0a1.724 1.724 0 002.573 1.066c1.543-.94 3.31.826 2.37 2.37a1.724 1.724 0 001.065 2.572c1.756.426 1.756 2.924 0 3.35a1.724 1.724 0 00-1.066 2.573c.94 1.543-.826 3.31-2.37 2.37a1.724 1.724 0 00-2.572 1.065c-.426 1.756-2.924 1.756-3.35 0a1.724 1.724 0 00-2.573-1.066c-1.543.94-3.31-.826-2.37-2.37a1.724 1.724 0 00-1.065-2.572c-1.756-.426-1.756-2.924 0-3.35a1.724 1.724 0 001.066-2.573c-.94-1.543.826-3.31 2.37-2.37.996.608 2.296.07 2.572-1.065z M15 12a3 3 0 11-6 0 3 3 0 016 0z', section: 'manage', requiresAuth: true },
        { path: '/system-health', label: $_('nav.health', { default: 'Health' }), icon: 'M3 12h4l3-8 4 16 3-8h4', section: 'manage', requiresAuth: true },
        { path: '/about', label: $_('nav.about'), icon: 'M13 16h-1v-4h-1m1-4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z', section: 'manage' },
    ]));

    const navSections = $derived.by((): NavGroup[] => {
        const visibleItems = allNavItems.filter(item =>
            (!item.requiresAuth || authStore.showSettings) && item.available !== false
        );
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

<svelte:window onkeydown={handleWindowKeydown} />

{#if mobileSidebarOpen}
    <div
        role="button"
        tabindex="0"
        class="fixed inset-0 z-40 bg-media/50 transition-opacity duration-300 md:hidden"
        onclick={onMobileClose}
        onkeydown={(event) => event.key === 'Enter' ? onMobileClose?.() : null}
        aria-label={$_('nav.close_menu', { default: 'Close menu' })}
    ></div>
{/if}

<aside
    bind:this={asideEl}
    id="app-sidebar"
    inert={drawerClosed}
    data-sidebar-drawer={isMobile ? (mobileSidebarOpen ? 'open' : 'closed') : undefined}
    class="fixed left-0 top-0 z-50 flex h-full max-w-full flex-col border-r border-line-soft bg-surface transition-all duration-300 {collapsed ? 'w-20' : 'w-64'} {mobileSidebarOpen ? 'translate-x-0' : '-translate-x-full md:translate-x-0'}"
>
    <div
        data-sidebar-brand
        class="relative flex w-full flex-col items-center text-center gap-3 border-b border-line-soft px-4 py-5 [@media(max-height:42rem)]:py-3"
    >
        <button
            class="focus-ring -m-1 flex flex-col items-center gap-3 rounded-xl p-1"
            onclick={() => navigateAndClose('/')}
        >
            <BrandMark
                alt={$_('app.title')}
                sizes={collapsed ? '40px' : '64px'}
                class="shrink-0 rounded-2xl transition-all duration-300 {collapsed ? 'h-10 w-10' : 'h-16 w-16'}"
            />
            {#if !collapsed}
                <div class="flex flex-col items-center gap-0.5 overflow-hidden">
                    <!-- The wordmark, not a heading: each page carries its own h1. -->
                    <span class="truncate font-display text-lg font-bold leading-tight text-strong">
                        {$_('app.logo_title')}
                    </span>
                    <span class="truncate text-sm text-muted">
                        {$_('app.logo_subtitle')}
                    </span>
                </div>
            {/if}
        </button>
    </div>

    <!-- Every place in the app stays in view: on a short window System status below gives way first (it
         scrolls inside itself, see the style below), and only when it has no room left does the
         navigation scroll. -->
    <nav class="min-h-0 overflow-y-auto px-3 py-4" aria-label={$_('nav.navigation', { default: 'Primary navigation' })}>
        {#each navSections as section, sectionIndex}
            <div data-sidebar-section={section.id} class={sectionIndex === 0 ? '' : 'mt-5'}>
                {#if !collapsed}
                    <!-- Headed like the Settings rail's groups, so the two navigations read as one. -->
                    <div class="px-3 pb-1 text-sm font-semibold text-strong">
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
                            onpointerenter={(event) => { if (pointerMayPrefetch(event.pointerType)) onPrefetch?.(item.path); }}
                            onfocus={() => onPrefetch?.(item.path)}
                            title={collapsed ? item.label : ''}
                            aria-label={item.label}
                            aria-current={isRouteActive(item) ? 'page' : undefined}
                        >
                            <svg xmlns="http://www.w3.org/2000/svg" class="h-5 w-5 shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2" aria-hidden="true">
                                <path stroke-linecap="round" stroke-linejoin="round" d={item.icon} />
                            </svg>
                            {#if !collapsed}
                                <!-- A long label wraps onto a second line (German "Beobachtung hinzufügen") rather than losing its end. -->
                                <span class="min-w-0 hyphens-auto text-base leading-tight wrap-break-word">{item.label}</span>
                            {/if}
                        </button>
                    {/each}
                </div>
            </div>
        {/each}
    </nav>

    <!-- System status is a plain list on a neutral surface: measured states in words, one muted
         line of resource readings, and the way to Health. Only the owner can reach Health,
         so a guest gets no link. The link asks for attention only for issues Health lists as open,
         read from the same store, so the two always agree. -->
    <div data-sidebar-status class="mt-auto min-h-0 overflow-y-auto border-t border-line-soft p-3 [@media(max-height:42rem)]:hidden">
        {#if collapsed}
            <section class="flex flex-col items-center gap-1" aria-label={$_('status.title')} data-sidebar-status-card>
                {@render status?.(true)}
                {#if authStore.showSettings}
                    <a
                        href="/system-health"
                        class="focus-ring relative grid h-11 w-11 place-items-center rounded-lg text-ink transition-colors hover:bg-surface-raised"
                        title={healthLinkName}
                        data-sidebar-status-link
                        data-health-attention={health.needsAttention}
                        onclick={openHealth}
                        onpointerenter={(event) => { if (pointerMayPrefetch(event.pointerType)) onPrefetch?.('/system-health'); }}
                        onfocus={() => onPrefetch?.('/system-health')}
                    >
                        <span class="sr-only">{healthLinkName}</span>
                        <svg class="h-5 w-5" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
                            <path d="M3 12h4l2-6 4 12 2-6h6" />
                        </svg>
                        {#if health.needsAttention}
                            <span class="absolute right-1.5 top-1.5 h-2 w-2 rotate-45 bg-status-attention-line" aria-hidden="true"></span>
                        {/if}
                    </a>
                {/if}
            </section>
        {:else}
            <section
                class="rounded-xl border border-line-soft bg-surface-raised p-3"
                aria-labelledby="sidebar-status-title"
                data-sidebar-status-card
            >
                <h2 id="sidebar-status-title" class="mb-2 text-xs font-semibold leading-4 text-ink">
                    {$_('status.title')}
                </h2>
                {@render status?.(false)}
                <SystemTelemetryGraph />
                {#if authStore.showSettings}
                    <!-- One line, one control: with issues open the count is the link's wording and
                         "Health" is said before it for a screen reader; with none open the
                         link is just "Health". -->
                    <a
                        href="/system-health"
                        class="focus-ring -mx-1 mt-2 flex min-h-7 items-center justify-between gap-x-2 rounded-md border-t border-line-soft px-1 pt-2 text-xs font-semibold leading-4 text-ink transition-colors hover:text-accent-ink"
                        data-sidebar-status-link
                        data-health-attention={health.needsAttention}
                        onclick={openHealth}
                        onpointerenter={(event) => { if (pointerMayPrefetch(event.pointerType)) onPrefetch?.('/system-health'); }}
                        onfocus={() => onPrefetch?.('/system-health')}
                    >
                        {#if health.needsAttention}
                            <span class="flex min-w-0 items-center gap-2 text-status-attention">
                                <span class="h-2 w-2 shrink-0 rotate-45 bg-status-attention-line" aria-hidden="true"></span>
                                <span class="min-w-0">
                                    <span class="sr-only">{healthLinkPrefix}</span><span data-health-issues>{issuesLabel}</span>
                                </span>
                            </span>
                        {:else}
                            <span class="ml-auto">{$_('status.open_health', { default: 'Health' })}</span>
                        {/if}
                        <svg class="h-3 w-3 shrink-0" viewBox="0 0 20 20" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true" data-health-chevron><path stroke-linecap="round" stroke-linejoin="round" d="m8 5 5 5-5 5" /></svg>
                    </a>
                {/if}
            </section>
        {/if}
    </div>

    <div class="shrink-0 border-t border-line-soft p-3">
        {#if !collapsed}
            {#if authStore.isAuthenticated}
                <div data-sidebar-account class="flex min-w-0 items-center gap-2 rounded-xl border border-line-soft bg-surface-raised p-2">
                    {#if avatarStore.url}
                        <img src={avatarStore.url} alt="" class="h-8 w-8 shrink-0 rounded-lg object-cover" data-sidebar-avatar />
                    {:else}
                        <div class="grid h-8 w-8 shrink-0 place-items-center rounded-lg bg-accent-soft text-xs font-bold text-accent-ink">
                            {accountInitial}
                        </div>
                    {/if}
                    <div class="min-w-0 flex-1">
                        <div class="truncate text-xs font-semibold text-strong">{authStore.username}</div>
                        <div class="truncate text-xs text-muted">{$_('app.title')}</div>
                    </div>
                    <button
                        class="btn btn-ghost min-h-11 min-w-11 focus-ring rounded-lg p-2 text-muted transition hover:bg-status-fail-soft hover:text-status-fail"
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
                <div data-sidebar-account class="flex min-w-0 items-center gap-2 rounded-xl border border-line-soft bg-surface-raised p-2">
                    <div class="grid h-8 w-8 shrink-0 place-items-center rounded-lg bg-surface-raised text-ink">
                        <svg xmlns="http://www.w3.org/2000/svg" class="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2" aria-hidden="true">
                            <path stroke-linecap="round" stroke-linejoin="round" d="M15 12a3 3 0 11-6 0 3 3 0 016 0z" />
                            <path stroke-linecap="round" stroke-linejoin="round" d="M2.458 12C3.732 7.943 7.523 5 12 5c4.478 0 8.268 2.943 9.542 7-1.274 4.057-5.064 7-9.542 7-4.477 0-8.268-2.943-9.542-7z" />
                        </svg>
                    </div>
                    <div class="min-w-0 flex-1 truncate text-xs font-semibold text-ink">
                        {$_('auth.public_view')}
                    </div>
                    <button
                        class="btn btn-ghost min-h-11 min-w-11 focus-ring rounded-lg p-2 text-muted transition hover:bg-accent-soft hover:text-accent-ink"
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
                    class="sidebar-nav sidebar-nav-inactive justify-center px-0 hover:text-status-fail"
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

    <div class="shrink-0 border-t border-line-soft p-3">
        <div class="flex items-center {collapsed ? 'flex-col gap-1' : 'justify-around gap-1'}">
            <LanguageSelector dropUp compact />
            <button
                class="btn btn-ghost min-h-11 min-w-11 focus-ring rounded-xl p-2.5 text-muted transition-all duration-200 hover:bg-surface-raised"
                onclick={() => themeStore.toggle()}
                title={themeStore.prefersDark ? $_('theme.switch_light') : $_('theme.switch_dark')}
                aria-label={themeStore.prefersDark ? $_('theme.switch_light') : $_('theme.switch_dark')}
            >
                {#if themeStore.prefersDark}
                    <svg xmlns="http://www.w3.org/2000/svg" class="h-5 w-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2" aria-hidden="true">
                        <path stroke-linecap="round" stroke-linejoin="round" d="M12 3v1m0 16v1m9-9h-1M4 12H3m15.364 6.364l-.707-.707M6.343 6.343l-.707-.707m12.728 0l-.707.707M6.343 17.657l-.707.707M16 12a4 4 0 11-8 0 4 4 0 018 0z" />
                    </svg>
                {:else}
                    <svg xmlns="http://www.w3.org/2000/svg" class="h-5 w-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2" aria-hidden="true">
                        <path stroke-linecap="round" stroke-linejoin="round" d="M20.354 15.354A9 9 0 018.646 3.646 9.003 9.003 0 0012 21a9.003 9.003 0 008.354-5.646z" />
                    </svg>
                {/if}
            </button>
            <!-- Collapsing to an icon rail is a desktop choice; the phone drawer is either open or closed. -->
            {#if !isMobile}
            <button
                class="btn btn-ghost min-h-11 min-w-11 focus-ring rounded-xl p-2.5 text-muted transition-all duration-200 hover:bg-surface-raised"
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
            {/if}
        </div>
    </div>
</aside>

<style>
    /* System status yields its height long before the navigation does: both may shrink, but the
       status block a thousand times faster, so a short window scrolls the status card, not the list
       of places. A column-wide scroll would clip the language menu, which opens beyond the rail. */
    [data-sidebar-status] {
        flex-shrink: 1000;
    }
</style>
