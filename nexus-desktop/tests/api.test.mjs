import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import ts from 'typescript';

test('library query omits absent collection but preserves false and pagination', async () => {
  globalThis.window = { location: { hostname: '127.0.0.1', port: '1420', origin: 'http://127.0.0.1:1420' } };
  const source = await readFile(new URL('../src/services/api.ts', import.meta.url), 'utf8');
  const js = ts.transpileModule(source, { compilerOptions: { target: ts.ScriptTarget.ES2022, module: ts.ModuleKind.ES2022 } }).outputText;
  const { NexusApi } = await import(`data:text/javascript;base64,${Buffer.from(js).toString('base64')}`);
  const originalFetch = globalThis.fetch;
  let url;
  globalThis.fetch = async input => { url = new URL(input); return Response.json({ itens: [], total: 0 }); };
  try {
    await new NexusApi().games({ colecao_id: undefined, favorito: false, pagina: 1, busca: 'ação' });
    assert.equal(url.searchParams.has('colecao_id'), false);
    assert.equal(url.searchParams.get('favorito'), 'false');
    assert.equal(url.searchParams.get('pagina'), '1');
    assert.equal(url.searchParams.get('busca'), 'ação');
  } finally { globalThis.fetch = originalFetch; delete globalThis.window; }
});
