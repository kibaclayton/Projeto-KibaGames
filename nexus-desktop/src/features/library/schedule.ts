/** Cronograma de sessões: modelo puro portado de calendario.py (legado). Datas ISO locais, sem fuso. */
export type DayKind = 'single' | 'range';
export type Schedule = Record<string, DayKind>;
export type DayAppearance = 'empty' | 'single' | 'edge' | 'middle' | 'future';

export const MONTHS = ['Janeiro', 'Fevereiro', 'Março', 'Abril', 'Maio', 'Junho', 'Julho', 'Agosto', 'Setembro', 'Outubro', 'Novembro', 'Dezembro'];
export const WEEKDAYS = ['Seg', 'Ter', 'Qua', 'Qui', 'Sex', 'Sáb', 'Dom'];
export const WEEKDAY_NAMES = ['segunda-feira', 'terça-feira', 'quarta-feira', 'quinta-feira', 'sexta-feira', 'sábado', 'domingo'];
export const MAX_INTERVAL_DAYS = 3660;
const MIN_YEAR = 1900, MAX_YEAR = 9998;

const pad = (value: number) => String(value).padStart(2, '0');
/** Data local em ISO (YYYY-MM-DD) sem conversão para UTC. */
export function isoDate(date: Date) { return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}`; }
export function parseIso(iso: string) {
  const match = /^(\d{4})-(\d{2})-(\d{2})$/.exec(iso);
  if (!match) throw new Error('Use datas ISO YYYY-MM-DD no cronograma.');
  const date = new Date(Number(match[1]), Number(match[2]) - 1, Number(match[3]));
  if (isoDate(date) !== iso) throw new Error('Data inválida no cronograma.');
  return date;
}
export function todayIso() { return isoDate(new Date()); }
export function addDays(iso: string, amount: number) { const date = parseIso(iso); date.setDate(date.getDate() + amount); return isoDate(date); }
export function daysBetween(a: string, b: string) { return Math.round((parseIso(b).getTime() - parseIso(a).getTime()) / 86400000); }
/** Dia da semana com segunda = 0 e domingo = 6, como no calendário legado. */
export function weekday(iso: string) { return (parseIso(iso).getDay() + 6) % 7; }
export function daysInMonth(year: number, month: number) { return new Date(year, month, 0).getDate(); }

export function toggleDay(schedule: Schedule, iso: string): Schedule {
  const next = { ...schedule };
  if (next[iso]) delete next[iso]; else next[iso] = 'single';
  return next;
}

/** Marca uma sequência contínua, em qualquer ordem, limitada a 10 anos. */
export function markInterval(schedule: Schedule, a: string, b: string): Schedule {
  const [start, end] = a <= b ? [a, b] : [b, a];
  const length = daysBetween(start, end);
  if (length > MAX_INTERVAL_DAYS) throw new Error('Selecione um intervalo de até 10 anos.');
  const next = { ...schedule };
  for (let i = 0; i <= length; i++) next[addDays(start, i)] = 'range';
  return next;
}

/** Marca todas as ocorrências do dia da semana no mês; se todas já estiverem marcadas, remove-as. */
export function toggleWeekday(schedule: Schedule, year: number, month: number, day: number): Schedule {
  const days: string[] = [];
  for (let number = 1; number <= daysInMonth(year, month); number++) {
    const iso = `${year}-${pad(month)}-${pad(number)}`;
    if (weekday(iso) === day) days.push(iso);
  }
  const remove = days.every(iso => schedule[iso]);
  const next = { ...schedule };
  for (const iso of days) { if (remove) delete next[iso]; else next[iso] ??= 'single'; }
  return next;
}

/** Menor data vira início; maior vira término. Para um único dia, término fica vazio. */
export function bounds(schedule: Schedule): { start: string | null; end: string | null } {
  const days = Object.keys(schedule).sort();
  if (!days.length) return { start: null, end: null };
  const start = days[0], end = days[days.length - 1];
  return { start, end: start === end ? null : end };
}

export function appearance(schedule: Schedule, iso: string, today = todayIso()): DayAppearance {
  const kind = schedule[iso];
  if (!kind) return 'empty';
  if (iso > today) return 'future';
  if (kind === 'single') return 'single';
  const previous = schedule[addDays(iso, -1)] === 'range', following = schedule[addDays(iso, 1)] === 'range';
  return previous && following ? 'middle' : 'edge';
}

/** Intervalo contínuo a partir das datas digitadas; uma única data vira um dia de sequência. */
export function scheduleFromDates(start: string | null, end: string | null): Schedule {
  if (start && end) return start <= end ? markInterval({}, start, end) : {};
  const only = start || end;
  return only ? { [only]: 'range' } : {};
}

/** Semanas do mês começando na segunda; posições vazias são null. */
export function monthGrid(year: number, month: number): (number | null)[][] {
  const first = weekday(`${year}-${pad(month)}-01`), total = daysInMonth(year, month);
  const cells: (number | null)[] = Array.from({ length: first }, () => null);
  for (let day = 1; day <= total; day++) cells.push(day);
  while (cells.length % 7) cells.push(null);
  const weeks: (number | null)[][] = [];
  for (let i = 0; i < cells.length; i += 7) weeks.push(cells.slice(i, i + 7));
  return weeks;
}

export function shiftMonth(year: number, month: number, amount: number) {
  const index = year * 12 + month - 1 + amount;
  const nextYear = Math.floor(index / 12), nextMonth = (index % 12) + 1;
  return nextYear >= MIN_YEAR && nextYear <= MAX_YEAR ? { year: nextYear, month: nextMonth } : { year, month };
}

export function monthOf(iso: string) { const date = parseIso(iso); return { year: date.getFullYear(), month: date.getMonth() + 1 }; }
export function monthLabel(year: number, month: number) { return `${MONTHS[month - 1]} ${year}`; }
export function dayLabel(iso: string) { const date = parseIso(iso); return `${date.getDate()} de ${MONTHS[date.getMonth()].toLowerCase()} de ${date.getFullYear()}`; }
export const APPEARANCE_LABELS: Record<DayAppearance, string> = { empty: 'sem sessão', single: 'dia avulso', edge: 'início ou fim de sequência', middle: 'dentro da sequência', future: 'agendado' };
