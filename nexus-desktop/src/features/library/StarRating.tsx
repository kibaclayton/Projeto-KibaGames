import { Star } from 'lucide-react';

/** Nota pessoal de 1 a 5 estrelas; clicar na estrela atual limpa a nota. Teclado: setas mudam, Delete limpa. */
export function StarRating({ value, onChange, labelledBy, size = 22 }: { value: number | null; onChange?: (value: number | null) => void; labelledBy?: string; size?: number }) {
  const readOnly = !onChange;
  return <div className={`star-rating ${readOnly ? 'is-readonly' : ''}`} role={readOnly ? 'img' : 'radiogroup'} aria-labelledby={labelledBy} aria-label={readOnly ? `Nota ${value ?? 'não informada'}` : undefined}
    onKeyDown={event => {
      if (readOnly) return;
      if (event.key === 'ArrowRight' || event.key === 'ArrowUp') { event.preventDefault(); onChange(Math.min(5, (value ?? 0) + 1)); }
      if (event.key === 'ArrowLeft' || event.key === 'ArrowDown') { event.preventDefault(); onChange(value && value > 1 ? value - 1 : null); }
      if (event.key === 'Delete' || event.key === 'Backspace') { event.preventDefault(); onChange(null); }
    }}>
    {[1, 2, 3, 4, 5].map(star => <button key={star} type="button" role={readOnly ? undefined : 'radio'} aria-checked={readOnly ? undefined : value === star} aria-label={`${star} estrela${star === 1 ? '' : 's'}`}
      className={`star ${value !== null && star <= value ? 'is-on' : ''}`} tabIndex={readOnly ? -1 : star === (value ?? 1) ? 0 : -1} disabled={readOnly}
      onClick={() => onChange?.(value === star ? null : star)}><Star size={size} /></button>)}
    {!readOnly && <span className="muted star-rating-text">{value ? `${value} de 5` : 'sem nota'}</span>}
  </div>;
}
