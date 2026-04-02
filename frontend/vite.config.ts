import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
  build: {
    rollupOptions: {
      onwarn(warning, warn) {
        if (warning.code === 'SOURCEMAP_ERROR') return
        warn(warning)
      },
    },
  },
  server: {
    proxy: {
      '/ws': {
        target: 'ws://localhost:8000',
        ws: true,
        configure: (proxy) => {
          proxy.on('error', (err) => {
            if ((err as NodeJS.ErrnoException).code === 'EPIPE') return
            console.error('[ws proxy error]', err.message)
          })
        },
      },
    },
  },
})
