import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// Build straight into docs/ — the folder serve.py serves (gitignored artifact).
// `npm run dev` proxies API + data to the local Python server.
export default defineConfig({
  plugins: [react()],
  build: {
    outDir: '../docs',
    emptyOutDir: true,
  },
  server: {
    proxy: {
      '/api': 'http://localhost:8000',
    },
  },
})
