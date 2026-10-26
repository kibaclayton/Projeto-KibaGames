import { useEffect, useState, type FormEvent } from 'react';
import { ExternalLink, ImagePlus, KeyRound, Search, Smartphone, Trash2, UserRound } from 'lucide-react';
import type { AvatarSlot, CommonsImage, RememberedDeviceInfo } from '../services/api';
import { useBackend } from '../services/BackendProvider';
import { loadDevice } from '../services/device';
import { validateAvatarFile, validatePasswordChange, type CropRect } from '../features/account/model';
import { AvatarCropper } from './AvatarCropper';
import { AvatarImage } from './AvatarImage';
import { Button } from './ui';

function formatMoment(iso: string) {
  const date = new Date(iso);
  return Number.isNaN(date.getTime()) ? iso : date.toLocaleString('pt-BR', { day: '2-digit', month: '2-digit', year: 'numeric', hour: '2-digit', minute: '2-digit' });
}

/** Foto de uma posição da galeria, servida pela rota autenticada de imagens (só o próprio perfil vê). */
function SlotImage({ imageId, name }: { imageId: string; name: string }) {
  const { api } = useBackend();
  const [url, setUrl] = useState<string | null>(null);
  useEffect(() => {
    const controller = new AbortController();
    let created: string | undefined;
    api.image(imageId, true, controller.signal).then(blob => { if (!controller.signal.aborted) { created = URL.createObjectURL(blob); setUrl(created); } }).catch(() => { /* fica o ícone */ });
    return () => { controller.abort(); if (created) URL.revokeObjectURL(created); };
  }, [api, imageId]);
  return <span className="avatar avatar-lg">{url ? <img src={url} alt={name} /> : <UserRound size={40} />}</span>;
}

/** Prévia de uma imagem do Wikimedia Commons, buscada pelo serviço (nunca direto do navegador). */
function CommonsPreview({ url }: { url: string }) {
  const { api } = useBackend();
  const [objectUrl, setObjectUrl] = useState<string | null>(null);
  useEffect(() => {
    const controller = new AbortController();
    let created: string | undefined;
    api.coverPreview(url, controller.signal).then(blob => { if (!controller.signal.aborted) { created = URL.createObjectURL(blob); setObjectUrl(created); } }).catch(() => { /* resultado sem prévia */ });
    return () => { controller.abort(); if (created) URL.revokeObjectURL(created); };
  }, [api, url]);
  return objectUrl ? <img src={objectUrl} alt="" /> : <span className="cover-candidate-loading" aria-hidden="true" />;
}

