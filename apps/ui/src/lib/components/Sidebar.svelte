<script lang="ts">
    import { fitStatus } from '../utils/whole-lines';
    import { pointerMayPrefetch } from '../app/route-prefetch';
    import { ADD_OBSERVATION_ICON, ADD_OBSERVATION_PATH, addObservationEntry } from '../app/add-observation';
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
    import SystemLoadMeters from './SystemLoadMeters.svelte';
    import { trapFocus } from '../utils/focus-trap';
    import { incidentWorkspaceStore } from '../stores/incident_workspace.svelte';
    import { systemStatusStore } from '../stores/system_status.svelte';
    import { healthAttention, healthPlaceName, openHealthItems } from '../utils/system-status';
    import type { StatusTier } from '../utils/whole-lines';

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
        /** The status rows: in the icon rail or not, and in full, or as the one line that stands in for them. */
        status?: import('svelte').Snippet<[boolean, import('../utils/system-status').SummaryRequest | null]>;
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
                systemStatusStore.snapshot,
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

    // Which form of the status shows, as fitStatus measured it. Where none of them fits at rest, the
    // Health place carries the status: its mark and its name say the open issues, and only then, so the
    // mark never shows twice at rest. While it does, the card waiting past the fold is inert, out of the
    // tab order and the accessibility tree, so the issues are announced once; with nothing for the
    // Health place to carry (no issues, or a guest), the card stays reachable by scrolling.
    let statusTier = $state<StatusTier['tier'] | null>(null);
    const healthCarriesStatus = $derived(statusTier === 'health' && health.needsAttention);
    const placeName = (item: { path: string; label: string }): string =>
        item.path === '/system-health' ? healthPlaceName(item.label, healthCarriesStatus ? issuesLabel : null) : item.label;

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
        /** Left out while false: a page for a feature this installation does not have, or one reached another way at this width. */
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

    // An action, not a place: from the docked sidebar's width up it is in the header's controls. A
    // phone's header has no room for it, so there it is a place in the menu.
    const addObservation = $derived(addObservationEntry(currentRoute, authStore.showSettings, isMobile));

    const allNavItems = $derived.by((): NavItem[] => ([
        { path: '/', label: $_('nav.dashboard'), icon: 'M3 12l2-2m0 0l7-7 7 7M5 10v10a1 1 0 001 1h3m10-11l2 2m-2-2v10a1 1 0 01-1 1h-3m-6 0a1 1 0 001-1v-4a1 1 0 011-1h2a1 1 0 011 1v4a1 1 0 001 1m-6 0h6', section: 'observe' },
        { path: '/events', label: $_('nav.explorer'), icon: 'M4 6h16M4 10h16M4 14h16M4 18h16', section: 'observe' },
        { path: ADD_OBSERVATION_PATH, label: $_('nav.add_observation', { default: 'Add observation' }), icon: ADD_OBSERVATION_ICON, section: 'observe', requiresAuth: true, available: addObservation.inMenu },
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

    // Where the status's other form has no control to take keyboard focus (a guest's summary), focus
    // goes to Health among the places (the owner's), or else to the page you are on, never staying on
    // something unseen.
    function refocusFromStatus(): HTMLElement | null {
        return asideEl?.querySelector<HTMLElement>('nav [data-nav-path="/system-health"]')
            ?? asideEl?.querySelector<HTMLElement>('nav [aria-current="page"]')
            ?? asideEl?.querySelector<HTMLElement>('nav button')
            ?? null;
    }

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

<!-- The icon rail's way to Health: in the group under the status icons, alone as its one icon, or as a
     compact 24 px icon. -->
{#snippet railHealthLink(kind: 'group' | 'summary' | 'compact')}
    <a
        href="/system-health"
        class="focus-ring relative grid place-items-center rounded-lg text-ink transition-colors hover:bg-surface-raised {kind === 'compact' ? 'h-7 w-7' : 'h-11 w-11'}"
        title={healthLinkName}
        data-sidebar-status-link={kind === 'group' ? '' : undefined}
        data-sidebar-summary-link={kind === 'summary' ? '' : undefined}
        data-sidebar-compact-link={kind === 'compact' ? '' : undefined}
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
            <span class="absolute h-2 w-2 rotate-45 bg-status-attention-line {kind === 'compact' ? '-right-0.5 -top-0.5' : 'right-1.5 top-1.5'}" aria-hidden="true"></span>
        {/if}
    </a>
{/snippet}

<!-- The one line that stands in for the card: the open issues, as the card's own link counts them, or
     the most important measured state in words. The owner's line is the way to Health ("Health" said
     first for a screen reader); a guest's is the words alone. The full-size line is a full-size target
     on a touch screen; the compact one a 24 px target. -->
{#snippet summaryLine(compact: boolean)}
    {#if authStore.showSettings}
        <a
            href="/system-health"
            class="focus-ring -mx-1 flex min-h-7 items-center justify-between gap-x-2 rounded-md px-1 text-ink transition-colors hover:text-accent-ink {compact ? '' : 'pointer-coarse:min-h-11'}"
            data-sidebar-summary-link={compact ? undefined : ''}
            data-sidebar-compact-link={compact ? '' : undefined}
            data-health-attention={health.needsAttention}
            onclick={openHealth}
            onpointerenter={(event) => { if (pointerMayPrefetch(event.pointerType)) onPrefetch?.('/system-health'); }}
            onfocus={() => onPrefetch?.('/system-health')}
        >
            <span class="min-w-0"><span class="sr-only">{healthLinkPrefix}</span>{@render status?.(false, { attention: health, compact })}</span>
            <svg class="h-3 w-3 shrink-0 text-muted" viewBox="0 0 20 20" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true"><path stroke-linecap="round" stroke-linejoin="round" d="m8 5 5 5-5 5" /></svg>
        </a>
    {:else}
        <div class="flex min-h-7 items-center {compact ? '' : 'pointer-coarse:min-h-11'}">
            {@render status?.(false, { attention: null, compact })}
        </div>
    {/if}
{/snippet}

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
        class="relative flex w-full flex-col items-center text-center gap-3 border-b border-line-soft px-4 py-5 [@media(max-height:42rem)]:py-3 compact-height:py-3"
    >
        <button
            class="focus-ring -m-1 flex min-h-11 min-w-11 flex-col items-center justify-center gap-3 rounded-xl p-1 {collapsed ? '' : 'compact-height:flex-row compact-height:text-left'}"
            onclick={() => navigateAndClose('/')}
        >
            <BrandMark
                alt={$_('app.title')}
                sizes={collapsed ? '40px' : '64px'}
                class="shrink-0 rounded-2xl transition-all duration-300 {collapsed ? 'h-10 w-10' : 'h-16 w-16 compact-height:h-10 compact-height:w-10'}"
            />
            {#if !collapsed}
                <div class="flex flex-col items-center gap-0.5 overflow-hidden compact-height:items-start">
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

    <!-- Every place in the app and the way to Health stay in view: on a short window the brand sits
         beside its mark and System status gives up its readings first (they scroll inside the card,
         the Health link stays at its foot). Where the room under the places, measured, cannot hold the
         card's heading, first reading and link whole, one line stands in for the card (on the icon
         rail, one icon), so the sidebar never shows an unexplained gap. Only where not even that fits
         does the whole card wait just past the foot of the scrolling column, never cut. The controls
         below never scroll, so the language menu that opens past the collapsed rail is never clipped. -->
    <div class="flex min-h-0 flex-1 flex-col overflow-y-auto" data-sidebar-scroll>
        <nav class="shrink-0 px-3 py-4" aria-label={$_('nav.navigation', { default: 'Primary navigation' })}>
            {#each navSections as section, sectionIndex}
                <div data-sidebar-section={section.id} class={sectionIndex === 0 ? '' : 'mt-5 compact-height:mt-3'}>
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
                                title={collapsed ? placeName(item) : ''}
                                aria-label={placeName(item)}
                                aria-current={isRouteActive(item) ? 'page' : undefined}
                                data-nav-path={item.path}
                            >
                                <span class="relative shrink-0">
                                    <svg xmlns="http://www.w3.org/2000/svg" class="h-5 w-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2" aria-hidden="true">
                                        <path stroke-linecap="round" stroke-linejoin="round" d={item.icon} />
                                    </svg>
                                    {#if item.path === '/system-health' && healthCarriesStatus}
                                        <span class="absolute -right-1 -top-1 h-2 w-2 rotate-45 bg-status-attention-line" aria-hidden="true" data-health-carries-status></span>
                                    {/if}
                                </span>
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

        <!-- System status is a plain list on a neutral surface: measured states in words, the load as
             labelled meters in the Health chart's series colours, and the way to Health as the card's
             foot. Only the owner can reach Health, so a guest gets no link. The link asks for attention
             only for issues Health lists as open, read from the same store, so the two always agree.
             Both forms are always drawn, the card and the line that stands in for it, and fitStatus
             shows the one the room allows: the other stays laid out but unseen, so it is measured as the
             room changes, and a change of form changes no words a screen reader would announce. -->
        <div
            data-sidebar-status
            class="mt-auto flex flex-col border-t border-line-soft p-3 compact-height:p-2"
            inert={healthCarriesStatus}
            use:fitStatus={{ container: '[data-sidebar-scroll]', readings: '[data-sidebar-status-readings]', lines: ':scope > *, li', floor: '[data-status-row]', control: '[data-sidebar-status-link], [data-sidebar-summary-link], [data-sidebar-compact-link]', words: '[data-summary-row], [data-summary-issues]', fallbackFocus: refocusFromStatus, onTier: (tier) => (statusTier = tier) }}
        >
            <div class="relative">
            {#if collapsed}
                <!-- The icon rail's status has nothing that can give way: the whole group, or one icon. -->
                <section
                    class="flex flex-col items-center gap-1"
                    aria-label={$_('status.title')}
                    data-sidebar-status-card
                    data-status-form="full"
                >
                    {@render status?.(true, null)}
                    {#if authStore.showSettings}
                        {@render railHealthLink('group')}
                    {/if}
                </section>
                <!-- The one icon: the owner's way to Health, with its mark when issues are open; for a guest,
                     the most important status. The compact one is a 24 px target, its margins eating into
                     the frame. -->
                <div class="flex justify-center" role="status" data-sidebar-status-summary data-status-form="summary">
                    {#if authStore.showSettings}
                        {@render railHealthLink('summary')}
                    {:else}
                        {@render status?.(true, { attention: null })}
                    {/if}
                </div>
                <div class="-my-1.5 flex justify-center" role="status" data-sidebar-status-compact data-status-form="compact">
                    {#if authStore.showSettings}
                        {@render railHealthLink('compact')}
                    {:else}
                        {@render status?.(true, { attention: null, compact: true })}
                    {/if}
                </div>
            {:else}
                <section
                    class="flex flex-col rounded-xl border border-line-soft bg-surface-raised p-3 compact-height:p-2"
                    aria-labelledby="sidebar-status-title"
                    data-sidebar-status-card
                    data-status-form="full"
                >
                    <!-- On a short window at the usual text size the readings scroll inside the card and the way to
                         Health stays at its foot, so the issues link is never the part cut off. A tab stop of its
                         own, so the keyboard can scroll it where the browser does not. -->
                    <!-- svelte-ignore a11y_no_noninteractive_tabindex -->
                    <!-- At rest the readings show whole lines only: their height ends after the last line that
                         fits, never before the first reading, and the rest is scrolled to, so no line is ever
                         shown cut through its letters. The room is measured from the column (signed in, the
                         account band takes some of it), not guessed from the window's height. -->
                    <div
                        class="focus-ring"
                        role="group"
                        tabindex="0"
                        aria-labelledby="sidebar-status-title"
                        data-sidebar-status-readings
                    >
                        <h2 id="sidebar-status-title" class="mb-2 text-xs font-semibold leading-4 text-ink">
                            {$_('status.title')}
                        </h2>
                        {@render status?.(false, null)}
                        <SystemLoadMeters watchFrom="[data-sidebar-status-readings]" />
                    </div>
                    {#if authStore.showSettings}
                        <!-- One line, one control: with issues open the count is the link's wording and
                             "Health" is said before it for a screen reader; with none open the
                             link is just "Health". -->
                        <a
                            href="/system-health"
                            class="focus-ring -mx-1 mt-3 flex min-h-7 shrink-0 items-center justify-between gap-x-2 rounded-md border-t border-line-soft px-1 pt-2 text-xs leading-4 text-ink transition-colors hover:text-accent-ink"
                            data-sidebar-status-link
                            data-health-attention={health.needsAttention}
                            onclick={openHealth}
                            onpointerenter={(event) => { if (pointerMayPrefetch(event.pointerType)) onPrefetch?.('/system-health'); }}
                            onfocus={() => onPrefetch?.('/system-health')}
                        >
                            {#if health.needsAttention}
                                <span class="flex min-w-0 items-center gap-2 font-semibold text-status-attention">
                                    <span class="h-2 w-2 shrink-0 rotate-45 bg-status-attention-line" aria-hidden="true"></span>
                                    <span class="min-w-0">
                                        <span class="sr-only">{healthLinkPrefix}</span><span data-health-issues>{issuesLabel}</span>
                                    </span>
                                </span>
                            {:else}
                                <span>{$_('status.open_health', { default: 'Health' })}</span>
                            {/if}
                            <svg class="h-3 w-3 shrink-0 text-muted" viewBox="0 0 20 20" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true" data-health-chevron><path stroke-linecap="round" stroke-linejoin="round" d="m8 5 5 5-5 5" /></svg>
                        </a>
                    {/if}
                </section>
                <!-- The one line that stands in for the card (see summaryLine). The line is the live region in
                     this form, as the list's wrapper is in the card's, and every form is always drawn, so a
                     change of form announces nothing new. -->
                <div
                    class="rounded-xl border border-line-soft bg-surface-raised px-2 py-1 text-xs leading-4"
                    role="status"
                    data-sidebar-status-summary
                    data-status-form="summary"
                >
                    {@render summaryLine(false)}
                </div>
                <!-- The same line where only a 24 px target fits: no padding of its own, and its margins eat
                     into the frame's, so it fits where the full-size line does not. -->
                <div
                    class="-my-1.5 rounded-xl border border-line-soft bg-surface-raised px-2 text-xs leading-4"
                    role="status"
                    data-sidebar-status-compact
                    data-status-form="compact"
                >
                    {@render summaryLine(true)}
                </div>
            {/if}
            </div>
        </div>

    </div>

    <!-- Only when there is someone to show: an owner with sign-in off would get an empty ruled band. -->
    {#if authStore.isAuthenticated || authStore.isGuest}
        <div class="shrink-0 border-t border-line-soft p-3" data-sidebar-account-band>
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

    {/if}

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
    /* The places and the status share one column, which scrolls only as a last resort. The card always
       lays out whole: fitStatus gives the readings a height in whole lines, down to their heading and
       first reading, and they scroll inside the card under the Health link at its foot. No box here
       may shrink below its content, so the card is never squashed to an empty bar. */
    [data-sidebar-status-readings] {
        overflow-y: auto;
    }

    /* The form not shown (the summary, until fitStatus chooses it; or the card, once it has) stays laid
       out at the width it would have, so both are measured as the room changes, but out of the flow
       and unseen: hidden from the keyboard and screen readers like anything not shown, and parked far
       above the window, because the load meters sample only while they are on screen. The mark is
       written by fitStatus, not the template, so it is matched as global. */
    [data-status-form='summary'],
    [data-status-form='compact'],
    [data-sidebar-status]:global([data-fit='summary']) [data-status-form='full'],
    [data-sidebar-status]:global([data-fit='compact']) [data-status-form='full'] {
        position: absolute;
        inset-inline: 0;
        bottom: calc(100% + 200vh);
        visibility: hidden;
    }

    [data-sidebar-status]:global([data-fit='summary']) [data-status-form='summary'],
    [data-sidebar-status]:global([data-fit='compact']) [data-status-form='compact'] {
        position: static;
        visibility: visible;
    }
</style>
