import { mount } from 'svelte';
import { i18nReady } from '../src/lib/i18n';
import { setAuthToken } from '../src/lib/api/core';
import { authStore } from '../src/lib/stores/auth.svelte';
import { pageRefreshAction } from '../src/lib/stores/page_refresh_action.svelte';
import { systemStatusStore } from '../src/lib/stores/system_status.svelte';
import '../src/app.css';
import SettingsBackfillFixture from './SettingsBackfillFixture.svelte';

await i18nReady;
setAuthToken('fixture-owner-session');
authStore.statusLoaded = true;
authStore.statusHealthy = true;
authStore.isAuthenticated = true;
authStore.authRequired = true;
authStore.publicAccessEnabled = true;
// Lets a test deliver a status push, as the live stream does in the app.
(window as unknown as { __systemStatus: typeof systemStatusStore }).__systemStatus = systemStatusStore;
// Lets a test press the shell's refresh, which the fixture has no header for.
window.addEventListener('test-page-refresh', () => { void pageRefreshAction.run(); });
const target = document.getElementById('app');
if (!target) throw new Error('Missing settings backfill fixture mount');
mount(SettingsBackfillFixture, { target });
