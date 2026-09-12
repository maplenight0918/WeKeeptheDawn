import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';
import { resolve } from 'node:path';

export default defineConfig({
  plugins: [react()],
  server: { port: 5173, strictPort: true, fs: { allow: [resolve(__dirname, '..')] } },
  build: { chunkSizeWarningLimit: 1200 },
});
