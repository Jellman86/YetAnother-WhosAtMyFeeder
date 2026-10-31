import { mount } from 'svelte';
import { i18nReady } from '../src/lib/i18n';
import { authStore } from '../src/lib/stores/auth.svelte';
import '../src/app.css';
import TouchTargetsFixture from './TouchTargetsFixture.svelte';
import TouchTargetsKitFixture from './TouchTargetsKitFixture.svelte';

await i18nReady;
authStore.statusLoaded = true;
authStore.statusHealthy = true;
authStore.authRequired = true;
authStore.isAuthenticated = true;
authStore.username = 'Fixture owner';
const target = document.getElementById('app');
if (!target) throw new Error('Missing touch target fixture mount');
// `?surface=kit` mounts the shared page controls instead of the navigation chrome.
if (new URLSearchParams(window.location.search).get('surface') === 'kit') {
    authStore.needsInitialSetup = true;
    mount(TouchTargetsKitFixture, { target });
} else {
    mount(TouchTargetsFixture, { target });
}
