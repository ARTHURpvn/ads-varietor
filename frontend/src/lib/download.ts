/** Dispara o download de um Blob no navegador, com nome de arquivo. */
export function salvarBlobComoArquivo(blob: Blob, nomeArquivo: string): void {
  const url = URL.createObjectURL(blob);
  const link = document.createElement('a');

  link.href = url;
  link.download = nomeArquivo;
  link.rel = 'noopener';
  document.body.appendChild(link);
  link.click();
  document.body.removeChild(link);

  // Revoga depois do clique para não invalidar o download em andamento.
  window.setTimeout(() => URL.revokeObjectURL(url), 10_000);
}

/** Remove caracteres problemáticos em nome de arquivo. */
export function nomeSeguro(valor: string): string {
  return valor.replace(/[^a-zA-Z0-9-_]/g, '_').slice(0, 60);
}
