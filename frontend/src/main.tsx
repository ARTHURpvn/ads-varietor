import { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { App } from './App.tsx';
import { LimiteDeErro } from './components/LimiteDeErro.tsx';
import './index.css';

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      refetchOnWindowFocus: true,
      staleTime: 0,
      retry: 1,
    },
    mutations: {
      retry: 0,
    },
  },
});

const elementoRaiz = document.getElementById('root');

if (elementoRaiz === null) {
  throw new Error('Elemento raiz da aplicação não encontrado.');
}

createRoot(elementoRaiz).render(
  <StrictMode>
    <LimiteDeErro>
      <QueryClientProvider client={queryClient}>
        <App />
      </QueryClientProvider>
    </LimiteDeErro>
  </StrictMode>,
);
