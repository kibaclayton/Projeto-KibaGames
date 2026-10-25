import { useEffect, useState } from 'react';
import { UserRound } from 'lucide-react';
import { API_BASE } from '../services/api';

/** Avatar circular. Usa a miniatura pública do perfil, a mesma do seletor de contas; cai no ícone quando não há foto. */
export function AvatarImage({ profileId, avatarId, name, size = 'sm' }: { profileId: number; avatarId: string | null; name: string; size?: 'sm' | 'lg' }) {
  const [failed, setFailed] = useState(false);
  useEffect(() => setFailed(false), [avatarId]);
  const source = avatarId && !failed ? `${API_BASE}/perfis/${profileId}/avatar?v=${avatarId}` : null;
  return <span className={`avatar avatar-${size}`} aria-hidden={source ? undefined : true}>
    {source ? <img src={source} alt={`Foto de ${name}`} decoding="async" onError={() => setFailed(true)} /> : <UserRound size={size === 'lg' ? 40 : 20} />}
  </span>;
}
