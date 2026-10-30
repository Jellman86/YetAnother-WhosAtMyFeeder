<script module lang="ts">
    import { lazyComponent } from '../app/lazy-component';

    // markdown-it is over 100 kB, so it arrives only once there is AI text to render.
    const loadRenderer = lazyComponent(() => import('../utils/markdown').then((module) => module.renderMarkdown));
</script>

<script lang="ts">
    let { text }: { text: string } = $props();
</script>

<!-- Until the renderer arrives, or if it cannot, the same words read as plain, escaped text. -->
{#await loadRenderer()}
    <p class="whitespace-pre-line">{text}</p>
{:then render}
    {@html render(text)}
{:catch}
    <p class="whitespace-pre-line">{text}</p>
{/await}
