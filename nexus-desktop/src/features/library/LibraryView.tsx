import { useEffect, useRef, useState, type DragEvent, type FormEvent } from 'react';
import { ArrowLeft, ChevronLeft, ChevronRight, FolderInput, FolderPlus, Gamepad2, Grid2X2, List, MoreHorizontal, Plus, Search, Sparkles, Star, Trophy } from 'lucide-react';
import { Button, Modal, Panel } from '../../components/ui';
import { useBackend } from '../../services/BackendProvider';
import type { Collection, Game, GameSort } from '../../services/api';
import { CoverImage } from './CoverImage';
import { FavoriteSpotlight } from './FavoriteSpotlight';
import { GameCard } from './GameCard';
import { GameEditor } from './GameEditor';

type Sort = Exclude<GameSort, 'colecao'>;
const SORTS: [Sort, string][] = [['minha', 'Minha ordem'], ['nome', 'Nome'], ['recentes', 'Mais recentes'], ['progresso', 'Progresso']];
const FULL_VIEW = 100;
const sortKey = 'nexus-wolfs:ordenacao';
function initialSort(): Sort { try { const saved = localStorage.getItem(sortKey); return SORTS.some(([v]) => v === saved) ? saved as Sort : 'minha'; } catch { return 'minha'; } }

/**
 * Biblioteca (jogos, busca, filtros, ordem manual), Coleções (pastas; abrir mostra só os jogos da pasta) e Favoritos
 * (0 = orientação, 1 = painel amplo, 2+ = cards comparáveis). Arrastar reordena só em "Minha ordem" na visualização
 * completa; soltar sobre a faixa de coleções move o jogo para a pasta; o menu do card faz o mesmo sem mouse.
 */
