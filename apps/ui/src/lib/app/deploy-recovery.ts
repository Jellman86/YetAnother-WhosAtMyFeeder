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
const RECOVERY_COUNT_KEY = 'yawamf_deploy_recovery_count_v1';
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

function stripBuildMetadata(version: string): string {
    const plusIdx = version.indexOf('+');
    return plusIdx >= 0 ? version.slice(0, plusIdx) : version;
}

function getBuildMetadata(version: string): string {
    const plusIdx = version.indexOf('+');
    return plusIdx >= 0 ? version.slice(plusIdx + 1).trim().toLowerCase() : '';
}

function hasConcreteBuildMetadata(version: string): boolean {
    const metadata = getBuildMetadata(version);
    return metadata.length > 0 && metadata !== 'unknown';
}

/**
 * SemVer build metadata does not affect release precedence, but YA-WAMF's Git
 * suffix identifies the deployed frontend bundle. Two concrete, different
 * suffixes therefore mean an open tab is running stale code. Local/unknown
 * builds fall back to the SemVer identity to avoid reload loops in development.
 */
function isSameDeployment(appVersion: string, backendVersion: string): boolean {
    if (stripBuildMetadata(appVersion) !== stripBuildMetadata(backendVersion)) {
        return false;
    }
    if (hasConcreteBuildMetadata(appVersion) && hasConcreteBuildMetadata(backendVersion)) {
        return appVersion === backendVersion;
    }
    return true;
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

    function incrementRecoveryCount(): number {
        if (!storage) return 0;
        const raw = storage.getItem(RECOVERY_COUNT_KEY);
        const count = (parseInt(raw ?? '0', 10) || 0) + 1;
        storage.setItem(RECOVERY_COUNT_KEY, String(count));
        return count;
    }

    function triggerRecovery(): DeployRecoveryAction {
        if (!attemptSignature) return 'ignore';
        incrementRecoveryCount();
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
            if (isSameDeployment(appVersion, backendVersion)) {
                if (getStoredAttempt() === attemptSignature) {
                    setStoredAttempt('');
                }
                return 'ignore';
            }
            return triggerRecovery();
        },

        /** Total deploy-recovery attempts since last counter reset (persisted in storage). */
        getRecoveryCount(): number {
            if (!storage) return 0;
            return parseInt(storage.getItem(RECOVERY_COUNT_KEY) ?? '0', 10) || 0;
        }
    };
}
