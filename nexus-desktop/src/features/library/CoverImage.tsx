import { useEffect, useRef, useState } from 'react';
import { Gamepad2 } from 'lucide-react';
import { useBackend } from '../../services/BackendProvider';

/** Decode only visible artwork, cancel offscreen requests and release each object URL. */
export function CoverImage({ imageId, name, full = false }: { imageId: string | null; name: string; full?: boolean }) {
  const { api } = useBackend();
  const element = useRef<HTMLDivElement>(null);
  const [visible, setVisible] = useState(false);
  const [url, setUrl] = useState<string | null>(null);
  useEffect(() => {
    const observer = new IntersectionObserver(([entry]) => setVisible(entry.isIntersecting), { rootMargin: '0px' });
    if (element.current) observer.observe(element.current);
    return () => observer.disconnect();
  }, []);
  useEffect(() => {
    setUrl(null);
    if (!visible || !imageId) return;
    const controller = new AbortController();
    let objectUrl: string | undefined;
    api.image(imageId, !full, controller.signal).then(blob => {
      if (controller.signal.aborted) return;
      objectUrl = URL.createObjectURL(blob);
      setUrl(objectUrl);
    }).catch(() => { if (!controller.signal.aborted) setUrl(null); });
    return () => { controller.abort(); if (objectUrl) URL.revokeObjectURL(objectUrl); };
  }, [api, imageId, visible, full]);
  return <div className="cover-image" ref={element}>{url ? <img src={url} alt={`Capa de ${name}`} decoding="async" onError={() => setUrl(null)} /> : <div className="cover-placeholder" aria-label={`${name}: capa indisponível`}><Gamepad2 size={36} /><span>NEXUS</span></div>}</div>;
}
