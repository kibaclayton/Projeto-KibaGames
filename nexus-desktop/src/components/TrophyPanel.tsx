import { useEffect, useState, type FormEvent } from 'react';
import { Download, ExternalLink, Link2, RefreshCw, Trophy, Unlink } from 'lucide-react';
import { ON_THIS_COMPUTER, type TrophyGameItem, type TrophySource, type TrophySourceStatus, type TrophySources, type TrophySyncResult } from '../services/api';
import { useBackend } from '../services/BackendProvider';
import { formatDuration } from '../features/library/model';
import { Button } from './ui';

const HELP: Record<TrophySource, { identification: string; placeholder: string; keyHelp: string; keyUrl: string; idHelp: string }> = {
  steam: {
    identification: 'SteamID64', placeholder: '7656119…', keyUrl: 'https://steamcommunity.com/dev/apikey',
    keyHelp: 'Chave Web API pessoal, gerada na sua conta Steam (qualquer nome serve como domínio).',
    idHelp: 'O SteamID64 tem 17 dígitos e aparece em Dados da conta ou na URL do seu perfil. Em Privacidade, deixe "Detalhes do jogo" público.',
  },
  retroachievements: {
    identification: 'Usuário', placeholder: 'seu usuário', keyUrl: 'https://retroachievements.org/settings',
    keyHelp: 'Chave de API web, em Configurações → Keys do RetroAchievements.',
    idHelp: 'O mesmo nome de usuário com que você entra no site.',
  },
};

/** Prévia pequena buscada pelo serviço (nunca direto dos CDNs das fontes). */
function Thumb({ url, name }: { url: string | null; name: string }) {
  const { api } = useBackend();
  const [objectUrl, setObjectUrl] = useState<string | null>(null);
  useEffect(() => {
    if (!url) return;
    const controller = new AbortController();
    let created: string | undefined;
    api.coverPreview(url, controller.signal).then(blob => { if (!controller.signal.aborted) { created = URL.createObjectURL(blob); setObjectUrl(created); } }).catch(() => { /* fica o espaço vazio */ });
    return () => { controller.abort(); if (created) URL.revokeObjectURL(created); };
  }, [api, url]);
  return objectUrl ? <img src={objectUrl} alt="" /> : <span className="trophy-thumb" aria-label={name} />;
}

