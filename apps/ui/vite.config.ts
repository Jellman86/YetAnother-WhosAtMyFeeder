import { defineConfig } from 'vite'
import { svelte } from '@sveltejs/vite-plugin-svelte'
import { execSync } from 'child_process'

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

const gitHash = getGitHash();
const appVersion = `2.0.0+${gitHash}`;

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
                target: 'http://backend:8000',
                changeOrigin: true,
            }
        }
    }
})
