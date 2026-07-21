import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';
import tailwindcss from '@tailwindcss/vite';
import type { ClientRequest } from 'node:http';

/**
 * O frontend nunca embute credencial. Em desenvolvimento o proxy abaixo
 * repassa /api para a API local, mantendo a mesma origem (sem CORS) e
 * injetando a chave — o mesmo papel que o reverse proxy cumpre em produção.
 *
 * A chave vem do ambiente do processo Node, sem o prefixo VITE_, então nunca
 * é embutida no bundle nem chega ao navegador: só o proxy a enxerga.
 */
const developmentApiKey = process.env['DEV_API_KEY'] ?? '';

export default defineConfig({
  plugins: [react(), tailwindcss()],
  server: {
    proxy: {
      '/api': {
        target: 'http://127.0.0.1:8000',
        changeOrigin: true,
        configure: (proxy: { on: (evento: string, ouvinte: (requisicao: ClientRequest) => void) => void }) => {
          proxy.on('proxyReq', (requisicao: ClientRequest) => {
            if (developmentApiKey) {
              requisicao.setHeader('X-API-Key', developmentApiKey);
            }
          });
        },
      },
    },
  },
});
