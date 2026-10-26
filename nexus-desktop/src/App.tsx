import { useEffect, useRef, useState } from 'react';
import { ChevronRight, Folder, Library, Menu, Moon, Palette, RotateCcw, Settings2, Star, Sun, UserRound, X } from 'lucide-react';
import { Brand } from './components/Brand';
import { Button, Modal, Panel } from './components/ui';
import { DEFAULT_PREFERENCES, devicePreferences, useTheme } from './theme/ThemeProvider';
import { LibraryView } from './features/library/LibraryView';
import { AccountPanel } from './components/AccountPanel';
import { AvatarImage } from './components/AvatarImage';
import { BackendPanel } from './components/BackendPanel';
import { MaintenancePanel } from './components/MaintenancePanel';
import { NetworkPanel } from './components/NetworkPanel';
import { TrophyPanel } from './components/TrophyPanel';
import { UpdatePanel } from './components/UpdatePanel';
import { useBackend } from './services/BackendProvider';
import type { Preferences } from './services/api';

const pages = [
  { id: 'library', label: 'Biblioteca', icon: Library },
  { id: 'collections', label: 'Coleções', icon: Folder },
  { id: 'favorites', label: 'Favoritos', icon: Star },
  { id: 'design', label: 'Personalizar visual', icon: Palette },
] as const;
type Page = typeof pages[number]['id'];

/**
 * Preferências visuais: com perfil conectado valem as do perfil (guardadas no serviço); sem sessão vale o padrão do
 * aparelho (localStorage). Trocar de perfil ou sair troca o visual na hora, sem recarregar.
 */
function useVisualPreferences() {
  const { session, api } = useBackend();
  const { preferences, setPreferences } = useTheme();
  const profileId = session?.perfil.id ?? null;
  const lastProfile = useRef<number | null>(null);
  useEffect(() => {
    if (profileId === null) { if (lastProfile.current !== null) setPreferences(devicePreferences(), false); lastProfile.current = null; return; }
    lastProfile.current = profileId;
    const controller = new AbortController();
    api.preferences(controller.signal).then(remote => { if (!controller.signal.aborted) setPreferences(remote, false); }).catch(() => { /* Sem acesso ao serviço, o padrão do aparelho segue valendo. */ });
    return () => controller.abort();
  }, [api, profileId, setPreferences]);
  const [saveError, setSaveError] = useState('');
  const update = (next: Preferences) => {
    setPreferences(next, profileId === null);
    setSaveError('');
    if (profileId !== null) api.savePreferences(next).catch(cause => setSaveError(cause instanceof Error ? cause.message : 'Não foi possível guardar a preferência no perfil.'));
  };
  return { preferences, update, saveError, perProfile: profileId !== null };
}

