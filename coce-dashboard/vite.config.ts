import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5174,
    strictPort: false,
    proxy: {
      '/api/coce': {
        target: process.env.VITE_COCE_API_URL || 'http://localhost:9000',
        changeOrigin: true,
      },
    },
  },
});
