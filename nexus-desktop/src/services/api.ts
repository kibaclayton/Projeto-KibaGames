const localRuntime = ['127.0.0.1', 'localhost'].includes(window.location.hostname) && !['1420', '4173'].includes(window.location.port);
export const API_BASE = localRuntime ? `${window.location.origin}/api` : 'http://127.0.0.1:8765/api';
export interface Profile { id: number; nome: string; avatar_id: string | null }
export interface Session { token: string; perfil: Profile; expira_em_segundos: number }
export interface Summary { total: number; em_andamento: number; concluidos: number; favoritos: number; colecoes: number }
export interface Health { status: string; versao: string; banco: string; schema: number }
export interface Game {
  id: number; nome: string; plataforma: string; progresso: number; capa_id: string | null;
  favorito: boolean; colecao_id: number | null; ordem: number;
  data_inicio: string | null; data_termino: string | null; status_avancado: string;
  trofeus_obtidos: number; trofeus_total: number; trofeus_percentual: number; platinado: boolean;
  genero: string; minutos_jogados: number; atualizado: string;
}
export interface GameDetails extends Game { grupo: string; notas: string; cronograma: Record<string, 'single' | 'range'> }
export type GameInput = Omit<GameDetails, 'id' | 'atualizado' | 'trofeus_percentual' | 'platinado'>;
export interface Collection { id: number; nome: string; capa_id: string | null; total: number; mosaico: string[] }
export interface ImageResult { id: string; tipo: string; largura: number; altura: number; bytes: number; miniatura_bytes: number }

export class ApiError extends Error {
  constructor(message: string, public status: number) { super(message); }
}

export class NexusApi {
  constructor(private token?: string) {}

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
  login(perfil_id: number, senha: string, signal?: AbortSignal) { return this.json<Session>('/sessao', { method: 'POST', body: JSON.stringify({ perfil_id, senha }), signal }); }
  logout() { return this.json<void>('/sessao', { method: 'DELETE' }); }
  summary(signal?: AbortSignal) { return this.json<Summary>('/resumo', { signal }); }
  games(params: { busca?: string; genero?: string; favorito?: boolean; colecao_id?: number; pagina?: number; limite?: number } = {}, signal?: AbortSignal) {
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
  downloadCover(url: string, tipo: 'capa' | 'avatar' | 'colecao' = 'capa') { return this.json<ImageResult>('/imagens/url', { method: 'POST', body: JSON.stringify({ url, tipo }) }); }
  async image(id: string, miniatura = true, signal?: AbortSignal) { return (await this.response(`/imagens/${id}?miniatura=${miniatura}`, { signal })).blob(); }
  avatar(imagem_id: string | null) { return this.json<{ avatar_id: string | null }>('/conta/avatar', { method: 'PUT', body: JSON.stringify({ imagem_id }) }); }
  password(senha_atual: string, nova_senha: string, confirmar_senha: string) { return this.json<void>('/conta/senha', { method: 'PUT', body: JSON.stringify({ senha_atual, nova_senha, confirmar_senha }) }); }
}
