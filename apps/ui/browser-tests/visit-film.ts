import { mount } from 'svelte';
import '../src/app.css';
import VisitFilmFixture from './VisitFilmFixture.svelte';

const target = document.getElementById('app');
if (!target) throw new Error('Missing film fixture mount');
mount(VisitFilmFixture, { target });
