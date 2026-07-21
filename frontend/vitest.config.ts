import { defineConfig } from 'vitest/config';

/**
 * Config isolada do Vitest — deliberadamente separada de vite.config.ts
 * para não tocar no build nem no proxy de desenvolvimento. Os testes aqui
 * cobrem só funções puras (lib/ e api/), então não precisam de plugins,
 * DOM completo nem transform de JSX.
 */
export default defineConfig({
  test: {
    environment: 'node',
    include: ['src/**/*.test.ts'],
    globals: false,
  },
});
