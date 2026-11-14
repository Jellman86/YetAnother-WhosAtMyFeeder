import { mount } from 'svelte';
import { i18nReady } from '../src/lib/i18n';
import '../src/app.css';
import StatusFeedFixture from './StatusFeedFixture.svelte';

await i18nReady;
const target = document.getElementById('app');
if (!target) throw new Error('Missing status feed fixture mount');
mount(StatusFeedFixture, { target });
