<script lang="ts">
    import Separator from './Separator.svelte';
    import BrandMark from './BrandMark.svelte';
    import { _ } from 'svelte-i18n';
    import { readVersion, type VersionInfo } from '../api';
    import { docsRefForBranch } from '../app/app-version';

    const appVersion = typeof __APP_VERSION__ === 'string' ? __APP_VERSION__ : 'unknown';
    const appVersionBase = appVersion.includes('+') ? appVersion.split('+')[0] : appVersion;

    let version = $state(appVersionBase);
    let versionInfo = $state<VersionInfo>({
        version: appVersion,
        base_version: appVersionBase,
        git_hash: __GIT_HASH__,
        branch: typeof __APP_BRANCH__ === 'string' ? __APP_BRANCH__ : 'unknown'
    });

    $effect(() => {
        (async () => {
            try {
                const info = await readVersion();
                versionInfo = info;
                // Show clean version - hide "+unknown" suffix if git hash isn't available
                version = info.git_hash === "unknown" ? info.base_version : info.version;
            } catch (e) {
                console.error('Failed to fetch version info', e);
            }
        })();
    });

    const year = $derived(new Date().getFullYear());
</script>

<!-- One slim band the full width of the content: which build this is, then the licence and the
     links. Nothing here changes from page to page, and it stacks on narrow screens. -->
<footer class="mt-auto border-t border-line-soft bg-surface">
    <div class="mx-auto flex max-w-shell flex-col items-center gap-x-8 gap-y-3 px-4 py-4 text-xs text-muted sm:px-6 lg:flex-row lg:flex-wrap lg:justify-between lg:px-8 lg:py-3 2xl:px-12">
        <div class="flex shrink-0 flex-wrap items-center justify-center gap-x-2 gap-y-1">
            <BrandMark class="h-5 w-5 rounded-md" sizes="20px" width={20} height={20} loading="lazy" alt="" />
            <span class="font-display text-sm font-bold text-strong">Yet Another WhosAtMyFeeder</span>
            <a
                href={`https://github.com/Jellman86/YetAnother-WhosAtMyFeeder/blob/${docsRefForBranch(versionInfo.branch)}/CHANGELOG.md`}
                target="_blank"
                rel="noopener noreferrer"
                class="inline-flex min-h-6 items-center rounded-sm tabular-nums underline decoration-dotted underline-offset-2 transition-colors hover:text-accent-ink focus-ring"
                title={versionInfo.git_hash !== "unknown" ? `Git: ${versionInfo.git_hash}` : $_('about.view_changelog', { default: 'View changelog' })}
            >
                v{version}
            </a>
        </div>

        <div class="flex shrink-0 flex-wrap items-center justify-center gap-x-3 gap-y-1">
            <a
                href="https://github.com/Jellman86/YetAnother-WhosAtMyFeeder"
                target="_blank"
                rel="noopener noreferrer"
                class="flex min-h-6 items-center gap-1.5 rounded-sm underline decoration-dotted underline-offset-2 transition-colors hover:text-strong focus-ring"
            >
                <svg class="h-3.5 w-3.5" fill="currentColor" viewBox="0 0 24 24" aria-hidden="true">
                        <path fill-rule="evenodd" d="M12 2C6.477 2 2 6.484 2 12.017c0 4.425 2.865 8.18 6.839 9.504.5.092.682-.217.682-.483 0-.237-.008-.868-.013-1.703-2.782.605-3.369-1.343-3.369-1.343-.454-1.158-1.11-1.466-1.11-1.466-.908-.62.069-.608.069-.608 1.003.07 1.531 1.032 1.531 1.032.892 1.53 2.341 1.088 2.91.832.092-.647.35-1.088.636-1.338-2.22-.253-4.555-1.113-4.555-4.951 0-1.093.39-1.988 1.029-2.688-.103-.253-.446-1.272.098-2.65 0 0 .84-.27 2.75 1.026A9.564 9.564 0 0112 6.844c.85.004 1.705.115 2.504.337 1.909-1.296 2.747-1.027 2.747-1.027.546 1.379.202 2.398.1 2.651.64.7 1.028 1.595 1.028 2.688 0 3.848-2.339 4.695-4.566 4.943.359.309.678.92.678 1.855 0 1.338-.012 2.419-.012 2.747 0 .268.18.58.688.482A10.019 10.019 0 0022 12.017C22 6.484 17.522 2 12 2z" clip-rule="evenodd" />
                    </svg>
                {$_('common.github', { default: 'GitHub' })}
            </a>
            <Separator />
            <span>{$_('common.mit_license', { default: 'MIT License' })}</span>
            <Separator />
            <span>&copy; {year} Jellman86</span>
        </div>
    </div>
</footer>
