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
const params = new URLSearchParams(location.search);
// ?style=scientific or ?style=hobbyist stands in for the reader's Bird Naming Style.
authStore.displayCommonNames = params.get('style') !== 'scientific';
authStore.scientificNamePrimary = params.get('style') === 'hobbyist';

document.getElementById('toggle-theme')?.addEventListener('click', () => themeStore.toggle());
const target = document.getElementById('app');
if (!target) throw new Error('Missing family tree fixture mount');
mount(TaxonomyLineage, { target, props: { scientificName: params.get('name') ?? 'Prunella modularis', subject: params.get('subject') === 'animal' ? 'animal' : 'bird' } });
