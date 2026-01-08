<script lang="ts">
  import { onMount } from 'svelte';
  import Header from './lib/components/Header.svelte';
  import Footer from './lib/components/Footer.svelte';
  import Dashboard from './lib/pages/Dashboard.svelte';
  import Events from './lib/pages/Events.svelte';
  import Species from './lib/pages/Species.svelte';
  import Settings from './lib/pages/Settings.svelte';
  import Login from './lib/components/Login.svelte';
  import { fetchEvents, fetchEventsCount, type Detection, setAuthErrorCallback } from './lib/api';
  import { theme } from './lib/stores/theme';
  import { settingsStore } from './lib/stores/settings.svelte';
  import { detectionsStore } from './lib/stores/detections.svelte';
  import { authStore } from './lib/stores/auth.svelte';


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

      <!-- Main Content -->
      <main class="flex-1 max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8 w-full">
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
</div>