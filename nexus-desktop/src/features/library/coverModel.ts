import type { CoverCandidate, ExternalDetails, GameInput } from '../../services/api';

/** Só links https simples viram `href`; qualquer outro valor vindo de fora é descartado. */
export function safeHttpsUrl(value: string | null | undefined): string {
  try {
    const url = new URL(value ?? '');
    return url.protocol === 'https:' && !url.username && !url.password && (url.port === '' || url.port === '443') ? url.href : '';
  } catch { return ''; }
}

/** Identidade estável de um resultado: fonte + identificador do provedor (nunca a URL da imagem). */
export const candidateKey = (item: Pick<CoverCandidate, 'fonte' | 'id'>) => `${item.fonte}:${item.id}`;

const SHORT_PLATFORMS: [RegExp, string][] = [[/^Microsoft Windows$|^Windows$/, 'PC'], [/^macOS$/, 'Mac'], [/^PlayStation (\d)$/, 'PS$1'], [/^Nintendo Switch( 2)?$/, 'Switch$1'], [/^Xbox Series X e Series S$/, 'Xbox Series'], [/^Xbox Series X and Series S$/, 'Xbox Series']];
export const shortPlatform = (name: string) => SHORT_PLATFORMS.reduce((value, [pattern, short]) => value.replace(pattern, short), name);

/** Linha curta de plataformas para o card: até três nomes abreviados e "+n" para o resto. */
export function platformSummary(names: string[], limit = 3): string {
  const shown = names.slice(0, limit).map(shortPlatform);
  return names.length > limit ? `${shown.join(', ')} +${names.length - limit}` : shown.join(', ');
}

/** Normaliza para comparar nomes: sem acentos, sem pontuação, sem sufixos como "(jogo eletrônico)". */
export function normalizeTitle(value: string) {
  return value.normalize('NFD').replace(/[̀-ͯ]/g, '').toLowerCase().replace(/\([^)]*\)/g, ' ').replace(/[^a-z0-9]+/g, ' ').trim();
}

/** Ordena candidatos pela aderência ao nome digitado; empate favorece a Steam (arte oficial em 3:4) e depois a ordem da fonte. */
export function rankCandidates(query: string, items: CoverCandidate[]): CoverCandidate[] {
  const wanted = normalizeTitle(query);
  const score = (item: CoverCandidate) => {
    const title = normalizeTitle(item.titulo);
    const match = !wanted ? 0 : title === wanted ? 3 : title.startsWith(wanted) || wanted.startsWith(title) ? 2 : title.includes(wanted) ? 1 : 0;
    return match * 2 + (item.fonte === 'steam' ? 1 : 0);
  };
  return items.map((item, index) => ({ item, index, score: score(item) })).sort((a, b) => b.score - a.score || a.index - b.index).map(entry => entry.item);
}

export type FillField = 'nome' | 'plataforma' | 'genero' | 'data_lancamento' | 'desenvolvedor' | 'publicadora' | 'descricao';
export const FILL_LABELS: Record<FillField, string> = { nome: 'Nome do jogo', plataforma: 'Plataforma', genero: 'Gênero', data_lancamento: 'Lançamento', desenvolvedor: 'Desenvolvedor', publicadora: 'Publicadora', descricao: 'Descrição' };
export interface FillChange { field: FillField; label: string; current: string; next: string }
export interface FillResult { form: GameInput; filled: FillField[]; conflicts: FillChange[]; platformChoices: string[] }

const same = (field: FillField, a: string, b: string) => field === 'nome' ? normalizeTitle(a) === normalizeTitle(b) : a.trim().toLowerCase() === b.trim().toLowerCase();

/**
 * Decide o que a ficha externa preenche no formulário. Só campos da obra entram aqui: progresso, status, coleção,
 * favorito, notas, troféus, minutos e as datas da jornada pessoal nunca são tocados.
 *
 * - Campo vazio: preenchido. Num jogo novo, o nome digitado é só o termo da busca e a plataforma padrão não escolhida
 *   à mão também contam como vazios.
 * - Campo já preenchido com outro valor: vira um conflito para a pessoa confirmar dentro do modal.
 * - Várias plataformas possíveis: a seleção atual é preservada se estiver entre elas; senão viram uma escolha rápida.
 */
export function mergeDetails(form: GameInput, details: ExternalDetails, options: { isNew: boolean; touched: ReadonlySet<string> }): FillResult {
  // Limites iguais aos do serviço (GameInput): a ficha nunca produz um valor que o salvamento rejeitaria.
  const proposed: Partial<Record<FillField, string>> = {
    nome: details.titulo.slice(0, 150), genero: details.genero.slice(0, 80), data_lancamento: details.data_lancamento ?? '',
    desenvolvedor: details.desenvolvedores.join(', ').slice(0, 200), publicadora: details.publicadoras.join(', ').slice(0, 200), descricao: details.descricao.slice(0, 4000),
  };
  let platformChoices: string[] = [];
  const mapped = details.plataformas_nexus;
  if (mapped.length === 1) proposed.plataforma = mapped[0];
  else if (mapped.length > 1 && !mapped.includes(form.plataforma)) platformChoices = mapped;
  const next: GameInput = { ...form, fonte_externa: details.fonte, id_externo: details.id, url_origem: safeHttpsUrl(details.origem) };
  const filled: FillField[] = [];
  const conflicts: FillChange[] = [];
  for (const [field, raw] of Object.entries(proposed) as [FillField, string][]) {
    const value = raw.trim();
    if (!value) continue;
    const current = (form[field] ?? '') as string;
    const treatAsEmpty = current.trim() === '' || (options.isNew && (field === 'nome' || (field === 'plataforma' && !options.touched.has('plataforma'))));
    if (treatAsEmpty) { (next as Record<FillField, string | null>)[field] = value; filled.push(field); }
    else if (!same(field, current, value)) conflicts.push({ field, label: FILL_LABELS[field], current, next: value });
  }
  return { form: next, filled, conflicts, platformChoices };
}

/** Aplica as substituições que a pessoa confirmou. */
export function applyChanges(form: GameInput, changes: FillChange[]): GameInput {
  return changes.reduce((current, change) => ({ ...current, [change.field]: change.next }), form);
}

/** Texto curto e anunciável sobre o que foi preenchido e de onde veio. */
export function fillSummary(filled: FillField[], coverApplied: boolean, source: string): string {
  const parts = filled.map(field => FILL_LABELS[field].toLowerCase());
  if (coverApplied) parts.unshift('capa');
  if (!parts.length) return `Nenhum campo vazio para preencher a partir de ${source}.`;
  return `Preenchido a partir de ${source}: ${parts.join(', ')}. Os campos continuam editáveis.`;
}
