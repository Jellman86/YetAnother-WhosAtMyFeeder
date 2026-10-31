<script lang="ts">
    import Settings from '../src/lib/pages/Settings.svelte';
    import Toast from '../src/lib/components/Toast.svelte';
    import ConfirmDialog from '../src/lib/components/ConfirmDialog.svelte';
    let visible = $state(true);
    let route = $state('/settings/connection');
</script>
<main class="p-4" data-fixture-route={route}>
    <button type="button" onclick={() => (visible = !visible)}>{visible ? 'Leave Settings' : 'Open Settings'}</button>
    {#if visible}
        <Settings currentRoute={route} onNavigate={(path) => (route = path)} />
    {/if}
</main>
<Toast />
<ConfirmDialog />
