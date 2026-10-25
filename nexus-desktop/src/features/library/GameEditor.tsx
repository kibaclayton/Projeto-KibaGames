import { useEffect, useRef, useState, type FormEvent } from 'react';
import { BookOpen, CalendarDays, CheckCircle2, ImagePlus, Save, Search, Trash2, Trophy } from 'lucide-react';
import { Button, Modal } from '../../components/ui';
import { useBackend } from '../../services/BackendProvider';
import type { Collection, CoverCandidate, CoverSource, DuplicateRef, GameInput } from '../../services/api';
import { CoverImage } from './CoverImage';
import { CoverSearch } from './CoverSearch';
import { applyChanges, candidateKey, fillSummary, mergeDetails, safeHttpsUrl, type FillChange } from './coverModel';
import { GameCalendar } from './GameCalendar';
import { blankGame, gamePayload, trophies } from './model';
import { bounds, scheduleFromDates, type Schedule } from './schedule';

const SOURCE_LABELS: Record<CoverSource, string> = { steam: 'Steam', wikipedia: 'Wikipedia' };

/** Valor de um campo na caixa de confirmação: datas em pt-BR e textos longos encurtados. */
function shown(field: FillChange['field'], value: string) {
  if (field === 'data_lancamento' && /^\d{4}-\d{2}-\d{2}$/.test(value)) { const [year, month, day] = value.split('-'); return `${day}/${month}/${year}`; }
  return value.length > 140 ? `${value.slice(0, 140).trimEnd()}…` : value;
}

