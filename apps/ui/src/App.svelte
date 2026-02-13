<script lang="ts">
  import { onMount } from 'svelte';
  import { _ } from 'svelte-i18n';
  import { get } from 'svelte/store';
  import ErrorBoundary from './lib/components/ErrorBoundary.svelte';
  import Header from './lib/components/Header.svelte';
  import Sidebar from './lib/components/Sidebar.svelte';
  import Footer from './lib/components/Footer.svelte';
  import TelemetryBanner from './lib/components/TelemetryBanner.svelte';
  import Toast from './lib/components/Toast.svelte';
  import KeyboardShortcuts from './lib/components/KeyboardShortcuts.svelte';
  import Dashboard from './lib/pages/Dashboard.svelte';
  import Events from './lib/pages/Events.svelte';
  import Species from './lib/pages/Species.svelte';
  import Settings from './lib/pages/Settings.svelte';
  import About from './lib/pages/About.svelte';
  import Notifications from './lib/pages/Notifications.svelte';
  import Login from './lib/components/Login.svelte';
  import FirstRunWizard from './lib/pages/FirstRunWizard.svelte';
  import { checkHealth, fetchCacheStats, fetchEvents, fetchEventsCount, type Detection, setAuthErrorCallback } from './lib/api';
  import { themeStore } from './lib/stores/theme.svelte';
  import { layoutStore } from './lib/stores/layout.svelte';
  import { settingsStore } from './lib/stores/settings.svelte';
  import { detectionsStore } from './lib/stores/detections.svelte';
  import { authStore } from './lib/stores/auth.svelte';
  import { notificationCenter } from './lib/stores/notification_center.svelte';
  import { notificationPolicy } from './lib/notifications/policy';
  import { announcer } from './lib/components/Announcer.svelte';
  import Announcer from './lib/components/Announcer.svelte';
  import { initKeyboardShortcuts } from './lib/utils/keyboard-shortcuts';
  import { logger } from './lib/utils/logger';

  // Track current layout using reactive derived
  let currentLayout = $derived(layoutStore.layout);
  let isSidebarCollapsed = $derived(layoutStore.sidebarCollapsed);
  let isMobile = $state(false);
  let effectiveLayout = $derived(isMobile ? 'vertical' : currentLayout);

  // Router state
  let currentRoute = $state('/');

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
      currentRoute = path;
      if (opts.replace) window.history.replaceState(null, '', path);
      else window.history.pushState(null, '', path);
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

  // SSE connection management
  let evtSource: EventSource | null = $state(null);
  let reconnectAttempts = $state(0);
  let reconnectTimeout: number | null = $state(null);
  let stalePruneInterval: number | null = $state(null);
  let isReconnecting = $state(false);
  let mobileSidebarOpen = $state(false);

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

  const STALE_PROCESS_MAX_AGE_MS = 45 * 60 * 1000;

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
          }

          // Register auth error callback
          setAuthErrorCallback(() => {
              authStore.handleAuthError();
          });

          const handlePopState = () => {
              currentRoute = window.location.pathname;
          };
          window.addEventListener('popstate', handlePopState);

          const path = window.location.pathname;
          currentRoute = path === '' ? '/' : path;

          await authStore.loadStatus();
          notificationCenter.hydrate();
          pruneStaleProcessNotifications();
          await runOwnerSystemChecks();
          stalePruneInterval = window.setInterval(() => {
              pruneStaleProcessNotifications();
          }, 60_000);

          // Handle page visibility changes - reconnect when tab becomes visible
          const handleVisibilityChange = () => {
              if (!document.hidden && !detectionsStore.connected && !isReconnecting) {
                  logger.info("Tab became visible, attempting to reconnect SSE");
                  reconnectAttempts = 0; // Reset backoff when user returns to tab
                  scheduleReconnect();
              }
          };
          document.addEventListener('visibilitychange', handleVisibilityChange);

          // Initialize keyboard shortcuts
          const cleanupShortcuts = initKeyboardShortcuts({
              '?': () => showKeyboardShortcuts = true,
              'g d': () => navigate('/'),
              'g e': () => navigate('/events'),
              'g l': () => navigate('/species'),
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
              document.removeEventListener('visibilitychange', handleVisibilityChange);
              cleanupShortcuts();
              if (mediaQuery) {
                  mediaQuery.removeEventListener('change', updateMobile);
              }
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
          };
      })();

      // Return cleanup function (will be assigned inside the async IIFE, but we need a stable ref)
      return () => {
          if (cleanupFn) cleanupFn();
      };
  });

  let cleanupFn: (() => void) | null = null;
  const t = (key: string, values: Record<string, any> = {}) => get(_)(key, { values });

  function shouldNotify() {
      return !authStore.isGuest;
  }

  function applyNotificationPolicy(id: string, signature: string, throttleMs = 0): boolean {
      return notificationPolicy.shouldEmit(id, signature, throttleMs);
  }

  function pruneStaleProcessNotifications() {
      const stale = notificationPolicy.settleStale(notificationCenter.items, STALE_PROCESS_MAX_AGE_MS);
      for (const item of stale) {
          notificationCenter.upsert(item);
      }
  }

  async function runOwnerSystemChecks() {
      if (!shouldNotify()) return;
      let startupInstanceId = 'unknown';

      try {
          const health: any = await checkHealth();
          startupInstanceId = String(health?.startup_instance_id ?? 'unknown');
          const status = String(health?.status ?? '').toLowerCase();
          if (status && status !== 'healthy') {
              const id = `system:health:${startupInstanceId}`;
              // Backward cleanup for earlier builds that used a static ID.
              notificationCenter.remove('system:health');
              if (!notificationCenter.items.some((item) => item.id === id)) {
                  notificationCenter.add({
                      id,
                      type: 'system',
                      title: t('notifications.system_health_title'),
                      message: t('notifications.system_health_message', { status: String(health?.status ?? 'unknown') }),
                      meta: { source: 'health', route: '/settings' }
                  });
              }
          }
      } catch (error) {
          logger.warn('health_check_failed', { error });
      }

      try {
          const cache = await fetchCacheStats();
          if (!cache.cache_enabled) {
              const id = `system:cache-disabled:${startupInstanceId}`;
              // Backward cleanup for earlier builds that used a static ID.
              notificationCenter.remove('system:cache-disabled');
              if (!notificationCenter.items.some((item) => item.id === id)) {
                  notificationCenter.add({
                      id,
                      type: 'system',
                      title: t('notifications.system_cache_disabled_title'),
                      message: t('notifications.system_cache_disabled_message'),
                      meta: { source: 'cache', route: '/settings' }
                  });
              }
          }
      } catch (error) {
          logger.warn('cache_stats_check_failed', { error });
      }
  }

  function addDetectionNotification(det: Detection) {
      if (!shouldNotify()) return;
      const id = `detection:${det.frigate_event}`;
      const signature = `${det.frigate_event}|${det.display_name}|${det.camera_name}|${det.detection_time}`;
      if (!applyNotificationPolicy(id, signature, 4000)) return;
      const title = t('notifications.event_detection');
      const message = t('notifications.event_detection_desc', {
          species: det.display_name,
          camera: det.camera_name
      });
      notificationCenter.upsert({
          id,
          type: 'detection',
          title,
          message,
          timestamp: Date.now(),
          read: false,
          meta: {
              source: 'sse',
              route: `/events?event=${encodeURIComponent(det.frigate_event)}`,
              event_id: det.frigate_event,
              open_label: t('notifications.open_action')
          }
      });
  }

  function addReclassifyNotification(eventId: string, label: string | null) {
      if (!shouldNotify()) return;
      const id = `reclassify:${eventId}`;
      const signature = `${eventId}|${label ?? 'unknown'}`;
      if (!applyNotificationPolicy(id, signature, 1500)) return;
      const title = t('notifications.event_reclassify');
      const message = t('notifications.event_reclassify_desc', {
          species: label ?? 'Unknown'
      });
      notificationCenter.upsert({
          id,
          type: 'update',
          title,
          message,
          timestamp: Date.now(),
          read: false,
          meta: {
              source: 'sse',
              route: `/events?event=${encodeURIComponent(eventId)}`,
              event_id: eventId,
              open_label: t('notifications.open_action')
          }
      });
  }

  function updateReclassifyProgress(eventId: string, current: number, total: number) {
      if (!shouldNotify()) return;
      const id = `reclassify:progress:${eventId}`;
      const signature = `${eventId}|${current}|${total}`;
      if (!applyNotificationPolicy(id, signature, 1200)) return;
      const title = t('notifications.event_reclassify');
      const message = t('notifications.event_reclassify_progress', {
          current: current.toLocaleString(),
          total: total.toLocaleString()
      });
      notificationCenter.upsert({
          id,
          type: 'process',
          title,
          message,
          timestamp: Date.now(),
          read: false,
          meta: {
              source: 'sse',
              route: `/events?event=${encodeURIComponent(eventId)}`,
              event_id: eventId,
              current,
              total,
              open_label: t('notifications.open_action')
          }
      });
  }

  function clearReclassifyProgressNotification(eventId: string) {
      notificationCenter.remove(`reclassify:progress:${eventId}`);
  }

  function updateBackfillNotification(payload: any) {
      if (!shouldNotify()) return;
      if (!payload || typeof payload !== 'object') return;
      const data = payload.data ?? {};
      const jobId = data.id ?? data.job_id ?? 'unknown';
      const kind = data.kind ?? 'detections';
      const isWeather = kind === 'weather';
      const total = data.total ?? 0;
      const processed = data.processed ?? 0;
      const updated = data.updated ?? data.new_detections ?? 0;
      const skipped = data.skipped ?? 0;
      const errors = data.errors ?? 0;

      let title = isWeather ? t('notifications.event_weather_backfill') : t('notifications.event_backfill');
      if (payload.type === 'backfill_complete') {
          title = isWeather ? t('notifications.event_weather_backfill_done') : t('notifications.event_backfill_done');
      }
      if (payload.type === 'backfill_failed') {
          title = isWeather ? t('notifications.event_weather_backfill_failed') : t('notifications.event_backfill_failed');
      }

      let message = '';
      if (payload.type === 'backfill_progress' || payload.type === 'backfill_started') {
          message = `${processed.toLocaleString()}/${total.toLocaleString()} • ${updated.toLocaleString()} upd • ${skipped.toLocaleString()} skip • ${errors.toLocaleString()} err`;
      } else if (payload.type === 'backfill_complete') {
          message = data.message || `${updated.toLocaleString()} updated, ${skipped.toLocaleString()} skipped, ${errors.toLocaleString()} errors`;
      } else if (payload.type === 'backfill_failed') {
          message = data.message || t('notifications.event_backfill_failed');
      }

      const id = `backfill:${jobId}`;
      const signature = `${payload.type}|${jobId}|${processed}|${total}|${updated}|${skipped}|${errors}`;
      const throttleMs = payload.type === 'backfill_progress' ? 1200 : 0;
      if (!applyNotificationPolicy(id, signature, throttleMs)) return;

      notificationCenter.upsert({
          id,
          type: 'process',
          title,
          message,
          timestamp: Date.now(),
          read: payload.type === 'backfill_complete' || payload.type === 'backfill_failed',
          meta: {
              source: 'sse',
              route: '/settings',
              kind,
              processed,
              total
          }
      });
  }

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

                 // Validate payload structure
                 if (!payload || typeof payload !== 'object') {
                     logger.error("SSE Invalid payload structure", undefined, { payload });
                     return;
                 }

                 if (!payload.type) {
                     logger.error("SSE Missing payload type", undefined, { payload });
                     return;
                 }

                 // Handle different message types with error boundaries
                 try {
                     if (payload.type === 'connected') {
                         detectionsStore.setConnected(true);
                         reconnectAttempts = 0; // Reset backoff on successful connection
                         logger.sseEvent("connected", { message: payload.message });
                     } else if (payload.type === 'detection') {
                         if (!payload.data || !payload.data.frigate_event) {
                             logger.error("SSE Invalid detection data", undefined, { payload });
                             return;
                         }
                         const newDet: Detection = {
                             frigate_event: payload.data.frigate_event,
                             display_name: payload.data.display_name,
                             score: payload.data.score,
                             detection_time: payload.data.timestamp,
                             camera_name: payload.data.camera,
                             frigate_score: payload.data.frigate_score,
                             sub_label: payload.data.sub_label,
                             manual_tagged: payload.data.manual_tagged,
                             audio_confirmed: payload.data.audio_confirmed,
                             audio_species: payload.data.audio_species,
                             audio_score: payload.data.audio_score,
                             temperature: payload.data.temperature,
                             weather_condition: payload.data.weather_condition,
                             weather_cloud_cover: payload.data.weather_cloud_cover,
                             weather_wind_speed: payload.data.weather_wind_speed,
                             weather_wind_direction: payload.data.weather_wind_direction,
                             weather_precipitation: payload.data.weather_precipitation,
                             weather_rain: payload.data.weather_rain,
                             weather_snowfall: payload.data.weather_snowfall,
                             scientific_name: payload.data.scientific_name,
                             common_name: payload.data.common_name,
                             taxa_id: payload.data.taxa_id,
                             video_classification_score: payload.data.video_classification_score,
                             video_classification_label: payload.data.video_classification_label,
                             video_classification_status: payload.data.video_classification_status,
                             video_classification_timestamp: payload.data.video_classification_timestamp
                         };
                         detectionsStore.addDetection(newDet);
                         if (settingsStore.liveAnnouncements) {
                             announcer.announce(`New bird detected: ${newDet.display_name} at ${newDet.camera_name}`);
                         }
                         addDetectionNotification(newDet);
                     } else if (payload.type === 'detection_updated') {
                         if (!payload.data || !payload.data.frigate_event) {
                             logger.error("SSE Invalid detection_updated data", undefined, { payload });
                             return;
                         }
                         const updatedDet: Detection = {
                             frigate_event: payload.data.frigate_event,
                             display_name: payload.data.display_name,
                             score: payload.data.score,
                             detection_time: payload.data.timestamp,
                             camera_name: payload.data.camera,
                             frigate_score: payload.data.frigate_score,
                             sub_label: payload.data.sub_label,
                             is_hidden: payload.data.is_hidden,
                             manual_tagged: payload.data.manual_tagged,
                             audio_confirmed: payload.data.audio_confirmed,
                             audio_species: payload.data.audio_species,
                             audio_score: payload.data.audio_score,
                             temperature: payload.data.temperature,
                             weather_condition: payload.data.weather_condition,
                             weather_cloud_cover: payload.data.weather_cloud_cover,
                             weather_wind_speed: payload.data.weather_wind_speed,
                             weather_wind_direction: payload.data.weather_wind_direction,
                             weather_precipitation: payload.data.weather_precipitation,
                             weather_rain: payload.data.weather_rain,
                             weather_snowfall: payload.data.weather_snowfall,
                             scientific_name: payload.data.scientific_name,
                             common_name: payload.data.common_name,
                             taxa_id: payload.data.taxa_id,
                             video_classification_score: payload.data.video_classification_score,
                             video_classification_label: payload.data.video_classification_label,
                             video_classification_status: payload.data.video_classification_status,
                             video_classification_timestamp: payload.data.video_classification_timestamp
                         };
                         detectionsStore.updateDetection(updatedDet);
                     } else if (payload.type === 'detection_deleted') {
                         if (!payload.data || !payload.data.frigate_event) {
                             logger.error("SSE Invalid detection_deleted data", undefined, { payload });
                             return;
                         }
                         detectionsStore.removeDetection(payload.data.frigate_event, payload.data.timestamp);
                     } else if (payload.type === 'reclassification_started') {
                         if (!payload.data || !payload.data.event_id) {
                             logger.warn("SSE invalid reclassification_started payload", { payload });
                             return;
                         }
                         detectionsStore.startReclassification(payload.data.event_id);
                         updateReclassifyProgress(payload.data.event_id, 0, payload.data.total_frames ?? 0);
                     } else if (payload.type === 'reclassification_progress') {
                         if (!payload.data || !payload.data.event_id) {
                             logger.warn("SSE invalid reclassification_progress payload", { payload });
                             return;
                         }
                         detectionsStore.updateReclassificationProgress(
                             payload.data.event_id,
                             payload.data.current_frame,
                             payload.data.total_frames,
                             payload.data.frame_score,
                             payload.data.top_label,
                             payload.data.frame_thumb,
                             payload.data.frame_index,
                             payload.data.clip_total,
                             payload.data.model_name
                         );
                         updateReclassifyProgress(payload.data.event_id, payload.data.current_frame, payload.data.total_frames);
                     } else if (payload.type === 'reclassification_completed') {
                         if (!payload.data || !payload.data.event_id) {
                             logger.warn("SSE invalid reclassification_completed payload", { payload });
                             return;
                         }
                         clearReclassifyProgressNotification(payload.data.event_id);
                         detectionsStore.completeReclassification(
                             payload.data.event_id,
                             payload.data.results
                         );
                         const topLabel = Array.isArray(payload.data.results) && payload.data.results.length > 0
                             ? payload.data.results[0]?.label ?? null
                             : null;
                         addReclassifyNotification(payload.data.event_id, topLabel);
                     } else if (payload.type === 'backfill_started' || payload.type === 'backfill_progress' || payload.type === 'backfill_complete' || payload.type === 'backfill_failed') {
                         updateBackfillNotification(payload);
                     } else if (payload.type === 'settings_updated') {
                         const signature = `${payload.type}|${JSON.stringify(payload.data ?? {})}`;
                         if (shouldNotify() && applyNotificationPolicy('settings:updated', signature, 3000)) {
                             notificationCenter.upsert({
                                 id: 'settings:updated',
                                 type: 'update',
                                 title: t('notifications.settings_updated_title'),
                                 message: t('notifications.settings_updated_message'),
                                 timestamp: Date.now(),
                                 read: false,
                                 meta: { source: 'sse', route: '/settings' }
                             });
                         }
                     } else {
                         console.warn("SSE Unknown message type:", payload.type);
                     }
                 } catch (handlerError) {
                     console.error(`SSE Handler error for type '${payload.type}':`, handlerError, "Payload:", payload);
                 }
              } catch (e) {
                  console.error("SSE Unexpected error in message handler:", e, "Event:", event);
              }
          };

          evtSource.onerror = (err) => {
              logger.warn("SSE connection issue", {
                  type: (err as any)?.type ?? 'error',
                  attempt: reconnectAttempts + 1
              });
              detectionsStore.setConnected(false);
              if (shouldNotify()) {
                  const id = 'system:sse-disconnected';
                  const signature = `${String((err as any)?.type ?? 'error')}|${document.hidden ? 'hidden' : 'visible'}`;
                  if (applyNotificationPolicy(id, signature, 120000)) {
                      notificationCenter.upsert({
                          id,
                          type: 'update',
                          title: t('notifications.live_updates_disconnected_title'),
                          message: t('notifications.live_updates_disconnected_message'),
                          timestamp: Date.now(),
                          read: false,
                          meta: { source: 'sse', route: '/notifications' }
                      });
                  }
              }

              if (evtSource) {
                  evtSource.close();
                  evtSource = null;
              }

              // Schedule reconnection with backoff
              scheduleReconnect();
          };
      } catch (error) {
          logger.error("Failed to create SSE connection", error);
          detectionsStore.setConnected(false);
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
          <!-- Mobile Header -->
          <div class="md:hidden sticky top-0 z-40 bg-white/90 dark:bg-slate-900/90 backdrop-blur-xl border-b border-slate-200/80 dark:border-slate-700/50 h-16 flex items-center px-4 justify-between">
              <button 
                  class="p-2 -ml-2 text-slate-500 hover:bg-slate-100 dark:hover:bg-slate-800 rounded-lg transition-colors" 
                  onclick={() => mobileSidebarOpen = !mobileSidebarOpen}
                  aria-label={$_('nav.toggle_menu', { default: 'Toggle menu' }) || 'Toggle menu'}
              >
                  <svg xmlns="http://www.w3.org/2000/svg" class="h-6 w-6" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                      <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 6h16M4 12h16M4 18h16" />
                  </svg>
                  <span class="sr-only">{$_('nav.toggle_menu', { default: 'Toggle menu' }) || 'Toggle menu'}</span>
              </button>
              <div class="flex items-center gap-2">
                  <div class="w-7 h-7 rounded-lg bg-transparent border border-slate-200/70 dark:border-slate-700/60 shadow-sm flex items-center justify-center overflow-hidden p-0.5">
                      <img src="/pwa-192x192.png" alt={$_('app.title')} class="w-full h-full object-contain bg-transparent" />
                  </div>
                  <span class="text-sm font-bold text-gradient">{$_('app.title')}</span>
              </div>
              <!-- Theme toggle for mobile -->
              <button
                  class="p-2 rounded-lg hover:bg-slate-100 dark:hover:bg-slate-800 text-slate-500 dark:text-slate-400 transition-colors"
                  onclick={() => themeStore.toggle()}
                  aria-label={themeStore.theme === 'dark'
                      ? ($_('theme.switch_light', { default: 'Switch to light mode' }) || 'Switch to light mode')
                      : ($_('theme.switch_dark', { default: 'Switch to dark mode' }) || 'Switch to dark mode')}
              >
                  {#if themeStore.theme === 'dark'}
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

          <Sidebar {currentRoute} onNavigate={navigate} {mobileSidebarOpen} onMobileClose={() => mobileSidebarOpen = false}>
              {#snippet status()}
                  <div class="flex items-center gap-4 px-2">
                      {#if settingsStore.birdnetEnabled}
                          <div class="relative flex items-center justify-center group cursor-help text-teal-500 dark:text-teal-400" title={$_('status.audio_active')}>
                              <span class="animate-ping absolute inline-flex h-full w-full rounded-full bg-teal-400 opacity-20"></span>
                              <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M15.536 8.464a5 5 0 010 7.072m2.828-9.9a9 9 0 010 12.728M5.586 15H4a1 1 0 01-1-1v-4a1 1 0 011-1h1.586l4.707-4.707C10.923 3.663 12 4.109 12 5v14c0 .891-1.077 1.337-1.707.707L5.586 15z" /></svg>
                          </div>
                      {/if}

                      {#if notificationsActive}
                          <div class="relative flex items-center justify-center text-indigo-500 dark:text-indigo-400 cursor-help" title={$_('status.notifications_enabled')}>
                              <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M7 8h10M7 12h6m-6 8 4-4h6a4 4 0 0 0 4-4V7a4 4 0 0 0-4-4H7a4 4 0 0 0-4 4v9a4 4 0 0 0 4 4z" /></svg>
                          </div>
                      {/if}

                      <div class="flex items-center gap-2 cursor-help" title={detectionsStore.connected ? $_('status.system_online') : $_('status.system_offline')}>
                          {#if detectionsStore.connected}
                              <div class="relative flex items-center justify-center text-emerald-500 dark:text-emerald-400">
                                  <span class="animate-ping absolute inline-flex h-full w-full rounded-full bg-emerald-400 opacity-20"></span>
                                  <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M5 12h14M5 12a2 2 0 01-2-2V6a2 2 0 012-2h14a2 2 0 012 2v4a2 2 0 01-2 2M5 12a2 2 0 00-2 2v4a2 2 0 002 2h14a2 2 0 002-2v-4a2 2 0 00-2-2m-2-4h.01M17 16h.01" /></svg>
                              </div>
                          {:else}
                              <div class="relative flex items-center justify-center text-red-500">
                                  <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 8v4m0 4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" /></svg>
                              </div>
                          {/if}
                      </div>
                  </div>
              {/snippet}
          </Sidebar>
      {:else}
          <Header {currentRoute} onNavigate={navigate} onShowKeyboardShortcuts={() => showKeyboardShortcuts = true}>
              {#snippet status()}
                  <div class="flex items-center gap-4">
                      {#if settingsStore.birdnetEnabled}
                          <div class="relative flex items-center justify-center group cursor-help text-teal-500 dark:text-teal-400" title={$_('status.audio_active')}>
                              <span class="animate-ping absolute inline-flex h-full w-full rounded-full bg-teal-400 opacity-20"></span>
                              <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M15.536 8.464a5 5 0 010 7.072m2.828-9.9a9 9 0 010 12.728M5.586 15H4a1 1 0 01-1-1v-4a1 1 0 011-1h1.586l4.707-4.707C10.923 3.663 12 4.109 12 5v14c0 .891-1.077 1.337-1.707.707L5.586 15z" /></svg>
                          </div>
                      {/if}

                      {#if notificationsActive}
                          <div class="relative flex items-center justify-center text-indigo-500 dark:text-indigo-400 cursor-help" title={$_('status.notifications_enabled')}>
                              <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M7 8h10M7 12h6m-6 8 4-4h6a4 4 0 0 0 4-4V7a4 4 0 0 0-4-4H7a4 4 0 0 0-4 4v9a4 4 0 0 0 4 4z" /></svg>
                          </div>
                      {/if}

                      <div class="flex items-center gap-2 cursor-help" title={detectionsStore.connected ? $_('status.system_online') : $_('status.system_offline')}>
                          {#if detectionsStore.connected}
                              <div class="relative flex items-center justify-center text-emerald-500 dark:text-emerald-400">
                                  <span class="animate-ping absolute inline-flex h-full w-full rounded-full bg-emerald-400 opacity-20"></span>
                                  <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M5 12h14M5 12a2 2 0 01-2-2V6a2 2 0 012-2h14a2 2 0 012 2v4a2 2 0 01-2 2M5 12a2 2 0 00-2 2v4a2 2 0 002 2h14a2 2 0 002-2v-4a2 2 0 00-2-2m-2-4h.01M17 16h.01" /></svg>
                              </div>
                          {:else}
                              <div class="relative flex items-center justify-center text-red-500">
                                  <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 8v4m0 4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" /></svg>
                              </div>
                          {/if}
                      </div>
                  </div>
              {/snippet}
          </Header>
      {/if}

      <!-- Telemetry Banner (shown on first visit if telemetry disabled) -->
      <TelemetryBanner />

      <!-- Main Content Wrapper -->
      <div class="flex-1 flex flex-col transition-all duration-300 {effectiveLayout === 'vertical' ? (isSidebarCollapsed ? 'md:pl-20' : 'md:pl-64') : ''}">
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
                  <Notifications />
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
