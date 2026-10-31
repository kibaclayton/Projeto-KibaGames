import { useEffect, useState } from 'react';
import { Award, Link2, RefreshCw, Settings2, Trophy } from 'lucide-react';
import { Button, Panel } from '../../components/ui';
import { useBackend } from '../../services/BackendProvider';
import { SOURCE_NAMES, type TrophyOverview, type TrophyOverviewItem, type TrophySyncResult } from '../../services/api';
import { CoverImage } from './CoverImage';
import { TrophyViewer } from './TrophyViewer';

type Filter = 'todos' | 'ligados' | 'platinados' | 'andamento' | 'manuais';
const FILTERS: [Filter, string][] = [['todos', 'Todos'], ['ligados', 'Com fonte'], ['andamento', 'Em andamento'], ['platinados', 'Platinados'], ['manuais', 'Manuais']];

function keep(item: TrophyOverviewItem, filter: Filter) {
  if (filter === 'ligados') return Boolean(item.fonte);
  if (filter === 'platinados') return item.platinado;
  if (filter === 'andamento') return item.trofeus_total > 0 && !item.platinado;
  if (filter === 'manuais') return !item.fonte;
  return true;
}
function formatMoment(iso: string | null) {
  if (!iso) return '';
  const date = new Date(iso);
  return Number.isNaN(date.getTime()) ? iso : date.toLocaleString('pt-BR', { day: '2-digit', month: '2-digit', hour: '2-digit', minute: '2-digit' });
}

/**
 * Página Troféus: a coleção inteira vista pelas conquistas. Totais do perfil, sincronização com as fontes vinculadas e um
 * cartão por jogo com a barra obtidos/total; "Ver troféus" abre o visualizador para os jogos ligados a uma fonte.
 */
