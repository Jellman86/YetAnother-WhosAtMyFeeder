import { mount } from 'svelte';
import '../src/app.css';
import Map from '../src/lib/components/Map.svelte';
const target = document.getElementById('app');
if (!target) throw new Error('Missing map fixture');
const variant = new URL(location.href).searchParams.get('variant') ?? 'title';
const hostile = `<img src="data:," onerror="document.documentElement.dataset.popupExecuted='yes'">`;
const markers = [{lat:51,lng:0,title:variant === 'title' ? hostile : 'Fixture location',
    popupLines: variant === 'body' ? [hostile, 'Count: 2'] : undefined}];
mount(Map, {target,props:{markers,center:[51,0],zoom:12}});
