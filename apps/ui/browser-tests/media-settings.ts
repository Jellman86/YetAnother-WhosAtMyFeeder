import { mount } from 'svelte';
import { i18nReady } from '../src/lib/i18n';
import '../src/app.css';
import MediaSettingsFixture from './MediaSettingsFixture.svelte';

await i18nReady;
const target = document.getElementById('app');
if (!target) throw new Error('Missing media settings fixture mount');
mount(MediaSettingsFixture, { target });
