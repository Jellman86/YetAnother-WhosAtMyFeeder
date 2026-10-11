import type { BirdScanResponse } from '../api/media';

/** Bind an explicit scan to the retained pixels the owner is currently viewing. */
export function birdScanMediaVersion(imageUrl: string | null): string | null {
    if (!imageUrl) return null;
    try {
        const versions = new URL(imageUrl, 'http://localhost').searchParams.getAll('v');
        const version = versions[0];
        return versions.length === 1 && version && version.trim() && version.length <= 128 ? version : null;
    } catch {
        return null;
    }
}

export interface BirdScanView {
    response: BirdScanResponse | null;
    pending: boolean;
    readError: boolean;
    startUnconfirmed: boolean;
}
interface Options {
    eventId: string;
    candidateId: string;
    read: (signal: AbortSignal) => Promise<BirdScanResponse>;
    start: (force: boolean, signal: AbortSignal) => Promise<BirdScanResponse>;
    onChange: (view: BirdScanView) => void;
    onCompleted: () => void;
    isVisible: () => boolean;
}

interface BirdScanController {
    refresh: () => Promise<void>;
    start: (force?: boolean) => Promise<void>;
    visibilityChanged: () => Promise<void>;
    dispose: () => void;
}

/** One scene owns its requests and timer. Retiring it cannot update the next scene. */
export function createBirdScanController(options: Options): BirdScanController {
    let disposed = false;
    let submissionPending = false;
    let request: AbortController | null = null;
    let timer: ReturnType<typeof setTimeout> | null = null;
    let view: BirdScanView = { response: null, pending: false, readError: false, startUnconfirmed: false };
    const active = () => view.response?.status === 'queued' || view.response?.status === 'running';
    const emit = () => { if (!disposed) options.onChange({ ...view }); };
    function clearTimer(): void {
        if (timer !== null) clearTimeout(timer);
        timer = null;
    }
    function schedule(): void {
        clearTimer();
        if (disposed || !options.isVisible() || (!active() && !view.readError && view.response?.unavailable_reason !== 'scan_in_progress')) return;
        // A running scan is read every second so each step shows; waiting needs less.
        timer = setTimeout(() => { void refresh(); }, view.readError ? 10_000 : view.response?.status === 'running' ? 1_000 : 2_000);
    }
    async function run(force?: boolean): Promise<void> {
        if (disposed || request || (force === undefined && !options.isVisible())) return;
        clearTimer();
        request = new AbortController();
        if (force !== undefined) submissionPending = true;
        view = { ...view, pending: true, readError: false, startUnconfirmed: false };
        emit();
        try {
            const response = await (force === undefined ? options.read(request.signal) : options.start(force, request.signal));
            if (disposed) return;
            if (response.event_id !== options.eventId || response.candidate_id !== options.candidateId) {
                throw new Error('Scan response belongs to a different scene');
            }
            const completed = response.status === 'completed' && (active() || submissionPending);
            if (response.status !== 'queued' && response.status !== 'running') submissionPending = false;
            view = { response, pending: false, readError: false, startUnconfirmed: false };
            emit();
            if (completed) options.onCompleted();
        } catch {
            if (!disposed) view = { ...view, pending: false, readError: true, startUnconfirmed: force !== undefined };
        } finally {
            request = null;
            if (!disposed) {
                view = { ...view, pending: false };
                emit();
                schedule();
            }
        }
    }
    async function refresh(): Promise<void> { await run(); }
    return {
        refresh,
        async start(force = false): Promise<void> { await run(force); },
        async visibilityChanged(): Promise<void> {
            clearTimer();
            if (options.isVisible()) await refresh();
        },
        dispose(): void {
            disposed = true;
            clearTimer();
            request?.abort();
        }
    };
}
