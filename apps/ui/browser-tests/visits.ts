import { mount } from 'svelte';
import { i18nReady } from '../src/lib/i18n';
import '../src/app.css';
import VisitsFixture from './VisitsFixture.svelte';
await i18nReady;
const target = document.getElementById('app');
if (!target) throw new Error('Missing visits fixture mount');
mount(VisitsFixture, { target });
