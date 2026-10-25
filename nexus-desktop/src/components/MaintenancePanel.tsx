import { useEffect, useState } from 'react';
import { Archive, Download, HardDriveDownload, RotateCcw, ShieldCheck, Trash2 } from 'lucide-react';
import { ON_THIS_COMPUTER, type BackupInfo, type IntegrityReport, type OrphanReport } from '../services/api';
import { useBackend } from '../services/BackendProvider';
import { Button } from './ui';

function formatBytes(value: number) {
  if (value < 1024) return `${value} B`;
  if (value < 1024 * 1024) return `${(value / 1024).toFixed(0)} KB`;
  if (value < 1024 * 1024 * 1024) return `${(value / 1024 / 1024).toFixed(1)} MB`;
  return `${(value / 1024 / 1024 / 1024).toFixed(2)} GB`;
}
function formatMoment(iso: string) {
  const date = new Date(iso);
  return Number.isNaN(date.getTime()) ? iso : date.toLocaleString('pt-BR', { day: '2-digit', month: '2-digit', year: 'numeric', hour: '2-digit', minute: '2-digit' });
}
const REASONS: Record<string, string> = { manual: 'manual', 'antes-de-restaurar': 'segurança antes de restaurar', 'antes-de-limpar': 'segurança antes de limpar' };

