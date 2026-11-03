import { mount } from 'svelte';
import { i18nReady } from '../src/lib/i18n';
import '../src/app.css';
import SpeciesKeptBirdFixture from './SpeciesKeptBirdFixture.svelte';
await i18nReady;
const target = document.getElementById('app');
if (!target) throw new Error('Missing kept bird fixture mount');
mount(SpeciesKeptBirdFixture, { target });
