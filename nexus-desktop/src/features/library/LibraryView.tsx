import { useEffect, useState, type FormEvent } from 'react';
import { ArrowLeft, ChevronLeft, ChevronRight, FolderPlus, Gamepad2, Grid2X2, List, MoreHorizontal, Plus, Search, Sparkles, Trophy } from 'lucide-react';
import { Button, Modal, Panel } from '../../components/ui';
import { useBackend } from '../../services/BackendProvider';
import type { Collection, Game } from '../../services/api';
import { CoverImage } from './CoverImage';
import { GameCard } from './GameCard';
import { GameEditor } from './GameEditor';

export function LibraryView({ section, onLogin }: { section: 'library' | 'favorites' | 'collections'; onLogin: () => void }) {
  const { session, api, refreshSummary, restoring } = useBackend();
  const [search, setSearch] = useState('');
  const [query, setQuery] = useState('');
  const [genre, setGenre] = useState('');
  const [page, setPage] = useState(1);
  const [layout, setLayout] = useState<'grid' | 'list'>('grid');
  const [games, setGames] = useState<Game[]>([]);
  const [total, setTotal] = useState(0);
  const [collections, setCollections] = useState<Collection[]>([]);
  const [collectionId, setCollectionId] = useState<number | null>(null);
  const [highlights, setHighlights] = useState<Game[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [revision, setRevision] = useState(0);
  const [editor, setEditor] = useState<{ id: number | null } | null>(null);
  const [collectionEditor, setCollectionEditor] = useState<{ id: number | null; name: string; cover: string | null } | null>(null);
  const [deleteCollection, setDeleteCollection] = useState(false);
  const [pending, setPending] = useState<number | null>(null);
  const [collectionBusy, setCollectionBusy] = useState(false);
  const [collectionError, setCollectionError] = useState('');
  const [dragOver, setDragOver] = useState<number | null>(null);
  const limit = 20;

  useEffect(() => { const timer = setTimeout(() => { setQuery(search); setPage(1); }, 300); return () => clearTimeout(timer); }, [search]);
  useEffect(() => {
    if (!session) return;
    const controller = new AbortController();
    setLoading(true); setError(''); setGames([]);
    Promise.all([api.games({ busca: query, genero: genre, favorito: section === 'favorites', colecao_id: collectionId ?? undefined, pagina: page, limite: limit }, controller.signal), api.collections(), api.highlights(controller.signal)])
      .then(([result, folders, featured]) => { if (controller.signal.aborted) return; setPage(current => Math.min(current, Math.max(1, Math.ceil(result.total / limit)))); setGames(result.itens); setTotal(result.total); setCollections(folders); setHighlights(featured); })
      .catch(cause => { if (!controller.signal.aborted) setError(cause.message); })
      .finally(() => { if (!controller.signal.aborted) setLoading(false); });
    return () => controller.abort();
  }, [api, session, query, genre, page, collectionId, revision, section]);

  function changed() { setEditor(null); setRevision(value => value + 1); void refreshSummary(); }
  async function favorite(game: Game) {
    setPending(game.id); setError('');
    try { await api.patchGame(game.id, { favorito: !game.favorito }); setRevision(n => n + 1); void refreshSummary(); }
    catch (cause) { setError((cause as Error).message); }
    finally { setPending(null); }
  }
  async function drop(gameId: string, targetId: number) {
    setDragOver(null);
    if (!/^\d+$/.test(gameId)) return;
    try { await api.patchGame(Number(gameId), { colecao_id: targetId, grupo: '' }); changed(); }
    catch (cause) { setError((cause as Error).message); }
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

  if (!session && restoring) return <Panel className="empty-state" aria-busy="true"><div className="empty-icon"><Gamepad2 size={30} /></div><h2>Entrando…</h2><p role="status">Reconhecendo o perfil lembrado neste aparelho.</p></Panel>;
  if (!session) return <Panel className="empty-state"><div className="empty-icon"><Gamepad2 size={30} /></div><h2>Seu próximo mundo está aqui</h2><p>Selecione seu perfil para explorar seus jogos e coleções.</p><Button variant="primary" onClick={onLogin}>Escolher meu perfil</Button></Panel>;
  const selectedCollection = collections.find(c => c.id === collectionId);
  const featured = highlights[0];

  return <div className="library-view">
    {section === 'library' && featured && !query && !collectionId && <section className="featured-game"><CoverImage imageId={featured.capa_id} name={featured.nome} /><div className="featured-copy"><span className="eyebrow"><Sparkles size={14} /> CONTINUE SUA JORNADA</span><h2>{featured.nome}</h2><p>{featured.plataforma} · {featured.progresso}% concluído</p><Button variant="primary" onClick={() => setEditor({ id: featured.id })}>Continuar acompanhando <ChevronRight size={16} /></Button></div><div className="featured-percent" aria-hidden="true">{featured.progresso}<span>%</span></div></section>}
    <div className="library-toolbar"><div className="search-field"><Search size={18} /><input type="search" aria-label="Buscar jogos" placeholder="Encontre seu próximo universo…" value={search} onChange={e => setSearch(e.target.value)} /></div><div className="layout-switch" aria-label="Visualização"><Button variant="ghost" aria-label="Grade de capas" aria-pressed={layout === 'grid'} onClick={() => setLayout('grid')}><Grid2X2 size={17} /></Button><Button variant="ghost" aria-label="Lista de jogos" aria-pressed={layout === 'list'} onClick={() => setLayout('list')}><List size={17} /></Button></div><Button variant="primary" onClick={() => setEditor({ id: null })}><Plus size={17} /> Adicionar jogo</Button></div>
    <div className="filter-row"><div className="genre-chips" aria-label="Gêneros">{['', 'RPG', 'Ação', 'FPS', 'Aventura', 'Terror', 'Estratégia'].map(value => <button key={value} className={`chip ${genre === value ? 'selected' : ''}`} aria-pressed={genre === value} onClick={() => { setGenre(value); setPage(1); }}>{value || 'Todos'}</button>)}</div><span className="muted">{loading ? 'Carregando…' : `${total} jogo${total !== 1 ? 's' : ''}`}</span></div>
    {(section === 'collections' || collections.length > 0) && <section className="collections-section"><div className="section-heading"><h2>Coleções</h2><Button variant="ghost" onClick={() => { setCollectionEditor({ id: null, name: '', cover: null }); setDeleteCollection(false); setCollectionError(''); }}><FolderPlus size={16} /> Criar coleção</Button></div><div className="collection-grid"><button className="new-collection" onClick={() => { setCollectionEditor({ id: null, name: '', cover: null }); setDeleteCollection(false); setCollectionError(''); }}><Plus size={26} /><span>Criar coleção</span></button>{collections.map(collection => <article key={collection.id} className={`collection-card ${dragOver === collection.id ? 'drop-target' : ''}`} onDragOver={event => { event.preventDefault(); setDragOver(collection.id); }} onDragLeave={() => setDragOver(null)} onDrop={event => { event.preventDefault(); void drop(event.dataTransfer.getData('application/x-nexus-game'), collection.id); }}><button className="collection-open" onClick={() => { setCollectionId(collection.id); setPage(1); }} aria-label={`Abrir coleção ${collection.nome}`}><div className="collection-mosaic">{(collection.capa_id ? [collection.capa_id] : collection.mosaico.length ? collection.mosaico : [null]).map((id, index) => <CoverImage imageId={id} name={collection.nome} key={index} />)}</div><div className="collection-caption"><strong>{collection.nome}</strong><small>{collection.total} jogos</small></div></button><button className="collection-menu" aria-label={`Gerenciar coleção ${collection.nome}`} onClick={() => { setCollectionEditor({ id: collection.id, name: collection.nome, cover: collection.capa_id }); setDeleteCollection(false); setCollectionError(''); }}><MoreHorizontal size={20} /></button></article>)}</div><p className="collection-hint">Arraste uma capa até a coleção ou escolha a coleção ao editar o jogo.</p></section>}
    {selectedCollection && <div className="section-heading"><Button variant="ghost" onClick={() => { setCollectionId(null); setPage(1); }}><ArrowLeft size={16} /> Todos os jogos</Button><h2>{selectedCollection.nome}</h2></div>}
    {error && <div role="alert" className="form-error">{error}<Button onClick={() => setRevision(n => n + 1)}>Tentar novamente</Button></div>}
    {loading ? <div className="game-grid" aria-label="Carregando jogos" aria-busy="true">{Array.from({ length: 6 }, (_, i) => <div className="card-skeleton" key={i} />)}</div> : games.length ? <div className={layout === 'grid' ? 'game-grid' : 'game-list'}>{games.map(game => <GameCard key={game.id} game={game} list={layout === 'list'} pending={pending !== null} onOpen={() => setEditor({ id: game.id })} onFavorite={() => void favorite(game)} />)}</div> : !error && <Panel className="empty-state"><div className="empty-icon"><Trophy size={28} /></div><h3>{query || genre ? 'Nenhum jogo encontrado' : section === 'favorites' ? 'Seus favoritos vão aparecer aqui' : 'Uma nova aventura começa com um jogo'}</h3><p>{query || genre ? 'Experimente outro nome ou gênero.' : section === 'favorites' ? 'Toque na estrela de uma capa para guardar seus preferidos.' : 'Adicione seu primeiro jogo e acompanhe cada conquista.'}</p><Button onClick={() => setEditor({ id: null })}>Adicionar jogo</Button></Panel>}
    <nav className="pagination" aria-label="Páginas de jogos"><Button disabled={page <= 1 || loading} onClick={() => setPage(p => p - 1)}><ChevronLeft size={16} /> Anterior</Button><span>Página {page} de {Math.max(1, Math.ceil(total / limit))}</span><Button disabled={page * limit >= total || loading} onClick={() => setPage(p => p + 1)}>Próxima <ChevronRight size={16} /></Button></nav>
    {editor && <GameEditor gameId={editor.id} collections={collections} onClose={() => setEditor(null)} onSaved={changed} />}
    {collectionEditor && <Modal open title={collectionEditor.id === null ? 'Criar coleção' : 'Editar coleção'} onClose={() => { if (!collectionBusy) setCollectionEditor(null); }}><form onSubmit={saveCollection}>{collectionError && <p role="alert" className="form-error">{collectionError}</p>}<label htmlFor="collection-name" className="field-label">Nome da coleção</label><input className="input" id="collection-name" value={collectionEditor.name} maxLength={150} required disabled={collectionBusy} onChange={e => setCollectionEditor({ ...collectionEditor, name: e.target.value })} /><div className="control-row"><Button type="submit" variant="primary" disabled={collectionBusy || !collectionEditor.name.trim()}>Salvar coleção</Button>{collectionEditor.id !== null && <Button disabled={collectionBusy} onClick={() => setDeleteCollection(true)}>Excluir coleção</Button>}</div>{deleteCollection && <div className="confirm-box" role="alert"><p>Excluir esta coleção? Seus jogos serão mantidos na biblioteca.</p><Button disabled={collectionBusy} onClick={async () => { if (collectionEditor.id === null) return; setCollectionBusy(true); try { await api.deleteCollection(collectionEditor.id); if (collectionId === collectionEditor.id) setCollectionId(null); setCollectionEditor(null); changed(); } catch (cause) { setCollectionError((cause as Error).message); } finally { setCollectionBusy(false); } }}>Confirmar exclusão</Button><Button disabled={collectionBusy} onClick={() => setDeleteCollection(false)}>Manter coleção</Button></div>}</form></Modal>}
  </div>;
}
