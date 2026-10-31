import { useEffect, useMemo, useState } from 'react';
import { EyeOff, Lock, RefreshCw, Trophy } from 'lucide-react';
import { Button, Modal } from '../../components/ui';
import { useBackend } from '../../services/BackendProvider';
import { SOURCE_NAMES, type Achievement, type GameAchievements } from '../../services/api';

type Filter = 'todas' | 'obtidas' | 'faltam';
type Order = 'fonte' | 'raridade' | 'data';

function formatMoment(iso: string | null) {
  if (!iso) return '';
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return iso;
  return iso.length <= 10 ? date.toLocaleDateString('pt-BR', { timeZone: 'UTC' }) : date.toLocaleString('pt-BR', { day: '2-digit', month: '2-digit', year: 'numeric', hour: '2-digit', minute: '2-digit' });
}
/** Faixa de raridade em palavras, pela parcela de jogadores que obteve a conquista. */
export function rarityLabel(percent: number | null) {
  if (percent === null) return '';
  if (percent < 5) return 'Ultra rara';
  if (percent < 15) return 'Muito rara';
  if (percent < 40) return 'Rara';
  return 'Comum';
}
/** Ordena e filtra a lista no navegador; a fonte define a ordem padrão. */
export function arrange(items: Achievement[], filter: Filter, order: Order): Achievement[] {
  const kept = items.filter(item => filter === 'todas' || (filter === 'obtidas' ? item.obtida : !item.obtida));
  if (order === 'raridade') return [...kept].sort((a, b) => (a.raridade ?? 101) - (b.raridade ?? 101));
  if (order === 'data') return [...kept].sort((a, b) => (b.obtida_em ?? '').localeCompare(a.obtida_em ?? ''));
  return kept;
}

/** Ícone da conquista pelo proxy do serviço (nunca direto dos CDNs); conquistas não obtidas usam a versão apagada. */
function Icon({ item }: { item: Achievement }) {
  const { api } = useBackend();
  const url = item.obtida ? item.icone ?? item.icone_bloqueado : item.icone_bloqueado ?? item.icone;
  const [objectUrl, setObjectUrl] = useState<string | null>(null);
  useEffect(() => {
    if (!url) return;
    const controller = new AbortController();
    let created: string | undefined;
    api.coverPreview(url, controller.signal).then(blob => { if (!controller.signal.aborted) { created = URL.createObjectURL(blob); setObjectUrl(created); } }).catch(() => { /* fica o troféu genérico */ });
    return () => { controller.abort(); if (created) URL.revokeObjectURL(created); };
  }, [api, url]);
  return <span className={`achievement-icon ${item.obtida ? '' : 'is-locked'}`}>{objectUrl ? <img src={objectUrl} alt="" /> : item.obtida ? <Trophy size={22} /> : <Lock size={20} />}</span>;
}

/**
 * Visualizador de conquistas de um jogo ligado à Steam ou ao RetroAchievements. Lê pela conta vinculada do perfil; a
 * contagem obtidos/total do jogo é atualizada pelo serviço na mesma consulta, e `onClose(true)` avisa que a lista deve recarregar.
 */
export function TrophyViewer({ gameId, onClose }: { gameId: number; onClose: (changed: boolean) => void }) {
  const { api } = useBackend();
  const [data, setData] = useState<GameAchievements | null>(null);
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(true);
  const [attempt, setAttempt] = useState(0);
  const [filter, setFilter] = useState<Filter>('todas');
  const [order, setOrder] = useState<Order>('fonte');
  useEffect(() => {
    const controller = new AbortController();
    setLoading(true); setError('');
    api.gameAchievements(gameId, controller.signal).then(result => { if (!controller.signal.aborted) { setData(result); setLoading(false); } })
      .catch(cause => { if (!controller.signal.aborted) { setError(cause instanceof Error ? cause.message : 'Não foi possível consultar as conquistas.'); setLoading(false); } });
    return () => controller.abort();
  }, [api, gameId, attempt]);
  const shown = useMemo(() => data ? arrange(data.itens, filter, order) : [], [data, filter, order]);
  const percent = data && data.total ? Math.round(data.obtidos * 100 / data.total) : 0;
  const close = () => onClose(Boolean(data));
  const rare = data ? data.itens.filter(item => item.obtida && item.raridade !== null && item.raridade < 15).length : 0;

  return <Modal open onClose={close} title={data ? `Troféus de ${data.jogo.nome}` : 'Troféus'} wide>
    {loading && <p role="status">Consultando a fonte…</p>}
    {error && <div><p role="alert" className="form-error">{error}</p><div className="control-row"><Button onClick={() => setAttempt(n => n + 1)}><RefreshCw size={16} /> Tentar novamente</Button><Button onClick={close}>Fechar</Button></div></div>}
    {data && <>
      <div className="achievement-summary">
        <div><strong>{data.obtidos}</strong> de <strong>{data.total}</strong> conquistas · {percent}%{data.obtidos === data.total && data.total > 0 ? ' · completo!' : ''}</div>
        <progress className="trophy-progress" max={100} value={percent} aria-label="Progresso de conquistas" />
        <p className="muted">{SOURCE_NAMES[data.jogo.fonte]}{data.jogo.titulo_fonte && data.jogo.titulo_fonte !== data.jogo.nome ? ` · ${data.jogo.titulo_fonte}` : ''} · {data.jogo.plataforma} · consultado em {formatMoment(data.consultado_em)}{rare ? ` · ${rare} rara${rare === 1 ? '' : 's'} obtida${rare === 1 ? '' : 's'}` : ''}. A contagem do jogo na biblioteca foi atualizada com estes números.</p>
      </div>
      <div className="achievement-controls" role="group" aria-label="Filtro e ordem">
        <div className="family-chips">{([['todas', 'Todas'], ['obtidas', 'Obtidas'], ['faltam', 'Faltam']] as [Filter, string][]).map(([value, label]) => <button key={value} type="button" className={`chip ${filter === value ? 'selected' : ''}`} aria-pressed={filter === value} onClick={() => setFilter(value)}>{label}</button>)}</div>
        <label className="muted">Ordenar por <select className="input trophy-mode" value={order} onChange={e => setOrder(e.target.value as Order)}><option value="fonte">ordem da fonte</option><option value="raridade">mais raras primeiro</option><option value="data">obtidas mais recentes</option></select></label>
        <Button variant="ghost" onClick={() => setAttempt(n => n + 1)} disabled={loading}><RefreshCw size={16} /> Atualizar</Button>
      </div>
      {shown.length === 0 ? <p className="muted">Nenhuma conquista neste filtro.</p> : <ul className="achievement-list">{shown.map(item => <li key={item.id} className={item.obtida ? 'is-earned' : ''}>
        <Icon item={item} />
        <div className="achievement-text">
          <strong>{item.nome}{item.oculta && !item.obtida && <span className="achievement-hidden" title="Conquista oculta na fonte"><EyeOff size={12} /> oculta</span>}</strong>
          <span>{item.oculta && !item.obtida && !item.descricao ? 'Descrição revelada só depois de obter.' : item.descricao || '—'}</span>
          <small>{item.obtida ? `Obtida em ${formatMoment(item.obtida_em) || 'data não informada'}` : 'Ainda não obtida'}{item.raridade !== null ? ` · ${item.raridade}% dos jogadores · ${rarityLabel(item.raridade)}` : ''}{item.pontos ? ` · ${item.pontos} pontos` : ''}</small>
        </div>
      </li>)}</ul>}
      <div className="editor-footer"><span /><Button onClick={close}>Fechar</Button></div>
    </>}
  </Modal>;
}