function SourceBlock({ status, local, onChanged, onLibraryChanged }: { status: TrophySourceStatus; local: boolean; onChanged: () => void; onLibraryChanged: () => void }) {
  const { api, refreshSummary } = useBackend();
  const help = HELP[status.fonte];
  const [key, setKey] = useState('');
  const [identification, setIdentification] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [note, setNote] = useState('');
  const [confirmUnlink, setConfirmUnlink] = useState(false);
  const [mode, setMode] = useState<'recentes' | 'possuidos' | 'todos'>('recentes');
  const [items, setItems] = useState<TrophyGameItem[] | null>(null);
  const [selected, setSelected] = useState<Set<string>>(new Set());
  // Importar todos: lista completa da conta, em lotes de 25 pedidos ao serviço, com progresso visível.
  const [confirmAll, setConfirmAll] = useState(false);
  const [importAll, setImportAll] = useState<{ done: number; total: number; imported: number } | null>(null);

  async function importEverything() {
    setConfirmAll(false); setBusy(true); setError(''); setNote('');
    const listMode = status.fonte === 'steam' ? 'todos' : 'possuidos';
    try {
      const everything = (await api.trophyGames(status.fonte, listMode)).itens.filter(item => !item.na_biblioteca);
      if (!everything.length) { setNote('Todos os jogos da conta já estão na biblioteca.'); return; }
      let imported = 0; const skipped: string[] = [];
      setImportAll({ done: 0, total: everything.length, imported: 0 });
      for (let start = 0; start < everything.length; start += 25) {
        const chunk = everything.slice(start, start + 25);
        const result = await api.importTrophyGames(status.fonte, chunk.map(item => item.id), listMode);
        imported += result.importados.length;
        skipped.push(...result.ignorados.filter(g => !g.motivo.startsWith('Já está')).map(g => `${g.nome || g.id}: ${g.motivo}`));
        setImportAll({ done: Math.min(start + chunk.length, everything.length), total: everything.length, imported });
        if (result.importados.length) { onLibraryChanged(); void refreshSummary(); }
      }
      setNote(`Importação concluída: ${imported} jogo${imported === 1 ? '' : 's'} entraram na biblioteca.${skipped.length ? ` Não entraram: ${skipped.join(' ')}` : ''}`);
      if (items) await load();
    } catch (cause) { setError(cause instanceof Error ? `${cause.message} Os jogos já importados ficaram na biblioteca; clique de novo para continuar de onde parou.` : 'A importação parou; clique de novo para continuar.'); }
    finally { setImportAll(null); setBusy(false); }
  }

  async function link(event: FormEvent) {
    event.preventDefault(); setBusy(true); setError(''); setNote('');
    try {
      const result = await api.linkTrophySource(status.fonte, key, identification);
      setKey(''); setIdentification(''); setNote(result.aviso ? `Vinculada, com aviso: ${result.aviso}` : `${result.rotulo} vinculada como ${result.identificacao}.`); onChanged();
    } catch (cause) { setError(cause instanceof Error ? cause.message : 'Não foi possível vincular a fonte.'); }
    finally { setBusy(false); }
  }
  async function unlink() {
    setBusy(true); setError('');
    try { await api.unlinkTrophySource(status.fonte); setConfirmUnlink(false); setItems(null); setNote(`${status.rotulo} desvinculada. A chave foi apagada deste computador.`); onChanged(); }
    catch (cause) { setError(cause instanceof Error ? cause.message : 'Não foi possível desvincular.'); }
    finally { setBusy(false); }
  }
  async function load(nextMode = mode) {
    setBusy(true); setError(''); setNote('');
    try { const result = await api.trophyGames(status.fonte, nextMode); setItems(result.itens); setSelected(new Set()); }
    catch (cause) { setError(cause instanceof Error ? cause.message : 'Não foi possível listar os jogos da conta.'); }
    finally { setBusy(false); }
  }
  async function importSelected() {
    if (!selected.size) return;
    setBusy(true); setError('');
    try {
      const result = await api.importTrophyGames(status.fonte, Array.from(selected), mode);
      const names = result.importados.map(g => g.nome);
      const skipped = result.ignorados.map(g => `${g.nome || g.id}: ${g.motivo}`);
      setNote(`${names.length ? `Importados: ${names.join(', ')}.` : 'Nada importado.'}${skipped.length ? ` Ignorados: ${skipped.join(' ')}` : ''}`);
      if (names.length) { onLibraryChanged(); void refreshSummary(); }
      await load();
    } catch (cause) { setError(cause instanceof Error ? cause.message : 'Não foi possível importar.'); setBusy(false); }
  }
  const toggle = (id: string) => setSelected(current => { const next = new Set(current); if (next.has(id)) next.delete(id); else next.add(id); return next; });
  const importable = (items ?? []).filter(item => !item.na_biblioteca);

  return <div className="trophy-source">
    <h4><Trophy size={15} /> {status.rotulo} <span className={`service-status ${status.configurada ? 'online' : ''}`}>{status.configurada ? `Vinculada · ${status.identificacao}` : 'Não vinculada'}</span></h4>
    {error && <p role="alert" className="form-error">{error}</p>}
    {note && <p role="status" className="muted trophy-result">{note}</p>}
    {!status.configurada && !local && <p className="muted">Vincule esta fonte no computador onde está a biblioteca; pelo celular ou pela rede a chave não é aceita.</p>}
    {!status.configurada && local && <form onSubmit={link} className="trophy-form">
      <div><label htmlFor={`trophy-key-${status.fonte}`} className="field-label">Chave de API</label><input id={`trophy-key-${status.fonte}`} className="input" type="password" autoComplete="off" value={key} onChange={e => setKey(e.target.value)} required minLength={8} maxLength={80} /></div>
      <div><label htmlFor={`trophy-id-${status.fonte}`} className="field-label">{help.identification}</label><input id={`trophy-id-${status.fonte}`} className="input" value={identification} onChange={e => setIdentification(e.target.value)} placeholder={help.placeholder} required minLength={2} maxLength={40} /></div>
      <Button type="submit" variant="primary" disabled={busy || !key || !identification}><Link2 size={16} /> {busy ? 'Conferindo…' : 'Vincular'}</Button>
      <p className="muted trophy-help">{help.keyHelp} <a href={help.keyUrl} target="_blank" rel="noreferrer noopener">Abrir página da chave <ExternalLink size={12} /></a>. {help.idHelp} A chave vale só para este perfil e fica no arquivo <code>{status.arquivo}</code>; cada perfil vincula a própria conta.</p>
    </form>}
    {status.configurada && <>
      <div className="trophy-actions">
        <label htmlFor={`trophy-mode-${status.fonte}`} className="muted">Listar</label>
        <select id={`trophy-mode-${status.fonte}`} className="input trophy-mode" value={mode} disabled={busy} onChange={e => { const next = e.target.value as 'recentes' | 'possuidos' | 'todos'; setMode(next); void load(next); }}><option value="recentes">jogados recentemente</option><option value="possuidos">{status.fonte === 'steam' ? 'todos com tempo de jogo' : 'todos com progresso'}</option>{status.fonte === 'steam' && <option value="todos">todos da conta (inclusive nunca abertos)</option>}</select>
        <Button disabled={busy} onClick={() => void load()}><Download size={16} /> {items ? 'Atualizar lista' : 'Escolher jogos para importar'}</Button>
        <Button variant="primary" disabled={busy || Boolean(importAll)} onClick={() => setConfirmAll(true)}><Download size={16} /> Importar todos os jogos da conta</Button>
        {local && !confirmUnlink && <Button variant="ghost" disabled={busy} onClick={() => setConfirmUnlink(true)}><Unlink size={16} /> Desvincular</Button>}
      </div>
      {confirmAll && <div className="confirm-box" role="alertdialog" aria-labelledby={`all-title-${status.fonte}`}><p id={`all-title-${status.fonte}`}>Importar todos os jogos da conta {status.rotulo}{status.fonte === 'steam' ? ' (inclusive os nunca abertos)' : ''}? Cada jogo entra com capa, ficha, tempo de jogo e conquistas; os que já estão na biblioteca são pulados. Isso é feito em lotes de 25 e pode levar alguns minutos numa conta grande; deixe esta janela aberta.</p><Button variant="primary" disabled={busy} onClick={() => void importEverything()}>Importar todos</Button><Button onClick={() => setConfirmAll(false)}>Agora não</Button></div>}
      {importAll && <p role="status" className="muted trophy-result">Importando {importAll.done} de {importAll.total} jogos… {importAll.imported} entraram até agora.</p>}
      {confirmUnlink && <div className="confirm-box" role="alert"><p>Desvincular {status.rotulo}? A chave é apagada deste computador; os jogos e troféus já importados continuam na biblioteca.</p><Button disabled={busy} onClick={() => void unlink()}>Desvincular</Button><Button onClick={() => setConfirmUnlink(false)}>Manter</Button></div>}
      {items && items.length === 0 && <p className="muted">A fonte não listou jogos para esta conta neste modo.</p>}
      {items && items.length > 0 && <>
        <ul className="trophy-list" aria-label={`Jogos da conta ${status.rotulo}`}>{items.map(item => <li key={item.id}><label className={item.na_biblioteca ? 'is-linked' : ''}>
          <input type="checkbox" disabled={Boolean(item.na_biblioteca) || busy} checked={selected.has(item.id)} onChange={() => toggle(item.id)} />
          <Thumb url={item.previa} name={item.titulo} />
          <span><strong>{item.titulo}</strong><small>{[item.plataforma, item.minutos ? formatDuration(item.minutos) + ' jogadas' : '', item.ultimo_jogo ? `último jogo ${item.ultimo_jogo.split('-').reverse().join('/')}` : '', item.trofeus_total ? `${item.trofeus_obtidos ?? 0}/${item.trofeus_total} conquistas` : ''].filter(Boolean).join(' · ')}{item.na_biblioteca ? ` · já na biblioteca como "${item.na_biblioteca.nome}"` : ''}</small></span>
        </label></li>)}</ul>
        <div className="trophy-actions">
          <Button variant="ghost" disabled={busy || !importable.length} onClick={() => setSelected(new Set(importable.map(item => item.id)))}>Marcar todos</Button>
          <Button variant="primary" disabled={busy || !selected.size} onClick={() => void importSelected()}><Download size={16} /> {busy ? 'Importando…' : `Importar ${selected.size || ''} selecionado${selected.size === 1 ? '' : 's'}`}</Button>
        </div>
        <p className="muted">A importação traz ficha, capa, tempo de jogo e conquistas da sua conta. Progresso, notas, datas e calendário ficam vazios para você preencher; jogos já ligados ao mesmo id nunca são sobrescritos.</p>
      </>}
    </>}
  </div>;
}

