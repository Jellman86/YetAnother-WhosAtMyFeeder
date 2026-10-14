import { mount } from 'svelte';
import { i18nReady } from '../src/lib/i18n';
import '../src/app.css';
import Dashboard from '../src/lib/pages/Dashboard.svelte';
import Toast from '../src/lib/components/Toast.svelte';
import { authStore } from '../src/lib/stores/auth.svelte';
import { detectionsStore } from '../src/lib/stores/detections.svelte';
import { settingsStore } from '../src/lib/stores/settings.svelte';
import { fetchEvents, type Settings } from '../src/lib/api';

// Actual dashboard and review handlers, with HTTP responses owned by the spec.
// No SSE: a saved owner decision must settle the local queue on its own.
await i18nReady;
authStore.statusLoaded = true;
authStore.statusHealthy = true;
authStore.authRequired = true;
authStore.isAuthenticated = true;
settingsStore.settings = { classification_threshold: 0.6, birdnet_enabled: false } as Settings;
detectionsStore.detections = await fetchEvents({ limit: 50 });
detectionsStore.historyStatus = 'ready';
const target = document.getElementById('app');
if (!target) throw new Error('Missing dashboard review fixture mount');
mount(Dashboard, { target });
mount(Toast, { target });
