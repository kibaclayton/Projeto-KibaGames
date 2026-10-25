import type { GameInput } from '../../services/api';

export function trophies(earned: number, total: number) {
  return { percent: total > 0 ? Math.round(earned * 100 / total) : 0, platinum: total > 0 && earned === total, remaining: Math.max(0, total - earned) };
}

export const blankGame: GameInput = { nome: '', plataforma: 'PC', progresso: 0, capa_id: null, favorito: false, colecao_id: null, grupo: '', ordem: 1, data_inicio: null, data_termino: null,
  trofeus_obtidos: 0, trofeus_total: 0, status_avancado: '', notas: '', cronograma: {}, genero: '', minutos_jogados: 0,
  data_lancamento: null, desenvolvedor: '', publicadora: '', descricao: '', fonte_externa: '', id_externo: '', url_origem: '' };

export function gamePayload(input: Partial<Omit<GameInput, 'data_inicio' | 'data_termino' | 'data_lancamento'>> & { data_inicio?: string | null; data_termino?: string | null; data_lancamento?: string | null }): GameInput {
  const result: GameInput = { ...blankGame, ...input, nome: input.nome?.trim() ?? '', data_inicio: input.data_inicio || null, data_termino: input.data_termino || null, data_lancamento: input.data_lancamento || null };
  if (!result.nome) throw new Error('Informe o nome do jogo.');
  if (!Number.isInteger(result.trofeus_obtidos) || !Number.isInteger(result.trofeus_total) || result.trofeus_obtidos < 0 || result.trofeus_obtidos > result.trofeus_total) throw new Error('Confira os troféus obtidos e o total.');
  if (result.data_inicio && result.data_termino && result.data_termino < result.data_inicio) throw new Error('O término não pode ser anterior ao início.');
  return result;
}
