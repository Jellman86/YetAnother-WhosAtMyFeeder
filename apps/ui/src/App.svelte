<script lang="ts">
  import { onMount } from 'svelte';
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
  import Login from './lib/components/Login.svelte';
  import { fetchEvents, fetchEventsCount, type Detection, setAuthErrorCallback } from './lib/api';
  import { themeStore } from './lib/stores/theme.svelte';
  import { layoutStore } from './lib/stores/layout.svelte';
  import { settingsStore } from './lib/stores/settings.svelte';
  import { detectionsStore } from './lib/stores/detections.svelte';
  import { authStore } from './lib/stores/auth.svelte';
  import { announcer } from './lib/components/Announcer.svelte';
  import Announcer from './lib/components/Announcer.svelte';
  import { initKeyboardShortcuts } from './lib/utils/keyboard-shortcuts';
  import { logger } from './lib/utils/logger';

  // Track current layout using reactive derived
  let currentLayout = $derived(layoutStore.layout);
  let isSidebarCollapsed = $derived(layoutStore.sidebarCollapsed);


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

  function navigate(path: string) {
      currentRoute = path;
      window.history.pushState(null, '', path);
  }

  // SSE connection management
  let evtSource: EventSource | null = $state(null);
  let reconnectAttempts = $state(0);
  let reconnectTimeout: number | null = $state(null);
  let isReconnecting = $state(false);
  let mobileSidebarOpen = $state(false);

  // Keyboard shortcuts
  let showKeyboardShortcuts = $state(false);

  // Handle back button and initial load
  onMount(() => {
      // Register auth error callback
      setAuthErrorCallback(() => {
          authStore.setRequiresLogin(true);
      });

      const handlePopState = () => {
          currentRoute = window.location.pathname;
      };
      window.addEventListener('popstate', handlePopState);

      const path = window.location.pathname;
      currentRoute = path === '' ? '/' : path;

      // Initialize settings and load initial data
      // (theme is automatically initialized in the store constructor)
      settingsStore.load();
      detectionsStore.loadInitial();
      connectSSE();

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

      return () => {
          window.removeEventListener('popstate', handlePopState);
          document.removeEventListener('visibilitychange', handleVisibilityChange);
          cleanupShortcuts();
          if (evtSource) {
              evtSource.close();
              evtSource = null;
          }
          if (reconnectTimeout) {
              clearTimeout(reconnectTimeout);
              reconnectTimeout = null;
          }
      };
  });

  function scheduleReconnect() {
      // Prevent multiple reconnection attempts
      if (isReconnecting || reconnectTimeout) {
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
          evtSource = new EventSource('/api/sse');

          evtSource.onopen = () => {
              logger.sseEvent("connection_opened");
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
                             scientific_name: payload.data.scientific_name,
                             common_name: payload.data.common_name,
                             taxa_id: payload.data.taxa_id,
                             video_classification_score: payload.data.video_classification_score,
                             video_classification_label: payload.data.video_classification_label,
                             video_classification_status: payload.data.video_classification_status,
                             video_classification_timestamp: payload.data.video_classification_timestamp
                         };
                         detectionsStore.addDetection(newDet);
                         if (settingsStore.settings?.accessibility_live_announcements ?? true) {
                             announcer.announce(`New bird detected: ${newDet.display_name} at ${newDet.camera_name}`);
                         }
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
                             console.error("SSE Invalid reclassification_started data:", payload);
                             return;
                         }
                         detectionsStore.startReclassification(payload.data.event_id);
                     } else if (payload.type === 'reclassification_progress') {
                         if (!payload.data || !payload.data.event_id) {
                             console.error("SSE Invalid reclassification_progress data:", payload);
                             return;
                         }
                         detectionsStore.updateReclassificationProgress(
                             payload.data.event_id,
                             payload.data.current_frame,
                             payload.data.total_frames,
                             payload.data.frame_score,
                             payload.data.top_label,
                             payload.data.frame_thumb
                         );
                     } else if (payload.type === 'reclassification_completed') {
                         if (!payload.data || !payload.data.event_id) {
                             console.error("SSE Invalid reclassification_completed data:", payload);
                             return;
                         }
                         detectionsStore.completeReclassification(
                             payload.data.event_id,
                             payload.data.results
                         );
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
              console.error("SSE Connection Error", err);
              detectionsStore.setConnected(false);

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
    Skip to content
  </a>

  {#if authStore.requiresLogin}
      <Login />
  {:else}
      {#if currentLayout === 'vertical'}
          <!-- Mobile Header -->
          <div class="md:hidden sticky top-0 z-40 bg-white/90 dark:bg-slate-900/90 backdrop-blur-xl border-b border-slate-200/80 dark:border-slate-700/50 h-16 flex items-center px-4 justify-between">
              <button 
                  class="p-2 -ml-2 text-slate-500 hover:bg-slate-100 dark:hover:bg-slate-800 rounded-lg transition-colors" 
                  onclick={() => mobileSidebarOpen = !mobileSidebarOpen}
                  aria-label="Toggle menu"
              >
                  <svg xmlns="http://www.w3.org/2000/svg" class="h-6 w-6" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                      <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 6h16M4 12h16M4 18h16" />
                  </svg>
              </button>
              <div class="flex items-center gap-2">
                  <span class="text-lg">🐦</span>
                  <span class="text-sm font-bold text-gradient">YA-WAMF</span>
              </div>
              <!-- Theme toggle for mobile -->
              <button
                  class="p-2 rounded-lg hover:bg-slate-100 dark:hover:bg-slate-800 text-slate-500 dark:text-slate-400 transition-colors"
                  onclick={() => themeStore.toggle()}
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
                  <div class="flex flex-col gap-2">
                      {#if settingsStore.settings?.birdnet_enabled}
                          <div class="flex items-center gap-1.5 px-2 py-1 rounded-full bg-teal-500/10 border border-teal-500/20" title="Audio Analysis Active">
                              <span class="relative flex h-2 w-2">
                                  <span class="animate-ping absolute inline-flex h-full w-full rounded-full bg-teal-400 opacity-75"></span>
                                  <span class="relative inline-flex rounded-full h-2 w-2 bg-teal-500"></span>
                              </span>
                              <span class="text-[10px] font-bold text-teal-600 dark:text-teal-400 uppercase tracking-tight">Audio Active</span>
                          </div>
                      {/if}

                      <div class="flex items-center gap-2">
                          {#if detectionsStore.connected}
                              <span class="relative flex h-2.5 w-2.5">
                                  <span class="animate-ping absolute inline-flex h-full w-full rounded-full bg-emerald-400 opacity-75"></span>
                                  <span class="relative inline-flex rounded-full h-2.5 w-2.5 bg-emerald-500 shadow-[0_0_10px_rgba(16,185,129,0.8)]"></span>
                              </span>
                              <span class="text-[10px] font-bold text-emerald-600 dark:text-emerald-400 uppercase tracking-tight">System Online</span>
                          {:else}
                              <span class="w-2.5 h-2.5 rounded-full bg-red-500"></span>
                              <span class="text-[10px] font-bold text-red-600 uppercase tracking-tight">System Offline</span>
                          {/if}
                      </div>
                  </div>
              {/snippet}
          </Sidebar>
      {:else}
          <Header {currentRoute} onNavigate={navigate} onShowKeyboardShortcuts={() => showKeyboardShortcuts = true}>
              {#snippet status()}
                  <div class="flex items-center gap-4">
                      {#if settingsStore.settings?.birdnet_enabled}
                          <div class="flex items-center gap-1.5 px-2 py-1 rounded-full bg-teal-500/10 border border-teal-500/20" title="Audio Analysis Active">
                              <span class="relative flex h-2 w-2">
                                  <span class="animate-ping absolute inline-flex h-full w-full rounded-full bg-teal-400 opacity-75"></span>
                                  <span class="relative inline-flex rounded-full h-2 w-2 bg-teal-500"></span>
                              </span>
                              <span class="text-[10px] font-bold text-teal-600 dark:text-teal-400 uppercase tracking-tight">Audio Active</span>
                          </div>
                      {/if}

                      <div class="flex items-center gap-2">
                          {#if detectionsStore.connected}
                              <span class="relative flex h-2.5 w-2.5">
                                  <span class="animate-ping absolute inline-flex h-full w-full rounded-full bg-emerald-400 opacity-75"></span>
                                  <span class="relative inline-flex rounded-full h-2.5 w-2.5 bg-emerald-500 shadow-[0_0_10px_rgba(16,185,129,0.8)]"></span>
                              </span>
                              <span class="text-[10px] font-bold text-emerald-600 dark:text-emerald-400 uppercase tracking-tight">System Online</span>
                          {:else}
                              <span class="w-2.5 h-2.5 rounded-full bg-red-500"></span>
                              <span class="text-[10px] font-bold text-red-600 uppercase tracking-tight">System Offline</span>
                          {/if}
                      </div>
                  </div>
              {/snippet}
          </Header>
      {/if}

      <!-- Telemetry Banner (shown on first visit if telemetry disabled) -->
      <TelemetryBanner />

      <!-- Main Content Wrapper -->
      <div class="flex-1 flex flex-col transition-all duration-300 {currentLayout === 'vertical' ? (isSidebarCollapsed ? 'md:pl-20' : 'md:pl-64') : ''}">
          <main id="main-content" class="flex-1 w-full max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
              {#if currentRoute === '/'}
                  <Dashboard onnavigate={navigate} />
              {:else if currentRoute.startsWith('/events')}
                  <Events />
              {:else if currentRoute.startsWith('/species')}
                  <Species />
              {:else if currentRoute.startsWith('/settings')}
                   <Settings />
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
