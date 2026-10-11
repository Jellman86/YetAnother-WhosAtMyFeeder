// Actual pages, mounted without the application's background schedulers. The
// documentation capture script supplies every HTTP response and rejects writes.
import { mount } from 'svelte';
import { i18nReady } from '../src/lib/i18n';
import { setAuthToken } from '../src/lib/api/core';
import { authStore } from '../src/lib/stores/auth.svelte';
import { settingsStore } from '../src/lib/stores/settings.svelte';
import { detectionsStore } from '../src/lib/stores/detections.svelte';
import { themeStore } from '../src/lib/stores/theme.svelte';
import Dashboard from '../src/lib/pages/Dashboard.svelte';
import ManualObservation from '../src/lib/pages/ManualObservation.svelte';
import '../src/app.css';

await i18nReady;
setAuthToken('documentation-fixture-session');
authStore.statusLoaded = true;
authStore.statusHealthy = true;
authStore.isAuthenticated = true;
authStore.authRequired = true;
themeStore.setTheme('dark');
themeStore.setColorTheme('bluetit');
await settingsStore.load();
await detectionsStore.loadInitial();
detectionsStore.setConnected(true);
const target = document.getElementById('app');
if (!target) throw new Error('Missing documentation capture mount');
if (new URLSearchParams(location.search).get('surface') === 'manual') {
    mount(ManualObservation, { target, props: { onNavigate: () => {} } });
} else {
    mount(Dashboard, { target });
}
