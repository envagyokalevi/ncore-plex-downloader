import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// A frontend build a backend image-ébe kerül, és a FastAPI szolgálja ki.
// Fejlesztéskor (npm run dev) az /api hívások a backendhez proxyzódnak.
export default defineConfig({
  plugins: [react()],
  server: {
    host: true,
    port: 5173,
    proxy: {
      '/api': {
        target: process.env.VITE_API_TARGET ?? 'http://localhost:8000',
        changeOrigin: false,
      },
    },
  },
  build: {
    outDir: 'dist',
    sourcemap: false,
  },
})
