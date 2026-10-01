import { mount } from 'svelte';
import { i18nReady } from '../src/lib/i18n';
import { authStore } from '../src/lib/stores/auth.svelte';
import '../src/app.css';
import TouchTargetsFixture from './TouchTargetsFixture.svelte';

await i18nReady;
authStore.statusLoaded = true;
authStore.statusHealthy = true;
authStore.authRequired = true;
authStore.isAuthenticated = true;
authStore.username = 'Fixture owner';
const target = document.getElementById('app');
if (!target) throw new Error('Missing touch target fixture mount');
mount(TouchTargetsFixture, { target });
