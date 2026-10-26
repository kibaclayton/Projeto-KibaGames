// Vite dev/preview talk to the separate service on 8765; the packaged app and phones on the LAN use the page's own origin.
const devPreview = ['1420', '4173'].includes(window.location.port);
export const API_BASE = devPreview ? 'http://127.0.0.1:8765/api' : `${window.location.origin}/api`;
export const ON_THIS_COMPUTER = ['127.0.0.1', 'localhost'].includes(window.location.hostname);
export const AUTHORITY_URL = `${API_BASE}/acesso-rede/ca.crt`;
export interface NetworkAccess {
  ativo: boolean; porta: number; executando: boolean; erro: string; enderecos: string[]; enderecos_atuais: string[];
  certificado: { validade: string; ca_impressao: string; ca_validade: string } | null; ca_disponivel: boolean; local: boolean;
}
export interface Profile { id: number; nome: string; avatar_id: string | null }
export interface Session { token: string; perfil: Profile; expira_em_segundos: number; aparelho_token?: string | null; aparelho_id?: number | null }
export interface RememberedDeviceInfo { id: number; nome: string; criado: string; ultimo_uso: string; expira: string }
export interface Summary { total: number; em_andamento: number; concluidos: number; favoritos: number; colecoes: number }
export interface Health { status: string; versao: string; banco: string; schema: number; build?: string; instalado?: boolean }
export interface UpdateManifest { versao: string; build: string; arquivo: string; sha256: string; tamanho: number; data?: string; notas?: string; nova: boolean }
export interface UpdateStatus {
  instalado: boolean; versao: string; build: string; pasta_dados: string; pasta_app: string; importado: boolean;
  canal: string; canal_configurado: boolean; disponivel: UpdateManifest | null; preparada: (UpdateManifest & { pasta: string }) | null; anterior: { versao?: string; build: string } | null; erro: string;
}
export interface Game {
  id: number; nome: string; plataforma: string; progresso: number; capa_id: string | null;
  favorito: boolean; colecao_id: number | null; ordem: number;
  data_inicio: string | null; data_termino: string | null; status_avancado: string;
  trofeus_obtidos: number; trofeus_total: number; trofeus_percentual: number; platinado: boolean;
  genero: string; minutos_jogados: number; atualizado: string;
  // Ficha vinda de uma fonte externa (opcional, editável); nunca inclui dados da jornada pessoal.
  data_lancamento: string | null; desenvolvedor: string; publicadora: string; fonte_externa: '' | CoverSource; id_externo: string;
  // Jornada em andamento (sem término), posição na ordem manual da biblioteca e origem do total de troféus.
  ainda_jogando: boolean; posicao: number | null; trofeus_fonte: string;
}
export interface GameDetails extends Game { grupo: string; notas: string; cronograma: Record<string, 'single' | 'range'>; descricao: string; url_origem: string; trofeus_escopo: string; trofeus_consultado_em: string | null }
export type GameInput = Omit<GameDetails, 'id' | 'atualizado' | 'trofeus_percentual' | 'platinado' | 'posicao'>;
export type GameSort = 'minha' | 'nome' | 'recentes' | 'progresso' | 'colecao';
export type PlatformFamily = 'todas' | 'pc' | 'playstation' | 'xbox' | 'nintendo';
export interface AvatarSlot { posicao: number; imagem_id: string | null; ativo: boolean }
export interface CommonsImage { titulo: string; previa: string; imagem: string; origem: string; licenca: string; autor: string }
export interface Preferences { tema: 'escuro' | 'claro'; movimento: 'padrao' | 'reduzida' | 'desligada'; densidade: 'confortavel' | 'compacta'; destaque: 'roxo' | 'magenta' | 'verde' | 'azul' }
export interface Collection { id: number; nome: string; capa_id: string | null; total: number; mosaico: string[] }
export interface ImageResult { id: string; tipo: string; largura: number; altura: number; bytes: number; miniatura_bytes: number }
export interface BackupInfo { nome: string; bytes: number; modificado: string; valido: boolean; erro: string; manifesto: { aplicativo: string; esquema: number; criado: string; motivo: string; contagens: Record<string, number>; imagens_arquivos: number } | null }
export interface IntegrityReport { ok: boolean; integridade: string[]; chaves_estrangeiras: unknown[]; contagens: Record<string, number>; esquema: number }
export interface OrphanReport { registros: number; arquivos_sem_registro: number; bytes: number }
export type CoverSource = 'steam' | 'wikipedia' | 'igdb';
/** Resultado resumido da busca: `fonte + id` é a identidade estável usada para pedir a ficha completa ao serviço. */
export interface CoverCandidate { fonte: CoverSource; id: string; titulo: string; imagem: string; previa: string; origem: string; ano: number | null; plataformas: string[] }
export interface CoverSearch { itens: CoverCandidate[]; avisos: string[]; igdb_configurada?: boolean }
/** Ficha tipada do jogo escolhido, já normalizada pelo serviço (plataformas do Nexus, gênero sugerido, total de troféus quando a fonte publica). */
export interface ExternalDetails {
  fonte: CoverSource; id: string; titulo: string; imagem: string | null; origem: string; data_lancamento: string | null; ano: number | null;
  plataformas: string[]; plataformas_nexus: string[]; generos: string[]; genero: string; desenvolvedores: string[]; publicadoras: string[]; descricao: string; atribuicao: string;
  trofeus_total: number | null; trofeus_fonte: string; trofeus_escopo: string; trofeus_consultado_em: string | null;
}
export interface DuplicateRef { id: number; nome: string; plataforma: string }
export interface ApplyResult { detalhes: ExternalDetails; imagem: ImageResult | null; erro_capa: string; duplicado_em: DuplicateRef | null }

