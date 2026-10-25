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

test('phones on the LAN call the page origin while Vite dev keeps the separate service', async () => {
  const source = await readFile(new URL('../src/services/api.ts', import.meta.url), 'utf8');
  const js = ts.transpileModule(source, { compilerOptions: { target: ts.ScriptTarget.ES2022, module: ts.ModuleKind.ES2022 } }).outputText;
  const load = async (location, tag) => {
    globalThis.window = { location };
    try { return await import(`data:text/javascript;base64,${Buffer.from(js + `\n// ${tag}`).toString('base64')}`); }
    finally { delete globalThis.window; }
  };
  const phone = await load({ hostname: '192.168.15.113', port: '8443', origin: 'https://192.168.15.113:8443', protocol: 'https:' }, 'phone');
  assert.equal(phone.API_BASE, 'https://192.168.15.113:8443/api');
  assert.equal(phone.ON_THIS_COMPUTER, false);
  assert.equal(phone.AUTHORITY_URL, 'https://192.168.15.113:8443/api/acesso-rede/ca.crt');
  const packaged = await load({ hostname: '127.0.0.1', port: '53117', origin: 'http://127.0.0.1:53117', protocol: 'http:' }, 'packaged');
  assert.equal(packaged.API_BASE, 'http://127.0.0.1:53117/api');
  assert.equal(packaged.ON_THIS_COMPUTER, true);
  const dev = await load({ hostname: '127.0.0.1', port: '1420', origin: 'http://127.0.0.1:1420', protocol: 'http:' }, 'dev');
  assert.equal(dev.API_BASE, 'http://127.0.0.1:8765/api');
});
