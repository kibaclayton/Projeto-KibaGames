import { useEffect, useState, type FormEvent } from 'react';
import { ImagePlus, Save, Trash2, Trophy } from 'lucide-react';
import { Button, Modal } from '../../components/ui';
import { useBackend } from '../../services/BackendProvider';
import type { Collection, GameInput } from '../../services/api';
import { CoverImage } from './CoverImage';
import { gamePayload, trophies } from './model';

const blank: GameInput = { nome: '', plataforma: 'PC', progresso: 0, capa_id: null, favorito: false, colecao_id: null, grupo: '', ordem: 1, data_inicio: null, data_termino: null, trofeus_obtidos: 0, trofeus_total: 0, status_avancado: '', notas: '', cronograma: {}, genero: '', minutos_jogados: 0 };

export function GameEditor({ gameId, collections, onClose, onSaved }: { gameId: number | null; collections: Collection[]; onClose: () => void; onSaved: () => void }) {
  const { api } = useBackend();
  const [form, setForm] = useState<GameInput>(blank);
  const [loading, setLoading] = useState(gameId !== null);
  const [loaded, setLoaded] = useState(gameId === null);
  const [loadAttempt, setLoadAttempt] = useState(0);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [coverUrl, setCoverUrl] = useState('');
  const [confirmDelete, setConfirmDelete] = useState(false);
  const [confirmDiscard, setConfirmDiscard] = useState(false);
  const [dirty, setDirty] = useState(false);
  useEffect(() => {
    let active = true;
    setLoading(gameId !== null); setLoaded(gameId === null); setError('');
    if (gameId !== null) api.game(gameId).then(game => {
      if (active) { const { id: _id, atualizado: _updated, trofeus_percentual: _percent, platinado: _platinum, ...input } = game; setForm(input); setLoaded(true); setLoading(false); }
    }).catch(cause => { if (active) { setError(cause.message); setLoading(false); } });
    return () => { active = false; };
  }, [api, gameId, loadAttempt]);
  function field<K extends keyof GameInput>(key: K, value: GameInput[K]) { setForm(old => ({ ...old, [key]: value })); setDirty(true); }
  async function save(event: FormEvent) {
    event.preventDefault(); if (!loaded || loading || busy) return; setError(''); setBusy(true);
    try { const payload = gamePayload(form); if (gameId === null) await api.createGame(payload); else await api.patchGame(gameId, payload); onSaved(); }
    catch (cause) { setError(cause instanceof Error ? cause.message : 'Não foi possível salvar.'); }
    finally { setBusy(false); }
  }
  async function image(file?: File) {
    setBusy(true); setError('');
    try { const result = file ? await api.uploadImage(file, 'capa') : await api.downloadCover(coverUrl); field('capa_id', result.id); setCoverUrl(''); }
    catch (cause) { setError(cause instanceof Error ? cause.message : 'Não foi possível salvar a capa.'); }
    finally { setBusy(false); }
  }
  const values = trophies(form.trofeus_obtidos, form.trofeus_total);
  const close = () => { if (busy) return; if (dirty) setConfirmDiscard(true); else onClose(); };
  return <Modal open onClose={close} title={gameId === null ? 'Adicionar jogo' : 'Editar jogo'} wide>
    {loading ? <p role="status">Carregando jogo…</p> : !loaded ? <div><p role="alert" className="form-error">{error || 'Não foi possível carregar o jogo.'}</p><Button onClick={() => setLoadAttempt(value => value + 1)}>Tentar novamente</Button></div> : <form onSubmit={save}>
      {error && <p className="form-error" role="alert">{error}</p>}
      <fieldset disabled={busy} className="editor-grid">
        <div><label htmlFor="game-name" className="field-label">Nome do jogo</label><input id="game-name" className="input" value={form.nome} onChange={e => field('nome', e.target.value)} required maxLength={150} />
          <div className="field-pair"><div><label htmlFor="game-platform" className="field-label">Plataforma</label><select id="game-platform" className="input" value={form.plataforma} onChange={e => field('plataforma', e.target.value)}>{Array.from(new Set(['PC', 'PS5', 'PS4', 'Xbox', 'Switch', 'Outro', form.plataforma])).map(p => <option key={p}>{p}</option>)}</select></div><div><label htmlFor="game-genre" className="field-label">Gênero</label><input id="game-genre" className="input" list="genre-options" value={form.genero} onChange={e => field('genero', e.target.value)} maxLength={80} /><datalist id="genre-options">{['RPG', 'Ação', 'FPS', 'Aventura', 'Terror', 'Estratégia'].map(g => <option key={g}>{g}</option>)}</datalist></div></div>
          <label htmlFor="game-progress" className="field-label">Progresso <span>{form.progresso}%</span></label><input id="game-progress" type="range" min={0} max={100} value={form.progresso} onChange={e => field('progresso', Number(e.target.value))} />
          <label htmlFor="game-status" className="field-label">Status</label><select id="game-status" className="input" value={form.status_avancado} onChange={e => field('status_avancado', e.target.value)}><option value="">Automático pelo progresso</option>{Array.from(new Set(['Jogando', 'Na fila', 'Pausado', 'Concluído', 'Abandonado', form.status_avancado])).filter(Boolean).map(s => <option key={s}>{s}</option>)}</select>
          <div className="field-pair"><div><label htmlFor="game-collection" className="field-label">Coleção</label><select id="game-collection" className="input" value={form.colecao_id ?? ''} onChange={e => field('colecao_id', e.target.value ? Number(e.target.value) : null)}><option value="">Sem coleção</option>{collections.map(c => <option value={c.id} key={c.id}>{c.nome}</option>)}</select></div><div><label htmlFor="game-order" className="field-label">Ordem na coleção</label><input id="game-order" className="input" type="number" min={1} max={9999} value={form.ordem} onChange={e => field('ordem', Number(e.target.value))} required /></div></div>
          <label htmlFor="game-notes" className="field-label">Notas</label><textarea id="game-notes" className="input notes-input" value={form.notas} onChange={e => field('notas', e.target.value)} maxLength={100000} />
        </div>
        <div><div className="editor-cover"><CoverImage imageId={form.capa_id} name={form.nome || 'Novo jogo'} full /></div><div className="control-row"><label className="button button-secondary upload-button"><ImagePlus size={16} /> Escolher capa<input type="file" accept="image/jpeg,image/png,image/webp" disabled={busy} onChange={e => { const selected = e.target.files?.[0]; if (selected) void image(selected); e.target.value = ''; }} /></label><Button onClick={() => field('capa_id', null)} disabled={!form.capa_id}>Remover capa</Button></div>
          <label htmlFor="game-cover-url" className="field-label">Link direto da capa (HTTPS)</label><div className="url-field"><input className="input" id="game-cover-url" type="url" placeholder="https://…/capa.jpg" value={coverUrl} onChange={e => setCoverUrl(e.target.value)} /><Button onClick={() => void image()} disabled={!coverUrl}>Buscar</Button></div>
          <div className="field-pair"><div><label className="field-label" htmlFor="game-start">Início</label><input id="game-start" className="input" type="date" value={form.data_inicio ?? ''} onChange={e => field('data_inicio', e.target.value || null)} /></div><div><label className="field-label" htmlFor="game-end">Término</label><input id="game-end" className="input" type="date" value={form.data_termino ?? ''} min={form.data_inicio ?? undefined} onChange={e => field('data_termino', e.target.value || null)} /></div></div>
          <h3 className="trophy-heading"><Trophy size={17} /> Conquistas / Troféus</h3><div className="field-pair"><div><label htmlFor="game-earned" className="field-label">Troféus obtidos</label><input id="game-earned" className="input" type="number" min={0} max={form.trofeus_total} value={form.trofeus_obtidos} onChange={e => field('trofeus_obtidos', Number(e.target.value))} required /></div><div><label htmlFor="game-total" className="field-label">Total de troféus</label><input id="game-total" className="input" type="number" min={0} max={1000000} value={form.trofeus_total} onChange={e => field('trofeus_total', Number(e.target.value))} required /></div></div><progress className="trophy-progress" max={100} value={values.percent} aria-label="Progresso de troféus" /><p className="muted">{values.platinum ? 'Platinado!' : `${values.percent}% · ${values.remaining} troféus restantes`}</p>
        </div>
      </fieldset>
      {confirmDiscard && <div className="confirm-box" role="alert"><p>Descartar as alterações deste jogo?</p><Button onClick={onClose}>Descartar</Button><Button onClick={() => setConfirmDiscard(false)}>Continuar editando</Button></div>}
      {confirmDelete && <div className="confirm-box" role="alert"><p>Excluir “{form.nome}” da sua biblioteca? Esta ação não pode ser desfeita.</p><Button disabled={busy} onClick={async () => { if (gameId === null) return; setBusy(true); try { await api.deleteGame(gameId); onSaved(); } catch (cause) { setError((cause as Error).message); } finally { setBusy(false); } }}>Confirmar exclusão</Button><Button onClick={() => setConfirmDelete(false)}>Manter jogo</Button></div>}
      <div className="editor-footer">{gameId !== null && <Button onClick={() => setConfirmDelete(true)} disabled={busy}><Trash2 size={16} /> Excluir</Button>}<span /><Button onClick={close} disabled={busy}>Cancelar</Button><Button type="submit" variant="primary" disabled={busy || !form.nome.trim()}><Save size={16} />{busy ? 'Salvando…' : 'Salvar jogo'}</Button></div>
    </form>}
  </Modal>;
}
