import { useEffect, useState } from 'react';
import { Power, Smartphone } from 'lucide-react';
import { AUTHORITY_URL, ON_THIS_COMPUTER, type NetworkAccess } from '../services/api';
import { useBackend } from '../services/BackendProvider';
import { Button } from './ui';

/** Liga ou desliga o acesso pela rede local. Só aparece no computador; o celular não pode ampliar o próprio acesso. */
export function NetworkPanel() {
  const { api, session } = useBackend();
  const [status, setStatus] = useState<NetworkAccess | null>(null);
  const [port, setPort] = useState('');
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  const [refresh, setRefresh] = useState(0);
  useEffect(() => {
    if (!session || !ON_THIS_COMPUTER) return;
    const controller = new AbortController();
    api.networkAccess(controller.signal).then(result => { if (!controller.signal.aborted) { setStatus(result); setPort(String(result.porta)); setError(''); } })
      .catch(cause => { if (!controller.signal.aborted) setError(cause instanceof Error ? cause.message : 'Não foi possível consultar o acesso pela rede.'); });
    return () => controller.abort();
  }, [api, session, refresh]);
  if (!session || !ON_THIS_COMPUTER) return null;

  const on = Boolean(status?.ativo && status.executando);
  async function toggle(active: boolean) {
    const chosen = Number(port);
    if (active && (!Number.isInteger(chosen) || chosen < 1024 || chosen > 65535)) { setError('Informe uma porta entre 1024 e 65535.'); return; }
    setBusy(true); setError('');
    try { const next = await api.setNetworkAccess(active, active ? chosen : undefined); setStatus(next); setPort(String(next.porta)); }
    catch (cause) { setError(cause instanceof Error ? cause.message : 'Não foi possível alterar o acesso pela rede.'); setRefresh(n => n + 1); }
    finally { setBusy(false); }
  }

  return <section className="network-panel" aria-labelledby="network-title">
    <div className="section-heading"><h3 id="network-title"><Smartphone size={17} /> Acesso pelo celular</h3><span className={`service-status ${on ? 'online' : ''}`}>{!status ? 'Consultando…' : on ? 'Ligado' : status.ativo ? 'Ligado, com erro' : 'Desligado'}</span></div>
    <p className="muted">Abre a sua biblioteca para o celular na rede Wi-Fi de casa, por HTTPS com um certificado criado neste computador. Fica desligado por padrão e só pode ser alterado aqui.</p>
    {error && <p role="alert" className="form-error">{error}</p>}
    {status?.erro && !error && <p role="alert" className="form-error">{status.erro}</p>}
    <div className="network-controls">
      <div><label htmlFor="network-port" className="field-label">Porta</label><input id="network-port" className="input" type="number" min={1024} max={65535} value={port} disabled={busy || on} onChange={e => setPort(e.target.value)} /></div>
      <Button variant={on ? 'secondary' : 'primary'} disabled={busy || !status} onClick={() => void toggle(!on)}><Power size={16} /> {busy ? 'Aguarde…' : on ? 'Desligar' : 'Ligar'}</Button>
    </div>
    {on && status && <>
      <h4>No celular, abra um destes endereços</h4>
      <ul className="network-addresses">{status.enderecos.map(address => <li key={address}><code>{address}</code></li>)}</ul>
      <ol className="network-steps">
        <li>Conecte o celular ao mesmo Wi-Fi deste computador.</li>
        <li>Instale o certificado da autoridade local: <a href={AUTHORITY_URL} download="nexus-ca.crt">baixar nexus-ca.crt</a>. Ele também fica na pasta <code>certificados</code> dentro da pasta de dados; a chave privada nunca sai de lá.</li>
        <li>Android: Configurações → Segurança → Criptografia e credenciais → Instalar certificado → Certificado de CA. iPhone: abra o arquivo, instale o perfil em Ajustes e ative a confiança em Ajustes → Geral → Sobre → Ajustes de Confiança de Certificado.</li>
        <li>Abra o endereço acima no navegador do celular, entre no seu perfil e use "Adicionar à tela inicial" para ter o ícone do Nexus.</li>
      </ol>
      <p className="muted network-fingerprint">Impressão digital da autoridade (SHA-256): <code>{status.certificado?.ca_impressao}</code>. Certificado do servidor válido até {status.certificado?.validade}; ele é renovado sozinho quando o endereço deste computador muda. Se o Windows perguntar sobre o firewall, permita apenas em redes privadas.</p>
    </>}
    {!on && status?.ca_disponivel && <p className="muted">O certificado já existe: ligar de novo reaproveita a mesma autoridade instalada nos celulares.</p>}
  </section>;
}
