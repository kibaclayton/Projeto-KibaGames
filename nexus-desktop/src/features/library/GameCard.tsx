import { useState, type DragEvent } from 'react';
import { ArrowDown, ArrowUp, FolderInput, MoreHorizontal, Star, Trophy, X } from 'lucide-react';
import type { Collection, Game } from '../../services/api';
import { CoverImage } from './CoverImage';
import { trophies } from './model';

/** Ações do menu do card: mover na ordem manual (teclado/toque) e mover para uma coleção sem arrastar. */
export interface CardMenu {
  collections: Collection[];
  onMoveToCollection: (collectionId: number | null) => void;
  onMove?: (direction: -1 | 1) => void;
  /** Abre o visualizador de conquistas; só oferecido para jogos ligados à Steam ou ao RetroAchievements. */
  onTrophies?: () => void;
  first?: boolean;
  last?: boolean;
}
export interface CardDrag {
  dragging: boolean;
  hint: 'before' | 'after' | null;
  onDragStart: (event: DragEvent<HTMLElement>) => void;
  onDragOver?: (event: DragEvent<HTMLElement>) => void;
  onDrop?: (event: DragEvent<HTMLElement>) => void;
  onDragEnd: () => void;
}

export function GameCard({ game, onOpen, onFavorite, pending = false, list = false, menu, drag }: {
  game: Game; onOpen: () => void; onFavorite: () => void; pending?: boolean; list?: boolean; menu?: CardMenu; drag?: CardDrag;
}) {
  const value = trophies(game.trofeus_obtidos, game.trofeus_total);
  const [open, setOpen] = useState(false);
  const classes = ['game-card', list ? 'list-card' : '', drag?.dragging ? 'is-dragging' : '', drag?.hint ? `drop-${drag.hint}` : ''].filter(Boolean).join(' ');
  return <article className={classes} draggable onDragStart={event => { event.dataTransfer.setData('application/x-nexus-game', String(game.id)); drag?.onDragStart(event); }}
    onDragOver={drag?.onDragOver} onDrop={drag?.onDrop} onDragEnd={drag?.onDragEnd}>
    <button className="game-open" onClick={onOpen} aria-label={`Abrir ${game.nome}`}><CoverImage imageId={game.capa_id} name={game.nome} />
      <div className="game-overlay"><span className="platform-label">{game.plataforma}{game.ainda_jogando ? ' · jogando' : ''}</span><h3>{game.nome}</h3><span className={`trophy-line ${value.platinum ? 'platinum' : ''}`}><Trophy size={14} />{value.platinum ? 'Platinado!' : game.trofeus_total ? `Faltam ${value.remaining} troféus` : 'Troféus não informados'}</span></div>
    </button>
    <button className={`favorite-button ${game.favorito ? 'selected' : ''}`} aria-label={`${game.favorito ? 'Remover' : 'Adicionar'} ${game.nome} ${game.favorito ? 'dos' : 'aos'} favoritos`} aria-pressed={game.favorito} onClick={onFavorite} disabled={pending}><Star size={18} fill={game.favorito ? 'currentColor' : 'none'} /></button>
    {menu && <>
      <button className="card-menu-button" aria-label={`Mais ações para ${game.nome}`} aria-expanded={open} aria-haspopup="menu" onClick={() => setOpen(current => !current)}>{open ? <X size={16} /> : <MoreHorizontal size={18} />}</button>
      {open && <div className="card-menu" role="menu" aria-label={`Ações de ${game.nome}`}>
        {menu.onTrophies && (game.fonte_externa === 'steam' || game.fonte_externa === 'retroachievements') && <button role="menuitem" type="button" onClick={() => { setOpen(false); menu.onTrophies?.(); }}><Trophy size={14} /> Ver troféus</button>}
        {menu.onMove && <><button role="menuitem" type="button" disabled={menu.first} onClick={() => { menu.onMove?.(-1); }}><ArrowUp size={14} /> Mover antes</button><button role="menuitem" type="button" disabled={menu.last} onClick={() => { menu.onMove?.(1); }}><ArrowDown size={14} /> Mover depois</button></>}
        <label className="card-menu-collection"><FolderInput size={14} /> <span>Mover para coleção</span>
          <select className="input" aria-label={`Coleção de ${game.nome}`} value={game.colecao_id ?? ''} onChange={event => { menu.onMoveToCollection(event.target.value ? Number(event.target.value) : null); setOpen(false); }}>
            <option value="">Sem coleção</option>{menu.collections.map(collection => <option key={collection.id} value={collection.id}>{collection.nome}</option>)}
          </select></label>
      </div>}
    </>}
  </article>;
}
