import { mount } from 'svelte';
import { i18nReady } from '../src/lib/i18n';
import '../src/app.css';
import CountedBirdsFixture from './CountedBirdsFixture.svelte';

await i18nReady;
const target = document.getElementById('app');
if (!target) throw new Error('Missing counted birds fixture mount');
mount(CountedBirdsFixture, { target });
