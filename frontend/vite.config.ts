import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react()],
  build: {
    // Windows on this machine intermittently refuses to remove dist/assets.
    // Keeping the directory avoids EPERM during startup/build verification.
    emptyOutDir: false,
  },
  server: {
    proxy: {
      '/api': {
        target: 'http://localhost:5000',
        changeOrigin: true,
      },
      '/slices': {
        target: 'http://localhost:5000',
        changeOrigin: true,
      },
      '/videos': {
        target: 'http://localhost:5000',
        changeOrigin: true,
      },
      '/thumbnails': {
        target: 'http://localhost:5000',
        changeOrigin: true,
      },
      '/socket.io': {
        target: 'http://localhost:5000',
        ws: true,
        changeOrigin: true,
      }
    }
  }
})