/** Troféus por fontes oficiais com chave pessoal (Steam Web API e RetroAchievements). PSN, Xbox, Nintendo e Epic ficam de fora por não terem API oficial. */
export function TrophyPanel({ onLibraryChanged }: { onLibraryChanged: () => void }) {
  const { api, session, refreshSummary } = useBackend();
  const [status, setStatus] = useState<TrophySources | null>(null);
  const [error, setError] = useState('');
  const [refresh, setRefresh] = useState(0);
  const [syncing, setSyncing] = useState(false);
  const [sync, setSync] = useState<TrophySyncResult | null>(null);
  const [syncError, setSyncError] = useState('');
  useEffect(() => {
    if (!session) return;
    const controller = new AbortController();
    api.trophySources(controller.signal).then(result => { if (!controller.signal.aborted) { setStatus(result); setError(''); } })
      .catch(cause => { if (!controller.signal.aborted) setError(cause instanceof Error ? cause.message : 'Não foi possível consultar as fontes de troféus.'); });
    return () => controller.abort();
  }, [api, session, refresh]);
  if (!session) return null;
  const local = status?.local ?? ON_THIS_COMPUTER;
  const anyLinked = Boolean(status && Object.values(status.fontes).some(source => source.configurada));

  async function syncNow() {
    setSyncing(true); setSyncError(''); setSync(null);
    try { const result = await api.syncTrophies(); setSync(result); if (result.atualizados.some(u => u.mudou)) { onLibraryChanged(); void refreshSummary(); } }
    catch (cause) { setSyncError(cause instanceof Error ? cause.message : 'Não foi possível sincronizar.'); }
    finally { setSyncing(false); }
  }

  return <section className="trophy-panel" aria-labelledby="trophy-title">
    <div className="section-heading"><h3 id="trophy-title"><Trophy size={17} /> Troféus e conquistas</h3><span className={`service-status ${anyLinked ? 'online' : ''}`}>{!status ? 'Consultando…' : anyLinked ? 'Fonte vinculada' : 'Manual'}</span></div>
    <p className="muted">Sincronize obtidos e total pela sua própria conta, só por APIs oficiais com chave pessoal: Steam (PC) e RetroAchievements (emulação). Cada perfil vincula a própria conta; fica desligado até você vincular, e a chave nunca sai deste computador nem vai para o navegador.</p>
    {error && <p role="alert" className="form-error">{error}</p>}
    {status && (Object.keys(status.fontes) as TrophySource[]).map(source => <SourceBlock key={source} status={status.fontes[source]} local={local} onChanged={() => setRefresh(n => n + 1)} onLibraryChanged={onLibraryChanged} />)}
    {anyLinked && <div className="trophy-source">
      <h4><RefreshCw size={15} /> Sincronizar troféus</h4>
      <p className="muted">Atualiza obtidos e total de todos os jogos ligados às fontes vinculadas. Jogos sem conquistas, perfil privado ou fonte fora do ar são relatados e mantêm os valores atuais.</p>
      <div className="trophy-actions"><Button variant="primary" disabled={syncing} onClick={() => void syncNow()}><RefreshCw size={16} /> {syncing ? 'Sincronizando…' : 'Sincronizar agora'}</Button></div>
      {syncError && <p role="alert" className="form-error">{syncError}</p>}
      {sync && <div role="status" className="trophy-result">
        <p>{sync.total === 0 ? 'Nenhum jogo da biblioteca está ligado a uma fonte vinculada. Importe jogos acima ou escolha um resultado da Steam no editor.' : `${sync.atualizados.length} de ${sync.total} jogos consultados; ${sync.atualizados.filter(u => u.mudou).length} mudaram.`}</p>
        {sync.atualizados.filter(u => u.mudou).length > 0 && <ul>{sync.atualizados.filter(u => u.mudou).map(u => <li key={u.id}>{u.nome}: {u.antes.obtidos}/{u.antes.total} → {u.obtidos}/{u.total}</li>)}</ul>}
        {sync.ignorados.length > 0 && <ul>{sync.ignorados.map(u => <li key={u.id}>{u.nome}: {u.motivo}</li>)}</ul>}
      </div>}
    </div>}
    <p className="muted trophy-help">PlayStation, Xbox, Nintendo e Epic não oferecem API oficial de troféus para o usuário; nesses jogos os valores continuam manuais, por segurança da sua conta.</p>
  </section>;
}
