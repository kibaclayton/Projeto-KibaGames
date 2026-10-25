import { test } from 'node:test';
import assert from 'node:assert/strict';
const covers = await import('../src/features/library/coverModel.ts').catch(() => ({}));

const candidate = (fonte, titulo) => ({ fonte, titulo, imagem: `https://x/${titulo}.jpg`, previa: `https://x/${titulo}-p.jpg`, origem: 'https://x' });

test('titles are compared without accents, punctuation or article suffixes', () => {
  assert.equal(typeof covers.normalizeTitle, 'function');
  assert.equal(covers.normalizeTitle('Alan Wake (jogo eletrônico)'), 'alan wake');
  assert.equal(covers.normalizeTitle('God of War: Ragnarök'), 'god of war ragnarok');
  assert.equal(covers.normalizeTitle('  HOLLOW   Knight!!'), 'hollow knight');
});

test('the exact title wins, Steam breaks ties, and unrelated results sink to the bottom', () => {
  const items = [candidate('wikipedia', 'Batman: Arkham Knight'), candidate('wikipedia', 'Hollow Knight (jogo eletrônico)'), candidate('steam', 'Hollow Knight: Silksong'), candidate('steam', 'Hollow Knight')];
  const ranked = covers.rankCandidates('Hollow Knight', items).map(item => `${item.fonte}:${item.titulo}`);
  assert.deepEqual(ranked, ['steam:Hollow Knight', 'wikipedia:Hollow Knight (jogo eletrônico)', 'steam:Hollow Knight: Silksong', 'wikipedia:Batman: Arkham Knight']);
});

test('without a query the source order is kept, Steam first', () => {
  const items = [candidate('wikipedia', 'A'), candidate('steam', 'B'), candidate('wikipedia', 'C')];
  assert.deepEqual(covers.rankCandidates('', items).map(item => item.titulo), ['B', 'A', 'C']);
});

test('candidates are identified by source and id, and platform lines stay short', () => {
  assert.equal(covers.candidateKey({ fonte: 'wikipedia', id: 'Q29300592' }), 'wikipedia:Q29300592');
  assert.equal(covers.platformSummary(['Microsoft Windows', 'PlayStation 5', 'Xbox Series X e Series S', 'Nintendo Switch', 'macOS']), 'PC, PS5, Xbox Series +2');
  assert.equal(covers.platformSummary(['Nintendo Switch 2']), 'Switch 2');
  assert.equal(covers.platformSummary([]), '');
});

const details = (over = {}) => ({ fonte: 'steam', id: '367520', titulo: 'Hollow Knight', imagem: null, origem: 'https://store.steampowered.com/app/367520/', data_lancamento: '2017-02-24', ano: 2017,
  plataformas: ['Windows'], plataformas_nexus: ['PC'], generos: ['Ação', 'Aventura'], genero: 'Ação', desenvolvedores: ['Team Cherry'], publicadoras: ['Team Cherry'], descricao: 'Um reino em ruínas.', atribuicao: 'Steam', ...over });
const game = (over = {}) => ({ nome: 'hollow kn', plataforma: 'PC', progresso: 40, capa_id: 'abc', favorito: true, colecao_id: 3, grupo: '', ordem: 2, data_inicio: '2026-09-07', data_termino: null, trofeus_obtidos: 2, trofeus_total: 10,
  status_avancado: 'Jogando', notas: 'minhas notas', cronograma: { '2026-09-07': 'single' }, genero: '', minutos_jogados: 120, data_lancamento: null, desenvolvedor: '', publicadora: '', descricao: '', fonte_externa: '', id_externo: '', url_origem: '', ...over });

