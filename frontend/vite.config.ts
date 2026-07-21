import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';
import tailwindcss from '@tailwindcss/vite';

/**
 * O frontend nunca embute credencial. Em desenvolvimento o proxy abaixo
 * repassa /api para a API local, mantendo mesma origem (sem CORS).
 * Em produção um reverse proxy faz o mesmo papel e injeta o header
 * X-API-Key antes de chegar ao backend.
 */
/**
 * A chave vem do ambiente do processo Node (sem o prefixo VITE_), então
 * ela nunca é embutida no bundle nem chega ao navegador — só o proxy a vê.
 */
const developmentApiKey = process.env.DEV_API_KEY ?? '';

export default defineConfig({
  plugins: [react(), tailwindcss()],
  server: {
    proxy: {
      '/api': {
        target: 'http://127.0.0.1:8000',
        changeOrigin: true,
        configure: (proxy) => {
          proxy.on('proxyReq', (proxyRequest) => {
            if (developmentApiKey) {
              proxyRequest.setHeader('X-API-Key', developmentApiKey);
            }
          });
        },
      },
    },
  },
});
