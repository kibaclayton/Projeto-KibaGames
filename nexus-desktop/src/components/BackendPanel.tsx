import { useEffect, useRef, useState, type FormEvent } from 'react';
import { CheckCircle2, LogOut, RefreshCw, UserRound } from 'lucide-react';
import { NexusApi, type Profile } from '../services/api';
import { useBackend } from '../services/BackendProvider';
import { Button } from './ui';

export function BackendPanel() {
  const { session, enter, leave, summary, summaryError, refreshSummary } = useBackend();
  const [profiles, setProfiles] = useState<Profile[]>([]);
  const [selected, setSelected] = useState<Profile | null>(null);
  const [creating, setCreating] = useState(false);
  const [name, setName] = useState('');
  const [password, setPassword] = useState('');
  const [confirmation, setConfirmation] = useState('');
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
  }, [refresh]);

  async function submit(event: FormEvent) {
    event.preventDefault();
    if (creating && password !== confirmation) { setError('A confirmação da senha não confere.'); return; }
    setBusy(true); setError('');
    const controller = new AbortController();
    loginRequest.current = controller;
    const api = new NexusApi();
    try {
      const person = creating ? await api.createProfile(name, password, controller.signal) : selected;
      if (controller.signal.aborted) return;
      if (!person) return;
      if (creating) { setProfiles(old => [...old, person]); setSelected(person); setCreating(false); }
      const authenticated = await api.login(person.id, password, controller.signal);
      if (controller.signal.aborted) return;
      enter(authenticated);
      setPassword(''); setConfirmation(''); setName('');
    } catch (cause) { if (!controller.signal.aborted) setError(cause instanceof Error ? cause.message : 'Não foi possível entrar.'); }
    finally { if (!controller.signal.aborted) setBusy(false); }
  }

  return <section className="backend-panel" aria-labelledby="profile-title">
    <div className="section-heading"><h3 id="profile-title">{session ? `Olá, ${session.perfil.nome}` : 'Quem vai jogar?'}</h3><span className={`service-status ${online ? 'online' : ''}`}>{online === null ? 'Conectando…' : online ? 'Serviço local conectado' : 'Serviço indisponível'}</span></div>
    {error && <p role="alert" className="form-error">{error}</p>}
    {online === false && <Button onClick={() => setRefresh(n => n + 1)}><RefreshCw size={15} /> Tentar novamente</Button>}
    {session ? <>
      <div className="account-confirmation"><CheckCircle2 size={20} /><p>Seu perfil está conectado à biblioteca local.</p></div>
      {summary && <p className="account-summary">{summary.total} jogos · {summary.colecoes} coleções · {summary.favoritos} favoritos</p>}
      {summaryError && <p role="alert" className="form-error">{summaryError}</p>}
      <div className="control-row"><Button onClick={refreshSummary}><RefreshCw size={15} /> Atualizar biblioteca</Button><Button disabled={busy} onClick={async () => { setBusy(true); try { await leave(); setSelected(null); setRefresh(n => n + 1); } catch { setError('Você saiu neste aparelho. A sessão remota expirará automaticamente.'); } finally { setBusy(false); } }}><LogOut size={15} /> Sair do perfil</Button></div>
    </> : online && <>
      <div className="profile-grid">{profiles.map(person => <button disabled={busy} className={`profile-choice ${selected?.id === person.id && !creating ? 'selected' : ''}`} aria-pressed={selected?.id === person.id && !creating} key={person.id} onClick={() => { setSelected(person); setCreating(false); setPassword(''); setConfirmation(''); setError(''); }}><span className="avatar"><UserRound size={20} /></span><span>{person.nome}</span></button>)}</div>
      {!creating && <Button disabled={busy} onClick={() => { setCreating(true); setSelected(null); setPassword(''); setError(''); }}>Criar perfil</Button>}
      {(selected || creating) && <form onSubmit={submit}>
        <h3 className="login-heading">{creating ? 'Seu novo perfil' : `Entrar como ${selected?.nome}`}</h3>
        {creating && <><label htmlFor="profile-name" className="field-label">Nome do perfil</label><input className="input" id="profile-name" value={name} onChange={e => setName(e.target.value)} required maxLength={60} autoComplete="nickname" disabled={busy} /></>}
        <label className="field-label" htmlFor="profile-password">Senha</label><input id="profile-password" className="input" type="password" autoComplete={creating ? 'new-password' : 'current-password'} value={password} onChange={e => setPassword(e.target.value)} minLength={creating ? 8 : 1} maxLength={256} required disabled={busy} />
        {creating && <><label className="field-label" htmlFor="profile-confirmation">Confirmar senha</label><input id="profile-confirmation" className="input" type="password" autoComplete="new-password" value={confirmation} onChange={e => setConfirmation(e.target.value)} minLength={8} maxLength={256} required disabled={busy} /></>}
        <div className="control-row"><Button type="submit" variant="primary" disabled={busy}>{busy ? 'Aguarde…' : creating ? 'Criar e entrar' : 'Entrar'}</Button><Button disabled={busy} onClick={() => { setCreating(false); setSelected(null); setPassword(''); setConfirmation(''); }}>Cancelar</Button></div>
      </form>}
      {!selected && !creating && <p className="muted">Seu perfil fica salvo neste computador. Para entrar novamente, basta selecioná-lo e informar a senha.</p>}
    </>}
  </section>;
}
