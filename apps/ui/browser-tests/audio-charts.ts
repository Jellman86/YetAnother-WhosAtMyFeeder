import { mount } from 'svelte';
import { i18nReady } from '../src/lib/i18n';
import { authStore } from '../src/lib/stores/auth.svelte';
import { themeStore } from '../src/lib/stores/theme.svelte';
import AudioHistory from '../src/lib/pages/AudioHistory.svelte';
import '../src/app.css';

await i18nReady;
authStore.statusLoaded = true;
authStore.statusHealthy = true;
authStore.authRequired = false;

document.getElementById('toggle-theme')?.addEventListener('click', () => themeStore.toggle());
const target = document.getElementById('app');
if (!target) throw new Error('Missing audio chart fixture mount');
mount(AudioHistory, { target });
