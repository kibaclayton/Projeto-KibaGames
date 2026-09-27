import { test } from 'node:test';
import assert from 'node:assert/strict';
const model = await import('../src/features/library/model.ts').catch(() => ({}));

test('zero trophies never awards platinum and partial totals round correctly', () => {
  assert.equal(typeof model.trophies, 'function');
  assert.deepEqual(model.trophies(0, 0), { percent: 0, platinum: false, remaining: 0 });
  assert.deepEqual(model.trophies(1, 3), { percent: 33, platinum: false, remaining: 2 });
  assert.deepEqual(model.trophies(3, 3), { percent: 100, platinum: true, remaining: 0 });
});

test('editing a game preserves calendar entries and converts empty dates to null', () => {
  assert.equal(typeof model.gamePayload, 'function');
  const result = model.gamePayload({ nome: ' Alan Wake 2 ', plataforma: 'PS5', progresso: 50, data_inicio: '2026-09-07', data_termino: '', cronograma: { '2026-09-07': 'single' }, trofeus_obtidos: 2, trofeus_total: 4 });
  assert.equal(result.nome, 'Alan Wake 2');
  assert.equal(result.data_termino, null);
  assert.deepEqual(result.cronograma, { '2026-09-07': 'single' });
});

test('invalid trophies or dates prevent sending an update', () => {
  assert.equal(typeof model.gamePayload, 'function');
  assert.throws(() => model.gamePayload({ nome: 'Jogo', trofeus_obtidos: 2, trofeus_total: 1 }));
  assert.throws(() => model.gamePayload({ nome: 'Jogo', data_inicio: '2026-09-10', data_termino: '2026-09-07' }));
});
