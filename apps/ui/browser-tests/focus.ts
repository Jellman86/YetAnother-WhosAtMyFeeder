import { mount } from 'svelte';
import '../src/app.css';
import FocusFixture from './FocusFixture.svelte';
const target = document.getElementById('app');
if (!target) throw new Error('Missing focus fixture mount');
mount(FocusFixture, { target });
