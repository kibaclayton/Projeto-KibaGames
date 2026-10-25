import { useEffect, useState } from 'react';
import { DownloadCloud, RefreshCw, RotateCcw, Sparkles } from 'lucide-react';
import { ON_THIS_COMPUTER, type UpdateStatus } from '../services/api';
import { useBackend } from '../services/BackendProvider';
import { Button } from './ui';

function formatBytes(value: number) { return value < 1024 * 1024 ? `${(value / 1024).toFixed(0)} KB` : `${(value / 1024 / 1024).toFixed(1)} MB`; }
function formatBuild(build: string) {
  const match = /^(\d{4})(\d{2})(\d{2})-(\d{2})(\d{2})/.exec(build);
  return match ? `${match[3]}/${match[2]}/${match[1]} ${match[4]}:${match[5]}` : build;
}

/** Versão instalada, verificação de atualização, preparação com hash e autoteste, aplicação confirmada e reversão. */
export function UpdatePanel() {
  const { session, api } = useBackend();
  const [status, setStatus] = useState<UpdateStatus | null>(null);
  const [busy, setBusy] = useState('');
  const [error, setError] = useState('');
  const [message, setMessage] = useState('');
  const [confirm, setConfirm] = useState<'aplicar' | 'reverter' | null>(null);
  const [closing, setClosing] = useState(false);
  const [refresh, setRefresh] = useState(0);
  useEffect(() => {
    if (!session || !ON_THIS_COMPUTER) return;
    const controller = new AbortController();
    api.updateStatus(controller.signal).then(result => { if (!controller.signal.aborted) { setStatus(result); setError(''); } })
      .catch(cause => { if (!controller.signal.aborted) setError(cause instanceof Error ? cause.message : 'Não foi possível consultar a versão.'); });
    return () => controller.abort();
  }, [api, session, refresh]);
  if (!session || !ON_THIS_COMPUTER || !status) return null;

  async function run(label: string, action: () => Promise<string>) {
    setBusy(label); setError(''); setMessage('');
    try { setMessage(await action()); setRefresh(n => n + 1); }
    catch (cause) { setError(cause instanceof Error ? cause.message : 'A operação falhou.'); }
    finally { setBusy(''); setConfirm(null); }
  }
  const available = status.disponivel?.nova ? status.disponivel : null;

  return <section className="update-panel" aria-labelledby="update-title">
    <div className="section-heading"><h3 id="update-title"><Sparkles size={17} /> Versão e atualizações</h3>{status.instalado && status.canal_configurado && <Button disabled={!!busy || closing} onClick={() => void run('verificar', async () => { const found = await api.updateCheck(); return found.nova ? `Nova versão disponível: build ${formatBuild(found.build)} (${formatBytes(found.tamanho)}).` : 'Você já está na versão mais recente.'; })}><RefreshCw size={16} /> {busy === 'verificar' ? 'Verificando…' : 'Verificar atualizações'}</Button>}</div>
    <p className="muted">Nexus Wolf's {status.versao} · build {formatBuild(status.build)} · {status.instalado ? 'instalado' : 'modo portátil'} · dados em <code>{status.pasta_dados}</code>{status.importado ? ' · biblioteca importada da versão portátil nesta abertura' : ''}.</p>
    {!status.instalado && <p className="muted">No modo portátil as atualizações chegam recompilando o projeto; <code>Abrir Nexus.bat</code> abre sempre a build mais recente. O instalador do Windows ativa a atualização automática.</p>}
    {status.instalado && !status.canal_configurado && <p className="muted">Nenhum canal de atualização configurado nesta instalação.</p>}
    {error && <p role="alert" className="form-error">{error}</p>}
    {status.erro && !error && <p role="alert" className="form-error">{status.erro}</p>}
    {message && <p role="status" className="form-success">{message}</p>}
    {closing && <p role="status" className="form-success">O Nexus vai fechar e reabrir na versão escolhida. Se não reabrir sozinho, abra pelo atalho.</p>}
    {available && !status.preparada && <div className="update-box"><p>Build <strong>{formatBuild(available.build)}</strong> ({formatBytes(available.tamanho)}){available.notas ? `: ${available.notas}` : ''}. Preparar baixa o pacote, confere o SHA-256 e executa o autoteste da versão nova; nada é trocado ainda.</p><Button variant="primary" disabled={!!busy || closing} onClick={() => void run('preparar', async () => { const staged = await api.updatePrepare(); return `Versão ${formatBuild(staged.build)} preparada e aprovada no autoteste. Aplique quando quiser.`; })}><DownloadCloud size={16} /> {busy === 'preparar' ? 'Preparando…' : 'Baixar e preparar'}</Button></div>}
    {status.preparada && <div className="update-box"><p>Build <strong>{formatBuild(status.preparada.build)}</strong> pronta para aplicar. Ao aplicar, o Nexus fecha, a pasta instalada é trocada e o aplicativo reabre; a versão atual fica guardada para reverter.</p>
      {confirm === 'aplicar' ? <div className="control-row"><Button variant="primary" disabled={!!busy || closing} onClick={() => void run('aplicar', async () => { const result = await api.updateApply(); setClosing(result.fechando); return `Aplicando a build ${formatBuild(result.aplicando)}…`; })}>{busy === 'aplicar' ? 'Aplicando…' : 'Confirmar: fechar e atualizar'}</Button><Button disabled={!!busy} onClick={() => setConfirm(null)}>Agora não</Button></div>
        : <Button variant="primary" disabled={!!busy || closing} onClick={() => setConfirm('aplicar')}>Aplicar atualização</Button>}
    </div>}
    {status.anterior && <div className="update-box update-previous"><p>Versão anterior guardada: build <strong>{formatBuild(status.anterior.build)}</strong>. Reverter fecha o Nexus, devolve essa versão e reabre.</p>
      {confirm === 'reverter' ? <div className="control-row"><Button disabled={!!busy || closing} onClick={() => void run('reverter', async () => { const result = await api.updateRollback(); setClosing(result.fechando); return 'Revertendo…'; })}><RotateCcw size={16} /> {busy === 'reverter' ? 'Revertendo…' : 'Confirmar: fechar e reverter'}</Button><Button disabled={!!busy} onClick={() => setConfirm(null)}>Cancelar</Button></div>
        : <Button disabled={!!busy || closing} onClick={() => setConfirm('reverter')}><RotateCcw size={16} /> Reverter para a versão anterior</Button>}
    </div>}
  </section>;
}
