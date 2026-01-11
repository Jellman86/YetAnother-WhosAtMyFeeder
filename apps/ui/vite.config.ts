import { defineConfig } from 'vite'
import { svelte } from '@sveltejs/vite-plugin-svelte'
import { execSync } from 'child_process'
import { readFileSync } from 'fs'
import { join } from 'path'

// Get base version from VERSION file
function getBaseVersion(): string {
    // Check environment variable first
    if (process.env.APP_VERSION_BASE) {
        return process.env.APP_VERSION_BASE;
    }
    try {
        const versionFile = join(__dirname, '..', '..', 'VERSION');
        return readFileSync(versionFile, 'utf-8').trim();
    } catch {
        return '2.2.0'; // Fallback
    }
}

// Get git hash for version tracking
function getGitHash(): string {
    // Check environment variable first (set during Docker build)
    if (process.env.GIT_HASH) {
        return process.env.GIT_HASH;
    }
    // Try to get from git command
    try {
        return execSync('git rev-parse --short HEAD').toString().trim();
    } catch {
        return 'unknown';
    }
}

const baseVersion = getBaseVersion();
const gitHash = getGitHash();
const appVersion = `${baseVersion}+${gitHash}`;

// https://vitejs.dev/config/
export default defineConfig({
    plugins: [svelte()],
    define: {
        __APP_VERSION__: JSON.stringify(appVersion),
        __GIT_HASH__: JSON.stringify(gitHash),
    },
    server: {
        host: true,
        port: 3000,
        proxy: {
            '/api': {
                target: 'http://yawamf-backend:8000',
                changeOrigin: true,
            }
        }
    }
})
