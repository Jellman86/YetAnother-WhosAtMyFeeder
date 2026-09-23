import { mount } from 'svelte';
import { i18nReady } from '../src/lib/i18n';
import '../src/app.css';
import HealthFixture from './HealthFixture.svelte';

await i18nReady;
const target = document.getElementById('app');
if (!target) throw new Error('Missing browser fixture mount');
mount(HealthFixture, { target });