export function LibraryView({ section, onLogin }: { section: 'library' | 'favorites' | 'collections'; onLogin: () => void }) {
  const { session, api, summary, refreshSummary, restoring } = useBackend();
  const [search, setSearch] = useState('');
  const [query, setQuery] = useState('');
  const [genre, setGenre] = useState('');
  const [page, setPage] = useState(1);
  const [layout, setLayout] = useState<'grid' | 'list'>('grid');
  const [sort, setSort] = useState<Sort>(initialSort);
  const [games, setGames] = useState<Game[]>([]);
  const [total, setTotal] = useState(0);
  const [collections, setCollections] = useState<Collection[]>([]);
  const [collectionId, setCollectionId] = useState<number | null>(null);
  const [highlights, setHighlights] = useState<Game[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [revision, setRevision] = useState(0);
  const [editor, setEditor] = useState<{ id: number | null } | null>(null);
  const [spotlight, setSpotlight] = useState<number | null>(null);
  const [collectionEditor, setCollectionEditor] = useState<{ id: number | null; name: string; cover: string | null } | null>(null);
  const [deleteCollection, setDeleteCollection] = useState(false);
  const [pending, setPending] = useState<number | null>(null);
  const [collectionBusy, setCollectionBusy] = useState(false);
  const [collectionError, setCollectionError] = useState('');
  const [dragging, setDragging] = useState<number | null>(null);
  const [dropHint, setDropHint] = useState<{ id: number; where: 'before' | 'after' } | null>(null);
  const [dragOverCollection, setDragOverCollection] = useState<number | null>(null);
  const [orderNote, setOrderNote] = useState('');
  const previousOrder = useRef<Game[] | null>(null);

  const favorites = section === 'favorites';
  const inCollection = section === 'collections' && collectionId !== null;
  const manual = section === 'library' && sort === 'minha' && !query && !genre;
  const limit = favorites || manual ? FULL_VIEW : 20;
  const canReorder = manual && !loading && total <= FULL_VIEW && games.length === total && total > 1;
  const favoritesTotal = summary?.favoritos ?? total;

  useEffect(() => { const timer = setTimeout(() => { setQuery(search); setPage(1); }, 300); return () => clearTimeout(timer); }, [search]);
  useEffect(() => { try { localStorage.setItem(sortKey, sort); } catch { /* preferência de dispositivo opcional */ } }, [sort]);
  useEffect(() => {
    if (!session) return;
    const controller = new AbortController();
    setLoading(true); setError(''); setGames([]);
    const listGames = section === 'collections' && collectionId === null
      ? Promise.resolve({ itens: [] as Game[], total: 0 })
      : api.games({ busca: query, genero: genre, favorito: favorites, colecao_id: inCollection ? collectionId ?? undefined : undefined, pagina: page, limite: limit, ordenacao: inCollection ? 'colecao' : favorites ? 'nome' : sort }, controller.signal);
    Promise.all([listGames, api.collections(), section === 'library' ? api.highlights(controller.signal) : Promise.resolve([] as Game[])])
      .then(([result, folders, featured]) => { if (controller.signal.aborted) return; setPage(current => Math.min(current, Math.max(1, Math.ceil(result.total / limit)))); setGames(result.itens); setTotal(result.total); setCollections(folders); setHighlights(featured); })
      .catch(cause => { if (!controller.signal.aborted) setError(cause.message); })
      .finally(() => { if (!controller.signal.aborted) setLoading(false); });
    return () => controller.abort();
  }, [api, session, query, genre, page, collectionId, revision, section, sort, limit, favorites, inCollection]);

  function changed() { setEditor(null); setRevision(value => value + 1); void refreshSummary(); }
  async function favorite(game: Game) {
    setPending(game.id); setError('');
    try { await api.patchGame(game.id, { favorito: !game.favorito }); setRevision(n => n + 1); void refreshSummary(); }
    catch (cause) { setError((cause as Error).message); }
    finally { setPending(null); }
  }
  async function moveToCollection(gameId: number, targetId: number | null) {
    setDragOverCollection(null); setError('');
    try { await api.patchGame(gameId, { colecao_id: targetId, grupo: '' }); setRevision(n => n + 1); void refreshSummary(); }
    catch (cause) { setError((cause as Error).message); }
  }
  async function reorder(next: Game[]) {
    previousOrder.current = games;
    setGames(next); setOrderNote('');
    try { await api.reorderGames(next.map(game => game.id)); setOrderNote('Ordem salva.'); }
    catch (cause) { setGames(previousOrder.current ?? next); setOrderNote(`A ordem não foi salva: ${(cause as Error).message}`); }
  }
  function move(gameId: number, direction: -1 | 1) {
    const index = games.findIndex(game => game.id === gameId);
    const target = index + direction;
    if (index < 0 || target < 0 || target >= games.length) return;
    const next = [...games];
    [next[index], next[target]] = [next[target], next[index]];
    void reorder(next);
  }
  function dropOnCard(event: DragEvent<HTMLElement>, targetId: number) {
    event.preventDefault();
    const hint = dropHint;
    setDropHint(null); setDragging(null);
    const sourceId = Number(event.dataTransfer.getData('application/x-nexus-game'));
    if (!canReorder || !sourceId || sourceId === targetId || !hint) return;
    const without = games.filter(game => game.id !== sourceId);
    const moving = games.find(game => game.id === sourceId);
    const targetIndex = without.findIndex(game => game.id === targetId);
    if (!moving || targetIndex < 0) return;
    without.splice(hint.where === 'after' ? targetIndex + 1 : targetIndex, 0, moving);
    void reorder(without);
  }
  function dragFor(game: Game) {
    return {
      dragging: dragging === game.id,
      hint: dropHint?.id === game.id ? dropHint.where : null,
      onDragStart: () => setDragging(game.id),
      onDragOver: canReorder ? (event: DragEvent<HTMLElement>) => {
        if (dragging === null || dragging === game.id) return;
        event.preventDefault();
        const box = event.currentTarget.getBoundingClientRect();
        const after = layout === 'list' ? event.clientY > box.top + box.height / 2 : event.clientX > box.left + box.width / 2;
        setDropHint({ id: game.id, where: after ? 'after' : 'before' });
      } : undefined,
      onDrop: canReorder ? (event: DragEvent<HTMLElement>) => dropOnCard(event, game.id) : undefined,
      onDragEnd: () => { setDragging(null); setDropHint(null); setDragOverCollection(null); },
    };
  }
  async function saveCollection(event: FormEvent) {
    event.preventDefault(); if (!collectionEditor) return; setCollectionBusy(true); setCollectionError('');
    try {
      if (collectionEditor.id === null) await api.createCollection(collectionEditor.name.trim());
      else await api.updateCollection(collectionEditor.id, collectionEditor.name.trim(), collectionEditor.cover);
      setCollectionEditor(null); setRevision(n => n + 1); void refreshSummary();
    } catch (cause) { setCollectionError((cause as Error).message); }
    finally { setCollectionBusy(false); }
  }
  const openCollectionEditor = (collection?: Collection) => { setCollectionEditor(collection ? { id: collection.id, name: collection.nome, cover: collection.capa_id } : { id: null, name: '', cover: null }); setDeleteCollection(false); setCollectionError(''); };

  if (!session && restoring) return <Panel className="empty-state" aria-busy="true"><div className="empty-icon"><Gamepad2 size={30} /></div><h2>Entrando…</h2><p role="status">Reconhecendo o perfil lembrado neste aparelho.</p></Panel>;
  if (!session) return <Panel className="empty-state"><div className="empty-icon"><Gamepad2 size={30} /></div><h2>Seu próximo mundo está aqui</h2><p>Selecione seu perfil para explorar seus jogos e coleções.</p><Button variant="primary" onClick={onLogin}>Escolher meu perfil</Button></Panel>;
  const selectedCollection = collections.find(c => c.id === collectionId);
  const featured = highlights[0];
  const editorModal = editor && <GameEditor gameId={editor.id} collections={collections} onClose={() => setEditor(null)} onSaved={changed} />;
  const collectionModal = collectionEditor && <Modal open title={collectionEditor.id === null ? 'Criar coleção' : 'Editar coleção'} onClose={() => { if (!collectionBusy) setCollectionEditor(null); }}><form onSubmit={saveCollection}>{collectionError && <p role="alert" className="form-error">{collectionError}</p>}<label htmlFor="collection-name" className="field-label">Nome da coleção</label><input className="input" id="collection-name" value={collectionEditor.name} maxLength={150} required disabled={collectionBusy} onChange={e => setCollectionEditor({ ...collectionEditor, name: e.target.value })} /><div className="control-row"><Button type="submit" variant="primary" disabled={collectionBusy || !collectionEditor.name.trim()}>Salvar coleção</Button>{collectionEditor.id !== null && <Button disabled={collectionBusy} onClick={() => setDeleteCollection(true)}>Excluir coleção</Button>}</div>{deleteCollection && <div className="confirm-box" role="alert"><p>Excluir esta coleção? Seus jogos serão mantidos na biblioteca.</p><Button disabled={collectionBusy} onClick={async () => { if (collectionEditor.id === null) return; setCollectionBusy(true); try { await api.deleteCollection(collectionEditor.id); if (collectionId === collectionEditor.id) setCollectionId(null); setCollectionEditor(null); changed(); } catch (cause) { setCollectionError((cause as Error).message); } finally { setCollectionBusy(false); } }}>Confirmar exclusão</Button><Button disabled={collectionBusy} onClick={() => setDeleteCollection(false)}>Manter coleção</Button></div>}</form></Modal>;
  const grid = (withMenu: boolean, onOpen: (game: Game) => void) => <div className={layout === 'grid' ? 'game-grid' : 'game-list'}>{games.map((game, index) => <GameCard key={game.id} game={game} list={layout === 'list'} pending={pending !== null} onOpen={() => onOpen(game)} onFavorite={() => void favorite(game)}
    menu={withMenu ? { collections, onMoveToCollection: target => void moveToCollection(game.id, target), onMove: canReorder ? direction => move(game.id, direction) : undefined, first: index === 0, last: index === games.length - 1 } : undefined}
    drag={withMenu ? dragFor(game) : undefined} />)}</div>;
  const skeleton = <div className="game-grid" aria-label="Carregando jogos" aria-busy="true">{Array.from({ length: 6 }, (_, i) => <div className="card-skeleton" key={i} />)}</div>;

  // --- Favoritos: 0, 1 ou vários -----------------------------------------------------------------------------------
  if (favorites) {
    const single = favoritesTotal === 1 ? games[0]?.id ?? null : null;
    const shown = spotlight ?? single;
    return <div className="library-view">
      {error && <div role="alert" className="form-error">{error}<Button onClick={() => setRevision(n => n + 1)}>Tentar novamente</Button></div>}
      {loading && !games.length ? skeleton
        : favoritesTotal === 0 ? <Panel className="empty-state"><div className="empty-icon"><Star size={28} /></div><h3>Seus favoritos vão aparecer aqui</h3><p>Toque na estrela de uma capa na Biblioteca para acompanhar um jogo de perto. Com um só favorito, ele ganha um painel amplo; com vários, cards para comparar.</p></Panel>
        : shown !== null ? <FavoriteSpotlight gameId={shown} collections={collections} onBack={favoritesTotal > 1 ? () => setSpotlight(null) : undefined} onEdit={() => setEditor({ id: shown })} onChanged={() => { setRevision(n => n + 1); void refreshSummary(); }} />
        : <>
          <div className="filter-row"><p className="muted">{favoritesTotal} favoritos. Toque num card para abrir a visão ampla.</p><div className="layout-switch" aria-label="Visualização"><Button variant="ghost" aria-label="Grade de capas" aria-pressed={layout === 'grid'} onClick={() => setLayout('grid')}><Grid2X2 size={17} /></Button><Button variant="ghost" aria-label="Lista de jogos" aria-pressed={layout === 'list'} onClick={() => setLayout('list')}><List size={17} /></Button></div></div>
          {grid(false, game => setSpotlight(game.id))}
        </>}
      {editorModal}
    </div>;
  }

  // --- Coleções: pastas na entrada; jogos só dentro da pasta aberta ------------------------------------------------
  if (section === 'collections') {
    return <div className="library-view">
      {error && <div role="alert" className="form-error">{error}<Button onClick={() => setRevision(n => n + 1)}>Tentar novamente</Button></div>}
      {selectedCollection ? <>
        <div className="section-heading"><Button variant="ghost" onClick={() => { setCollectionId(null); setPage(1); }}><ArrowLeft size={16} /> Todas as coleções</Button><h2>{selectedCollection.nome}</h2><Button variant="ghost" aria-label={`Gerenciar coleção ${selectedCollection.nome}`} onClick={() => openCollectionEditor(selectedCollection)}><MoreHorizontal size={18} /> Gerenciar</Button></div>
        <p className="muted collection-hint">{selectedCollection.total} jogos nesta coleção, na ordem da série. Para tirar um jogo daqui, use o menu do card ou o editor.</p>
        {loading ? skeleton : games.length ? grid(true, game => setEditor({ id: game.id })) : <Panel className="empty-state"><div className="empty-icon"><FolderInput size={28} /></div><h3>Coleção vazia</h3><p>Na Biblioteca, use o menu de um card ou arraste a capa até esta coleção.</p></Panel>}
        <nav className="pagination" aria-label="Páginas de jogos"><Button disabled={page <= 1 || loading} onClick={() => setPage(p => p - 1)}><ChevronLeft size={16} /> Anterior</Button><span>Página {page} de {Math.max(1, Math.ceil(total / limit))}</span><Button disabled={page * limit >= total || loading} onClick={() => setPage(p => p + 1)}>Próxima <ChevronRight size={16} /></Button></nav>
      </> : <section className="collections-section">
        <div className="section-heading"><h2>Suas coleções</h2><Button variant="primary" onClick={() => openCollectionEditor()}><FolderPlus size={16} /> Criar coleção</Button></div>
        <div className="collection-grid"><button className="new-collection" onClick={() => openCollectionEditor()}><Plus size={26} /><span>Criar coleção</span></button>{collections.map(collection => <article key={collection.id} className="collection-card"><button className="collection-open" onClick={() => { setCollectionId(collection.id); setPage(1); }} aria-label={`Abrir coleção ${collection.nome}`}><div className="collection-mosaic">{(collection.capa_id ? [collection.capa_id] : collection.mosaico.length ? collection.mosaico : [null]).map((id, index) => <CoverImage imageId={id} name={collection.nome} key={index} />)}</div><div className="collection-caption"><strong>{collection.nome}</strong><small>{collection.total} jogos</small></div></button><button className="collection-menu" aria-label={`Gerenciar coleção ${collection.nome}`} onClick={() => openCollectionEditor(collection)}><MoreHorizontal size={20} /></button></article>)}</div>
        {collections.length === 0 && <p className="collection-hint">Crie uma coleção e depois mova jogos para ela pela Biblioteca (menu do card ou arrastando a capa).</p>}
      </section>}
      {editorModal}{collectionModal}
    </div>;
  }

  // --- Biblioteca ----------------------------------------------------------------------------------------------------
  return <div className="library-view">
    {featured && !query && <section className="featured-game"><CoverImage imageId={featured.capa_id} name={featured.nome} /><div className="featured-copy"><span className="eyebrow"><Sparkles size={14} /> CONTINUE SUA JORNADA</span><h2>{featured.nome}</h2><p>{featured.plataforma} · {featured.progresso}% concluído</p><Button variant="primary" onClick={() => setEditor({ id: featured.id })}>Continuar acompanhando <ChevronRight size={16} /></Button></div><div className="featured-percent" aria-hidden="true">{featured.progresso}<span>%</span></div></section>}
    <div className="library-toolbar"><div className="search-field"><Search size={18} /><input type="search" aria-label="Buscar jogos" placeholder="Encontre seu próximo universo…" value={search} onChange={e => setSearch(e.target.value)} /></div>
      <label className="sort-field"><span className="muted">Ordenar por</span><select className="input" aria-label="Ordenar por" value={sort} onChange={e => { setSort(e.target.value as Sort); setPage(1); }}>{SORTS.map(([value, label]) => <option key={value} value={value}>{label}</option>)}</select></label>
      <div className="layout-switch" aria-label="Visualização"><Button variant="ghost" aria-label="Grade de capas" aria-pressed={layout === 'grid'} onClick={() => setLayout('grid')}><Grid2X2 size={17} /></Button><Button variant="ghost" aria-label="Lista de jogos" aria-pressed={layout === 'list'} onClick={() => setLayout('list')}><List size={17} /></Button></div><Button variant="primary" onClick={() => setEditor({ id: null })}><Plus size={17} /> Adicionar jogo</Button></div>
    <div className="filter-row"><div className="genre-chips" aria-label="Gêneros">{['', 'RPG', 'Ação', 'FPS', 'Aventura', 'Terror', 'Estratégia'].map(value => <button key={value} className={`chip ${genre === value ? 'selected' : ''}`} aria-pressed={genre === value} onClick={() => { setGenre(value); setPage(1); }}>{value || 'Todos'}</button>)}</div><span className="muted">{loading ? 'Carregando…' : `${total} jogo${total !== 1 ? 's' : ''}`}</span></div>
    {sort === 'minha' && <p className="muted order-hint" role="status">{canReorder ? `Arraste uma capa para antes ou depois de outra, ou use o menu do card (Mover antes/depois). ${orderNote}` : manual && total > FULL_VIEW ? `Sua biblioteca tem mais de ${FULL_VIEW} jogos: reordene pelo menu do card.` : query || genre ? 'Arrastar para reordenar fica desligado com busca ou filtro ativo; limpe-os para reordenar.' : orderNote}</p>}
    {dragging !== null && collections.length > 0 && <div className="collection-drop-bar" role="group" aria-label="Soltar numa coleção">{collections.map(collection => <div key={collection.id} className={`collection-drop ${dragOverCollection === collection.id ? 'drop-target' : ''}`} onDragOver={event => { event.preventDefault(); setDragOverCollection(collection.id); }} onDragLeave={() => setDragOverCollection(null)} onDrop={event => { event.preventDefault(); const id = Number(event.dataTransfer.getData('application/x-nexus-game')); setDragging(null); setDropHint(null); if (id) void moveToCollection(id, collection.id); }}><FolderInput size={14} /> {collection.nome}</div>)}</div>}
    {error && <div role="alert" className="form-error">{error}<Button onClick={() => setRevision(n => n + 1)}>Tentar novamente</Button></div>}
    {loading ? skeleton : games.length ? grid(true, game => setEditor({ id: game.id })) : !error && <Panel className="empty-state"><div className="empty-icon"><Trophy size={28} /></div><h3>{query || genre ? 'Nenhum jogo encontrado' : 'Uma nova aventura começa com um jogo'}</h3><p>{query || genre ? 'Experimente outro nome ou gênero.' : 'Adicione seu primeiro jogo e acompanhe cada conquista.'}</p><Button onClick={() => setEditor({ id: null })}>Adicionar jogo</Button></Panel>}
    {!(manual && total <= FULL_VIEW) && <nav className="pagination" aria-label="Páginas de jogos"><Button disabled={page <= 1 || loading} onClick={() => setPage(p => p - 1)}><ChevronLeft size={16} /> Anterior</Button><span>Página {page} de {Math.max(1, Math.ceil(total / limit))}</span><Button disabled={page * limit >= total || loading} onClick={() => setPage(p => p + 1)}>Próxima <ChevronRight size={16} /></Button></nav>}
    {editorModal}{collectionModal}
  </div>;
}
