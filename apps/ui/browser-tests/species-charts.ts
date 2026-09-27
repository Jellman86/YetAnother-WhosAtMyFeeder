import { mount } from 'svelte';
import { i18nReady } from '../src/lib/i18n';
import { authStore } from '../src/lib/stores/auth.svelte';
import { settingsStore } from '../src/lib/stores/settings.svelte';
import { themeStore } from '../src/lib/stores/theme.svelte';
import Species from '../src/lib/pages/Species.svelte';
import '../src/app.css';

await i18nReady;
authStore.statusLoaded = true;
authStore.statusHealthy = true;
authStore.authRequired = false;
settingsStore.settings = { llm_ready: true } as NonNullable<typeof settingsStore.settings>;

document.getElementById('toggle-theme')?.addEventListener('click', () => themeStore.toggle());
const target = document.getElementById('app');
if (!target) throw new Error('Missing species chart fixture mount');
mount(Species, { target });
