import { useEffect, useState } from 'react';
import { ArrowLeft, CalendarDays, PencilLine, Save, Trophy, Undo2 } from 'lucide-react';
import { Button, Panel } from '../../components/ui';
import { useBackend } from '../../services/BackendProvider';
import type { Collection, GameDetails } from '../../services/api';
import { CoverImage } from './CoverImage';
import { trophies } from './model';
import { journeyDays, playedDays } from './schedule';

const STATUSES = ['Jogando', 'Na fila', 'Pausado', 'Concluído', 'Abandonado'];
function formatDate(iso: string | null) { if (!iso) return '—'; const [y, m, d] = iso.split('-'); return `${d}/${m}/${y}`; }

/**
 * Painel amplo de um favorito: o que muda com frequência (progresso, status, troféus obtidos, notas) é editado aqui e
 * salvo só ao clicar em Salvar; o resto abre o editor completo. Cancelar volta aos valores carregados.
 */
export function FavoriteSpotlight({ gameId, collections, onBack, onEdit, onChanged }: { gameId: number; collections: Collection[]; onBack?: () => void; onEdit: () => void; onChanged: () => void }) {
  const { api } = useBackend();
  const [game, setGame] = useState<GameDetails | null>(null);
  const [draft, setDraft] = useState<{ progresso: number; status_avancado: string; trofeus_obtidos: number; notas: string } | null>(null);
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  const [saved, setSaved] = useState('');
  const [attempt, setAttempt] = useState(0);
  useEffect(() => {
    let active = true;
    setError(''); setGame(null); setDraft(null);
    api.game(gameId).then(loaded => { if (active) { setGame(loaded); setDraft({ progresso: loaded.progresso, status_avancado: loaded.status_avancado, trofeus_obtidos: loaded.trofeus_obtidos, notas: loaded.notas }); } })
      .catch(cause => { if (active) setError(cause instanceof Error ? cause.message : 'Não foi possível carregar o jogo.'); });
    return () => { active = false; };
  }, [api, gameId, attempt]);

  if (error && !game) return <Panel className="empty-state"><p role="alert" className="form-error">{error}</p><div className="control-row">{onBack && <Button onClick={onBack}><ArrowLeft size={16} /> Voltar</Button>}<Button onClick={() => setAttempt(n => n + 1)}>Tentar novamente</Button></div></Panel>;
  if (!game || !draft) return <Panel className="spotlight" aria-busy="true"><p role="status">Carregando favorito…</p></Panel>;
  const dirty = draft.progresso !== game.progresso || draft.status_avancado !== game.status_avancado || draft.trofeus_obtidos !== game.trofeus_obtidos || draft.notas !== game.notas;
  const value = trophies(draft.trofeus_obtidos, game.trofeus_total);
  const journey = journeyDays(game.data_inicio, game.data_termino, game.ainda_jogando);
  const played = playedDays(game.cronograma);
  const collection = collections.find(c => c.id === game.colecao_id);
  async function save() {
    if (!draft || !game) return;
    if (draft.trofeus_obtidos > game.trofeus_total && game.trofeus_total > 0) { setError('Obtidos não pode superar o total de troféus.'); return; }
    setBusy(true); setError(''); setSaved('');
    try { const updated = await api.patchGame(game.id, draft); setGame(updated); setSaved('Alterações salvas.'); onChanged(); }
    catch (cause) { setError(cause instanceof Error ? cause.message : 'Não foi possível salvar.'); }
    finally { setBusy(false); }
  }
  return <section className="spotlight" aria-labelledby="spotlight-title">
    {onBack && <Button variant="ghost" onClick={onBack}><ArrowLeft size={16} /> Todos os favoritos</Button>}
    <div className="spotlight-body">
      <div className="spotlight-cover"><CoverImage imageId={game.capa_id} name={game.nome} full /></div>
      <div className="spotlight-main">
        <p className="eyebrow">FAVORITO EM DESTAQUE</p>
        <h2 id="spotlight-title">{game.nome}</h2>
        <p className="muted">{game.plataforma}{game.genero ? ` · ${game.genero}` : ''}{collection ? ` · coleção ${collection.nome}` : ''}{game.data_lancamento ? ` · lançado em ${formatDate(game.data_lancamento)}` : ''}</p>
        <dl className="spotlight-facts">
          <div><dt><CalendarDays size={14} /> Início</dt><dd>{formatDate(game.data_inicio)}</dd></div>
          <div><dt>Término</dt><dd>{game.ainda_jogando ? 'Ainda estou jogando' : formatDate(game.data_termino)}</dd></div>
          <div><dt>Dias de jornada</dt><dd>{journey === null ? '—' : journey}</dd></div>
          <div><dt>Dias em que joguei</dt><dd>{played}</dd></div>
          <div><dt><Trophy size={14} /> Troféus</dt><dd>{game.trofeus_total ? `${draft.trofeus_obtidos} de ${game.trofeus_total} (${value.percent}%)` : 'Total não informado'}</dd></div>
        </dl>
        {error && <p role="alert" className="form-error">{error}</p>}
        {saved && !dirty && <p role="status" className="form-success">{saved}</p>}
        <fieldset disabled={busy} className="spotlight-form">
          <label htmlFor="spot-progress" className="field-label">Progresso <span>{draft.progresso}%</span></label><input id="spot-progress" type="range" min={0} max={100} value={draft.progresso} onChange={e => setDraft({ ...draft, progresso: Number(e.target.value) })} />
          <div className="field-pair">
            <div><label htmlFor="spot-status" className="field-label">Status</label><select id="spot-status" className="input" value={draft.status_avancado} onChange={e => setDraft({ ...draft, status_avancado: e.target.value })}><option value="">Automático pelo progresso</option>{Array.from(new Set([...STATUSES, draft.status_avancado])).filter(Boolean).map(s => <option key={s}>{s}</option>)}</select></div>
            <div><label htmlFor="spot-earned" className="field-label">Troféus obtidos</label><input id="spot-earned" className="input" type="number" min={0} max={game.trofeus_total || undefined} value={draft.trofeus_obtidos} onChange={e => setDraft({ ...draft, trofeus_obtidos: Number(e.target.value) })} /></div>
          </div>
          <label htmlFor="spot-notes" className="field-label">Notas</label><textarea id="spot-notes" className="input notes-input" value={draft.notas} maxLength={100000} onChange={e => setDraft({ ...draft, notas: e.target.value })} />
        </fieldset>
        <div className="control-row">
          <Button variant="primary" disabled={!dirty || busy} onClick={() => void save()}><Save size={16} /> {busy ? 'Salvando…' : 'Salvar'}</Button>
          <Button disabled={!dirty || busy} onClick={() => { setDraft({ progresso: game.progresso, status_avancado: game.status_avancado, trofeus_obtidos: game.trofeus_obtidos, notas: game.notas }); setError(''); }}><Undo2 size={16} /> Cancelar</Button>
          <Button variant="ghost" disabled={busy} onClick={onEdit}><PencilLine size={16} /> Editor completo</Button>
        </div>
      </div>
    </div>
  </section>;
}
