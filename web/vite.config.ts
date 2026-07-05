import { defineConfig } from 'vite'
import { resolve } from 'path'

export default defineConfig({
  build: {
    outDir: resolve(__dirname, '../src/mops/static'),
    emptyOutDir: true,
    rolldownOptions: {
      input: resolve(__dirname, 'index.html'),
      output: {
        entryFileNames: 'dashboard.js',
        assetFileNames: 'dashboard.[ext]',
      },
    },
    target: 'es2022',
    minify: 'esbuild',
    cssCodeSplit: false,
    chunkSizeWarningLimit: 1500,
  },
  server: {
    proxy: {
      '/api': 'http://127.0.0.1:10082',
    },
  },
})
