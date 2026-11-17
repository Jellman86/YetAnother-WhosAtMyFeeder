import { defineConfig, devices } from '@playwright/test';

// The production bundle, built by `npm run build` and served from `dist` by `vite preview`, with
// the API answered by the browser fixtures. The main suite runs on the dev server, which does not
// split code, so a start-up failure in the built chunks (a load cycle, a missing chunk) only shows
// here. Run `npm run build` first.
// Typed locally: the UI has no Node type package, and this is the only environment read.
const environment = (globalThis as { process?: { env: Record<string, string | undefined> } }).process?.env ?? {};
const port = Number(environment.PLAYWRIGHT_PRODUCTION_PORT ?? 4179);

export default defineConfig({
    testDir: './browser-tests/production',
    forbidOnly: true,
    retries: 0,
    workers: 1,
    timeout: 60_000,
    reporter: 'list',
    outputDir: './playwright-results/production',
    use: {
        baseURL: `http://127.0.0.1:${port}`,
        locale: 'en-GB',
        timezoneId: 'Europe/London',
        trace: 'retain-on-failure',
        screenshot: 'only-on-failure',
        serviceWorkers: 'block'
    },
    projects: [{ name: 'chromium', use: { ...devices['Desktop Chrome'] } }],
    webServer: {
        command: `npx vite preview --host 127.0.0.1 --port ${port} --strictPort`,
        url: `http://127.0.0.1:${port}/`,
        reuseExistingServer: false,
        timeout: 60_000
    }
});
