/**
 * One rule for what a build calls itself, shared by the bundle (vite.config.ts) and the
 * deploy-recovery check. The backend applies the same rule in `backend/app/version.py`, and a
 * contract test keeps the two channel lists identical.
 */

/** Channels whose builds are the release itself; their label never appears in the version. */
export const RELEASE_LIKE_CHANNELS = ['main', 'stable', 'unknown'] as const;

const TAG_NAME = /^v\d+\.\d+\.\d+(?:\.\d+)?$/;

export function isReleaseLikeChannel(branch: string): boolean {
    const name = branch.trim();
    return name === '' || (RELEASE_LIKE_CHANNELS as readonly string[]).includes(name) || TAG_NAME.test(name);
}

/**
 * The branch whose changelog and docs a build should link to. A release-like build (`stable`,
 * `main`, a tag, or no label at all) reads `main`; a working channel reads its own branch. The
 * footer once linked every build, releases included, to the dev changelog (#437).
 */
export function docsRefForBranch(branch: string): string {
    return isReleaseLikeChannel(branch) ? 'main' : branch.trim();
}

/** `base-branch+hash`, with the branch omitted for release-like channels. */
export function composeAppVersion(base: string, branch: string, hash: string): string {
    return isReleaseLikeChannel(branch) ? `${base}+${hash}` : `${base}-${branch}+${hash}`;
}

/**
 * What two builds share when only their channel label differs. A stable bundle stamped
 * `2.19.4-stable+abc` and a backend reporting `2.19.4+abc` are the same deployment; a dev
 * bundle against a release backend is not, and keeps its `-dev`.
 */
export function deploymentIdentity(version: string): string {
    const core = version.split('+')[0]?.trim() ?? '';
    const dash = core.indexOf('-');
    if (dash < 0) return core;
    const label = core.slice(dash + 1);
    return isReleaseLikeChannel(label) ? core.slice(0, dash) : core;
}
