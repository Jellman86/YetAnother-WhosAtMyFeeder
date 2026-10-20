<script lang="ts">
    import { onMount, onDestroy } from 'svelte';
    import { _ } from 'svelte-i18n';
    import DiagnosticDialog from '../DiagnosticDialog.svelte';
    import SettingsCard from './_primitives/SettingsCard.svelte';
    import { fetchNativeProfileRevalidation, prepareNativeProfileRevalidation, uploadNativeProfileInputs, cancelNativeProfileRevalidation, type RevalidationView, type RevalidationStatus } from '../../api/native-profile';
    import type { DiagnosticStage, DiagnosticResult } from '../../utils/diagnostic-runner';

    let view = $state.raw<RevalidationView | null>(null);
    let photos = $state<File[]>([]);
    let clip = $state<File | null>(null);
    let acknowledged = $state(false);
    let error = $state('');
    let dialog = $state(false);
    let submitting = $state(false);
    let stopping = $state(false);
    let knownAttempt = $state<string | null>(null);
    let generation = 0;
    let timer: ReturnType<typeof setTimeout> | undefined;
    let disposed = false;
    const attempt = $derived(view?.attempt);
    const active = $derived(['uploading', 'checking', 'running', 'restoring'].includes(attempt?.state ?? '') || submitting || stopping);
    const validInputs = $derived(photos.length === 3 && photos.every(photo => photo.size > 0 && photo.size <= 25 * 1024 ** 2) && clip !== null && clip.size > 0 && clip.size <= 32 * 1024 ** 2);
    const stages: DiagnosticStage[] = $derived([{
        id: 'representative-profile', label: $_('settings.native_revalidation.title'),
        state: active ? 'running' : attempt?.state === 'succeeded' ? 'passed' : attempt?.state === 'cancelled' || attempt?.state === 'superseded' ? 'warning' : 'failed',
        message: error || attempt?.message || ''
    }]);
    const result: DiagnosticResult | null = $derived(active ? null : { ok: attempt?.state === 'succeeded', message: error || attempt?.message || '' });

    function applyAttempt(status: RevalidationStatus): void {
        if (view) view = { ...view, attempt: status };
        knownAttempt = status.attempt_id ?? knownAttempt;
    }

    async function refresh(epoch = generation): Promise<void> {
        try {
            const next = await fetchNativeProfileRevalidation();
            if (disposed || epoch !== generation) return;
            if (view?.profile?.fingerprint !== next.profile?.fingerprint) acknowledged = false;
            view = next;
            knownAttempt = next.attempt?.attempt_id ?? null;
            error = '';
        } catch (cause) {
            if (disposed || epoch !== generation) return;
            error = cause instanceof Error ? cause.message : $_('common.error');
        }
        if (!disposed && epoch === generation && ['uploading', 'checking', 'running', 'restoring'].includes(view?.attempt?.state ?? '')) {
            clearTimeout(timer);
            timer = setTimeout(() => void refresh(epoch), 2000);
        }
    }

    async function run(): Promise<void> {
        if (!view?.profile?.eligible || !validInputs || !acknowledged || !clip || active) return;
        const fingerprint = view.profile.fingerprint;
        const epoch = ++generation;
        const id = crypto.randomUUID();
        knownAttempt = id;
        clearTimeout(timer);
        error = '';
        submitting = true;
        dialog = true;
        try {
            const prepared = await prepareNativeProfileRevalidation(fingerprint, id);
            if (epoch !== generation || disposed) return;
            applyAttempt(prepared);
            if (prepared.state !== 'uploading') throw new Error(prepared.message ?? '');
            const status = await uploadNativeProfileInputs(id, photos, clip);
            if (epoch !== generation || disposed) return;
            applyAttempt(status);
            photos = [];
            clip = null;
            acknowledged = false;
        } catch (cause) {
            if (epoch !== generation || disposed) return;
            error = cause instanceof Error ? cause.message : $_('common.error');
            try {
                applyAttempt(await cancelNativeProfileRevalidation(id));
            } catch {
                // Preserve the known attempt for explicit status/cancel recovery.
            }
        } finally {
            if (epoch === generation && !disposed) {
                submitting = false;
                if (!error) await refresh(epoch);
            }
        }
    }

    async function cancel(): Promise<void> {
        if (!knownAttempt || stopping) return;
        ++generation;
        clearTimeout(timer);
        submitting = false;
        stopping = true;
        error = '';
        try {
            applyAttempt(await cancelNativeProfileRevalidation(knownAttempt));
        } catch (cause) {
            error = cause instanceof Error ? cause.message : $_('common.error');
        } finally {
            stopping = false;
        }
    }

    onMount(() => { void refresh(); });
    onDestroy(() => { disposed = true; generation++; clearTimeout(timer); });
</script>

{#if error || view?.profile?.blocked || (attempt?.state && attempt.state !== 'idle')}
<SettingsCard title={$_('settings.native_revalidation.title')} description={$_('settings.native_revalidation.description')}>
    <div class="space-y-4" data-native-profile-revalidation>
        {#if error}<p role="alert" class="text-sm text-red-700 dark:text-red-300">{error}</p>{/if}
        <p class="text-sm text-muted">{view?.profile?.reason ?? attempt?.message ?? $_('common.loading')}</p>
        {#if view?.profile?.blocked}
            <p class="text-sm font-medium">{view.profile.model_id} · {view.profile.provider}</p>
            <label class="block space-y-1 text-sm">
                <span>{$_('settings.native_revalidation.photos')}</span>
                <input class="input-base w-full" type="file" accept="image/*" multiple disabled={active}
                    onchange={(event) => { photos = Array.from(event.currentTarget.files ?? []); }} />
            </label>
            <label class="block space-y-1 text-sm">
                <span>{$_('settings.native_revalidation.clip')}</span>
                <input class="input-base w-full" type="file" accept="video/*" disabled={active}
                    onchange={(event) => { clip = event.currentTarget.files?.[0] ?? null; }} />
            </label>
            <p class="text-xs text-muted">{$_('settings.native_revalidation.limits')}</p>
            <label class="flex items-start gap-2 text-sm">
                <input type="checkbox" class="mt-1" bind:checked={acknowledged} disabled={active} />
                <span>{$_('settings.native_revalidation.acknowledge')}</span>
            </label>
            <button type="button" class="btn btn-primary" disabled={!view.profile.eligible || !validInputs || !acknowledged || active} onclick={() => void run()}>{$_('settings.native_revalidation.run')}</button>
        {/if}
        {#if active || (attempt?.state && attempt.state !== 'idle')}
            <button type="button" class="btn btn-secondary" onclick={() => { dialog = true; }}>{$_('settings.native_revalidation.status')}</button>
        {/if}
        <button type="button" class="btn btn-ghost" disabled={submitting || stopping} onclick={() => void refresh()}>{$_('common.refresh', { default: 'Refresh' })}</button>
        <p class="text-xs text-muted">{$_('settings.native_revalidation.scope')}</p>
    </div>
</SettingsCard>
{/if}

{#if dialog}
    <DiagnosticDialog title={$_('settings.native_revalidation.title')} stages={stages} busy={active} {result}
        note={$_('settings.native_revalidation.scope')}
        closeLabel={active ? $_('settings.native_revalidation.cancel') : $_('common.close')}
        onClose={() => { if (active) void cancel(); else dialog = false; }} />
{/if}
