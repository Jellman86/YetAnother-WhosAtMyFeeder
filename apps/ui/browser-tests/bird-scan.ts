import { mount } from 'svelte';
import { i18nReady } from '../src/lib/i18n';
import '../src/app.css';
import BirdScanFixture from './BirdScanFixture.svelte';
await i18nReady;
const target = document.getElementById('app');
if (!target) throw new Error('Missing bird scan fixture mount');
mount(BirdScanFixture, { target });
