import { mount } from 'svelte';
import { i18nReady } from '../src/lib/i18n';
import { setAuthToken } from '../src/lib/api/core';
import '../src/app.css';
import ModelEvaluation from '../src/lib/pages/ModelEvaluation.svelte';

await i18nReady;
setAuthToken('fixture-owner-session');
const target = document.getElementById('app');
if (!target) throw new Error('Missing model evaluation fixture mount');
mount(ModelEvaluation, { target });
