import { defineConfig } from 'vite';

export default defineConfig({
  server: {
    port: 5173,
    proxy: {
      '/api/knowledge': { target: 'http://127.0.0.1:8001', rewrite: p => p.replace('/api/knowledge', ''), timeout: 3600000 },
      '/api/search': { target: 'http://127.0.0.1:8002', rewrite: p => p.replace('/api/search', ''), timeout: 3600000 },
    },
  },
});