export function App() {
  const [page, setPage] = useState<Page>('library');
  const [menuOpen, setMenuOpen] = useState(false);
  const [settingsOpen, setSettingsOpen] = useState(false);
  // Importações e sincronizações feitas em Conta e preferências recarregam a biblioteca ao mudar esta chave.
  const [libraryEpoch, setLibraryEpoch] = useState(0);
  const { theme } = useTheme();
  const visual = useVisualPreferences();
  const { session } = useBackend();
  const title = pages.find(item => item.id === page)!.label;
  const navigate = (next: Page) => { setPage(next); setMenuOpen(false); };
  const toggleTheme = () => visual.update({ ...visual.preferences, tema: visual.preferences.tema === 'claro' ? 'escuro' : 'claro' });

  return <div className="app-shell">
    <a href="#content" className="skip-link">Ir para o conteúdo</a>
    <aside className="sidebar">
      <div className="sidebar-top"><Brand /><Button className="mobile-menu" variant="ghost" aria-label={menuOpen ? 'Fechar navegação' : 'Abrir navegação'} aria-expanded={menuOpen} aria-controls="main-navigation" onClick={() => setMenuOpen(!menuOpen)}>{menuOpen ? <X /> : <Menu />}</Button></div>
      <div id="main-navigation" className={`sidebar-content ${menuOpen ? 'is-open' : ''}`}>
        <p className="eyebrow nav-caption">SEU UNIVERSO</p>
        <nav aria-label="Navegação principal">{pages.map(({ id, label, icon: Icon }) => <button key={id} className={`nav-item ${page === id ? 'active' : ''}`} aria-current={page === id ? 'page' : undefined} onClick={() => navigate(id)}><Icon size={19} /><span>{label}</span>{page === id && <span className="active-dot" />}</button>)}</nav>
        <div className="sidebar-bottom"><div className="foundation-note"><span className="status-dot" /> NOVA JORNADA <small>Uma nova casa para seus jogos.</small></div>
          <button className="profile-entry" onClick={() => setSettingsOpen(true)}>{session ? <AvatarImage profileId={session.perfil.id} avatarId={session.perfil.avatar_id} name={session.perfil.nome} /> : <span className="avatar"><UserRound size={20} /></span>}<span><strong>{session?.perfil.nome ?? 'Entrar no perfil'}</strong><small>Conta e preferências</small></span><Settings2 size={17} /></button>
        </div>
      </div>
    </aside>
    <div className="workspace">
      <header className="topbar"><span className="breadcrumb">Nexus Wolf’s <ChevronRight size={13} /> <span>{title}</span></span><div className="header-actions"><span className="version">NEXUS WOLF’S · 0.3</span><Button variant="ghost" aria-label={theme === 'dark' ? 'Ativar tema claro' : 'Ativar tema escuro'} onClick={toggleTheme}>{theme === 'dark' ? <Sun size={19} /> : <Moon size={19} />}</Button><Button variant="ghost" aria-label="Abrir preferências" onClick={() => setSettingsOpen(true)}><Settings2 size={19} /></Button></div></header>
      <main id="content" tabIndex={-1}>
        <div className="page-heading"><div><p className="eyebrow">A PRÓXIMA FASE COMEÇA AQUI</p><h1>{page === 'library' ? 'Seus mundos. Um só lugar.' : title}</h1></div><span className="stage-badge"><span className="status-dot" /> Biblioteca local</span></div>
        {page === 'design' ? <Personalize preferences={visual.preferences} onChange={visual.update} perProfile={visual.perProfile} saveError={visual.saveError} /> : <LibraryView key={`${session?.perfil.id ?? 0}:${page}:${libraryEpoch}`} section={page} onLogin={() => setSettingsOpen(true)} />}
        <footer className="page-footer"><span>NEXUS WOLF’S</span><span>Feito para a sua próxima aventura.</span></footer>
      </main>
    </div>
    <Modal open={settingsOpen} onClose={() => setSettingsOpen(false)} title="Conta e preferências">{settingsOpen && <BackendPanel />}{settingsOpen && <AccountPanel />}{settingsOpen && <TrophyPanel onLibraryChanged={() => setLibraryEpoch(n => n + 1)} />}{settingsOpen && <NetworkPanel />}{settingsOpen && <MaintenancePanel />}{settingsOpen && <UpdatePanel />}<div className="preference-row"><div><h3>Aparência</h3><p className="muted">Tema {theme === 'dark' ? 'escuro' : 'claro'}. Mais opções em Personalizar visual.</p></div><Button onClick={toggleTheme}>{theme === 'dark' ? <Sun size={18} /> : <Moon size={18} />} Alternar tema</Button></div></Modal>
  </div>;
}

