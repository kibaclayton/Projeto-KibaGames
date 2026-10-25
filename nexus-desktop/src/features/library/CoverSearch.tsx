import { useEffect, useRef, useState, type KeyboardEvent } from 'react';
import { ExternalLink, Search } from 'lucide-react';
import { Button } from '../../components/ui';
import { useBackend } from '../../services/BackendProvider';
import type { CoverCandidate, CoverSource } from '../../services/api';
import { candidateKey, platformSummary, rankCandidates, safeHttpsUrl } from './coverModel';

const SOURCE_LABELS: Record<CoverSource, string> = { steam: 'Steam', wikipedia: 'Wikipedia' };
const AUTO_DELAY = 800;

/** Prévia buscada pelo serviço (hosts das fontes apenas); candidatos sem imagem somem da lista. */
function CandidatePreview({ url, onFail }: { url: string; onFail: () => void }) {
  const { api } = useBackend();
  const [objectUrl, setObjectUrl] = useState<string | null>(null);
  const fail = useRef(onFail);
  fail.current = onFail;
  useEffect(() => {
    const controller = new AbortController();
    let created: string | undefined;
    api.coverPreview(url, controller.signal).then(blob => { if (!controller.signal.aborted) { created = URL.createObjectURL(blob); setObjectUrl(created); } })
      .catch(() => { if (!controller.signal.aborted) fail.current(); });
    return () => { controller.abort(); if (created) URL.revokeObjectURL(created); };
  }, [api, url]);
  return objectUrl ? <img src={objectUrl} alt="" onError={() => fail.current()} /> : <span className="cover-candidate-loading" aria-hidden="true" />;
}

/**
 * Busca jogos pelo nome em fontes públicas. Cada resultado representa um jogo (capa, nome oficial, ano, plataformas,
 * fonte) e carrega um identificador estável. Com `query`, a busca roda sozinha ao digitar o nome e devolve os candidatos
 * ordenados em `onResults`, para o editor aplicar a melhor capa automaticamente. Um toque ou Enter num resultado chama
 * `onPick`, que pede ao serviço a ficha e a capa do mesmo identificador; o texto devolvido é o erro daquele resultado.
 */
