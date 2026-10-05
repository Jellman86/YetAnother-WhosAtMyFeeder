import { mount } from 'svelte';
import { i18nReady } from '../src/lib/i18n';
import { authStore } from '../src/lib/stores/auth.svelte';
import { themeStore } from '../src/lib/stores/theme.svelte';
import TaxonomyLineage from '../src/lib/components/TaxonomyLineage.svelte';
import '../src/app.css';

await i18nReady;
authStore.statusLoaded = true;
authStore.statusHealthy = true;
authStore.authRequired = false;

document.getElementById('toggle-theme')?.addEventListener('click', () => themeStore.toggle());
const target = document.getElementById('app');
if (!target) throw new Error('Missing family tree fixture mount');
mount(TaxonomyLineage, { target, props: { scientificName: new URLSearchParams(location.search).get('name') ?? 'Prunella modularis' } });