const OPTIONS: { key: keyof Preferences; title: string; help: string; choices: [string, string][] }[] = [
  { key: 'tema', title: 'Tema', help: 'Escuro é o Dark Wand original; claro mantém os mesmos tons de destaque com contraste revisado.', choices: [['escuro', 'Escuro'], ['claro', 'Claro']] },
  { key: 'movimento', title: 'Animações', help: 'A preferência do sistema por movimento reduzido vale sempre, independentemente desta escolha.', choices: [['padrao', 'Padrão'], ['reduzida', 'Reduzida'], ['desligada', 'Desligada']] },
  { key: 'densidade', title: 'Densidade da grade', help: 'Compacta mostra mais capas por linha, mantendo alvos de toque e textos legíveis.', choices: [['confortavel', 'Confortável'], ['compacta', 'Compacta']] },
  { key: 'destaque', title: 'Cor de destaque', help: 'Só cores aprovadas do Design System; o contraste dos textos é preservado.', choices: [['roxo', 'Roxo'], ['magenta', 'Magenta'], ['verde', 'Verde'], ['azul', 'Azul']] },
];
const SWATCH: Record<Preferences['destaque'], string> = { roxo: '#9D00FF', magenta: '#FF007F', verde: '#00E676', azul: '#2F7BFF' };

function Personalize({ preferences, onChange, perProfile, saveError }: { preferences: Preferences; onChange: (next: Preferences) => void; perProfile: boolean; saveError: string }) {
  const [confirmReset, setConfirmReset] = useState(false);
  const isDefault = (Object.keys(DEFAULT_PREFERENCES) as (keyof Preferences)[]).every(key => preferences[key] === DEFAULT_PREFERENCES[key]);
  return <div className="design-system personalize">
    <Panel>
      <p className="eyebrow">PERSONALIZAR VISUAL</p>
      <h2>O Nexus do seu jeito</h2>
      <p className="muted">{perProfile ? 'Estas escolhas ficam guardadas no seu perfil e valem só para ele.' : 'Sem perfil conectado, as escolhas valem para este aparelho; ao entrar, cada perfil usa as suas.'} Tudo muda na hora, sem recarregar.</p>
      {saveError && <p role="alert" className="form-error">{saveError}</p>}
      {OPTIONS.map(option => <div key={option.key} className="option-group" role="group" aria-labelledby={`opt-${option.key}`}>
        <h3 id={`opt-${option.key}`}>{option.title}</h3>
        <div className="control-row">{option.choices.map(([value, label]) => <button key={value} type="button" className={`chip ${preferences[option.key] === value ? 'selected' : ''}`} aria-pressed={preferences[option.key] === value} onClick={() => onChange({ ...preferences, [option.key]: value })}>
          {option.key === 'destaque' && <span className="swatch-dot" style={{ backgroundColor: SWATCH[value as Preferences['destaque']] }} aria-hidden="true" />}{label}</button>)}</div>
        <p className="muted">{option.help}</p>
      </div>)}
      <div className="control-row"><Button disabled={isDefault} onClick={() => setConfirmReset(true)}><RotateCcw size={16} /> Restaurar padrões</Button></div>
      {confirmReset && <div className="confirm-box" role="alert"><p>Voltar ao tema escuro, animações padrão, grade confortável e destaque roxo?</p><Button onClick={() => { onChange(DEFAULT_PREFERENCES); setConfirmReset(false); }}>Restaurar</Button><Button onClick={() => setConfirmReset(false)}>Manter como está</Button></div>}
    </Panel>
    <Panel className="preview-panel">
      <p className="eyebrow">PRÉVIA</p>
      <h2>Como fica na biblioteca</h2>
      <div className="preview-grid" aria-hidden="true">{['Alan Wake 2', 'Hades', 'Zelda'].map(name => <div key={name} className="game-card preview-card"><div className="cover-placeholder"><span>NEXUS</span></div><div className="game-overlay"><span className="platform-label">PC</span><h3>{name}</h3></div></div>)}</div>
      <div className="control-row"><Button variant="primary">Botão principal</Button><Button>Secundário</Button><button type="button" className="chip selected" aria-pressed="true">Filtro ativo</button></div>
      <p className="muted">Passe o mouse sobre um card para ver a animação com a intensidade escolhida.</p>
    </Panel>
  </div>;
}
