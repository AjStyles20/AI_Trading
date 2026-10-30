/// <reference types="vitest" />
import { defineConfig } from 'vitest/config'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'

// https://vite.dev/config/
export default defineConfig({
  base: './',
  plugins: [react(), tailwindcss()],
  test: {
    globals: true,
    environment: 'jsdom',
    // Rendering the large panels can take several seconds on slower PCs. The
    // default 5s made unrelated tests fail at random there; assertions still fail at once.
    testTimeout: 30_000,
    globalSetup: ['./vitest.global-setup.js'],
    setupFiles: ['./src/setupTests.ts']
  }
})
