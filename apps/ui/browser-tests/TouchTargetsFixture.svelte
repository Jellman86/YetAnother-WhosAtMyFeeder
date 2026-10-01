<script lang="ts">
    import MobileTopBar from '../src/lib/components/MobileTopBar.svelte';
    import Sidebar from '../src/lib/components/Sidebar.svelte';
    import { themeStore } from '../src/lib/stores/theme.svelte';
    let open = $state(false);
</script>

<MobileTopBar
    appTitle="YA-WAMF" toggleMenuLabel="Open menu" switchThemeLabel="Switch theme"
    theme={themeStore.isDark ? 'dark' : 'light'}
    onToggleMenu={() => { open = !open; }} onToggleTheme={() => themeStore.toggle()}
/>
<Sidebar currentRoute="/" onNavigate={() => undefined} mobileSidebarOpen={open} onMobileClose={() => { open = false; }} />
