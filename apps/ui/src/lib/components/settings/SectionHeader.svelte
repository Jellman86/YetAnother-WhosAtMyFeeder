<script lang="ts">
    interface Props {
        icon: string;
        title: string;
        description?: string;
    }

    let { icon, title, description }: Props = $props();
</script>

<div class="flex items-start gap-3 mb-6">
    <div class="flex items-center justify-center w-10 h-10 rounded-xl
                bg-gradient-to-br from-teal-500/20 to-emerald-500/20
                dark:from-teal-500/10 dark:to-emerald-500/10
                text-xl flex-shrink-0">
        {icon}
    </div>
    <div class="min-w-0">
        <h3 class="text-lg font-semibold text-slate-900 dark:text-white">
            {title}
        </h3>
        {#if description}
            <p class="text-sm text-slate-500 dark:text-slate-400 mt-0.5">
                {description}
            </p>
        {/if}
    </div>
</div>
