// The Add observation page as an owner sees it. The spec supplies every HTTP response.
import { mount } from 'svelte';
import { i18nReady } from '../src/lib/i18n';
import { authStore } from '../src/lib/stores/auth.svelte';
import ManualObservation from '../src/lib/pages/ManualObservation.svelte';
import '../src/app.css';

await i18nReady;
authStore.statusLoaded = true;
authStore.statusHealthy = true;
authStore.isAuthenticated = true;
authStore.authRequired = true;
const target = document.getElementById('app');
const navigated = document.querySelector('[data-fixture-navigated]');
if (!target || !navigated) throw new Error('Missing manual observation fixture mount');
sessionStorage.clear();
mount(ManualObservation, { target, props: { onNavigate: (path: string) => { navigated.textContent = path; } } });