export class ApiError extends Error {
  constructor(message: string, public status: number) { super(message); }
}

export class NexusApi {
  /** `onUnauthorized` é chamado quando um pedido autenticado recebe 401: a sessão foi revogada ou expirou. */
  constructor(private token?: string, private onUnauthorized?: () => void) {}

  private async response(path: string, options: RequestInit = {}) {
    const headers = new Headers(options.headers);
    if (this.token) headers.set('Authorization', `Bearer ${this.token}`);
    if (typeof options.body === 'string') headers.set('Content-Type', 'application/json');
    let result: Response;
    const timeout = AbortSignal.timeout(30000);
    const signal = options.signal ? AbortSignal.any([options.signal, timeout]) : timeout;
    try { result = await fetch(API_BASE + path, { ...options, headers, signal }); }
    catch (error) {
      if (options.signal?.aborted) throw error;
      throw new ApiError('O serviço local não respondeu. Verifique se o Nexus está aberto e tente novamente.', 0);
    }
    if (!result.ok) {
      const data = await result.json().catch(() => ({}));
      const message = typeof data.detail === 'string' ? data.detail : Array.isArray(data.detail) ? data.detail.map((e: { msg: string }) => e.msg).join(' ') : 'Não foi possível concluir a operação.';
      // A troca de senha responde 401 para "senha atual incorreta" sem revogar a sessão; só os demais 401 a derrubam.
      if (result.status === 401 && this.token && path !== '/conta/senha') this.onUnauthorized?.();
      throw new ApiError(message, result.status);
    }
    return result;
  }

  private async json<T>(path: string, options?: RequestInit): Promise<T> {
    const result = await this.response(path, options);
    return result.status === 204 ? undefined as T : result.json();
  }

