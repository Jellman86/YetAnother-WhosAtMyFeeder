import { defineConfig, devices } from '@playwright/test';

// CI gates Chromium fixtures; the wider desktop/mobile matrix is available locally.
// PLAYWRIGHT_PORT lets a second checkout run its fixtures beside another one's server.
// Typed locally: the UI has no Node type package, and this is the only environment read.
const environment = (globalThis as { process?: { env: Record<string, string | undefined> } }).process?.env ?? {};
const port = Number(environment.PLAYWRIGHT_PORT ?? 4178);

export default defineConfig({
    testDir: './browser-tests',
    fullyParallel: true,
    forbidOnly: true,
    retries: 0,
    workers: 2,
    timeout: 30_000,
    reporter: 'list',
    outputDir: './playwright-results',
    use: {
        baseURL: `http://127.0.0.1:${port}`,
        locale: 'en-GB',
        timezoneId: 'Europe/London',
        trace: 'retain-on-failure',
        screenshot: 'only-on-failure',
        serviceWorkers: 'block'
    },
    projects: [
        { name: 'chromium', use: { ...devices['Desktop Chrome'] } },
        { name: 'webkit', use: { ...devices['Desktop Safari'] } },
        { name: 'mobile-chromium', use: { ...devices['Pixel 7'] } },
        { name: 'mobile-webkit', use: { ...devices['iPhone 13'] } }
    ],
    webServer: {
        command: `npm run dev -- --host 127.0.0.1 --port ${port} --strictPort`,
        url: `http://127.0.0.1:${port}/browser-tests/fixture.html`,
        reuseExistingServer: false,
        timeout: 60_000
    }
});
