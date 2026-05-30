import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
  server: {
    host: '127.0.0.1',  // match SPOTIFY_REDIRECT_URI and cookie domain
    port: 5173,
    strictPort: true,   // fail clearly if 5173 is busy instead of silently shifting ports
  },
})
