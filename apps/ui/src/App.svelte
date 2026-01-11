<script lang="ts">
  import { onMount } from 'svelte';
  import Header from './lib/components/Header.svelte';
  import Sidebar from './lib/components/Sidebar.svelte';
  import Footer from './lib/components/Footer.svelte';
  import TelemetryBanner from './lib/components/TelemetryBanner.svelte';
  import Toast from './lib/components/Toast.svelte';
  import Dashboard from './lib/pages/Dashboard.svelte';
  import Events from './lib/pages/Events.svelte';
  import Species from './lib/pages/Species.svelte';
  import Settings from './lib/pages/Settings.svelte';
  import Login from './lib/components/Login.svelte';
  import { fetchEvents, fetchEventsCount, type Detection, setAuthErrorCallback } from './lib/api';
  import { theme } from './lib/stores/theme';
  import { layout, sidebarCollapsed } from './lib/stores/layout';
  import { settingsStore } from './lib/stores/settings.svelte';
  import { detectionsStore } from './lib/stores/detections.svelte';
  import { authStore } from './lib/stores/auth.svelte';

  // Track current layout
  let currentLayout = $state<'horizontal' | 'vertical'>('horizontal');
  let isSidebarCollapsed = $state(false);

  layout.subscribe(value => {
      currentLayout = value;
  });

  sidebarCollapsed.subscribe(value => {
      isSidebarCollapsed = value;
  });


  // Router state
  let currentRoute = $state('/');

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

      // Initialize theme and settings
      theme.init();
      settingsStore.load();
      detectionsStore.loadInitial();
      connectSSE();

      // Handle page visibility changes - reconnect when tab becomes visible
      const handleVisibilityChange = () => {
          if (!document.hidden && !detectionsStore.connected && !isReconnecting) {
              console.log("Tab became visible, attempting to reconnect SSE...");
              reconnectAttempts = 0; // Reset backoff when user returns to tab
              scheduleReconnect();
          }
      };
      document.addEventListener('visibilitychange', handleVisibilityChange);

      return () => {
          window.removeEventListener('popstate', handlePopState);
          document.removeEventListener('visibilitychange', handleVisibilityChange);
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
      console.log(`Scheduling SSE reconnect in ${delay}ms (attempt ${reconnectAttempts + 1})`);

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
              console.log("SSE Connection opened");
          };

          evtSource.onmessage = (event) => {
              try {
                 // Parse JSON with validation
                 let payload: any;
                 try {
                     payload = JSON.parse(event.data);
                 } catch (parseError) {
                     console.error("SSE JSON Parse Error:", parseError, "Data:", event.data);
                     return;
                 }

                 // Validate payload structure
                 if (!payload || typeof payload !== 'object') {
                     console.error("SSE Invalid payload structure:", payload);
                     return;
                 }

                 if (!payload.type) {
                     console.error("SSE Missing payload type:", payload);
                     return;
                 }

                 // Handle different message types with error boundaries
                 try {
                     if (payload.type === 'connected') {
                         detectionsStore.setConnected(true);
                         reconnectAttempts = 0; // Reset backoff on successful connection
                         console.log("SSE Connected:", payload.message);
                     } else if (payload.type === 'detection') {
                         if (!payload.data || !payload.data.frigate_event) {
                             console.error("SSE Invalid detection data:", payload);
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
                     } else if (payload.type === 'detection_updated') {
                         if (!payload.data || !payload.data.frigate_event) {
                             console.error("SSE Invalid detection_updated data:", payload);
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
                             console.error("SSE Invalid detection_deleted data:", payload);
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
                             payload.data.top_label
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
          console.error("Failed to create SSE connection:", error);
          detectionsStore.setConnected(false);
          scheduleReconnect();
      }
  }
</script>

  <div class="min-h-screen flex flex-col bg-surface-light dark:bg-surface-dark text-slate-900 dark:text-white font-sans transition-colors duration-300">

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
                  onclick={() => theme.toggle()}
              >
                  {#if $theme === 'dark'}
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
                              <span class="text-[10px] font-bold text-teal-600 dark:text-teal-400 uppercase tracking-tight">Listening</span>
                          </div>
                      {/if}

                      <div class="flex items-center gap-2">
                          {#if detectionsStore.connected}
                              <span class="relative flex h-2.5 w-2.5">
                                  <span class="animate-ping absolute inline-flex h-full w-full rounded-full bg-emerald-400 opacity-75"></span>
                                  <span class="relative inline-flex rounded-full h-2.5 w-2.5 bg-emerald-500 shadow-[0_0_10px_rgba(16,185,129,0.8)]"></span>
                              </span>
                              <span class="text-[10px] font-bold text-emerald-600 dark:text-emerald-400 uppercase tracking-tight">Live</span>
                          {:else}
                              <span class="w-2.5 h-2.5 rounded-full bg-red-500"></span>
                              <span class="text-[10px] font-bold text-red-600 uppercase tracking-tight">Offline</span>
                          {/if}
                      </div>
                  </div>
              {/snippet}
          </Sidebar>
      {:else}
          <Header {currentRoute} onNavigate={navigate}>
              {#snippet status()}
                  <div class="flex items-center gap-4">
                      {#if settingsStore.settings?.birdnet_enabled}
                          <div class="flex items-center gap-1.5 px-2 py-1 rounded-full bg-teal-500/10 border border-teal-500/20" title="Audio Analysis Active">
                              <span class="relative flex h-2 w-2">
                                  <span class="animate-ping absolute inline-flex h-full w-full rounded-full bg-teal-400 opacity-75"></span>
                                  <span class="relative inline-flex rounded-full h-2 w-2 bg-teal-500"></span>
                              </span>
                              <span class="text-[10px] font-bold text-teal-600 dark:text-teal-400 uppercase tracking-tight">Listening</span>
                          </div>
                      {/if}

                      <div class="flex items-center gap-2">
                          {#if detectionsStore.connected}
                              <span class="relative flex h-2.5 w-2.5">
                                  <span class="animate-ping absolute inline-flex h-full w-full rounded-full bg-emerald-400 opacity-75"></span>
                                  <span class="relative inline-flex rounded-full h-2.5 w-2.5 bg-emerald-500 shadow-[0_0_10px_rgba(16,185,129,0.8)]"></span>
                              </span>
                              <span class="text-[10px] font-bold text-emerald-600 dark:text-emerald-400 uppercase tracking-tight">Live</span>
                          {:else}
                              <span class="w-2.5 h-2.5 rounded-full bg-red-500"></span>
                              <span class="text-[10px] font-bold text-red-600 uppercase tracking-tight">Offline</span>
                          {/if}
                      </div>
                  </div>
              {/snippet}
          </Header>
      {/if}

      <!-- Telemetry Banner (shown on first visit if telemetry disabled) -->
      <TelemetryBanner />

      <!-- Main Content -->
      <main class="flex-1 max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8 w-full transition-all duration-300 {currentLayout === 'vertical' ? (isSidebarCollapsed ? 'md:ml-20' : 'md:ml-64') : ''}">
          {#if currentRoute === '/'} 
              <Dashboard onnavigate={navigate} />
          {:else if currentRoute.startsWith('/events')}
              <Events />
          {:else if currentRoute.startsWith('/species')}
              <Species />
          {:else if currentRoute.startsWith('/settings')}
               <Settings />
          {/if}
      </main>

      <Footer />
  {/if}

  <!-- Toast Notifications -->
  <Toast />
</div>