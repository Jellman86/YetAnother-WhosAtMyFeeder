<script lang="ts">
    import FirstRunWizard from '../src/lib/pages/FirstRunWizard.svelte';
    import WizardShell from '../src/lib/components/setup/WizardShell.svelte';
    import { authStore } from '../src/lib/stores/auth.svelte';
    import { setupWizardStore } from '../src/lib/stores/setup_wizard.svelte';
    import Settings from '../src/lib/pages/Settings.svelte';
    const showSettings = new URL(window.location.href).searchParams.has('settings');
    let route = $state('/settings/detection');
</script>

<!-- The same two mount points App.svelte uses: first run replaces the app, a re-run overlays it. -->
{#if authStore.needsInitialSetup || (setupWizardStore.active && setupWizardStore.mode === 'first_run')}
    <FirstRunWizard />
{:else}
    {#if showSettings}
        <Settings currentRoute={route} onNavigate={(path) => (route = path)} />
    {:else}
    <main class="p-4">
        <h1>App opened</h1>
        <button type="button" class="btn btn-secondary" onclick={() => setupWizardStore.open('rerun')}>Open setup wizard</button>
    </main>
    {/if}
    {#if setupWizardStore.active && setupWizardStore.mode === 'rerun'}
        <WizardShell />
    {/if}
{/if}