/** Configurações da conta: galeria de até cinco fotos (arquivo ou busca na internet), aparelhos lembrados e senha. */
export function AccountPanel() {
  const { session, api, updateProfile, expire, forgetThisDevice } = useBackend();
  const [devices, setDevices] = useState<RememberedDeviceInfo[] | null>(null);
  const [devicesError, setDevicesError] = useState('');
  const [devicesBusy, setDevicesBusy] = useState(false);
  const [devicesRefresh, setDevicesRefresh] = useState(0);
  const [gallery, setGallery] = useState<AvatarSlot[] | null>(null);
  const [file, setFile] = useState<File | null>(null);
  const [target, setTarget] = useState<number | null>(null);
  const [pendingFile, setPendingFile] = useState<File | null>(null);
  const [avatarBusy, setAvatarBusy] = useState(false);
  const [avatarError, setAvatarError] = useState('');
  const [avatarMessage, setAvatarMessage] = useState('');
  const [confirmRemove, setConfirmRemove] = useState<number | null>(null);
  const [term, setTerm] = useState('');
  const [results, setResults] = useState<CommonsImage[] | null>(null);
  const [searching, setSearching] = useState(false);
  const [searchError, setSearchError] = useState('');
  const [current, setCurrent] = useState('');
  const [next, setNext] = useState('');
  const [confirmation, setConfirmation] = useState('');
  const [passwordBusy, setPasswordBusy] = useState(false);
  const [passwordError, setPasswordError] = useState('');
  const thisDevice = loadDevice();
  useEffect(() => {
    if (!session) return;
    const controller = new AbortController();
    api.devices(controller.signal).then(list => { if (!controller.signal.aborted) { setDevices(list); setDevicesError(''); } })
      .catch(cause => { if (!controller.signal.aborted) setDevicesError(cause instanceof Error ? cause.message : 'Não foi possível listar os aparelhos.'); });
    return () => controller.abort();
  }, [api, session, devicesRefresh]);
  useEffect(() => {
    if (!session) return;
    const controller = new AbortController();
    api.avatarGallery(controller.signal).then(list => { if (!controller.signal.aborted) setGallery(list); })
      .catch(cause => { if (!controller.signal.aborted) setAvatarError(cause instanceof Error ? cause.message : 'Não foi possível carregar a galeria.'); });
    return () => controller.abort();
  }, [api, session]);
  if (!session) return null;
  const profile = session.perfil;
  const slots = gallery ?? [];
  const freeSlot = slots.find(slot => !slot.imagem_id)?.posicao ?? null;

  function syncActive(list: AvatarSlot[]) { setGallery(list); updateProfile({ avatar_id: list.find(slot => slot.ativo)?.imagem_id ?? null }); }
  function startWith(selected: File | undefined, slot: number | null) {
    setAvatarError(''); setAvatarMessage('');
    if (!selected) return;
    const problem = validateAvatarFile(selected);
    if (problem) { setAvatarError(problem); return; }
    if (slot === null) { setPendingFile(selected); return; } // Galeria cheia: a pessoa escolhe qual posição substituir.
    setTarget(slot); setFile(selected);
  }
  async function upload(crop: CropRect) {
    if (!file || target === null) return;
    setAvatarBusy(true); setAvatarError('');
    try {
      const stored = await api.uploadImage(file, 'avatar', crop);
      const list = await api.setAvatarSlot(target, stored.id);
      await api.avatar(stored.id);
      syncActive(list.map(slot => ({ ...slot, ativo: slot.imagem_id === stored.id })));
      setFile(null); setTarget(null); setAvatarMessage(`Foto guardada na posição ${target} e em uso.`);
    } catch (cause) { setAvatarError(cause instanceof Error ? cause.message : 'Não foi possível salvar a foto.'); }
    finally { setAvatarBusy(false); }
  }
  async function use(slot: AvatarSlot) {
    if (!slot.imagem_id) return;
    setAvatarBusy(true); setAvatarError(''); setAvatarMessage('');
    try { await api.avatar(slot.imagem_id); syncActive(slots.map(item => ({ ...item, ativo: item.posicao === slot.posicao }))); setAvatarMessage(`Foto ${slot.posicao} em uso.`); }
    catch (cause) { setAvatarError(cause instanceof Error ? cause.message : 'Não foi possível trocar a foto.'); }
    finally { setAvatarBusy(false); }
  }
  async function remove(slot: number) {
    setAvatarBusy(true); setAvatarError(''); setAvatarMessage(''); setConfirmRemove(null);
    try { const list = await api.removeAvatarSlot(slot); syncActive(list); setAvatarMessage(`Foto ${slot} removida.`); }
    catch (cause) { setAvatarError(cause instanceof Error ? cause.message : 'Não foi possível remover a foto.'); }
    finally { setAvatarBusy(false); }
  }
  async function searchImages(event: FormEvent) {
    event.preventDefault();
    if (term.trim().length < 2) { setSearchError('Digite pelo menos 2 caracteres.'); return; }
    setSearching(true); setSearchError(''); setResults(null);
    try { setResults((await api.searchAvatars(term.trim())).itens); }
    catch (cause) { setSearchError(cause instanceof Error ? cause.message : 'Não foi possível buscar imagens.'); }
    finally { setSearching(false); }
  }
  async function pickRemote(image: CommonsImage) {
    setAvatarBusy(true); setAvatarError('');
    try {
      const blob = await api.coverPreview(image.imagem);
      const remote = new File([blob], `${image.titulo || 'imagem'}.${blob.type === 'image/png' ? 'png' : 'jpg'}`, { type: blob.type });
      startWith(remote, freeSlot);
    } catch (cause) { setAvatarError(cause instanceof Error ? cause.message : 'Não foi possível baixar esta imagem.'); }
    finally { setAvatarBusy(false); }
  }
  async function forget(id: number | 'todos') {
    setDevicesBusy(true); setDevicesError('');
    try {
      if (id === 'todos') await api.forgetDevices(); else await api.forgetDevice(id);
      if (id === 'todos' || id === thisDevice?.id) forgetThisDevice();
      setDevicesRefresh(n => n + 1);
    } catch (cause) { setDevicesError(cause instanceof Error ? cause.message : 'Não foi possível esquecer o aparelho.'); }
    finally { setDevicesBusy(false); }
  }
  async function changePassword(event: FormEvent) {
    event.preventDefault();
    const problem = validatePasswordChange(current, next, confirmation);
    if (problem) { setPasswordError(problem); return; }
    setPasswordBusy(true); setPasswordError('');
    try {
      await api.password(current, next, confirmation);
      forgetThisDevice();
      expire('Senha alterada. Entre novamente com a nova senha.');
    } catch (cause) { setPasswordError(cause instanceof Error ? cause.message : 'Não foi possível alterar a senha.'); }
    finally { setPasswordBusy(false); setCurrent(''); setNext(''); setConfirmation(''); }
  }

  return <section className="account-panel" aria-labelledby="account-title">
    <div className="section-heading"><h3 id="account-title">Fotos de perfil</h3><span className="muted">{slots.filter(slot => slot.imagem_id).length} de 5</span></div>
    <div className="avatar-row">
      <AvatarImage profileId={profile.id} avatarId={profile.avatar_id} name={profile.nome} size="lg" />
      <div>
        <strong>{profile.nome}</strong>
        <p className="muted">Guarde até cinco fotos e troque a ativa quando quiser, sem enviar de novo. A foto ativa aparece no seletor de perfis; as outras só você vê. JPEG, PNG ou WebP até 10 MB, recortadas em círculo e guardadas só neste computador.</p>
        <div className="control-row">
          <label className={`button button-secondary upload-button ${avatarBusy ? 'is-disabled' : ''}`}><ImagePlus size={16} /> {freeSlot ? 'Adicionar foto' : 'Substituir uma foto'}<input type="file" accept="image/jpeg,image/png,image/webp" disabled={avatarBusy} onChange={event => { startWith(event.target.files?.[0], freeSlot); event.target.value = ''; }} /></label>
        </div>
      </div>
    </div>
    {avatarError && <p role="alert" className="form-error">{avatarError}</p>}
    {avatarMessage && <p role="status" className="form-success">{avatarMessage}</p>}
    {pendingFile && <div className="confirm-box" role="alertdialog" aria-label="Escolher a foto a substituir"><p>As cinco posições estão ocupadas. Qual foto você quer substituir por "{pendingFile.name}"? A foto anterior dessa posição será descartada.</p>
      <div className="control-row">{slots.map(slot => <Button key={slot.posicao} disabled={avatarBusy} onClick={() => { setTarget(slot.posicao); setFile(pendingFile); setPendingFile(null); }}>Posição {slot.posicao}{slot.ativo ? ' (ativa)' : ''}</Button>)}<Button variant="ghost" onClick={() => setPendingFile(null)}>Cancelar</Button></div></div>}
    {file && target !== null && <AvatarCropper file={file} busy={avatarBusy} onConfirm={crop => void upload(crop)} onCancel={() => { setFile(null); setTarget(null); }} />}
    <ul className="avatar-gallery" aria-label="Galeria de fotos do perfil">{slots.map(slot => <li key={slot.posicao} className={slot.ativo ? 'is-active' : ''}>
      {slot.imagem_id ? <SlotImage imageId={slot.imagem_id} name={`Foto ${slot.posicao}`} /> : <span className="avatar avatar-lg avatar-empty" aria-hidden="true"><UserRound size={28} /></span>}
      <strong>Posição {slot.posicao}{slot.ativo ? ' · em uso' : ''}</strong>
      <div className="gallery-actions">
        {slot.imagem_id && !slot.ativo && <Button disabled={avatarBusy} onClick={() => void use(slot)}>Usar</Button>}
        <label className={`button button-secondary upload-button ${avatarBusy ? 'is-disabled' : ''}`}>{slot.imagem_id ? 'Substituir' : 'Adicionar'}<input type="file" accept="image/jpeg,image/png,image/webp" disabled={avatarBusy} onChange={event => { startWith(event.target.files?.[0], slot.posicao); event.target.value = ''; }} /></label>
        {slot.imagem_id && (confirmRemove === slot.posicao
          ? <><Button disabled={avatarBusy} onClick={() => void remove(slot.posicao)}>Confirmar</Button><Button variant="ghost" onClick={() => setConfirmRemove(null)}>Manter</Button></>
          : <Button variant="ghost" disabled={avatarBusy} aria-label={`Remover foto ${slot.posicao}`} onClick={() => setConfirmRemove(slot.posicao)}><Trash2 size={15} /></Button>)}
      </div>
    </li>)}</ul>
    <form className="commons-search" onSubmit={searchImages} role="search" aria-label="Buscar imagens na internet">
      <label htmlFor="avatar-term" className="field-label">Buscar uma imagem na internet (Wikimedia Commons)</label>
      <div className="url-field"><input id="avatar-term" className="input" value={term} maxLength={80} placeholder="Nome, personagem ou tema" onChange={event => setTerm(event.target.value)} disabled={avatarBusy} /><Button type="submit" disabled={searching || avatarBusy}><Search size={15} /> {searching ? 'Buscando…' : 'Buscar'}</Button></div>
      {searchError && <p role="alert" className="form-error">{searchError}</p>}
      {results && results.length === 0 && <p className="muted">Nenhuma imagem encontrada para este termo.</p>}
      {results && results.length > 0 && <ul className="commons-results" aria-label="Imagens encontradas">{results.map(image => <li key={image.origem}>
        <button type="button" className="cover-candidate" disabled={avatarBusy} onClick={() => void pickRemote(image)} aria-label={`Usar a imagem ${image.titulo} (${image.licenca})`}><CommonsPreview url={image.previa} /><span className="cover-candidate-caption"><strong>{image.titulo}</strong><small>{image.licenca}{image.autor ? ` · ${image.autor}` : ''}</small></span></button>
        <a className="cover-origin" href={image.origem} target="_blank" rel="noreferrer noopener"><ExternalLink size={13} /> origem</a>
      </li>)}</ul>}
      <p className="muted cover-attribution">Imagens do Wikimedia Commons, com a licença e o autor indicados em cada resultado; a página de origem tem os termos completos. A imagem escolhida é baixada pelo serviço, recortada aqui e guardada só neste computador.</p>
    </form>

    <div className="section-heading password-heading"><h3><Smartphone size={17} /> Aparelhos lembrados</h3>{devices && devices.length > 1 && <Button variant="ghost" disabled={devicesBusy} onClick={() => void forget('todos')}>Esquecer todos</Button>}</div>
    <p className="muted">Aparelhos que entram sem senha. Cada um guarda uma credencial própria, trocada a cada uso e válida por 90 dias sem uso; trocar a senha esquece todos.</p>
    {devicesError && <p role="alert" className="form-error">{devicesError}</p>}
    {devices && devices.length === 0 && <p className="muted">Nenhum aparelho lembrado. Marque "Lembrar neste aparelho" ao entrar.</p>}
    {devices && devices.length > 0 && <ul className="device-list">{devices.map(device => <li key={device.id}>
      <span><strong>{device.nome}</strong>{thisDevice?.id === device.id && <em> · este aparelho</em>}<small>Último uso {formatMoment(device.ultimo_uso)} · lembrado desde {formatMoment(device.criado)}</small></span>
      <Button disabled={devicesBusy} onClick={() => void forget(device.id)}>Esquecer</Button>
    </li>)}</ul>}

    <div className="section-heading password-heading"><h3><KeyRound size={17} /> Alterar senha</h3></div>
    <form onSubmit={changePassword} className="password-form">
      {passwordError && <p role="alert" className="form-error">{passwordError}</p>}
      <fieldset disabled={passwordBusy}>
        <label className="field-label" htmlFor="password-current">Senha atual</label>
        <input id="password-current" className="input" type="password" autoComplete="current-password" value={current} onChange={event => setCurrent(event.target.value)} required maxLength={256} />
        <div className="field-pair">
          <div><label className="field-label" htmlFor="password-next">Nova senha</label><input id="password-next" className="input" type="password" autoComplete="new-password" value={next} onChange={event => setNext(event.target.value)} required minLength={8} maxLength={256} aria-describedby="password-hint" /></div>
          <div><label className="field-label" htmlFor="password-confirm">Confirmar nova senha</label><input id="password-confirm" className="input" type="password" autoComplete="new-password" value={confirmation} onChange={event => setConfirmation(event.target.value)} required minLength={8} maxLength={256} /></div>
        </div>
        <p id="password-hint" className="muted">Mínimo de 8 caracteres. Depois da troca, todos os aparelhos conectados ou lembrados precisam entrar de novo com a nova senha.</p>
        <div className="control-row"><Button type="submit" variant="primary" disabled={passwordBusy || !current || !next || !confirmation}>{passwordBusy ? 'Alterando…' : 'Alterar senha'}</Button></div>
      </fieldset>
    </form>
  </section>;
}
