import { useEffect, useState } from 'react';
import { ArrowLeft, CalendarDays, Clock3, ExternalLink, Gamepad2, Heart, PencilLine, Trophy } from 'lucide-react';
import { Button, Panel } from '../../components/ui';
import { useBackend } from '../../services/BackendProvider';
import { SOURCE_NAMES, type Collection, type ExternalSource, type GameDetails } from '../../services/api';
import { safeHttpsUrl } from './coverModel';
import { CoverImage } from './CoverImage';
import { fichaCount, formatDuration, trophies } from './model';
import { journeyDays, playedDays } from './schedule';
import { StarRating } from './StarRating';

const STATUSES = ['Jogando', 'Na fila', 'Pausado', 'Concluído', 'Abandonado'];
function formatDate(iso: string | null) { if (!iso) return null; const [y, m, d] = iso.split('-'); return `${d}/${m}/${y}`; }
const splitNames = (value: string) => value.split(',').map(part => part.trim()).filter(Boolean);
const sourceName = (source: string) => SOURCE_NAMES[source as ExternalSource] ?? source;

/**
 * Página do jogo: imagem de fundo (captura da fonte ou a capa desfocada), capa com ações rápidas (nota, favorito, status),
 * ficha da obra, números da sua jornada e a ficha completa. O que muda com frequência é salvo aqui; o resto abre o editor.
 */
