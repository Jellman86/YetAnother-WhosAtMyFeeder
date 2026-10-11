import { mount } from 'svelte';
import { i18nReady } from '../src/lib/i18n';
import '../src/app.css';
import Garden from '../src/lib/pages/Garden.svelte';

await i18nReady;
const target = document.getElementById('app');
if (!target) throw new Error('Missing garden fixture mount');
target.className = 'mx-auto max-w-6xl p-4';
mount(Garden, { target, props: { onNavigate: (path: string) => { window.location.href = path; } } });
