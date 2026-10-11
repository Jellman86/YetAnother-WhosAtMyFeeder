import { beforeEach, expect, it, vi } from 'vitest';
const fetchAuthStatus = vi.hoisted(() => vi.fn());
vi.mock('../api', () => ({
    fetchAuthStatus, getAuthToken: () => null,
    createSessionCookie: vi.fn(), login: vi.fn(), logout: vi.fn(), setAuthToken: vi.fn(), setInitialPassword: vi.fn()
}));
import { authStore } from './auth.svelte';

beforeEach(() => { fetchAuthStatus.mockReset(); authStore.statusLoading = false; });
it.each([[1, 1], [30, 30], [100, 100], [undefined, 30], [0, 30], [101, 30], ['30', 30]])('loads the public pacing cap %s as %s', async (value, expected) => {
    fetchAuthStatus.mockResolvedValue({ auth_required: true, public_access_enabled: true, is_authenticated: false, public_access_rate_limit_per_minute: value });
    await authStore.loadStatus();
    expect(authStore.publicAccessRateLimitPerMinute).toBe(expected);
    expect(authStore.statusHealthy).toBe(true);
});
