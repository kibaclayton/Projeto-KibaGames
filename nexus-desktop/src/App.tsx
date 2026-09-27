import { useState } from 'react';
import { motion } from 'framer-motion';
import { Check, ChevronRight, Folder, Library, Menu, Moon, Palette, Settings2, Sparkles, Star, Sun, UserRound, X } from 'lucide-react';
import { Brand } from './components/Brand';
import { Button, Modal, Panel } from './components/ui';
import { useTheme } from './theme/ThemeProvider';
import { LibraryView } from './features/library/LibraryView';
import { BackendPanel } from './components/BackendPanel';
import { useBackend } from './services/BackendProvider';

const pages = [
  { id: 'library', label: 'Biblioteca', icon: Library },
  { id: 'collections', label: 'Coleções', icon: Folder },
  { id: 'favorites', label: 'Favoritos', icon: Star },
  { id: 'design', label: 'Design System', icon: Palette },
] as const;
type Page = typeof pages[number]['id'];

export function App() {
  const [page, setPage] = useState<Page>('library');
  const [menuOpen, setMenuOpen] = useState(false);
  const [settingsOpen, setSettingsOpen] = useState(false);
  const { theme, toggleTheme } = useTheme();
  const { session } = useBackend();
  const title = pages.find(item => item.id === page)!.label;
  const navigate = (next: Page) => { setPage(next); setMenuOpen(false); };

  return <div className="app-shell">
    <a href="#content" className="skip-link">Ir para o conteúdo</a>
    <aside className="sidebar">
      <div className="sidebar-top"><Brand /><Button className="mobile-menu" variant="ghost" aria-label={menuOpen ? 'Fechar navegação' : 'Abrir navegação'} aria-expanded={menuOpen} aria-controls="main-navigation" onClick={() => setMenuOpen(!menuOpen)}>{menuOpen ? <X /> : <Menu />}</Button></div>
      <div id="main-navigation" className={`sidebar-content ${menuOpen ? 'is-open' : ''}`}>
        <p className="eyebrow nav-caption">SEU UNIVERSO</p>
        <nav aria-label="Navegação principal">{pages.map(({ id, label, icon: Icon }) => <button key={id} className={`nav-item ${page === id ? 'active' : ''}`} aria-current={page === id ? 'page' : undefined} onClick={() => navigate(id)}><Icon size={19} /><span>{label}</span>{page === id && <span className="active-dot" />}</button>)}</nav>
        <div className="sidebar-bottom"><div className="foundation-note"><span className="status-dot" /> NOVA JORNADA <small>Uma nova casa para seus jogos.</small></div>
          <button className="profile-entry" onClick={() => setSettingsOpen(true)}><span className="avatar"><UserRound size={20} /></span><span><strong>{session?.perfil.nome ?? 'Entrar no perfil'}</strong><small>Conta e preferências</small></span><Settings2 size={17} /></button>
        </div>
      </div>
    </aside>
    <div className="workspace">
      <header className="topbar"><span className="breadcrumb">Nexus Wolf’s <ChevronRight size={13} /> <span>{title}</span></span><div className="header-actions"><span className="version">NEXUS WOLF’S · 0.3</span><Button variant="ghost" aria-label={theme === 'dark' ? 'Ativar tema claro' : 'Ativar tema escuro'} onClick={toggleTheme}>{theme === 'dark' ? <Sun size={19} /> : <Moon size={19} />}</Button><Button variant="ghost" aria-label="Abrir preferências" onClick={() => setSettingsOpen(true)}><Settings2 size={19} /></Button></div></header>
      <main id="content" tabIndex={-1}>
        <div className="page-heading"><div><p className="eyebrow">A PRÓXIMA FASE COMEÇA AQUI</p><h1>{page === 'library' ? 'Seus mundos. Um só lugar.' : title}</h1></div><span className="stage-badge"><span className="status-dot" /> Biblioteca local</span></div>
        {page === 'design' ? <DesignSystem /> : <LibraryView key={`${session?.perfil.id ?? 0}:${page}`} section={page} onLogin={() => setSettingsOpen(true)} />}
        <footer className="page-footer"><span>NEXUS WOLF’S</span><span>Feito para a sua próxima aventura.</span></footer>
      </main>
    </div>
    <Modal open={settingsOpen} onClose={() => setSettingsOpen(false)} title="Conta e preferências">{settingsOpen && <BackendPanel />}<div className="preference-row"><div><h3>Aparência</h3><p className="muted">Tema {theme === 'dark' ? 'escuro' : 'claro'}</p></div><Button onClick={toggleTheme}>{theme === 'dark' ? <Sun size={18} /> : <Moon size={18} />} Alternar tema</Button></div></Modal>
  </div>;
}