export function CoverSearch({ query, auto, busy, selectedKey, onPick, onResults }: {
  query: string; auto: boolean; busy: boolean; selectedKey: string | null; onPick: (candidate: CoverCandidate) => Promise<string>; onResults: (ranked: CoverCandidate[], query: string) => void;
}) {
  const { api } = useBackend();
  // Jogos que já têm capa escolhida não disparam buscas sozinhos; o painel fica recolhido até a pessoa pedir.
  const [open, setOpen] = useState(auto);
  useEffect(() => { if (auto) setOpen(true); }, [auto]);
  const [text, setText] = useState(query);
  const [touched, setTouched] = useState(false);
  const [source, setSource] = useState<CoverSource | 'todas'>('todas');
  const [items, setItems] = useState<CoverCandidate[] | null>(null);
  const [warnings, setWarnings] = useState<string[]>([]);
  const [hidden, setHidden] = useState<Set<string>>(new Set());
  const [searching, setSearching] = useState(false);
  const [error, setError] = useState('');
  const [searchedFor, setSearchedFor] = useState('');
  const [applying, setApplying] = useState<string | null>(null);
  const [failures, setFailures] = useState<Record<string, string>>({});
  const request = useRef<AbortController | null>(null);
  const results = useRef(onResults);
  results.current = onResults;
  useEffect(() => () => request.current?.abort(), []);
  // O campo acompanha o nome do jogo até a pessoa digitar aqui por conta própria.
  useEffect(() => { if (!touched) setText(query); }, [query, touched]);

  const inFlight = useRef('');
  async function search(name: string, chosen: CoverSource | 'todas') {
    const trimmed = name.trim();
    if (trimmed.length < 2) { setError('Digite pelo menos 2 caracteres.'); return; }
    const key = `${chosen}:${trimmed}`;
    if (inFlight.current === key) return; // A mesma busca já está em andamento.
    request.current?.abort(); // Uma busca mais antiga nunca substitui a mais recente.
    const controller = new AbortController();
    request.current = controller;
    inFlight.current = key;
    setSearching(true); setError(''); setHidden(new Set()); setFailures({});
    try {
      const result = await api.searchCovers(trimmed, chosen, controller.signal);
      if (controller.signal.aborted) return;
      const ranked = rankCandidates(trimmed, result.itens);
      setItems(ranked); setWarnings(result.avisos); setSearchedFor(trimmed);
      results.current(ranked, trimmed);
    } catch (cause) { if (!controller.signal.aborted) setError(cause instanceof Error ? cause.message : 'Não foi possível buscar jogos.'); }
    finally { if (inFlight.current === key) inFlight.current = ''; if (!controller.signal.aborted) setSearching(false); }
  }
  // Busca automática: espera a digitação parar e só repete quando o nome muda de verdade.
  useEffect(() => {
    const name = text.trim();
    if (!auto || !open || name.length < 3 || name === searchedFor) return;
    const timer = setTimeout(() => { void search(name, source); }, AUTO_DELAY);
    return () => clearTimeout(timer);
  }, [text, source, auto, open]); // eslint-disable-line react-hooks/exhaustive-deps -- searchedFor é lido no momento do disparo.

  // Erro de um candidato fica só nele, com "Tentar de novo"; os demais resultados e o formulário continuam utilizáveis.
  async function pick(item: CoverCandidate) {
    const key = candidateKey(item);
    setApplying(key);
    setFailures(current => { const next = { ...current }; delete next[key]; return next; });
    try {
      const problem = await onPick(item);
      if (problem) setFailures(current => ({ ...current, [key]: problem }));
    } finally { setApplying(current => (current === key ? null : current)); }
  }

  function keyDown(event: KeyboardEvent<HTMLInputElement>) { if (event.key === 'Enter') { event.preventDefault(); void search(text, source); } }
  const visible = items?.filter(item => !hidden.has(item.imagem)) ?? [];

  if (!open) return <div className="cover-search cover-search-collapsed"><Button variant="ghost" disabled={busy} onClick={() => { setOpen(true); void search(text, source); }}><Search size={16} /> Buscar capa e dados pelo nome</Button></div>;
  return <section className="cover-search" aria-labelledby="cover-search-title">
    <div className="section-heading"><h4 id="cover-search-title">Jogos encontrados pelo nome</h4><span className="muted" aria-live="polite">{searching ? 'Buscando…' : items ? `${visible.length} resultado${visible.length === 1 ? '' : 's'}` : ''}</span></div>
    <p className="muted cover-hint">Toque num resultado para usar a capa e preencher os campos vazios do jogo. Nada é salvo até você clicar em Salvar jogo.</p>
    <div role="search" className="cover-search-form">
      <input className="input" aria-label="Nome do jogo para buscar" value={text} onChange={event => { setTouched(true); setText(event.target.value); }} onKeyDown={keyDown} maxLength={120} disabled={busy} />
      <select className="input" aria-label="Fonte dos dados" value={source} onChange={event => setSource(event.target.value as CoverSource | 'todas')} disabled={busy}><option value="todas">Todas as fontes</option><option value="steam">Steam</option><option value="wikipedia">Wikipedia</option></select>
      <Button variant="secondary" disabled={busy || searching} onClick={() => void search(text, source)}><Search size={16} /> {error ? 'Tentar de novo' : 'Buscar de novo'}</Button>
    </div>
    {error && <p role="alert" className="form-error">{error}</p>}
    {warnings.map(warning => <p key={warning} role="status" className="muted cover-warning">{warning}</p>)}
    {searching && !items && <ul className="cover-results" aria-hidden="true">{[0, 1, 2].map(i => <li key={i}><span className="cover-candidate cover-candidate-loading" /></li>)}</ul>}
    {items && !searching && visible.length === 0 && !error && <p className="muted">Nenhum jogo encontrado para este nome. Tente outro nome, ou use um arquivo local ou um link direto para a capa.</p>}
    {visible.length > 0 && <ul className="cover-results" aria-label="Jogos encontrados">
      {visible.map(item => {
        const key = candidateKey(item);
        const selected = selectedKey === key;
        const meta = [item.ano, platformSummary(item.plataformas)].filter(Boolean).join(' · ');
        return <li key={key}>
          <button type="button" className={`cover-candidate ${selected ? 'is-selected' : ''} ${applying === key ? 'is-applying' : ''}`} disabled={busy || applying !== null} onClick={() => void pick(item)} aria-pressed={selected}
            aria-label={`Usar ${item.titulo}${item.ano ? ` (${item.ano})` : ''}, fonte ${SOURCE_LABELS[item.fonte]}: aplica a capa e preenche os dados do jogo`}>
            <CandidatePreview url={item.previa} onFail={() => setHidden(current => new Set(current).add(item.imagem))} />
            <span className="cover-candidate-caption"><strong>{item.titulo}</strong>{meta && <span className="cover-candidate-meta">{meta}</span>}<small>{SOURCE_LABELS[item.fonte]}{selected ? ' · em uso' : applying === key ? ' · aplicando…' : ''}</small></span>
          </button>
          {failures[key] && <p role="alert" className="cover-candidate-error">{failures[key]} <button type="button" className="link-button" disabled={busy || applying !== null} onClick={() => void pick(item)}>Tentar de novo</button></p>}
          {safeHttpsUrl(item.origem) && <a className="cover-origin" href={safeHttpsUrl(item.origem)} target="_blank" rel="noreferrer noopener" aria-label={`Abrir a página de origem de ${item.titulo}`}><ExternalLink size={13} /> origem</a>}
        </li>;
      })}
    </ul>}
    <p className="muted cover-attribution">Dados e imagens: Steam (Valve); Wikidata (CC0) e Wikipedia (texto CC BY-SA). A imagem de um artigo nem sempre é a capa oficial. A capa escolhida é baixada e guardada só neste computador.</p>
  </section>;
}
