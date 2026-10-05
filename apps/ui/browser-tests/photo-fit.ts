import { mount } from 'svelte';
import { i18nReady } from '../src/lib/i18n';
import '../src/app.css';
import PhotoFitFixture from './PhotoFitFixture.svelte';

await i18nReady;
const target = document.getElementById('app');
if (!target) throw new Error('Missing photo fit fixture mount');
mount(PhotoFitFixture, { target });
