import { mount } from 'svelte';
import { i18nReady } from '../src/lib/i18n';
import '../src/app.css';
import FrameScanFixture from './FrameScanFixture.svelte';
await i18nReady;
const target = document.getElementById('app');
if (!target) throw new Error('Missing frame scan fixture mount');
mount(FrameScanFixture, { target });
