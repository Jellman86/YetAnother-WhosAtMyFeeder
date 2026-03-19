<script lang="ts">
  import { onMount } from 'svelte';
  import { _ } from 'svelte-i18n';
  import { get } from 'svelte/store';
  import ErrorBoundary from './lib/components/ErrorBoundary.svelte';
  import Header from './lib/components/Header.svelte';
  import MobileTopBar from './lib/components/MobileTopBar.svelte';
  import Sidebar from './lib/components/Sidebar.svelte';
  import Footer from './lib/components/Footer.svelte';
  import TelemetryBanner from './lib/components/TelemetryBanner.svelte';
  import Toast from './lib/components/Toast.svelte';
  import KeyboardShortcuts from './lib/components/KeyboardShortcuts.svelte';
  import ConnectionStatus from './lib/components/ConnectionStatus.svelte';
  import Dashboard from './lib/pages/Dashboard.svelte';
  import Events from './lib/pages/Events.svelte';
  import Species from './lib/pages/Species.svelte';
  import Settings from './lib/pages/Settings.svelte';
  import About from './lib/pages/About.svelte';
  import Notifications from './lib/pages/Notifications.svelte';
  import Login from './lib/components/Login.svelte';
  import FirstRunWizard from './lib/pages/FirstRunWizard.svelte';
  import { checkHealth, fetchAnalysisStatus, fetchCacheStats, fetchEventClassificationStatus, setAuthErrorCallback } from './lib/api';
  import { themeStore } from './lib/stores/theme.svelte';
  import { layoutStore } from './lib/stores/layout.svelte';
  import { settingsStore } from './lib/stores/settings.svelte';
  import { detectionsStore } from './lib/stores/detections.svelte';
  import { authStore } from './lib/stores/auth.svelte';
  import { notificationCenter } from './lib/stores/notification_center.svelte';
  import { jobProgressStore } from './lib/stores/job_progress.svelte';
  import { jobDiagnosticsStore } from './lib/stores/job_diagnostics.svelte';
  import { incidentWorkspaceStore } from './lib/stores/incident_workspace.svelte';
  import { notificationPolicy } from './lib/notifications/policy';
  import { announcer } from './lib/components/Announcer.svelte';
  import Announcer from './lib/components/Announcer.svelte';
  import GlobalProgress from './lib/components/GlobalProgress.svelte';
  import { initKeyboardShortcuts } from './lib/utils/keyboard-shortcuts';
  import { logger } from './lib/utils/logger';
  import { LiveUpdateCoordinator } from './lib/app/live-updates';
  import {
      canonicalizeNotificationRouteForAccess,
      getCanonicalNotificationRoute,
      getNotificationsTabPathForAccess,
      getNotificationsTabPath,
      isNotificationRoute
  } from './lib/app/notifications_route';
  import { createReclassifyRecovery } from './lib/app/reclassify_recovery';

  // Track current layout using reactive derived
  let currentLayout = $derived(layoutStore.layout);
  let isSidebarCollapsed = $derived(layoutStore.sidebarCollapsed);
  let isMobile = $state(false);
  let effectiveLayout = $derived(isMobile ? 'vertical' : currentLayout);

  // Router state
  let currentRoute = $state('/');
  let globalProgressHasScrolled = $state(false);

  function syncGlobalProgressSticky() {
      if (typeof window === 'undefined') return;
      globalProgressHasScrolled = window.scrollY > 0;
  }

  function normalizeRouteForCurrentAccess(path: string): string {
      if (!authStore.statusLoaded) {
          return getCanonicalNotificationRoute(path) ?? path;
      }
      return canonicalizeNotificationRouteForAccess(path, authStore.showSettings);
  }

  // Accessibility Logic
  $effect(() => {
      const s = settingsStore.settings;
      if (s) {
          if (s.accessibility_high_contrast) document.documentElement.classList.add('high-contrast');
          else document.documentElement.classList.remove('high-contrast');

          if (s.accessibility_dyslexia_font) document.documentElement.classList.add('font-dyslexic');
          else document.documentElement.classList.remove('font-dyslexic');
      }
  });

  function navigate(path: string, opts: { replace?: boolean } = {}) {
      const targetPath = normalizeRouteForCurrentAccess(path);
      currentRoute = targetPath;
      if (opts.replace) window.history.replaceState(null, '', targetPath);
      else window.history.pushState(null, '', targetPath);
  }

  // Route guard: settings page should only be accessible when authenticated
  // (or when auth is disabled entirely).
  $effect(() => {
      if (!authStore.statusLoaded) return;
      if (authStore.needsInitialSetup) return;
      if (!currentRoute.startsWith('/settings')) return;

      if (!authStore.showSettings) {
          authStore.requestLogin();
          navigate('/', { replace: true });
      }
  });

  $effect(() => {
      if (!authStore.statusLoaded) return;
      notificationCenter.filterForAccess(authStore.showSettings);
  });

  $effect(() => {
      if (!authStore.statusLoaded) return;
      if (!currentRoute.startsWith('/notifications') && !currentRoute.startsWith('/jobs')) return;

      const allowedRoute = canonicalizeNotificationRouteForAccess(currentRoute, authStore.showSettings);
      if (allowedRoute !== currentRoute) {
          navigate(allowedRoute, { replace: true });
      }
  });

  // SSE connection management
  let evtSource: EventSource | null = $state(null);
  let reconnectAttempts = $state(0);
  let reconnectTimeout: number | null = $state(null);
  let stalePruneInterval: number | null = $state(null);
  let staleReclassifyPollInterval: number | null = $state(null);
  let ownerChecksInterval: number | null = $state(null);
  let analysisQueueInterval: number | null = $state(null);
  let isReconnecting = $state(false);
  let mobileSidebarOpen = $state(false);
  const STALE_RECLASSIFY_STATUS_POLL_MS = 20_000;
  const ANALYSIS_QUEUE_POLL_MS = 5_000;

  // Keyboard shortcuts
  let showKeyboardShortcuts = $state(false);

  let appInitialized = $state(false);
  let canAccess = $derived(!authStore.authRequired || authStore.publicAccessEnabled || authStore.isAuthenticated);
  let requiresLogin = $derived(
      (authStore.authRequired && !authStore.publicAccessEnabled && !authStore.isAuthenticated && !authStore.needsInitialSetup) ||
      (authStore.forceLogin && !authStore.isAuthenticated)
  );

  let notificationsActive = $derived.by(() => {
      const s = settingsStore.settings;
      if (!s) return false;
      const active = s.notifications_discord_enabled ||
      s.notifications_pushover_enabled ||
      s.notifications_telegram_enabled ||
      s.notifications_email_enabled ||
      s.notifications?.discord?.enabled ||
      s.notifications?.pushover?.enabled ||
      s.notifications?.telegram?.enabled ||
      s.notifications?.email?.enabled;
      // console.log('Notifications Active:', active);
      return active;
  });

  const t = (key: string, values: Record<string, any> = {}) => get(_)(key, { values });

  function shouldNotify() {
      return !authStore.isGuest;
  }

  function applyNotificationPolicy(id: string, signature: string, throttleMs = 0): boolean {
      return notificationPolicy.shouldEmit(id, signature, throttleMs);
  }

  const liveUpdates = new LiveUpdateCoordinator({
      t,
      shouldNotify,
      hasOwnerAccess: () => authStore.showSettings,
      applyNotificationPolicy,
      notificationCenter,
      jobProgress: jobProgressStore,
      detectionsStore,
      settingsStore,
      announcer,
      logger,
      checkHealth,
      fetchCacheStats,
      fetchAnalysisStatus,
      diagnostics: jobDiagnosticsStore,
      syncDiagnosticsWorkspace: () => incidentWorkspaceStore.refresh(),
      onConnected: () => {
          reconnectAttempts = 0;
      }
  });

  $effect(() => {
      incidentWorkspaceStore.ingestLocalDiagnosticGroups(jobDiagnosticsStore.groups);
  });

  const reclassifyRecovery = createReclassifyRecovery({
      fetchStatus: fetchEventClassificationStatus,
      jobProgress: jobProgressStore,
      logger
  });

  // Handle back button and initial load
  onMount(() => {
      (async () => {
          let mediaQuery: MediaQueryList | null = null;
          const updateMobile = () => {
              if (!mediaQuery) return;
              isMobile = mediaQuery.matches;
          };
          if (typeof window !== 'undefined') {
              mediaQuery = window.matchMedia('(max-width: 767px)');
              updateMobile();
              mediaQuery.addEventListener('change', updateMobile);
              syncGlobalProgressSticky();
              window.addEventListener('scroll', syncGlobalProgressSticky, { passive: true });
          }

          // Register auth error callback
          setAuthErrorCallback(() => {
              authStore.handleAuthError();
          });

          const handlePopState = () => {
              currentRoute = normalizeRouteForCurrentAccess(window.location.pathname);
          };
          window.addEventListener('popstate', handlePopState);

          // Surface actionable diagnostics for production-minified runtime exceptions.
          const handleWindowError = (event: ErrorEvent) => {
              const payload = event.error instanceof Error
                  ? { message: event.error.message, stack: event.error.stack, name: event.error.name }
                  : { message: event.message, error: event.error };
              logger.error('window_runtime_error', payload);
              jobDiagnosticsStore.recordError({
                  source: 'runtime',
                  component: 'browser',
                  reasonCode: 'window_error',
                  message: String(payload.message || 'Uncaught window error'),
                  severity: 'error',
                  context: payload
              });
              console.error('window_runtime_error', payload);
          };
          const handleUnhandledRejection = (event: PromiseRejectionEvent) => {
              const reason = event.reason;
              const payload = reason instanceof Error
                  ? { message: reason.message, stack: reason.stack, name: reason.name }
                  : { reason };
              logger.error('window_unhandled_rejection', payload);
              jobDiagnosticsStore.recordError({
                  source: 'runtime',
                  component: 'browser',
                  reasonCode: 'unhandled_rejection',
                  message: String((payload as any).message || 'Unhandled promise rejection'),
                  severity: 'error',
                  context: payload
              });
              console.error('window_unhandled_rejection', payload);
          };
          window.addEventListener('error', handleWindowError);
          window.addEventListener('unhandledrejection', handleUnhandledRejection);

          const path = window.location.pathname;
          const resolvedPath = path === '' ? '/' : path;
          const canonicalPath = getCanonicalNotificationRoute(resolvedPath) ?? resolvedPath;
          currentRoute = canonicalPath;
          if (canonicalPath !== resolvedPath) {
              window.history.replaceState(null, '', canonicalPath);
          }

          await authStore.loadStatus();
          const accessAdjustedPath = canonicalizeNotificationRouteForAccess(currentRoute, authStore.showSettings);
          if (accessAdjustedPath !== currentRoute) {
              currentRoute = accessAdjustedPath;
              window.history.replaceState(null, '', accessAdjustedPath);
          }
          notificationCenter.hydrate();
          jobDiagnosticsStore.hydrate();
          liveUpdates.pruneStaleProcessNotifications();
          void reclassifyRecovery.reconcile();
          await liveUpdates.syncAnalysisQueueStatus();
          await liveUpdates.runOwnerSystemChecks();
          ownerChecksInterval = window.setInterval(() => {
              void liveUpdates.runOwnerSystemChecks();
          }, 60_000);
          analysisQueueInterval = window.setInterval(() => {
              void liveUpdates.syncAnalysisQueueStatus();
          }, ANALYSIS_QUEUE_POLL_MS);
          stalePruneInterval = window.setInterval(() => {
              liveUpdates.pruneStaleProcessNotifications();
              detectionsStore.pruneReclassifications();
          }, 10_000);
          staleReclassifyPollInterval = window.setInterval(() => {
              void reclassifyRecovery.reconcile();
          }, STALE_RECLASSIFY_STATUS_POLL_MS);

          // Handle page visibility changes - reconnect when tab becomes visible
          const handleVisibilityChange = () => {
              if (!document.hidden && !detectionsStore.connected && !isReconnecting) {
                  logger.info("Tab became visible, attempting to reconnect SSE");
                  reconnectAttempts = 0; // Reset backoff when user returns to tab
                  scheduleReconnect();
              }
              if (!document.hidden) {
                  void reclassifyRecovery.reconcile();
                  void liveUpdates.syncAnalysisQueueStatus();
              }
          };
          document.addEventListener('visibilitychange', handleVisibilityChange);

          // Initialize keyboard shortcuts
          const cleanupShortcuts = initKeyboardShortcuts({
              '?': () => showKeyboardShortcuts = true,
              'g d': () => navigate('/'),
              'g e': () => navigate('/events'),
              'g l': () => navigate('/species'),
              'g j': () => navigate(getNotificationsTabPathForAccess('jobs', authStore.showSettings)),
              'g t': () => navigate('/settings'),
              'Escape': () => {
                  // Close keyboard shortcuts modal
                  showKeyboardShortcuts = false;
              },
              'r': () => window.location.reload()
          });

          // Store cleanup function to return
          cleanupFn = () => {
              window.removeEventListener('popstate', handlePopState);
              window.removeEventListener('error', handleWindowError);
              window.removeEventListener('unhandledrejection', handleUnhandledRejection);
              document.removeEventListener('visibilitychange', handleVisibilityChange);
              cleanupShortcuts();
              if (mediaQuery) {
                  mediaQuery.removeEventListener('change', updateMobile);
              }
              window.removeEventListener('scroll', syncGlobalProgressSticky);
              if (evtSource) {
                  evtSource.close();
                  evtSource = null;
              }
              if (reconnectTimeout) {
                  clearTimeout(reconnectTimeout);
                  reconnectTimeout = null;
              }
              if (stalePruneInterval) {
                  clearInterval(stalePruneInterval);
                  stalePruneInterval = null;
              }
              if (staleReclassifyPollInterval) {
                  clearInterval(staleReclassifyPollInterval);
                  staleReclassifyPollInterval = null;
              }
              if (ownerChecksInterval) {
                  clearInterval(ownerChecksInterval);
                  ownerChecksInterval = null;
              }
              if (analysisQueueInterval) {
                  clearInterval(analysisQueueInterval);
                  analysisQueueInterval = null;
              }
          };
      })();

      // Return cleanup function (will be assigned inside the async IIFE, but we need a stable ref)
      return () => {
          if (cleanupFn) cleanupFn();
      };
  });

  let cleanupFn: (() => void) | null = null;

  $effect(() => {
      if (!authStore.statusLoaded) {
          return;
      }
      if (authStore.needsInitialSetup) {
          return;
      }

      if (canAccess && !appInitialized) {
          if (authStore.isAuthenticated || !authStore.authRequired) {
              settingsStore.load();
          }
          detectionsStore.loadInitial();
          connectSSE();
          appInitialized = true;
      }

      if (!canAccess && appInitialized) {
          if (evtSource) {
              evtSource.close();
              evtSource = null;
          }
          detectionsStore.setConnected(false);
          appInitialized = false;
      }
  });

  function scheduleReconnect() {
      // Prevent multiple reconnection attempts
      if (isReconnecting || reconnectTimeout) {
          return;
      }
      if (!canAccess) {
          return;
      }

      isReconnecting = true;

      // Exponential backoff: 1s, 2s, 4s, 8s, 16s, max 30s
      const delay = Math.min(1000 * Math.pow(2, reconnectAttempts), 30000);
      logger.debug(`Scheduling SSE reconnect`, { delay, attempt: reconnectAttempts + 1 });

      reconnectTimeout = window.setTimeout(() => {
          reconnectTimeout = null;
          isReconnecting = false;
          reconnectAttempts++;
          connectSSE();
      }, delay);
  }

  function connectSSE() {
      // Close existing connection if any
      if (evtSource) {
          evtSource.close();
          evtSource = null;
      }

      try {
          const token = authStore.token;
          const sseUrl = token ? `/api/sse?token=${encodeURIComponent(token)}` : '/api/sse';
          evtSource = new EventSource(sseUrl);

          evtSource.onopen = () => {
              logger.sseEvent("connection_opened");
              notificationCenter.remove('system:sse-disconnected');
          };

          evtSource.onmessage = (event) => {
              try {
                 // Parse JSON with validation
                 let payload: any;
                 try {
                     payload = JSON.parse(event.data);
                 } catch (parseError) {
                     logger.error("SSE JSON Parse Error", parseError, { data: event.data });
                     return;
                 }

                 liveUpdates.handlePayload(payload);
              } catch (e) {
                  console.error("SSE Unexpected error in message handler:", e, "Event:", event);
              }
          };

          evtSource.onerror = (err) => {
              logger.warn("SSE connection issue", {
                  type: (err as any)?.type ?? 'error',
                  attempt: reconnectAttempts + 1
              });
              liveUpdates.handleDisconnect(err, document.hidden);

              if (evtSource) {
                  evtSource.close();
                  evtSource = null;
              }

              // Schedule reconnection with backoff
              scheduleReconnect();
          };
      } catch (error) {
          logger.error("Failed to create SSE connection", error);
          liveUpdates.handleDisconnect(error, document.hidden);
          scheduleReconnect();
      }
  }
