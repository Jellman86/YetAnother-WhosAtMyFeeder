export type DeployRecoveryAction = 'ignore' | 'reload' | 'warn';

interface StorageLike {
    getItem(key: string): string | null;
    setItem(key: string, value: string): void;
    removeItem(key: string): void;
}

interface DeployRecoveryOptions {
    appVersion: string;
    storage?: StorageLike | null;
    reload: () => void;
    warn: (message: string) => void;
    warningMessage?: string;
}

interface HealthLike {
    version?: string;
    startup_instance_id?: string;
}

const RECOVERY_ATTEMPT_KEY = 'yawamf_deploy_recovery_attempt_v1';
const STALE_BUNDLE_PATTERNS = [
    'failed to fetch dynamically imported module',
    'error loading dynamically imported module',
    'importing a module script failed',
    'chunkloaderror',
    'loading chunk'
];

function normalizeString(value: unknown): string {
    return typeof value === 'string' ? value.trim() : '';
}

function collectErrorText(input: unknown): string {
    if (!input) return '';
    if (typeof input === 'string') return input;
    if (input instanceof Error) return `${input.name} ${input.message}`.trim();
    if (typeof input !== 'object') return '';

    const value = input as Record<string, unknown>;
    return [
        normalizeString(value.name),
        normalizeString(value.message),
        collectErrorText(value.error),
        collectErrorText(value.reason)
    ]
        .filter((part) => part.length > 0)
        .join(' ')
        .trim();
}

export function isLikelyStaleBundleError(input: unknown): boolean {
    const text = collectErrorText(input).toLowerCase();
    if (!text) return false;
    return STALE_BUNDLE_PATTERNS.some((pattern) => text.includes(pattern));
}

export function createDeployRecovery(options: DeployRecoveryOptions) {
    const appVersion = normalizeString(options.appVersion);
    const storage = options.storage ?? null;
    const warningMessage = normalizeString(options.warningMessage) || 'The app was updated while this tab was open. Refresh the page.';
    const attemptSignature = appVersion ? `stale:${appVersion}` : '';

    function getStoredAttempt(): string {
        if (!storage) return '';
        return normalizeString(storage.getItem(RECOVERY_ATTEMPT_KEY));
    }

    function setStoredAttempt(value: string) {
        if (!storage) return;
        if (!value) {
            storage.removeItem(RECOVERY_ATTEMPT_KEY);
            return;
        }
        storage.setItem(RECOVERY_ATTEMPT_KEY, value);
    }

    function triggerRecovery(): DeployRecoveryAction {
        if (!attemptSignature) return 'ignore';
        if (getStoredAttempt() === attemptSignature) {
            options.warn(warningMessage);
            return 'warn';
        }
        setStoredAttempt(attemptSignature);
        options.reload();
        return 'reload';
    }

    return {
        handleRuntimeFailure(error: unknown): DeployRecoveryAction {
            if (!isLikelyStaleBundleError(error)) return 'ignore';
            return triggerRecovery();
        },

        observeHealth(health: HealthLike | null | undefined): DeployRecoveryAction {
            const backendVersion = normalizeString(health?.version);
            if (!appVersion || !backendVersion || backendVersion === 'unknown') return 'ignore';
            if (backendVersion === appVersion) {
                if (getStoredAttempt() === attemptSignature) {
                    setStoredAttempt('');
                }
                return 'ignore';
            }
            return triggerRecovery();
        }
    };
}
