<script lang="ts">
    import Notifications from '../src/lib/pages/Notifications.svelte';
    import Errors from '../src/lib/pages/Errors.svelte';
    import { authStore } from '../src/lib/stores/auth.svelte';
    let route = $state('/notifications');
</script>
<main class="mx-auto max-w-5xl p-4">
    <button type="button" onclick={() => (authStore.isAuthenticated = false)}>Become guest</button>
    <output aria-label="Current route">{route}</output>
    {#if route === '/notifications'}
        <Notifications onNavigate={(path) => (route = path)} />
    {:else}
        <Errors />
    {/if}
</main>
