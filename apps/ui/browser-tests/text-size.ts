import { mount } from 'svelte';
import { i18nReady } from '../src/lib/i18n';
import '../src/app.css';
import TextSizeFixture from './TextSizeFixture.svelte';
await i18nReady;
const target = document.getElementById('app');
if (!target) throw new Error('Missing text size fixture mount');
mount(TextSizeFixture, { target });
