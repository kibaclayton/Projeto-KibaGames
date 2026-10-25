import { useEffect, useRef, useState, type FormEvent } from 'react';
import { CheckCircle2, KeyRound, LogOut, RefreshCw } from 'lucide-react';
import { AUTHORITY_URL, NexusApi, ON_THIS_COMPUTER, type Profile } from '../services/api';
import { useBackend } from '../services/BackendProvider';
import { deviceName } from '../services/device';
import { AvatarImage } from './AvatarImage';
import { Button } from './ui';

export function BackendPanel() {
  const { session, enter, leave, summary, summaryError, refreshSummary, notice, restoring } = useBackend();
  const [profiles, setProfiles] = useState<Profile[]>([]);
  const [selected, setSelected] = useState<Profile | null>(null);
  const [creating, setCreating] = useState(false);
  // "Esqueci a senha": redefinição só neste computador, com senha nova confirmada; nunca pelo celular ou pela rede.
  const [resetting, setResetting] = useState(false);
  const [resetDone, setResetDone] = useState('');
  const [name, setName] = useState('');
  const [password, setPassword] = useState('');
  const [confirmation, setConfirmation] = useState('');
  const [remember, setRemember] = useState(!ON_THIS_COMPUTER);
  const [online, setOnline] = useState<boolean | null>(null);
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  const [refresh, setRefresh] = useState(0);
  const loginRequest = useRef<AbortController | null>(null);
  useEffect(() => () => loginRequest.current?.abort(), []);

  useEffect(() => {
    const controller = new AbortController();
    const api = new NexusApi();
    setOnline(null);
    Promise.all([api.health(controller.signal), api.profiles(controller.signal)]).then(([, people]) => {
      if (controller.signal.aborted) return;
      setProfiles(people); setOnline(true); setError('');
    }).catch(cause => {
      if (!controller.signal.aborted) { setOnline(false); setError(cause.message); }
    });
    return () => controller.abort();
  }, [refresh, session]); // Recarrega ao sair ou expirar, para o seletor mostrar avatares atualizados.

  function choose(person: Profile | null, create = false) {
    setSelected(person); setCreating(create); setResetting(false); setResetDone(''); setPassword(''); setConfirmation(''); setError('');
  }

  async function submit(event: FormEvent) {
    event.preventDefault();
    if ((creating || resetting) && password !== confirmation) { setError('A confirmação da senha não confere.'); return; }
    setBusy(true); setError('');
    const controller = new AbortController();
    loginRequest.current = controller;
    const api = new NexusApi();
    try {
      if (resetting && selected) {
        await api.resetPassword(selected.id, password, confirmation, controller.signal);
        if (controller.signal.aborted) return;
        setResetting(false); setPassword(''); setConfirmation('');
        setResetDone(`Senha de ${selected.nome} redefinida. Sessões e aparelhos lembrados desse perfil foram desconectados; entre com a senha nova.`);
        return;
      }
      const person = creating ? await api.createProfile(name, password, controller.signal) : selected;
      if (controller.signal.aborted) return;
      if (!person) return;
      if (creating) { setProfiles(old => [...old, person]); setSelected(person); setCreating(false); }
      const authenticated = await api.login(person.id, password, controller.signal, remember, remember ? deviceName(navigator.userAgent, ON_THIS_COMPUTER) : '');
      if (controller.signal.aborted) return;
      enter(authenticated);
      setPassword(''); setConfirmation(''); setName('');
    } catch (cause) { if (!controller.signal.aborted) setError(cause instanceof Error ? cause.message : 'Não foi possível entrar.'); }
    finally { if (!controller.signal.aborted) setBusy(false); }
  }

  const newPassword = creating || resetting;
  return <section className="backend-panel" aria-labelledby="profile-title">
    <div className="section-heading"><h3 id="profile-title">{session ? `Olá, ${session.perfil.nome}` : 'Quem vai jogar?'}</h3><span className={`service-status ${online ? 'online' : ''}`}>{online === null ? 'Conectando…' : online ? 'Serviço local conectado' : 'Serviço indisponível'}</span></div>
    {error && <p role="alert" className="form-error">{error}</p>}
    {notice && <p role="status" className="form-success">{notice}</p>}
    {resetDone && <p role="status" className="form-success">{resetDone}</p>}
    {!session && restoring && <p role="status" className="muted">Entrando com o perfil lembrado neste aparelho…</p>}
    {!ON_THIS_COMPUTER && <p className="muted network-remote-note">Você está usando o Nexus pela rede local. Para instalar como app sem avisos de segurança, <a href={AUTHORITY_URL} download="nexus-ca.crt">baixe o certificado nexus-ca.crt</a> e instale-o no celular como certificado de autoridade.</p>}
    {online === false && <Button onClick={() => setRefresh(n => n + 1)}><RefreshCw size={15} /> Tentar novamente</Button>}
    {session ? <>
      <div className="account-confirmation"><CheckCircle2 size={20} /><p>Seu perfil está conectado à biblioteca local.</p></div>
      {summary && <p className="account-summary">{summary.total} jogos · {summary.colecoes} coleções · {summary.favoritos} favoritos</p>}
      {summaryError && <p role="alert" className="form-error">{summaryError}</p>}
      <div className="control-row"><Button onClick={refreshSummary}><RefreshCw size={15} /> Atualizar biblioteca</Button><Button disabled={busy} onClick={async () => { setBusy(true); try { await leave(); setSelected(null); setRefresh(n => n + 1); } catch { setError('Você saiu neste aparelho. A sessão remota expirará automaticamente.'); } finally { setBusy(false); } }}><LogOut size={15} /> Sair do perfil</Button></div>
    </> : online && <>
      <div className="profile-grid">{profiles.map(person => <button disabled={busy} className={`profile-choice ${selected?.id === person.id && !creating ? 'selected' : ''}`} aria-pressed={selected?.id === person.id && !creating} key={person.id} onClick={() => choose(person)}><AvatarImage profileId={person.id} avatarId={person.avatar_id} name={person.nome} /><span>{person.nome}</span></button>)}</div>
      {!creating && <Button disabled={busy} onClick={() => choose(null, true)}>Criar perfil</Button>}
      {(selected || creating) && <form onSubmit={submit}>
        <h3 className="login-heading">{creating ? 'Seu novo perfil' : resetting ? `Nova senha para ${selected?.nome}` : `Entrar como ${selected?.nome}`}</h3>
        {resetting && <p className="muted reset-note">A senha é redefinida sem pedir a antiga, por isso só funciona neste computador. Ao confirmar, todas as sessões e aparelhos lembrados deste perfil são desconectados e o evento fica registrado.</p>}
        {creating && <><label htmlFor="profile-name" className="field-label">Nome do perfil</label><input className="input" id="profile-name" value={name} onChange={e => setName(e.target.value)} required maxLength={60} autoComplete="nickname" disabled={busy} /></>}
        <label className="field-label" htmlFor="profile-password">{resetting ? 'Senha nova' : 'Senha'}</label><input id="profile-password" className="input" type="password" autoComplete={newPassword ? 'new-password' : 'current-password'} value={password} onChange={e => setPassword(e.target.value)} minLength={newPassword ? 8 : 1} maxLength={256} required disabled={busy} />
        {newPassword && <><label className="field-label" htmlFor="profile-confirmation">Confirmar senha</label><input id="profile-confirmation" className="input" type="password" autoComplete="new-password" value={confirmation} onChange={e => setConfirmation(e.target.value)} minLength={8} maxLength={256} required disabled={busy} /></>}
        {!resetting && <label className="remember-row"><input type="checkbox" checked={remember} onChange={e => setRemember(e.target.checked)} disabled={busy} /><span><strong>Lembrar neste aparelho</strong><small>Entra sozinho nas próximas aberturas, por até 90 dias sem uso. Use só em aparelhos seus; dá para esquecer um aparelho em Conta.</small></span></label>}
        <div className="control-row"><Button type="submit" variant="primary" disabled={busy}>{busy ? 'Aguarde…' : creating ? 'Criar e entrar' : resetting ? 'Redefinir senha' : 'Entrar'}</Button><Button disabled={busy} onClick={() => resetting ? choose(selected) : choose(null)}>Cancelar</Button></div>
        {!creating && !resetting && selected && (ON_THIS_COMPUTER
          ? <p className="muted reset-link"><button type="button" className="link-button" disabled={busy} onClick={() => { setResetting(true); setPassword(''); setConfirmation(''); setError(''); setResetDone(''); }}><KeyRound size={13} /> Esqueci a senha</button></p>
          : <p className="muted reset-link">Esqueceu a senha? Ela só pode ser redefinida no computador onde o Nexus está instalado.</p>)}
      </form>}
      {!selected && !creating && <p className="muted">Seu perfil fica salvo neste computador. Para entrar novamente, basta selecioná-lo e informar a senha.</p>}
    </>}
  </section>;
}