export function GameEditor({ gameId, collections, onClose, onSaved }: { gameId: number | null; collections: Collection[]; onClose: () => void; onSaved: () => void }) {
  const { api } = useBackend();
  const [form, setForm] = useState<GameInput>(blankGame);
  const [loading, setLoading] = useState(gameId !== null);
  const [loaded, setLoaded] = useState(gameId === null);
  const [loadAttempt, setLoadAttempt] = useState(0);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [coverUrl, setCoverUrl] = useState('');
  const [confirmDelete, setConfirmDelete] = useState(false);
  const [confirmDiscard, setConfirmDiscard] = useState(false);
  const [dirty, setDirty] = useState(false);
  const [jump, setJump] = useState<{ iso: string | null; key: number }>({ iso: null, key: 0 });
  // Campos que a pessoa editou à mão nesta sessão: a ficha externa nunca os substitui em silêncio.
  const touched = useRef(new Set<string>());
  // Capa vinda da busca (automática ou escolhida): `key` identifica o resultado em uso; a automação só troca o que ela mesma colocou.
  const [applied, setApplied] = useState<{ id: string; key: string } | null>(null);
  const [autoOff, setAutoOff] = useState(false);
  const [autoBusy, setAutoBusy] = useState(false);
  const [autoNote, setAutoNote] = useState('');
  // Preenchimento pela ficha do jogo escolhido: resumo anunciável, conflitos a confirmar, escolha de plataforma e duplicata.
  const [fillNote, setFillNote] = useState('');
  const [pending, setPending] = useState<FillChange[] | null>(null);
  const [platformChoices, setPlatformChoices] = useState<string[]>([]);
  const [duplicate, setDuplicate] = useState<DuplicateRef | null>(null);
  useEffect(() => {
    let active = true;
    setLoading(gameId !== null); setLoaded(gameId === null); setError('');
    if (gameId !== null) api.game(gameId).then(game => {
      if (active) { const { id: _id, atualizado: _updated, trofeus_percentual: _percent, platinado: _platinum, ...input } = game; setForm({ ...blankGame, ...input }); setLoaded(true); setLoading(false); }
    }).catch(cause => { if (active) { setError(cause.message); setLoading(false); } });
    return () => { active = false; };
  }, [api, gameId, loadAttempt]);
  function field<K extends keyof GameInput>(key: K, value: GameInput[K]) { touched.current.add(key); setForm(old => ({ ...old, [key]: value })); setDirty(true); }
  // Registros antigos sem cronograma mostram as datas existentes como pontos; só viram cronograma quando o calendário é usado.
  const schedule: Schedule = Object.keys(form.cronograma).length ? form.cronograma : scheduleFromDates(form.data_inicio, form.data_termino);
  function scheduleChanged(next: Schedule) {
    const { start, end } = bounds(next);
    setForm(old => ({ ...old, cronograma: next, data_inicio: start, data_termino: end }));
    setDirty(true);
  }
  function dateChanged(key: 'data_inicio' | 'data_termino', value: string | null) {
    setForm(old => {
      const next = { ...old };
      next[key] = value;
      if (!next.data_inicio || !next.data_termino || next.data_termino >= next.data_inicio) next.cronograma = scheduleFromDates(next.data_inicio, next.data_termino);
      return next;
    });
    setDirty(true);
    setJump(current => ({ iso: value, key: current.key + 1 }));
  }
  async function save(event: FormEvent) {
    event.preventDefault(); if (!loaded || loading || busy) return; setError(''); setBusy(true);
    try { const payload = gamePayload(form); if (gameId === null) await api.createGame(payload); else await api.patchGame(gameId, payload); onSaved(); }
    catch (cause) { setError(cause instanceof Error ? cause.message : 'Não foi possível salvar.'); }
    finally { setBusy(false); }
  }
  async function image(file?: File) {
    setBusy(true); setError('');
    try { const result = file ? await api.uploadImage(file, 'capa') : await api.downloadCover(coverUrl); field('capa_id', result.id); setApplied(null); setAutoOff(true); setAutoNote(''); setCoverUrl(''); }
    catch (cause) { setError(cause instanceof Error ? cause.message : 'Não foi possível salvar a capa.'); }
    finally { setBusy(false); }
  }
  /** Escolha consciente de um resultado: a ficha e a capa vêm do mesmo identificador; só campos vazios são preenchidos. */
  async function pickCover(candidate: CoverCandidate): Promise<string> {
    setBusy(true); setError('');
    try {
      const result = await api.applyCandidate(candidate.fonte, candidate.id, gameId);
      const merged = mergeDetails(form, result.detalhes, { isNew: gameId === null, touched: touched.current });
      const next = result.imagem ? { ...merged.form, capa_id: result.imagem.id } : merged.form;
      setForm(next); setDirty(true);
      setApplied(result.imagem ? { id: result.imagem.id, key: candidateKey(candidate) } : null);
      setAutoOff(true); setAutoNote('');
      setPending(merged.conflicts.length ? merged.conflicts : null);
      setPlatformChoices(merged.platformChoices);
      setDuplicate(result.duplicado_em);
      setFillNote(`${fillSummary(merged.filled, Boolean(result.imagem), SOURCE_LABELS[candidate.fonte])}${result.erro_capa ? ` ${result.erro_capa}` : ''}`);
      return '';
    } catch (cause) { return cause instanceof Error ? cause.message : 'Não foi possível obter os dados deste jogo.'; }
    finally { setBusy(false); }
  }
  async function autoCoverFrom(ranked: CoverCandidate[], query: string) {
    // Só substitui uma capa que a própria automação colocou; uma capa escolhida à mão nunca é trocada. Dados do jogo só com um toque.
    if (autoOff || autoBusy || (form.capa_id && form.capa_id !== applied?.id)) return;
    setAutoBusy(true);
    try {
      for (const candidate of ranked.slice(0, 3)) {
        const key = candidateKey(candidate);
        if (key === applied?.key) { setAutoBusy(false); return; }
        try {
          const result = await api.applyCandidate(candidate.fonte, candidate.id, gameId);
          const picture = result.imagem;
          if (!picture) continue; // A fonte não tem arte para este jogo; tenta o próximo candidato.
          setForm(old => ({ ...old, capa_id: picture.id })); setDirty(true);
          setApplied({ id: picture.id, key });
          setAutoNote(`Capa aplicada automaticamente para "${query}": ${candidate.titulo} (${SOURCE_LABELS[candidate.fonte]}). Toque num resultado para preencher também os dados do jogo, ou em Remover capa.`);
          return;
        } catch { /* Tenta o próximo candidato: a arte pode não existir na fonte. */ }
      }
      setAutoNote('Nenhuma capa pôde ser baixada automaticamente. Escolha um resultado abaixo, envie um arquivo ou use um link.');
    } finally { setAutoBusy(false); }
  }
  function removeCover() { field('capa_id', null); setApplied(null); setAutoOff(true); setAutoNote(''); }
  const values = trophies(form.trofeus_obtidos, form.trofeus_total);
  const close = () => { if (busy) return; if (dirty) setConfirmDiscard(true); else onClose(); };
  return <Modal open onClose={close} title={gameId === null ? 'Adicionar jogo' : 'Editar jogo'} wide>
    {loading ? <p role="status">Carregando jogo…</p> : !loaded ? <div><p role="alert" className="form-error">{error || 'Não foi possível carregar o jogo.'}</p><Button onClick={() => setLoadAttempt(value => value + 1)}>Tentar novamente</Button></div> : <form onSubmit={save}>
      {error && <p className="form-error" role="alert">{error}</p>}
      <fieldset disabled={busy} className="editor-grid">
        <div><label htmlFor="game-name" className="field-label">Nome do jogo</label><input id="game-name" className="input" value={form.nome} onChange={e => field('nome', e.target.value)} required maxLength={150} />
          {duplicate && <p role="status" className="muted fill-duplicate">Você já tem “{duplicate.nome}” ({duplicate.plataforma}) ligado a este mesmo jogo da fonte. Pode continuar se for outra edição ou plataforma.</p>}
          <div className="field-pair"><div><label htmlFor="game-platform" className="field-label">Plataforma</label><select id="game-platform" className="input" value={form.plataforma} onChange={e => field('plataforma', e.target.value)}>{Array.from(new Set(['PC', 'PS5', 'PS4', 'Xbox', 'Switch', 'Outro', form.plataforma])).map(p => <option key={p}>{p}</option>)}</select></div><div><label htmlFor="game-genre" className="field-label">Gênero</label><input id="game-genre" className="input" list="genre-options" value={form.genero} onChange={e => field('genero', e.target.value)} maxLength={80} /><datalist id="genre-options">{['RPG', 'Ação', 'FPS', 'Aventura', 'Terror', 'Estratégia'].map(g => <option key={g}>{g}</option>)}</datalist></div></div>
          {platformChoices.length > 0 && <div role="group" aria-label="Plataforma em que você joga" className="fill-choice"><span className="muted">Este jogo saiu em várias plataformas. Em qual você joga?</span>{platformChoices.map(p => <Button key={p} variant="ghost" onClick={() => { field('plataforma', p); setPlatformChoices([]); }}>{p}</Button>)}<Button variant="ghost" onClick={() => setPlatformChoices([])}>Manter {form.plataforma}</Button></div>}
          <label htmlFor="game-progress" className="field-label">Progresso <span>{form.progresso}%</span></label><input id="game-progress" type="range" min={0} max={100} value={form.progresso} onChange={e => field('progresso', Number(e.target.value))} />
          <label htmlFor="game-status" className="field-label">Status</label><select id="game-status" className="input" value={form.status_avancado} onChange={e => field('status_avancado', e.target.value)}><option value="">Automático pelo progresso</option>{Array.from(new Set(['Jogando', 'Na fila', 'Pausado', 'Concluído', 'Abandonado', form.status_avancado])).filter(Boolean).map(s => <option key={s}>{s}</option>)}</select>
          <div className="field-pair"><div><label htmlFor="game-collection" className="field-label">Coleção</label><select id="game-collection" className="input" value={form.colecao_id ?? ''} onChange={e => field('colecao_id', e.target.value ? Number(e.target.value) : null)}><option value="">Sem coleção</option>{collections.map(c => <option value={c.id} key={c.id}>{c.nome}</option>)}</select></div><div><label htmlFor="game-order" className="field-label">Ordem na coleção</label><input id="game-order" className="input" type="number" min={1} max={9999} value={form.ordem} onChange={e => field('ordem', Number(e.target.value))} required /></div></div>
          <label htmlFor="game-notes" className="field-label">Notas</label><textarea id="game-notes" className="input notes-input" value={form.notas} onChange={e => field('notas', e.target.value)} maxLength={100000} />
          <h3 className="trophy-heading"><BookOpen size={17} /> Ficha do jogo</h3>
          <div className="field-pair"><div><label htmlFor="game-release" className="field-label">Lançamento</label><input id="game-release" className="input" type="date" value={form.data_lancamento ?? ''} onChange={e => field('data_lancamento', e.target.value || null)} /></div><div><label htmlFor="game-developer" className="field-label">Desenvolvedor</label><input id="game-developer" className="input" value={form.desenvolvedor} onChange={e => field('desenvolvedor', e.target.value)} maxLength={200} /></div></div>
          <label htmlFor="game-publisher" className="field-label">Publicadora</label><input id="game-publisher" className="input" value={form.publicadora} onChange={e => field('publicadora', e.target.value)} maxLength={200} />
          <label htmlFor="game-description" className="field-label">Descrição</label><textarea id="game-description" className="input description-input" value={form.descricao} onChange={e => field('descricao', e.target.value)} maxLength={4000} />
          <p className="muted fill-source">{form.fonte_externa ? <>Dados de {SOURCE_LABELS[form.fonte_externa]}{safeHttpsUrl(form.url_origem) && <>, <a href={safeHttpsUrl(form.url_origem)} target="_blank" rel="noreferrer noopener">página de origem</a></>}. </> : null}A data de lançamento é do jogo; início e término, no calendário, são da sua jornada.</p>
        </div>
        <div><div className="editor-cover"><CoverImage imageId={form.capa_id} name={form.nome || 'Novo jogo'} full /></div><div className="control-row"><label className="button button-secondary upload-button"><ImagePlus size={16} /> Escolher capa<input type="file" accept="image/jpeg,image/png,image/webp" disabled={busy} onChange={e => { const selected = e.target.files?.[0]; if (selected) void image(selected); e.target.value = ''; }} /></label><Button onClick={removeCover} disabled={!form.capa_id}>Remover capa</Button></div>
          {(autoBusy || autoNote) && <p role="status" className={`muted cover-auto-note ${autoBusy ? 'is-busy' : ''}`}><Search size={14} /> {autoBusy ? 'Procurando a capa pelo nome…' : autoNote}</p>}
          <p role="status" aria-live="polite" className="muted cover-auto-note fill-note">{fillNote && <><CheckCircle2 size={14} /> {fillNote}</>}</p>
          <CoverSearch query={form.nome} auto={!form.capa_id || form.capa_id === applied?.id} busy={busy || autoBusy} selectedKey={applied?.key ?? null} onPick={pickCover} onResults={(ranked, query) => void autoCoverFrom(ranked, query)} />
          <label htmlFor="game-cover-url" className="field-label">Link direto da capa (HTTPS)</label><div className="url-field"><input className="input" id="game-cover-url" type="url" placeholder="https://…/capa.jpg" value={coverUrl} onChange={e => setCoverUrl(e.target.value)} /><Button onClick={() => void image()} disabled={!coverUrl}>Buscar</Button></div>
          <h3 className="trophy-heading"><CalendarDays size={17} /> Calendário de sessões</h3>
          <GameCalendar schedule={schedule} onChange={scheduleChanged} jump={jump} />
          <div className="field-pair"><div><label className="field-label" htmlFor="game-start">Início</label><input id="game-start" className="input" type="date" value={form.data_inicio ?? ''} onChange={e => dateChanged('data_inicio', e.target.value || null)} /></div><div><label className="field-label" htmlFor="game-end">Término</label><input id="game-end" className="input" type="date" value={form.data_termino ?? ''} min={form.data_inicio ?? undefined} onChange={e => dateChanged('data_termino', e.target.value || null)} /></div></div>
          <p className="calendar-hint">Datas futuras representam planejamento. Editar as datas substitui a seleção do calendário por um intervalo contínuo.</p>
          <h3 className="trophy-heading"><Trophy size={17} /> Conquistas / Troféus</h3><div className="field-pair"><div><label htmlFor="game-earned" className="field-label">Troféus obtidos</label><input id="game-earned" className="input" type="number" min={0} max={form.trofeus_total} value={form.trofeus_obtidos} onChange={e => field('trofeus_obtidos', Number(e.target.value))} required /></div><div><label htmlFor="game-total" className="field-label">Total de troféus</label><input id="game-total" className="input" type="number" min={0} max={1000000} value={form.trofeus_total} onChange={e => field('trofeus_total', Number(e.target.value))} required /></div></div><progress className="trophy-progress" max={100} value={values.percent} aria-label="Progresso de troféus" /><p className="muted">{values.platinum ? 'Platinado!' : `${values.percent}% · ${values.remaining} troféus restantes`}</p>
        </div>
      </fieldset>
      {pending && <div className="confirm-box" role="alertdialog" aria-labelledby="fill-confirm-title" aria-describedby="fill-confirm-list"><p id="fill-confirm-title">Alguns campos já estavam preenchidos. Substituir pelos dados da fonte?</p>
        <ul id="fill-confirm-list" className="fill-changes">{pending.map(change => <li key={change.field}><strong>{change.label}:</strong> <s>{shown(change.field, change.current)}</s> passa a ser “{shown(change.field, change.next)}”</li>)}</ul>
        <Button onClick={() => { setForm(applyChanges(form, pending)); setDirty(true); setPending(null); }}>Substituir</Button><Button onClick={() => setPending(null)}>Manter os meus</Button></div>}
      {confirmDiscard && <div className="confirm-box" role="alert"><p>Descartar as alterações deste jogo?</p><Button onClick={onClose}>Descartar</Button><Button onClick={() => setConfirmDiscard(false)}>Continuar editando</Button></div>}
      {confirmDelete && <div className="confirm-box" role="alert"><p>Excluir “{form.nome}” da sua biblioteca? Esta ação não pode ser desfeita.</p><Button disabled={busy} onClick={async () => { if (gameId === null) return; setBusy(true); try { await api.deleteGame(gameId); onSaved(); } catch (cause) { setError((cause as Error).message); } finally { setBusy(false); } }}>Confirmar exclusão</Button><Button onClick={() => setConfirmDelete(false)}>Manter jogo</Button></div>}
      <div className="editor-footer">{gameId !== null && <Button onClick={() => setConfirmDelete(true)} disabled={busy}><Trash2 size={16} /> Excluir</Button>}<span /><Button onClick={close} disabled={busy}>Cancelar</Button><Button type="submit" variant="primary" disabled={busy || !form.nome.trim()}><Save size={16} />{busy ? 'Salvando…' : 'Salvar jogo'}</Button></div>
    </form>}
  </Modal>;
}