</script>

<ErrorBoundary>
  {#snippet children()}
  <div class="min-h-screen flex flex-col bg-surface-light dark:bg-surface-dark text-slate-900 dark:text-white font-sans transition-colors duration-300">
  <!-- Skip to content for accessibility -->
  <a href="#main-content" class="sr-only focus:not-sr-only focus:absolute focus:z-[100] focus:bg-brand-500 focus:text-white focus:px-4 focus:py-2 focus:rounded-b-lg focus:left-4 focus:top-0 focus:font-bold">
    {$_('common.skip_to_content', { default: 'Skip to content' })}
  </a>

  {#if !authStore.statusLoaded}
      <div class="min-h-screen flex items-center justify-center bg-surface-50 dark:bg-surface-900 px-4">
          <div class="text-sm font-semibold text-slate-600 dark:text-slate-300">
              {$_('auth.loading_status', { default: 'Loading authentication status...' })}
          </div>
      </div>
  {:else if authStore.needsInitialSetup}
      <FirstRunWizard />
  {:else if requiresLogin}
      <Login />
  {:else}
      {#if effectiveLayout === 'vertical'}
          <MobileTopBar
              onToggleMenu={() => mobileSidebarOpen = !mobileSidebarOpen}
              onToggleTheme={() => themeStore.toggle()}
              theme={themeStore.theme}
              appTitle={$_('app.title')}
              toggleMenuLabel={$_('nav.toggle_menu', { default: 'Toggle menu' }) || 'Toggle menu'}
              switchThemeLabel={themeStore.theme === 'dark'
                  ? ($_('theme.switch_light', { default: 'Switch to light mode' }) || 'Switch to light mode')
                  : ($_('theme.switch_dark', { default: 'Switch to dark mode' }) || 'Switch to dark mode')}
          />

          <Sidebar {currentRoute} onNavigate={navigate} {mobileSidebarOpen} onMobileClose={() => mobileSidebarOpen = false}>
              {#snippet status()}
                  <ConnectionStatus
                      birdnetEnabled={Boolean(settingsStore.birdnetEnabled)}
                      {notificationsActive}
                      connected={detectionsStore.connected}
                      className="gap-4 px-2"
                  />
              {/snippet}
          </Sidebar>
      {:else}
          <Header {currentRoute} onNavigate={navigate} onShowKeyboardShortcuts={() => showKeyboardShortcuts = true}>
              {#snippet status()}
                  <ConnectionStatus
                      birdnetEnabled={Boolean(settingsStore.birdnetEnabled)}
                      {notificationsActive}
                      connected={detectionsStore.connected}
                  />
              {/snippet}
          </Header>
      {/if}

      <!-- Telemetry Banner (shown on first visit if telemetry disabled) -->
      <TelemetryBanner />

      <!-- Main Content Wrapper -->
      <div
          class="flex-1 flex flex-col transition-all duration-300 {effectiveLayout === 'vertical' ? (isSidebarCollapsed ? 'md:pl-20' : 'md:pl-64') : ''}"
          style="--app-chrome-height: {effectiveLayout === 'horizontal' || isMobile ? '4rem' : '0rem'};"
      >
          {#if !isNotificationRoute(currentRoute) && !authStore.isGuest}
              <div class={globalProgressHasScrolled
                  ? 'sticky top-[var(--app-chrome-height)] z-30 shrink-0'
                  : 'relative z-30 shrink-0 mb-2'}>
                  <GlobalProgress onNavigate={navigate} />
              </div>
          {/if}
          <main id="main-content" class="flex-1 w-full max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
              {#if currentRoute === '/'}
                  <Dashboard onnavigate={navigate} />
              {:else if currentRoute.startsWith('/events')}
                  <Events />
              {:else if currentRoute.startsWith('/species')}
                  <Species />
              {:else if currentRoute.startsWith('/settings')}
                   {#if authStore.showSettings}
                       <Settings />
                   {:else}
                       <!-- Block settings view for guests; route guard will redirect + prompt login. -->
                       <div class="h-24"></div>
                   {/if}
              {:else if currentRoute.startsWith('/notifications')}
                  <Notifications onNavigate={navigate} {currentRoute} />
              {:else if currentRoute.startsWith('/about')}
                   <About />
              {/if}
          </main>
          
          <Footer />
      </div>
  {/if}

  <!-- Toast Notifications -->
  <Toast />
  <Announcer />

  <!-- Keyboard Shortcuts Modal -->
  <KeyboardShortcuts bind:visible={showKeyboardShortcuts} />
</div>
  {/snippet}
</ErrorBoundary>
