import { mount } from 'svelte';
import { i18nReady } from '../src/lib/i18n';
import '../src/app.css';
import SpeciesCheckFixture from './SpeciesCheckFixture.svelte';
await i18nReady;
const target = document.getElementById('app');
if (!target) throw new Error('Missing species check fixture mount');
mount(SpeciesCheckFixture, { target });
