import { mount } from 'svelte';
import { i18nReady } from '../src/lib/i18n';
import '../src/app.css';
import Dashboard from '../src/lib/pages/Dashboard.svelte';
import Toast from '../src/lib/components/Toast.svelte';
import { authStore } from '../src/lib/stores/auth.svelte';
import { detectionsStore } from '../src/lib/stores/detections.svelte';
import { settingsStore } from '../src/lib/stores/settings.svelte';
import { pageRefreshAction } from '../src/lib/stores/page_refresh_action.svelte';
import type { Settings } from '../src/lib/api';

// The real Dashboard over an empty, fully read visit history, so whatever "Needs your call" says
// comes from the range check the spec serves. `?viewer=guest` signs in as a visitor instead.
await i18nReady;
const guest = new URLSearchParams(location.search).get('viewer') === 'guest';
authStore.statusLoaded = true;
authStore.statusHealthy = true;
authStore.authRequired = true;
authStore.isAuthenticated = !guest;
authStore.publicAccessEnabled = guest;
settingsStore.settings = { classification_threshold: 0.6, birdnet_enabled: false, beta_garden_animals: true } as Settings;
detectionsStore.detections = [];
detectionsStore.historyStatus = 'ready';
// The header's refresh button, so a spec can ask for a fresh read without waiting a minute.
window.addEventListener('test-page-refresh', () => { void pageRefreshAction.run(); });
const target = document.getElementById('app');
if (!target) throw new Error('Missing dashboard species checks fixture mount');
const navigated = document.querySelector('[data-navigated]');
mount(Dashboard, { target, props: { onnavigate: (path: string) => { if (navigated) navigated.textContent = path; } } });
mount(Toast, { target });
