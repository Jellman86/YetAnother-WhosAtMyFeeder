import { defineConfig, devices } from '@playwright/test';

// Deliberately local-only: no automatic CI matrix or paid browser service.
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
        baseURL: 'http://127.0.0.1:4178',
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
        command: 'npm run dev -- --host 127.0.0.1 --port 4178 --strictPort',
        url: 'http://127.0.0.1:4178/browser-tests/fixture.html',
        reuseExistingServer: false,
        timeout: 60_000
    }
});
