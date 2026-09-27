import { Star, Trophy } from 'lucide-react';
import type { Game } from '../../services/api';
import { CoverImage } from './CoverImage';
import { trophies } from './model';

export function GameCard({ game, onOpen, onFavorite, pending = false, list = false }: {
  game: Game; onOpen: () => void; onFavorite: () => void; pending?: boolean; list?: boolean;
}) {
  const value = trophies(game.trofeus_obtidos, game.trofeus_total);
  return <article className={`game-card ${list ? 'list-card' : ''}`} draggable onDragStart={event => { event.dataTransfer.setData('application/x-nexus-game', String(game.id)); }}>
    <button className="game-open" onClick={onOpen} aria-label={`Abrir ${game.nome}`}><CoverImage imageId={game.capa_id} name={game.nome} />
      <div className="game-overlay"><span className="platform-label">{game.plataforma}</span><h3>{game.nome}</h3><span className={`trophy-line ${value.platinum ? 'platinum' : ''}`}><Trophy size={14} />{value.platinum ? 'Platinado!' : game.trofeus_total ? `Faltam ${value.remaining} troféus` : 'Troféus não informados'}</span></div>
    </button>
    <button className={`favorite-button ${game.favorito ? 'selected' : ''}`} aria-label={`${game.favorito ? 'Remover' : 'Adicionar'} ${game.nome} ${game.favorito ? 'dos' : 'aos'} favoritos`} aria-pressed={game.favorito} onClick={onFavorite} disabled={pending}><Star size={18} fill={game.favorito ? 'currentColor' : 'none'} /></button>
  </article>;
}
