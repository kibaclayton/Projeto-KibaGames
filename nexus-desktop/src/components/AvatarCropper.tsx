import { useEffect, useRef, useState, type KeyboardEvent, type PointerEvent } from 'react';
import { Check, X, ZoomIn } from 'lucide-react';
import { Button } from './ui';
import { MAX_ZOOM, MIN_ZOOM, centeredOffset, clampOffset, cropRect, displayScale, zoomAround, type CropRect, type CropState } from '../features/account/model';

const VIEWPORT = 280;
const STEP = 12;

/** Recorte quadrado com arraste e zoom; a área circular mostra como a foto vai aparecer. Sem bibliotecas externas. */
export function AvatarCropper({ file, busy, onConfirm, onCancel }: { file: File; busy: boolean; onConfirm: (crop: CropRect) => void; onCancel: () => void }) {
  const [url, setUrl] = useState<string | null>(null);
  const [state, setState] = useState<CropState | null>(null);
  const [error, setError] = useState('');
  const drag = useRef<{ pointerId: number; startX: number; startY: number; offsetX: number; offsetY: number } | null>(null);
  useEffect(() => {
    const objectUrl = URL.createObjectURL(file);
    setUrl(objectUrl); setState(null); setError('');
    return () => URL.revokeObjectURL(objectUrl);
  }, [file]);

  function loaded(image: HTMLImageElement) {
    const { naturalWidth, naturalHeight } = image;
    if (!naturalWidth || !naturalHeight) { setError('Não foi possível ler esta imagem.'); return; }
    setState({ viewport: VIEWPORT, naturalWidth, naturalHeight, zoom: 1, ...centeredOffset(VIEWPORT, naturalWidth, naturalHeight) });
  }
  function move(deltaX: number, deltaY: number) {
    setState(current => current ? { ...current, ...clampOffset({ ...current, offsetX: current.offsetX + deltaX, offsetY: current.offsetY + deltaY }) } : current);
  }
  function pointerDown(event: PointerEvent<HTMLDivElement>) {
    if (!state || event.button !== 0) return;
    event.currentTarget.setPointerCapture(event.pointerId);
    drag.current = { pointerId: event.pointerId, startX: event.clientX, startY: event.clientY, offsetX: state.offsetX, offsetY: state.offsetY };
  }
  function pointerMove(event: PointerEvent<HTMLDivElement>) {
    const current = drag.current;
    if (!current || current.pointerId !== event.pointerId) return;
    setState(value => value ? { ...value, ...clampOffset({ ...value, offsetX: current.offsetX + event.clientX - current.startX, offsetY: current.offsetY + event.clientY - current.startY }) } : value);
  }
  function pointerUp() { drag.current = null; }
  function keyDown(event: KeyboardEvent<HTMLDivElement>) {
    const moves: Record<string, [number, number]> = { ArrowLeft: [STEP, 0], ArrowRight: [-STEP, 0], ArrowUp: [0, STEP], ArrowDown: [0, -STEP] };
    if (event.key in moves) { event.preventDefault(); move(...moves[event.key]); }
    else if (event.key === '+' || event.key === '=') { event.preventDefault(); setState(current => current ? zoomAround(current, current.zoom + 0.25) : current); }
    else if (event.key === '-') { event.preventDefault(); setState(current => current ? zoomAround(current, current.zoom - 0.25) : current); }
  }

  const scale = state ? displayScale(state) : 1;
  return <div className="cropper" aria-busy={busy}>
    {error && <p role="alert" className="form-error">{error}</p>}
    <div className="cropper-viewport" role="img" aria-label="Pré-visualização do avatar. Arraste para enquadrar; setas movem e as teclas + e - alteram o zoom." tabIndex={0}
      onPointerDown={pointerDown} onPointerMove={pointerMove} onPointerUp={pointerUp} onPointerCancel={pointerUp} onKeyDown={keyDown}>
      {url && <img src={url} alt="" draggable={false} onLoad={event => loaded(event.currentTarget)}
        style={state ? { width: state.naturalWidth, height: state.naturalHeight, transform: `translate(${state.offsetX}px, ${state.offsetY}px) scale(${scale})` } : { visibility: 'hidden' }} />}
      <div className="cropper-mask" />
    </div>
    <div className="cropper-controls">
      <label className="field-label" htmlFor="avatar-zoom"><span><ZoomIn size={14} /> Zoom</span><span>{state ? `${Math.round(state.zoom * 100)}%` : '—'}</span></label>
      <input id="avatar-zoom" type="range" min={MIN_ZOOM} max={MAX_ZOOM} step={0.01} value={state?.zoom ?? 1} disabled={!state || busy} onChange={event => setState(current => current ? zoomAround(current, Number(event.target.value)) : current)} />
      <p className="muted">Arraste a foto para enquadrar. O círculo mostra o resultado final.</p>
      <div className="control-row"><Button variant="primary" disabled={!state || busy} onClick={() => state && onConfirm(cropRect(state))}><Check size={16} /> {busy ? 'Enviando…' : 'Usar esta foto'}</Button><Button disabled={busy} onClick={onCancel}><X size={16} /> Cancelar</Button></div>
    </div>
  </div>;
}
