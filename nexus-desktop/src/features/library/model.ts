import type { Ficha, GameInput } from '../../services/api';

export function trophies(earned: number, total: number) {
  return { percent: total > 0 ? Math.round(earned * 100 / total) : 0, platinum: total > 0 && earned === total, remaining: Math.max(0, total - earned) };
}

export const emptyFicha = (): Ficha => ({ requisitos_minimos: '', requisitos_recomendados: '', idiomas: [], classificacao: '', classificacao_detalhe: '', tempo_historia: null, tempo_extras: null, tempo_completo: null, metacritic: null, categorias: [] });
export const FICHA_KEYS = Object.keys(emptyFicha()) as (keyof Ficha)[];
/** Um campo da ficha "tem valor" quando não é vazio nem nulo; usado para contar e para decidir o que a fonte preenche. */
export function fichaHas(value: Ficha[keyof Ficha]) { return Array.isArray(value) ? value.length > 0 : value !== null && value !== ''; }
export function fichaCount(ficha: Ficha) { return FICHA_KEYS.filter(key => fichaHas(ficha[key])).length; }
/** Minutos → "12 h", "1 h 30 min" ou "45 min". */
export function formatDuration(minutes: number | null) {
  if (minutes === null || minutes <= 0) return '';
  const hours = Math.floor(minutes / 60), rest = minutes % 60;
  return hours === 0 ? `${rest} min` : rest === 0 ? `${hours} h` : `${hours} h ${rest} min`;
}

export const blankGame: GameInput = { nome: '', plataforma: 'PC', progresso: 0, capa_id: null, favorito: false, colecao_id: null, grupo: '', ordem: 1, data_inicio: null, data_termino: null,
  trofeus_obtidos: 0, trofeus_total: 0, status_avancado: '', notas: '', cronograma: {}, genero: '', minutos_jogados: 0,
  data_lancamento: null, desenvolvedor: '', publicadora: '', descricao: '', fonte_externa: '', id_externo: '', url_origem: '',
  ainda_jogando: false, trofeus_fonte: '', trofeus_escopo: '', trofeus_consultado_em: null, ficha: emptyFicha(), fundo_id: null, nota: null };

export function gamePayload(input: Partial<Omit<GameInput, 'data_inicio' | 'data_termino' | 'data_lancamento'>> & { data_inicio?: string | null; data_termino?: string | null; data_lancamento?: string | null }): GameInput {
  const result: GameInput = { ...blankGame, ...input, nome: input.nome?.trim() ?? '', data_inicio: input.data_inicio || null, data_termino: input.data_termino || null, data_lancamento: input.data_lancamento || null };
  if (!result.nome) throw new Error('Informe o nome do jogo.');
  if (!Number.isInteger(result.trofeus_obtidos) || !Number.isInteger(result.trofeus_total) || result.trofeus_obtidos < 0 || result.trofeus_obtidos > result.trofeus_total) throw new Error('Confira os troféus obtidos e o total.');
  if (result.data_inicio && result.data_termino && result.data_termino < result.data_inicio) throw new Error('O término não pode ser anterior ao início.');
  return result;
}
