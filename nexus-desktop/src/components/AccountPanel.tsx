import { useEffect, useState, type FormEvent } from 'react';
import { ImagePlus, KeyRound, Smartphone, Trash2 } from 'lucide-react';
import { useBackend } from '../services/BackendProvider';
import type { RememberedDeviceInfo } from '../services/api';
import { loadDevice } from '../services/device';
import { validateAvatarFile, validatePasswordChange, type CropRect } from '../features/account/model';
import { AvatarCropper } from './AvatarCropper';
import { AvatarImage } from './AvatarImage';
import { Button } from './ui';

/** Configurações da conta: foto de perfil com recorte e troca de senha. Só aparece com um perfil conectado. */
function formatMoment(iso: string) {
  const date = new Date(iso);
  return Number.isNaN(date.getTime()) ? iso : date.toLocaleString('pt-BR', { day: '2-digit', month: '2-digit', year: 'numeric', hour: '2-digit', minute: '2-digit' });
}

export function AccountPanel() {
  const { session, api, updateProfile, expire, forgetThisDevice } = useBackend();
  const [devices, setDevices] = useState<RememberedDeviceInfo[] | null>(null);
  const [devicesError, setDevicesError] = useState('');
  const [devicesBusy, setDevicesBusy] = useState(false);
  const [devicesRefresh, setDevicesRefresh] = useState(0);
  const thisDevice = loadDevice();
  useEffect(() => {
    if (!session) return;
    const controller = new AbortController();
    api.devices(controller.signal).then(list => { if (!controller.signal.aborted) { setDevices(list); setDevicesError(''); } })
      .catch(cause => { if (!controller.signal.aborted) setDevicesError(cause instanceof Error ? cause.message : 'Não foi possível listar os aparelhos.'); });
    return () => controller.abort();
  }, [api, session, devicesRefresh]);
  const [file, setFile] = useState<File | null>(null);
  const [avatarBusy, setAvatarBusy] = useState(false);
  const [avatarError, setAvatarError] = useState('');
  const [avatarMessage, setAvatarMessage] = useState('');
  const [current, setCurrent] = useState('');
  const [next, setNext] = useState('');
  const [confirmation, setConfirmation] = useState('');
  const [passwordBusy, setPasswordBusy] = useState(false);
  const [passwordError, setPasswordError] = useState('');
  if (!session) return null;
  const profile = session.perfil;

  function choose(selected: File | undefined) {
    setAvatarError(''); setAvatarMessage('');
    if (!selected) return;
    const problem = validateAvatarFile(selected);
    if (problem) { setAvatarError(problem); return; }
    setFile(selected);
  }
  async function upload(crop: CropRect) {
    if (!file) return;
    setAvatarBusy(true); setAvatarError('');
    try {
      const stored = await api.uploadImage(file, 'avatar', crop);
      await api.avatar(stored.id);
      updateProfile({ avatar_id: stored.id });
      setFile(null); setAvatarMessage('Foto de perfil atualizada.');
    } catch (cause) { setAvatarError(cause instanceof Error ? cause.message : 'Não foi possível salvar a foto.'); }
    finally { setAvatarBusy(false); }
  }
  async function remove() {
    setAvatarBusy(true); setAvatarError(''); setAvatarMessage('');
    try { await api.avatar(null); updateProfile({ avatar_id: null }); setAvatarMessage('Foto removida.'); }
    catch (cause) { setAvatarError(cause instanceof Error ? cause.message : 'Não foi possível remover a foto.'); }
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
      // O serviço revoga todas as sessões e aparelhos lembrados do perfil; a interface acompanha e pede a nova senha.
      forgetThisDevice();
      expire('Senha alterada. Entre novamente com a nova senha.');
    } catch (cause) { setPasswordError(cause instanceof Error ? cause.message : 'Não foi possível alterar a senha.'); }
    finally { setPasswordBusy(false); setCurrent(''); setNext(''); setConfirmation(''); }
  }

  return <section className="account-panel" aria-labelledby="account-title">
    <div className="section-heading"><h3 id="account-title">Foto de perfil</h3></div>
    <div className="avatar-row">
      <AvatarImage profileId={profile.id} avatarId={profile.avatar_id} name={profile.nome} size="lg" />
      <div>
        <strong>{profile.nome}</strong>
        <p className="muted">JPEG, PNG ou WebP até 10 MB. A foto é recortada em círculo e guardada só neste computador.</p>
        <div className="control-row">
          <label className={`button button-secondary upload-button ${avatarBusy ? 'is-disabled' : ''}`}><ImagePlus size={16} /> Escolher foto<input type="file" accept="image/jpeg,image/png,image/webp" disabled={avatarBusy} onChange={event => { choose(event.target.files?.[0]); event.target.value = ''; }} /></label>
          {profile.avatar_id && <Button disabled={avatarBusy} onClick={() => void remove()}><Trash2 size={16} /> Remover foto</Button>}
        </div>
      </div>
    </div>
    {avatarError && <p role="alert" className="form-error">{avatarError}</p>}
    {avatarMessage && <p role="status" className="form-success">{avatarMessage}</p>}
    {file && <AvatarCropper file={file} busy={avatarBusy} onConfirm={crop => void upload(crop)} onCancel={() => setFile(null)} />}

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
