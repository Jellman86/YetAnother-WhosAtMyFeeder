import { mount } from 'svelte';
import { i18nReady } from '../src/lib/i18n';
import '../src/app.css';
import ScoreToneFixture from './ScoreToneFixture.svelte';

await i18nReady;
const target = document.getElementById('app');
if (!target) throw new Error('Missing score tone fixture mount');
mount(ScoreToneFixture, { target });