export function GameDetail({ gameId, collections, onBack, onEdit, onTrophies, onChanged }: { gameId: number; collections: Collection[]; onBack: () => void; onEdit: () => void; onTrophies: () => void; onChanged: () => void }) {
  const { api } = useBackend();
  const [game, setGame] = useState<GameDetails | null>(null);
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  const [attempt, setAttempt] = useState(0);
  useEffect(() => {
    let active = true;
    api.game(gameId).then(result => { if (active) { setGame(result); setError(''); } }).catch(cause => { if (active) setError(cause instanceof Error ? cause.message : 'Não foi possível carregar o jogo.'); });
    return () => { active = false; };
  }, [api, gameId, attempt]);
  async function quick(patch: Partial<Pick<GameDetails, 'nota' | 'favorito' | 'status_avancado'>>) {
    if (!game) return;
    setBusy(true); setError('');
    try { setGame(await api.patchGame(game.id, patch)); onChanged(); }
    catch (cause) { setError(cause instanceof Error ? cause.message : 'Não foi possível salvar.'); }
    finally { setBusy(false); }
  }
  if (error && !game) return <Panel className="empty-state"><p role="alert" className="form-error">{error}</p><div className="control-row"><Button onClick={onBack}><ArrowLeft size={16} /> Voltar</Button><Button onClick={() => setAttempt(n => n + 1)}>Tentar novamente</Button></div></Panel>;
  if (!game) return <p role="status">Carregando jogo…</p>;

  const value = trophies(game.trofeus_obtidos, game.trofeus_total);
  const journey = journeyDays(game.data_inicio, game.data_termino, game.ainda_jogando);
  const played = playedDays(game.cronograma);
  const collection = collections.find(c => c.id === game.colecao_id);
  const origin = safeHttpsUrl(game.url_origem);
  const sheet = game.ficha;
  const linked = game.fonte_externa === 'steam' || game.fonte_externa === 'retroachievements';
  const released = formatDate(game.data_lancamento);
  const times: [string, number | null][] = [['História', sheet.tempo_historia], ['Com extras', sheet.tempo_extras], ['100%', sheet.tempo_completo]];
  const hasTimes = times.some(([, minutes]) => minutes);
  const makers = [...new Set([...splitNames(game.desenvolvedor), ...splitNames(game.publicadora)])];

  return <section className="game-page" aria-labelledby="game-page-title">
    <div className="game-hero">
      <div className={`game-hero-art ${game.fundo_id ? '' : 'is-cover'}`}><CoverImage imageId={game.fundo_id ?? game.capa_id} name="" full /></div>
      <div className="game-hero-shade" />
      <Button variant="ghost" className="game-hero-back" onClick={onBack}><ArrowLeft size={16} /> Voltar</Button>
    </div>
    <div className="game-page-body">
      <aside className="game-page-side">
        <div className="game-page-cover"><CoverImage imageId={game.capa_id} name={game.nome} full /></div>
        <div className="game-page-actions">
          <span className="field-label" id="game-page-rating">Minha nota</span>
          <StarRating value={game.nota} onChange={nota => void quick({ nota })} labelledBy="game-page-rating" size={24} />
          <Button variant={game.favorito ? 'primary' : 'secondary'} disabled={busy} aria-pressed={game.favorito} onClick={() => void quick({ favorito: !game.favorito })}><Heart size={16} /> {game.favorito ? 'Favorito' : 'Favoritar'}</Button>
          <label className="field-label" htmlFor="game-page-status">Status</label>
          <select id="game-page-status" className="input" value={game.status_avancado} disabled={busy} onChange={e => void quick({ status_avancado: e.target.value })}><option value="">Automático pelo progresso</option>{Array.from(new Set([...STATUSES, game.status_avancado])).filter(Boolean).map(s => <option key={s}>{s}</option>)}</select>
          <Button variant="secondary" disabled={busy} onClick={onEdit}><PencilLine size={16} /> Editar jogo</Button>
          {linked && <Button variant="secondary" disabled={busy} onClick={onTrophies}><Trophy size={16} /> Ver troféus</Button>}
        </div>
      </aside>
      <div className="game-page-main">
        {error && <p role="alert" className="form-error">{error}</p>}
        <div className="game-page-head">
          <div>
            <h2 id="game-page-title">{game.nome}</h2>
            {makers.length > 0 && <p className="game-page-by">por <strong>{makers.join(', ')}</strong></p>}
          </div>
          {released && <span className="game-page-release"><span>Lançado</span> {released}</span>}
        </div>
        {game.descricao && <p className="game-page-description">{game.descricao}</p>}
        <dl className="game-page-facts">
          <div><dt>Gêneros</dt><dd>{game.genero ? <span className="chip selected">{game.genero}</span> : <span className="muted">não informado</span>}</dd></div>
          <div><dt>Plataformas</dt><dd><span className="chip selected"><Gamepad2 size={13} /> {game.plataforma}</span>{sheet.classificacao && <span className="chip">{sheet.classificacao}</span>}{sheet.metacritic !== null && <span className="chip">Metacritic {sheet.metacritic}</span>}</dd></div>
          {collection && <div><dt>Coleção</dt><dd><span className="chip">{collection.nome} · nº {game.ordem}</span></dd></div>}
        </dl>
        {origin && <p className="game-page-more"><a href={origin} target="_blank" rel="noreferrer noopener">Mais informações em {game.fonte_externa ? sourceName(game.fonte_externa) : 'página de origem'} <ExternalLink size={12} /></a></p>}
        <div className="game-page-tiles">
          <div className="tile tile-wide">
            <span className="tile-label"><Trophy size={14} /> Troféus</span>
            <strong>{game.trofeus_total ? `${game.trofeus_obtidos} / ${game.trofeus_total}` : '—'}</strong>
            <progress className="trophy-progress" max={100} value={value.percent} aria-label="Progresso de troféus" />
            <small>{value.platinum ? 'Platinado!' : game.trofeus_total ? `${value.percent}% · faltam ${value.remaining}` : 'Total não informado'}{game.trofeus_fonte ? ` · ${sourceName(game.trofeus_fonte)}` : ''}</small>
          </div>
          <div className="tile"><span className="tile-label">Progresso</span><strong>{game.progresso}%</strong><small>{game.status_avancado || (game.progresso >= 100 ? 'Concluído' : game.progresso > 0 ? 'Em andamento' : 'Não iniciado')}</small></div>
          <div className="tile"><span className="tile-label"><Clock3 size={14} /> Tempo jogado</span><strong>{formatDuration(game.minutos_jogados) || '—'}</strong><small>{game.ainda_jogando ? 'ainda jogando' : 'registrado'}</small></div>
          <div className="tile"><span className="tile-label"><CalendarDays size={14} /> Jornada</span><strong>{journey === null ? '—' : `${journey} dia${journey === 1 ? '' : 's'}`}</strong><small>{played} dia{played === 1 ? '' : 's'} com sessão · {formatDate(game.data_inicio) ?? 'sem início'}{game.data_termino ? ` → ${formatDate(game.data_termino)}` : game.ainda_jogando ? ' → hoje' : ''}</small></div>
        </div>
        {hasTimes && <div className="game-page-times">{times.map(([label, minutes]) => <div key={label} className="tile tile-time"><strong>{minutes ? formatDuration(minutes) : '—'}</strong><small>{label}</small></div>)}</div>}
        {(sheet.idiomas.length > 0 || sheet.categorias.length > 0 || sheet.classificacao_detalhe) && <dl className="game-page-facts">
          {sheet.classificacao_detalhe && <div><dt>Classificação</dt><dd className="muted">{sheet.classificacao} · {sheet.classificacao_detalhe}</dd></div>}
          {sheet.idiomas.length > 0 && <div><dt>Idiomas</dt><dd>{sheet.idiomas.map(l => <span key={l} className="chip">{l}</span>)}</dd></div>}
          {sheet.categorias.length > 0 && <div><dt>Categorias</dt><dd>{sheet.categorias.map(c => <span key={c} className="chip">{c}</span>)}</dd></div>}
        </dl>}
        {(sheet.requisitos_minimos || sheet.requisitos_recomendados) && <details className="ficha-details"><summary>Requisitos do sistema</summary><div className="game-page-requirements">{sheet.requisitos_minimos && <div><h4>Mínimos</h4><pre>{sheet.requisitos_minimos}</pre></div>}{sheet.requisitos_recomendados && <div><h4>Recomendados</h4><pre>{sheet.requisitos_recomendados}</pre></div>}</div></details>}
        {game.notas && <div className="game-page-notes"><h4>Minhas notas</h4><p>{game.notas}</p></div>}
        <p className="muted game-page-foot">Ficha completa: {fichaCount(sheet)} de 10 itens. {game.fonte_externa ? `Dados de ${sourceName(game.fonte_externa)}.` : 'Jogo cadastrado à mão; escolha um resultado da Steam no editor para preencher a ficha.'}</p>
      </div>
    </div>
  </section>;
}
