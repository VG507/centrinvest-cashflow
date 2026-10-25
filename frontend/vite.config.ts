import { defineConfig, loadEnv } from 'vite';
import react from '@vitejs/plugin-react';
import tailwindcss from '@tailwindcss/vite';

export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), '');
  const proxyTarget = env.API_PROXY_TARGET || (env.VITE_API_USE_PROXY === 'true' ? env.VITE_API_BASE_URL : '');
  const proxy = proxyTarget
    ? Object.fromEntries(['/api', '/health'].map(route => [route, { target: proxyTarget, changeOrigin: true }]))
    : undefined;
  return { plugins: [react(), tailwindcss()], server: { proxy, fs: { allow: ['..'] } } };
});
