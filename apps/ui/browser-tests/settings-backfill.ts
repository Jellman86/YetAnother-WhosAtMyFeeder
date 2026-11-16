import { mount } from 'svelte';
import { i18nReady } from '../src/lib/i18n';
import { setAuthToken } from '../src/lib/api/core';
import { authStore } from '../src/lib/stores/auth.svelte';
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
const target = document.getElementById('app');
if (!target) throw new Error('Missing settings backfill fixture mount');
mount(SettingsBackfillFixture, { target });
