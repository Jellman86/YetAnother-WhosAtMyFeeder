export type DeployRecoveryAction = 'ignore' | 'reload' | 'warn';
export type DeployRecoveryReason = 'runtime_failure' | 'version_mismatch';

export interface DeployRecoveryEvent {
    action: Exclude<DeployRecoveryAction, 'ignore'>;
    reason: DeployRecoveryReason;
    frontendVersion: string;
    backendVersion?: string;
}

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
    report?: (event: DeployRecoveryEvent) => void;
    warningMessage?: string;
}

interface HealthLike {
    version?: string;
    startup_instance_id?: string;
}

const RECOVERY_ATTEMPT_KEY = 'yawamf_deploy_recovery_attempt_v1';
const RECOVERY_COUNT_KEY = 'yawamf_deploy_recovery_count_v1';
const MAX_REMEMBERED_ATTEMPTS = 8;
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
    const warningMessage =
        normalizeString(options.warningMessage) ||
        'The app was updated while this tab was open. Refresh the page.';
    const hasUsableAppVersion = Boolean(appVersion && appVersion.toLowerCase() !== 'unknown');
    const attemptPrefix = hasUsableAppVersion ? `stale:${appVersion}` : '';
    const warnedSignatures = new Set<string>();
    const inMemoryAttempts = new Set<string>();
    let storageAvailable = storage !== null;
    let inMemoryRecoveryCount = 0;

    function readStorage(key: string): string {
        if (!storage || !storageAvailable) return '';
        try {
            return normalizeString(storage.getItem(key));
        } catch {
            storageAvailable = false;
            return '';
        }
    }

    function writeStorage(key: string, value: string): boolean {
        if (!storage || !storageAvailable) return false;
        try {
            storage.setItem(key, value);
            return true;
        } catch {
            storageAvailable = false;
            return false;
        }
    }

    function getStoredAttempts(): Set<string> {
        const attempts = new Set(inMemoryAttempts);
        const raw = readStorage(RECOVERY_ATTEMPT_KEY);
        if (!raw) return attempts;
        try {
            const parsed = JSON.parse(raw);
            if (Array.isArray(parsed)) {
                for (const value of parsed) {
                    const signature = normalizeString(value);
                    if (signature) attempts.add(signature);
                }
                return attempts;
            }
        } catch {
            // Older builds stored one plain signature. Preserve it during migration.
        }
        attempts.add(raw);
        return attempts;
    }

    function rememberAttempts(attempts: Set<string>): boolean {
        const bounded = [...attempts].slice(-MAX_REMEMBERED_ATTEMPTS);
        inMemoryAttempts.clear();
        for (const signature of bounded) inMemoryAttempts.add(signature);
        return writeStorage(RECOVERY_ATTEMPT_KEY, JSON.stringify(bounded));
    }

    function incrementRecoveryCount(): number {
        const storedCount = parseInt(readStorage(RECOVERY_COUNT_KEY) || '0', 10) || 0;
        inMemoryRecoveryCount = Math.max(inMemoryRecoveryCount, storedCount) + 1;
        writeStorage(RECOVERY_COUNT_KEY, String(inMemoryRecoveryCount));
        return inMemoryRecoveryCount;
    }

    function warnOnce(
        signature: string,
        reason: DeployRecoveryReason,
        backendVersion?: string
    ): DeployRecoveryAction {
        if (warnedSignatures.has(signature)) return 'warn';
        warnedSignatures.add(signature);
        incrementRecoveryCount();
        options.report?.({ action: 'warn', reason, frontendVersion: appVersion, backendVersion });
        options.warn(warningMessage);
        return 'warn';
    }

    function triggerRecovery(
        signature: string,
        reason: DeployRecoveryReason,
        backendVersion?: string
    ): DeployRecoveryAction {
        if (!attemptPrefix || !signature) return 'ignore';
        const attempts = getStoredAttempts();
        if (attempts.has(signature)) return warnOnce(signature, reason, backendVersion);

        attempts.add(signature);
        if (!rememberAttempts(attempts)) return warnOnce(signature, reason, backendVersion);

        incrementRecoveryCount();
        options.report?.({ action: 'reload', reason, frontendVersion: appVersion, backendVersion });
        options.reload();
        return 'reload';
    }

    return {
        handleRuntimeFailure(error: unknown): DeployRecoveryAction {
            if (!isLikelyStaleBundleError(error)) return 'ignore';
            return triggerRecovery(attemptPrefix ? `${attemptPrefix}:runtime` : '', 'runtime_failure');
        },

        observeHealth(health: HealthLike | null | undefined): DeployRecoveryAction {
            const backendVersion = normalizeString(health?.version);
            if (!attemptPrefix || !backendVersion || backendVersion === 'unknown') return 'ignore';
            if (isSameDeployment(appVersion, backendVersion)) return 'ignore';
            return triggerRecovery(
                `${attemptPrefix}:backend:${backendVersion.toLowerCase()}`,
                'version_mismatch',
                backendVersion
            );
        },

        /** Total deploy-recovery attempts since last counter reset (persisted in storage). */
        getRecoveryCount(): number {
            const storedCount = parseInt(readStorage(RECOVERY_COUNT_KEY) || '0', 10) || 0;
            return Math.max(inMemoryRecoveryCount, storedCount);
        }
    };
}
