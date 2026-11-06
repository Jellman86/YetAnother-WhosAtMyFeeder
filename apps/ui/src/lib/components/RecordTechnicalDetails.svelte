<script lang="ts">
    import type { Snippet } from 'svelte';
    import type { HTMLAttributes } from 'svelte/elements';

    let { title, command, identifier, children, ...attributes }: {
        title: string;
        command: string;
        identifier: string;
        children?: Snippet;
    } & HTMLAttributes<HTMLDetailsElement> = $props();

    /**
     * A terminal borrows the viewer's own window furniture: traffic lights on macOS, the
     * bevelled Windows 95 set on Windows, and a single round close button in the GNOME manner
     * on Linux. Purely cosmetic, so an unknown platform gets the macOS set rather than nothing.
     */
    const windowChrome = $derived.by((): 'mac' | 'windows' | 'linux' => {
        if (typeof navigator === 'undefined') return 'mac';
        const agent = navigator as Navigator & { userAgentData?: { platform?: string } };
        const platform = (agent.userAgentData?.platform ?? navigator.platform ?? navigator.userAgent ?? '')
            .toLowerCase();
        if (platform.includes('win')) return 'windows';
        // Android reports Linux in its user agent, and is not a desktop window manager.
        if (platform.includes('linux') && !platform.includes('android')) return 'linux';
        return 'mac';
    });

    /**
     * The window's insides follow its furniture: a plain dark shell on macOS, the black and grey
     * of a DOS box on Windows, and the aubergine GNOME Terminal ships with on Linux.
     */
    const terminalTheme = $derived.by(() => {
        if (windowChrome === 'windows') {
            return {
                shell: 'bg-black',
                prompt: 'text-[#c0c0c0]',
                host: null,
                sigil: 'C:\\>',
                output: 'text-[#c0c0c0]'
            };
        }
        if (windowChrome === 'linux') {
            // Ubuntu: the aubergine terminal and its bash prompt, green user@host then blue path.
            return {
                shell: 'bg-[#300a24]',
                prompt: 'text-[#d3d7cf]',
                host: 'yawamf@feeder',
                sigil: ':~$',
                output: 'text-[#eeeeec]'
            };
        }
        return {
            shell: 'bg-slate-950',
            prompt: 'text-slate-500',
            host: null,
            sigil: '$',
            output: 'text-emerald-300'
        };
    });

</script>

<details
    {...attributes}
    data-record-technical-details
    class="group order-last rounded-lg border border-slate-300 dark:border-slate-700/70 {terminalTheme.shell}"
>
    <summary
        class="flex min-h-11 flex-wrap cursor-pointer list-none items-center gap-1.5 rounded-[7px] px-3 py-1.5 marker:hidden focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-brand-400 group-open:rounded-b-none group-open:border-b group-open:border-slate-800 {windowChrome ===
        'windows'
            ? 'bg-[#000080]'
            : 'bg-slate-900/80'}"
    >
        {#if windowChrome === 'mac'}
            <span class="h-2 w-2 rounded-full bg-rose-500/70" aria-hidden="true"></span>
            <span class="h-2 w-2 rounded-full bg-amber-500/70" aria-hidden="true"></span>
            <span class="h-2 w-2 rounded-full bg-emerald-500/70" aria-hidden="true"></span>
            <span class="ml-1.5 font-mono text-xs text-slate-400">{title}</span>
        {:else if windowChrome === 'windows'}
            <!-- Deliberate Windows 95 pastiche, so the raised bevel and the period
                 greys are literal values rather than palette tokens. -->
            <span class="font-mono text-xs font-bold text-white">{title}</span>
            <span class="ml-auto flex items-center gap-0.5" aria-hidden="true">
                {#each ['minimise', 'maximise', 'close'] as control (control)}
                    <span
                        class="grid h-3.5 w-4 place-items-center border border-l-white border-t-white border-r-[#404040] border-b-[#404040] bg-[#c0c0c0] text-black"
                    >
                        {#if control === 'minimise'}
                            <svg class="h-2 w-2" viewBox="0 0 10 10" stroke="currentColor" stroke-width="1.4"><path d="M2 8h6" /></svg>
                        {:else if control === 'maximise'}
                            <svg class="h-2 w-2" viewBox="0 0 10 10" fill="none" stroke="currentColor" stroke-width="1.2"><rect x="1.6" y="1.6" width="6.8" height="6.8" /><path d="M1.6 3.2h6.8" /></svg>
                        {:else}
                            <svg class="h-2 w-2" viewBox="0 0 10 10" stroke="currentColor" stroke-width="1.4"><path d="m2 2 6 6M8 2l-6 6" /></svg>
                        {/if}
                    </span>
                {/each}
            </span>
        {:else}
            <span class="font-mono text-xs text-slate-400">{title}</span>
            <span class="ml-auto grid h-4 w-4 place-items-center rounded-full bg-slate-700/70 text-slate-300" aria-hidden="true">
                <svg class="h-2 w-2" viewBox="0 0 10 10" stroke="currentColor" stroke-width="1.4"><path d="m2 2 6 6M8 2l-6 6" /></svg>
            </span>
        {/if}
        <svg class="h-3.5 w-3.5 shrink-0 motion-safe:transition-transform group-open:rotate-180 {windowChrome === 'mac' ? 'ml-auto text-slate-500' : windowChrome === 'windows' ? 'ml-2.5 text-white/70' : 'ml-2.5 text-slate-500'}" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" aria-hidden="true">
            <path stroke-linecap="round" stroke-linejoin="round" d="m6 9 6 6 6-6" />
        </svg>
    </summary>
    <div class="px-3 py-2.5 font-mono text-xs leading-relaxed {terminalTheme.output}">
        <p class={terminalTheme.prompt}>
            {#if terminalTheme.host}<span class="font-bold text-[#8ae234]" aria-hidden="true">{terminalTheme.host}</span>{/if}<span
                aria-hidden="true">{terminalTheme.sigil}</span>
            {command}
        </p>
        <p class="mt-1 break-all {terminalTheme.output}">
            {identifier}<span class="terminal-caret" aria-hidden="true">&#9608;</span>
        </p>
        {#if children}{@render children()}{/if}
    </div>
</details>

<style>
    /* Svelte scopes @keyframes, so a name referenced from a class resolves to nothing without
       the -global- prefix. */
    @keyframes -global-terminal-blink {
        0%, 49% { opacity: 1; }
        50%, 100% { opacity: 0; }
    }

    .terminal-caret {
        margin-left: 0.15em;
        animation: terminal-blink 1.1s steps(1) infinite;
    }

    @media (prefers-reduced-motion: reduce) {
        .terminal-caret { animation: none; opacity: 1; }
    }

</style>
