import { mount } from 'svelte';
import { i18nReady } from '../src/lib/i18n';
import { setAuthToken } from '../src/lib/api/core';
import { authStore } from '../src/lib/stores/auth.svelte';
import '../src/app.css';
import SupportFixture from './SupportFixture.svelte';

await i18nReady;
setAuthToken('fixture-owner-session');
authStore.statusLoaded = true;
authStore.statusHealthy = true;
authStore.isAuthenticated = true;
authStore.authRequired = true;
authStore.publicAccessEnabled = true;
const target = document.getElementById('app');
if (!target) throw new Error('Missing support fixture mount');
mount(SupportFixture, { target });