  health(signal?: AbortSignal) { return this.json<Health>('/saude', { signal }); }
  profiles(signal?: AbortSignal) { return this.json<Profile[]>('/perfis', { signal }); }
  createProfile(nome: string, senha: string, signal?: AbortSignal) { return this.json<Profile>('/perfis', { method: 'POST', body: JSON.stringify({ nome, senha }), signal }); }
  login(perfil_id: number, senha: string, signal?: AbortSignal, lembrar = false, aparelho = '') { return this.json<Session>('/sessao', { method: 'POST', body: JSON.stringify({ perfil_id, senha, lembrar, aparelho }), signal }); }
  /** "Esqueci a senha": aceito só a partir deste computador; desconecta sessões e aparelhos lembrados do perfil. */
  resetPassword(perfil_id: number, nova_senha: string, confirmar_senha: string, signal?: AbortSignal) { return this.json<void>(`/perfis/${perfil_id}/redefinir-senha`, { method: 'PUT', body: JSON.stringify({ nova_senha, confirmar_senha }), signal }); }
  deviceLogin(token: string, signal?: AbortSignal) { return this.json<Session>('/sessao/aparelho', { method: 'POST', body: JSON.stringify({ token }), signal }); }
  devices(signal?: AbortSignal) { return this.json<RememberedDeviceInfo[]>('/conta/aparelhos', { signal }); }
  forgetDevice(id: number) { return this.json<void>(`/conta/aparelhos/${id}`, { method: 'DELETE' }); }
  forgetDevices() { return this.json<void>('/conta/aparelhos', { method: 'DELETE' }); }
  logout() { return this.json<void>('/sessao', { method: 'DELETE' }); }
  summary(signal?: AbortSignal) { return this.json<Summary>('/resumo', { signal }); }
  games(params: { busca?: string; genero?: string; favorito?: boolean; colecao_id?: number; pagina?: number; limite?: number; ordenacao?: GameSort } = {}, signal?: AbortSignal) {
    const query = new URLSearchParams(Object.entries(params).filter(([, value]) => value !== undefined).map(([key, value]) => [key, String(value)]));
    return this.json<{ itens: Game[]; total: number; pagina: number; limite: number }>(`/jogos?${query}`, { signal });
  }
  highlights(signal?: AbortSignal) { return this.json<Game[]>('/destaques', { signal }); }
  game(id: number) { return this.json<GameDetails>(`/jogos/${id}`); }
  createGame(input: Pick<GameInput, 'nome'> & Partial<GameInput>) { return this.json<GameDetails>('/jogos', { method: 'POST', body: JSON.stringify(input) }); }
  patchGame(id: number, patch: Partial<GameInput>) { return this.json<GameDetails>(`/jogos/${id}`, { method: 'PATCH', body: JSON.stringify(patch) }); }
  deleteGame(id: number) { return this.json<void>(`/jogos/${id}`, { method: 'DELETE' }); }
  collections() { return this.json<Collection[]>('/colecoes'); }
  createCollection(nome: string, capa_id: string | null = null) { return this.json<Pick<Collection, 'id' | 'nome' | 'capa_id'>>('/colecoes', { method: 'POST', body: JSON.stringify({ nome, capa_id }) }); }
  updateCollection(id: number, nome: string, capa_id: string | null) { return this.json<Pick<Collection, 'id' | 'nome' | 'capa_id'>>(`/colecoes/${id}`, { method: 'PUT', body: JSON.stringify({ nome, capa_id }) }); }
  deleteCollection(id: number) { return this.json<void>(`/colecoes/${id}`, { method: 'DELETE' }); }
  uploadImage(file: Blob, tipo: 'capa' | 'avatar' | 'colecao', crop?: { x: number; y: number; width: number; height: number }) {
    const query = new URLSearchParams({ tipo });
    if (crop) Object.entries({ x: crop.x, y: crop.y, largura: crop.width, altura: crop.height }).forEach(([k, v]) => query.set(k, String(v)));
    return this.json<ImageResult>(`/imagens?${query}`, { method: 'POST', body: file });
  }
  updateStatus(signal?: AbortSignal) { return this.json<UpdateStatus>('/atualizacao', { signal }); }
  updateCheck() { return this.json<UpdateManifest>('/atualizacao/verificar', { method: 'POST' }); }
  updatePrepare() { return this.json<UpdateManifest & { pasta: string }>('/atualizacao/preparar', { method: 'POST' }); }
  updateApply() { return this.json<{ aplicando: string; fechando: boolean }>('/atualizacao/aplicar', { method: 'POST' }); }
  updateRollback() { return this.json<{ revertendo: boolean; fechando: boolean }>('/atualizacao/reverter', { method: 'POST' }); }
  backups(signal?: AbortSignal) { return this.json<{ pasta: string; itens: BackupInfo[] }>('/manutencao/backups', { signal }); }
  createBackup() { return this.json<BackupInfo>('/manutencao/backups', { method: 'POST' }); }
  async downloadBackup(nome: string) { return (await this.response(`/manutencao/backups/${encodeURIComponent(nome)}`)).blob(); }
  deleteBackup(nome: string) { return this.json<void>(`/manutencao/backups/${encodeURIComponent(nome)}`, { method: 'DELETE' }); }
  restoreBackup(nome: string) { return this.json<{ restaurado: string; backup_seguranca: string; contagens: Record<string, number> | null }>(`/manutencao/backups/${encodeURIComponent(nome)}/restaurar`, { method: 'POST' }); }
  integrity(signal?: AbortSignal) { return this.json<IntegrityReport>('/manutencao/integridade', { signal }); }
  orphans(signal?: AbortSignal) { return this.json<OrphanReport>('/manutencao/orfas', { signal }); }
  cleanOrphans() { return this.json<{ registros_removidos: number; arquivos_removidos: number; bytes_liberados: number; backup_seguranca: string }>('/manutencao/orfas/limpar', { method: 'POST' }); }
  searchCovers(nome: string, fonte: CoverSource | 'todas' = 'todas', signal?: AbortSignal, plataforma: PlatformFamily = 'todas') {
    return this.json<CoverSearch>(`/capas/busca?${new URLSearchParams({ nome, fonte, plataforma })}`, { signal });
  }
  coverSources(signal?: AbortSignal) { return this.json<{ igdb_configurada: boolean; arquivo_igdb: string }>('/capas/fontes', { signal }); }
  /** Ordem manual da biblioteca: os ids informados vão para o início, na sequência dada; atômico no serviço. */
  reorderGames(ids: number[]) { return this.json<{ total: number }>('/jogos/ordem', { method: 'PUT', body: JSON.stringify({ ids }) }); }
  avatarGallery(signal?: AbortSignal) { return this.json<AvatarSlot[]>('/conta/avatares', { signal }); }
  setAvatarSlot(posicao: number, imagem_id: string) { return this.json<AvatarSlot[]>(`/conta/avatares/${posicao}`, { method: 'PUT', body: JSON.stringify({ imagem_id }) }); }
  removeAvatarSlot(posicao: number) { return this.json<AvatarSlot[]>(`/conta/avatares/${posicao}`, { method: 'DELETE' }); }
  searchAvatars(termo: string, signal?: AbortSignal) { return this.json<{ itens: CommonsImage[] }>(`/avatares/busca?${new URLSearchParams({ termo })}`, { signal }); }
  preferences(signal?: AbortSignal) { return this.json<Preferences>('/conta/preferencias', { signal }); }
  savePreferences(preferences: Preferences) { return this.json<Preferences>('/conta/preferencias', { method: 'PUT', body: JSON.stringify(preferences) }); }
  /** Escolha de um resultado: ficha e capa do mesmo identificador; nada é gravado no jogo até "Salvar jogo". */
  applyCandidate(fonte: CoverSource, id: string, jogo_id: number | null = null, signal?: AbortSignal) {
    return this.json<ApplyResult>('/capas/aplicar', { method: 'POST', body: JSON.stringify(jogo_id ? { fonte, id, jogo_id } : { fonte, id }), signal });
  }
  async coverPreview(url: string, signal?: AbortSignal) { return (await this.response(`/capas/previa?${new URLSearchParams({ url })}`, { signal })).blob(); }
  downloadCover(url: string, tipo: 'capa' | 'avatar' | 'colecao' = 'capa') { return this.json<ImageResult>('/imagens/url', { method: 'POST', body: JSON.stringify({ url, tipo }) }); }
  async image(id: string, miniatura = true, signal?: AbortSignal) { return (await this.response(`/imagens/${id}?miniatura=${miniatura}`, { signal })).blob(); }
  networkAccess(signal?: AbortSignal) { return this.json<NetworkAccess>('/acesso-rede', { signal }); }
  setNetworkAccess(ativo: boolean, porta?: number) { return this.json<NetworkAccess>('/acesso-rede', { method: 'PUT', body: JSON.stringify(porta ? { ativo, porta } : { ativo }) }); }
  avatar(imagem_id: string | null) { return this.json<{ avatar_id: string | null }>('/conta/avatar', { method: 'PUT', body: JSON.stringify({ imagem_id }) }); }
  password(senha_atual: string, nova_senha: string, confirmar_senha: string) { return this.json<void>('/conta/senha', { method: 'PUT', body: JSON.stringify({ senha_atual, nova_senha, confirmar_senha }) }); }
}
