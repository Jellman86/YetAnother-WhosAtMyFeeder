import { mount } from 'svelte';
import { i18nReady } from '../src/lib/i18n';
import '../src/app.css';
import LazyModalFixture from './LazyModalFixture.svelte';

await i18nReady;
const target = document.getElementById('app');
if (!target) throw new Error('Missing lazy dialog fixture mount');
mount(LazyModalFixture, { target });