/** Backup, restauração, integridade e imagens órfãs. Abrange todos os perfis, por isso só aparece no computador. */
export function MaintenancePanel() {
  const { session, api, expire, forgetThisDevice } = useBackend();
  const [folder, setFolder] = useState('');
  const [backups, setBackups] = useState<BackupInfo[] | null>(null);
  const [integrity, setIntegrity] = useState<IntegrityReport | null>(null);
  const [orphans, setOrphans] = useState<OrphanReport | null>(null);
  const [busy, setBusy] = useState('');
  const [error, setError] = useState('');
  const [message, setMessage] = useState('');
  const [confirm, setConfirm] = useState<{ kind: 'restaurar' | 'excluir' | 'limpar'; nome?: string } | null>(null);
  const [refresh, setRefresh] = useState(0);
  useEffect(() => {
    if (!session || !ON_THIS_COMPUTER) return;
    const controller = new AbortController();
    Promise.all([api.backups(controller.signal), api.orphans(controller.signal)]).then(([list, found]) => {
      if (controller.signal.aborted) return;
      setFolder(list.pasta); setBackups(list.itens); setOrphans(found); setError('');
    }).catch(cause => { if (!controller.signal.aborted) setError(cause instanceof Error ? cause.message : 'Não foi possível consultar a manutenção.'); });
    return () => controller.abort();
  }, [api, session, refresh]);
  if (!session || !ON_THIS_COMPUTER) return null;

  async function run(label: string, action: () => Promise<string>) {
    setBusy(label); setError(''); setMessage('');
    try { setMessage(await action()); setRefresh(n => n + 1); }
    catch (cause) { setError(cause instanceof Error ? cause.message : 'A operação falhou.'); }
    finally { setBusy(''); setConfirm(null); }
  }
  async function download(nome: string) {
    setBusy(nome); setError('');
    try {
      const blob = await api.downloadBackup(nome);
      const url = URL.createObjectURL(blob);
      const anchor = document.createElement('a');
      anchor.href = url; anchor.download = nome; document.body.appendChild(anchor); anchor.click(); anchor.remove();
      setTimeout(() => URL.revokeObjectURL(url), 60_000);
    } catch (cause) { setError(cause instanceof Error ? cause.message : 'Não foi possível baixar o backup.'); }
    finally { setBusy(''); }
  }

  return <section className="maintenance-panel" aria-labelledby="maintenance-title">
    <div className="section-heading"><h3 id="maintenance-title"><Archive size={17} /> Backup e recuperação</h3><Button variant="primary" disabled={!!busy} onClick={() => void run('criar', async () => { const made = await api.createBackup(); return `Backup criado: ${made.nome} (${formatBytes(made.bytes)}).`; })}><HardDriveDownload size={16} /> {busy === 'criar' ? 'Criando…' : 'Criar backup agora'}</Button></div>
    <p className="muted">Cada backup é um arquivo ZIP com todos os perfis, jogos, coleções e imagens, guardado em <code>{folder || '…'}</code>. Para levar a outro lugar, use <em>Baixar</em>; para restaurar um arquivo vindo de fora, copie-o para essa pasta. Restaurar substitui a biblioteca inteira, sempre depois de um backup de segurança automático.</p>
    {error && <p role="alert" className="form-error">{error}</p>}
    {message && <p role="status" className="form-success">{message}</p>}
    {backups && backups.length === 0 && <p className="muted">Nenhum backup ainda.</p>}
    {backups && backups.length > 0 && <ul className="backup-list">{backups.map(item => <li key={item.nome}>
      <span>
        <strong>{item.manifesto ? formatMoment(item.manifesto.criado) : item.nome}</strong>
        <small>{item.valido && item.manifesto ? `${REASONS[item.manifesto.motivo] ?? item.manifesto.motivo} · ${item.manifesto.contagens.usuarios} perfis, ${item.manifesto.contagens.jogos} jogos, ${item.manifesto.imagens_arquivos} imagens · ${formatBytes(item.bytes)}` : item.erro || 'Arquivo inválido'}</small>
        <small className="backup-file">{item.nome}</small>
      </span>
      <span className="backup-actions">
        <Button variant="ghost" aria-label={`Baixar ${item.nome}`} disabled={!!busy} onClick={() => void download(item.nome)}><Download size={16} /></Button>
        <Button variant="ghost" aria-label={`Restaurar ${item.nome}`} disabled={!!busy || !item.valido} onClick={() => setConfirm({ kind: 'restaurar', nome: item.nome })}><RotateCcw size={16} /></Button>
        <Button variant="ghost" aria-label={`Excluir ${item.nome}`} disabled={!!busy} onClick={() => setConfirm({ kind: 'excluir', nome: item.nome })}><Trash2 size={16} /></Button>
      </span>
    </li>)}</ul>}
    {confirm?.kind === 'restaurar' && <div className="confirm-box" role="alert"><p>Restaurar <strong>{confirm.nome}</strong>? A biblioteca atual inteira (todos os perfis, jogos e imagens) será substituída pelo conteúdo do backup. Um backup de segurança do estado atual é criado antes, e todos os perfis precisam entrar de novo.</p><Button variant="primary" disabled={!!busy} onClick={() => void run('restaurar', async () => { const result = await api.restoreBackup(confirm.nome!); forgetThisDevice(); setTimeout(() => expire(`Biblioteca restaurada a partir de ${result.restaurado}. Entre novamente.`), 50); return `Restaurado. Backup de segurança: ${result.backup_seguranca}.`; })}>{busy === 'restaurar' ? 'Restaurando…' : 'Confirmar restauração'}</Button><Button disabled={!!busy} onClick={() => setConfirm(null)}>Cancelar</Button></div>}
    {confirm?.kind === 'excluir' && <div className="confirm-box" role="alert"><p>Excluir o arquivo <strong>{confirm.nome}</strong>? Esta ação não pode ser desfeita.</p><Button disabled={!!busy} onClick={() => void run('excluir', async () => { await api.deleteBackup(confirm.nome!); return 'Backup excluído.'; })}>Confirmar exclusão</Button><Button disabled={!!busy} onClick={() => setConfirm(null)}>Manter</Button></div>}

    <div className="section-heading maintenance-subheading"><h4><ShieldCheck size={16} /> Integridade do banco</h4><Button disabled={!!busy} onClick={() => void run('integridade', async () => { const report = await api.integrity(); setIntegrity(report); return report.ok ? 'Banco íntegro.' : 'O banco apresentou problemas; veja o relatório.'; })}>{busy === 'integridade' ? 'Verificando…' : 'Verificar'}</Button></div>
    {integrity && <p className={`muted ${integrity.ok ? '' : 'form-error'}`}>{integrity.ok ? `Verificação ok · esquema ${integrity.esquema} · ${integrity.contagens.usuarios} perfis, ${integrity.contagens.jogos} jogos, ${integrity.contagens.colecoes} coleções, ${integrity.contagens.imagens} imagens.` : `Problemas: ${integrity.integridade.join('; ')} ${integrity.chaves_estrangeiras.length ? `· ${integrity.chaves_estrangeiras.length} referência(s) quebrada(s)` : ''}. Restaure um backup válido.`}</p>}

    <div className="section-heading maintenance-subheading"><h4><Trash2 size={16} /> Imagens sem uso</h4>{orphans && (orphans.registros > 0 || orphans.arquivos_sem_registro > 0) && <Button disabled={!!busy} onClick={() => setConfirm({ kind: 'limpar' })}>Limpar</Button>}</div>
    <p className="muted">{!orphans ? 'Consultando…' : orphans.registros === 0 && orphans.arquivos_sem_registro === 0 ? 'Nenhuma imagem sem uso.' : `${orphans.registros} imagem(ns) sem jogo, avatar ou coleção e ${orphans.arquivos_sem_registro} arquivo(s) sem registro, ocupando ${formatBytes(orphans.bytes)}.`}</p>
    {confirm?.kind === 'limpar' && <div className="confirm-box" role="alert"><p>Apagar as imagens sem uso? Um backup de segurança é criado antes.</p><Button disabled={!!busy} onClick={() => void run('limpar', async () => { const result = await api.cleanOrphans(); return `${result.arquivos_removidos} arquivo(s) removido(s), ${formatBytes(result.bytes_liberados)} liberados. Backup de segurança: ${result.backup_seguranca}.`; })}>{busy === 'limpar' ? 'Limpando…' : 'Confirmar limpeza'}</Button><Button disabled={!!busy} onClick={() => setConfirm(null)}>Cancelar</Button></div>}
  </section>;
}