export function TrophyHub({ onLogin, onOpenSettings }: { onLogin: () => void; onOpenSettings: () => void }) {
  const { api, session, restoring, refreshSummary } = useBackend();
  const [data, setData] = useState<TrophyOverview | null>(null);
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(true);
  const [revision, setRevision] = useState(0);
  const [filter, setFilter] = useState<Filter>('todos');
  const [viewing, setViewing] = useState<number | null>(null);
  const [syncing, setSyncing] = useState(false);
  const [sync, setSync] = useState<TrophySyncResult | null>(null);
  useEffect(() => {
    if (!session) { setData(null); setLoading(false); return; }
    const controller = new AbortController();
    setLoading(true);
    api.trophyOverview(controller.signal).then(result => { if (!controller.signal.aborted) { setData(result); setError(''); setLoading(false); } })
      .catch(cause => { if (!controller.signal.aborted) { setError(cause instanceof Error ? cause.message : 'Não foi possível carregar os troféus.'); setLoading(false); } });
    return () => controller.abort();
  }, [api, session, revision]);
  if (!session) return <Panel className="empty-state"><div className="empty-icon"><Trophy size={28} /></div><h3>Seus troféus, todos num só lugar</h3><p>{restoring ? 'Restaurando sua sessão…' : 'Entre no seu perfil para ver as conquistas de cada jogo.'}</p>{!restoring && <Button variant="primary" onClick={onLogin}>Escolher meu perfil</Button>}</Panel>;

  async function syncNow() {
    setSyncing(true); setSync(null); setError('');
    try { const result = await api.syncTrophies(); setSync(result); setRevision(n => n + 1); void refreshSummary(); }
    catch (cause) { setError(cause instanceof Error ? cause.message : 'Não foi possível sincronizar.'); }
    finally { setSyncing(false); }
  }
  const items = data ? data.itens.filter(item => keep(item, filter)) : [];
  const totals = data?.totais;
  const percent = totals && totals.total ? Math.round(totals.obtidos * 100 / totals.total) : 0;

  return <section className="trophy-hub" aria-labelledby="trophy-hub-title">
    <h2 id="trophy-hub-title" className="visually-hidden">Troféus</h2>
    {error && <p role="alert" className="form-error">{error}</p>}
    {totals && <div className="trophy-stats">
      <div><span className="eyebrow">CONQUISTAS</span><strong>{totals.obtidos}</strong><small>de {totals.total} · {percent}%</small></div>
      <div><span className="eyebrow">PLATINADOS</span><strong>{totals.platinados}</strong><small>de {totals.com_trofeus} com troféus</small></div>
      <div><span className="eyebrow">LIGADOS A UMA FONTE</span><strong>{totals.ligados}</strong><small>de {totals.jogos} jogos</small></div>
      <div className="trophy-stats-actions">
        {data!.fontes_vinculadas.length
          ? <Button variant="primary" disabled={syncing} onClick={() => void syncNow()}><RefreshCw size={16} /> {syncing ? 'Sincronizando…' : 'Sincronizar agora'}</Button>
          : <Button variant="primary" onClick={onOpenSettings}><Link2 size={16} /> Vincular Steam ou RetroAchievements</Button>}
        <Button variant="ghost" onClick={onOpenSettings}><Settings2 size={16} /> Importar jogos da conta</Button>
      </div>
    </div>}
    {sync && <p role="status" className="muted trophy-result">{sync.total === 0 ? 'Nenhum jogo ligado a uma fonte vinculada.' : `${sync.atualizados.length} de ${sync.total} jogos consultados; ${sync.atualizados.filter(u => u.mudou).length} mudaram.`}{sync.ignorados.length ? ` Não atualizados: ${sync.ignorados.map(u => `${u.nome} (${u.motivo})`).join('; ')}` : ''}</p>}
    {data && data.fontes_vinculadas.length > 0 && <p className="muted">Fontes vinculadas: {data.fontes_vinculadas.map(source => SOURCE_NAMES[source]).join(', ')}. Troféus de PlayStation, Xbox e Nintendo continuam manuais (sem API oficial).</p>}
    <div className="family-chips" role="group" aria-label="Filtro">{FILTERS.map(([value, label]) => <button key={value} type="button" className={`chip ${filter === value ? 'selected' : ''}`} aria-pressed={filter === value} onClick={() => setFilter(value)}>{label}</button>)}</div>
    {loading && !data ? <p role="status">Carregando troféus…</p>
      : items.length === 0 ? <Panel className="empty-state"><div className="empty-icon"><Award size={28} /></div><h3>{data && data.itens.length === 0 ? 'Nenhum jogo ainda' : 'Nada neste filtro'}</h3><p>{data && data.itens.length === 0 ? 'Importe os jogos da sua conta Steam em Conta e preferências ou adicione um jogo na Biblioteca.' : 'Escolha outro filtro acima.'}</p></Panel>
      : <ul className="trophy-games">{items.map(item => <li key={item.id} className={item.platinado ? 'is-platinum' : ''}>
        <div className="trophy-game-cover"><CoverImage imageId={item.capa_id} name={item.nome} /></div>
        <div className="trophy-game-body">
          <div className="trophy-game-head"><strong>{item.nome}</strong><span className="muted">{item.plataforma}{item.fonte ? ` · ${SOURCE_NAMES[item.fonte]}` : ' · manual'}</span></div>
          <progress className="trophy-progress" max={100} value={item.percentual} aria-label={`Troféus de ${item.nome}`} />
          <div className="trophy-game-foot">
            <span>{item.platinado ? <><Award size={14} /> Platinado · {item.trofeus_total} troféus</> : item.trofeus_total ? `${item.trofeus_obtidos} de ${item.trofeus_total} · ${Math.round(item.percentual)}%` : 'Total não informado'}</span>
            <span className="muted">{item.trofeus_consultado_em ? `atualizado ${formatMoment(item.trofeus_consultado_em)}` : ''}</span>
            {item.fonte && <Button variant="ghost" onClick={() => setViewing(item.id)}><Trophy size={15} /> Ver troféus</Button>}
          </div>
        </div>
      </li>)}</ul>}
    {viewing !== null && <TrophyViewer gameId={viewing} onClose={changed => { setViewing(null); if (changed) { setRevision(n => n + 1); void refreshSummary(); } }} />}
  </section>;
}