test('a new game takes the official name, metadata and single platform while personal data stays untouched', () => {
  assert.equal(typeof covers.mergeDetails, 'function');
  const result = covers.mergeDetails(game(), details({ plataformas_nexus: ['PS5'] }), { isNew: true, touched: new Set(['nome']) });
  assert.equal(result.form.nome, 'Hollow Knight');
  assert.equal(result.form.plataforma, 'PS5', 'the default platform was never chosen by hand, so a single clear platform replaces it');
  assert.equal(result.form.genero, 'Ação');
  assert.equal(result.form.data_lancamento, '2017-02-24');
  assert.equal(result.form.desenvolvedor, 'Team Cherry');
  assert.equal(result.form.descricao, 'Um reino em ruínas.');
  assert.deepEqual([result.form.fonte_externa, result.form.id_externo, result.form.url_origem], ['steam', '367520', 'https://store.steampowered.com/app/367520/']);
  assert.deepEqual(result.filled, ['nome', 'genero', 'data_lancamento', 'desenvolvedor', 'publicadora', 'descricao', 'plataforma']);
  assert.deepEqual(result.conflicts, []);
  const personal = ['progresso', 'capa_id', 'favorito', 'colecao_id', 'ordem', 'data_inicio', 'data_termino', 'trofeus_obtidos', 'trofeus_total', 'status_avancado', 'notas', 'cronograma', 'minutos_jogados'];
  for (const field of personal) assert.deepEqual(result.form[field], game()[field], `${field} must not change`);
});

test('editing an existing game fills only empty fields and turns differences into conflicts to confirm', () => {
  const existing = game({ nome: 'Hollow Knight: Edição Especial', genero: 'RPG', plataforma: 'Switch', desenvolvedor: '' });
  const result = covers.mergeDetails(existing, details(), { isNew: false, touched: new Set() });
  assert.equal(result.form.nome, 'Hollow Knight: Edição Especial');
  assert.equal(result.form.genero, 'RPG');
  assert.equal(result.form.plataforma, 'Switch');
  assert.equal(result.form.desenvolvedor, 'Team Cherry');
  assert.deepEqual(result.conflicts.map(c => [c.field, c.current, c.next]), [['nome', 'Hollow Knight: Edição Especial', 'Hollow Knight'], ['genero', 'RPG', 'Ação'], ['plataforma', 'Switch', 'PC']]);
  const confirmed = covers.applyChanges(result.form, result.conflicts.filter(c => c.field !== 'nome'));
  assert.equal(confirmed.nome, 'Hollow Knight: Edição Especial');
  assert.equal(confirmed.genero, 'Ação');
  assert.equal(confirmed.plataforma, 'PC');
  const equal = covers.mergeDetails(game({ nome: 'HOLLOW KNIGHT', genero: 'ação' }), details(), { isNew: false, touched: new Set() });
  assert.deepEqual(equal.conflicts, [], 'same values in another case are neither filled nor conflicts');
});

test('several possible platforms preserve the current choice or become a quick choice, never an arbitrary pick', () => {
  const kept = covers.mergeDetails(game({ plataforma: 'PS5' }), details({ plataformas_nexus: ['PC', 'PS5', 'Xbox'] }), { isNew: false, touched: new Set() });
  assert.equal(kept.form.plataforma, 'PS5');
  assert.deepEqual(kept.platformChoices, []);
  const choose = covers.mergeDetails(game({ plataforma: 'PC' }), details({ plataformas_nexus: ['PS5', 'Xbox'] }), { isNew: true, touched: new Set() });
  assert.equal(choose.form.plataforma, 'PC');
  assert.deepEqual(choose.platformChoices, ['PS5', 'Xbox']);
  const handPicked = covers.mergeDetails(game({ plataforma: 'Switch' }), details({ plataformas_nexus: ['PC'] }), { isNew: true, touched: new Set(['plataforma']) });
  assert.equal(handPicked.form.plataforma, 'Switch', 'a platform chosen by hand in a new game is a conflict, not a silent change');
  assert.deepEqual(handPicked.conflicts.map(c => c.field), ['plataforma']);
  assert.match(covers.fillSummary(['nome', 'genero'], true, 'Steam'), /capa, nome do jogo, gênero/);
  assert.match(covers.fillSummary([], false, 'Wikipedia'), /Nenhum campo vazio/);
});