function DesignSystem() {
  const [progress, setProgress] = useState(65);
  const [selected, setSelected] = useState('Todos');
  const swatches = [['Fundo', '#0A0B10'], ['Neon roxo', '#9D00FF'], ['Magenta', '#FF007F'], ['Sucesso', '#00E676'], ['Texto secundário', '#8890A5']];
  return <div className="design-system">
    <Panel><p className="eyebrow">01 / IDENTIDADE</p><h2>Cores que dão vida ao escuro</h2><div className="swatches">{swatches.map(([name, color]) => <div key={name}><div className="swatch" style={{ backgroundColor: color }} /><strong>{name}</strong><code>{color}</code></div>)}</div></Panel>
    <div className="design-columns"><Panel><p className="eyebrow">02 / TIPOGRAFIA</p><h2>Clareza em cada nível.</h2><p className="type-sample">Sua próxima aventura.</p><p>Inter, servida localmente. Leitura confortável em títulos, campos e textos de apoio.</p><p className="muted">Texto secundário · detalhes e metadados</p></Panel>
      <Panel><p className="eyebrow">03 / CONTROLES</p><h2>Pequenos detalhes. Mais controle.</h2><div className="control-row"><Button variant="primary" onClick={() => setProgress(100)}><Check size={16} /> Completar exemplo</Button><Button onClick={() => setProgress(0)}>Reiniciar</Button><Button disabled>Indisponível</Button></div><label className="field-label" htmlFor="demo-progress">Progresso de exemplo <span>{progress}%</span></label><input id="demo-progress" type="range" min="0" max="100" value={progress} onChange={event => setProgress(Number(event.target.value))} /><div className="control-row" aria-label="Exemplos de filtros">{['Todos', 'RPG', 'Ação', 'FPS'].map(genre => <button className={`chip ${genre === selected ? 'selected' : ''}`} aria-pressed={genre === selected} key={genre} onClick={() => setSelected(genre)}>{genre}</button>)}</div><p className="muted">Filtro de exemplo selecionado: {selected}</p></Panel></div>
    <div className="design-columns"><Panel><p className="eyebrow">04 / FORMULÁRIOS</p><h2>Uma base consistente</h2><label className="field-label" htmlFor="demo-name">Nome do jogo (exemplo)</label><input className="input" id="demo-name" placeholder="Ex.: Alan Wake 2" /><label className="field-label" htmlFor="demo-platform">Plataforma (exemplo)</label><select className="input" id="demo-platform" defaultValue="PC"><option>PC</option><option>PS5</option><option>Xbox</option></select><p className="muted">Campos de demonstração, sem salvar dados.</p></Panel><Panel><p className="eyebrow">05 / MOVIMENTO</p><h2>Uma presença sutil</h2><motion.div className="motion-sample" whileHover={{ y: -6 }} transition={{ duration: 0.3 }}><Sparkles size={28} /><span>Passe o mouse</span><small>Elevação de 6 px · brilho neon · 300 ms</small></motion.div><p className="muted">A preferência por movimento reduzido é respeitada.</p></Panel></div>
  </div>;
}
