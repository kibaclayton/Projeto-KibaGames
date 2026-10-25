import { test } from 'node:test';
import assert from 'node:assert/strict';
const schedule = await import('../src/features/library/schedule.ts').catch(() => ({}));

test('ISO dates use local calendar fields and reject impossible days', () => {
  assert.equal(typeof schedule.isoDate, 'function');
  assert.equal(schedule.isoDate(new Date(2026, 0, 1)), '2026-01-01');
  assert.equal(schedule.addDays('2026-02-28', 1), '2026-03-01');
  assert.equal(schedule.addDays('2024-02-28', 1), '2024-02-29');
  assert.equal(schedule.daysBetween('2026-01-01', '2026-12-31'), 364);
  assert.equal(schedule.weekday('2026-10-23'), 4, 'Friday is index 4 when Monday is 0');
  assert.throws(() => schedule.parseIso('2026-02-30'));
  assert.throws(() => schedule.parseIso('07/09/2026'));
});

test('clicking a day toggles a single entry without touching the others', () => {
  const base = { '2026-09-10': 'range' };
  const marked = schedule.toggleDay(base, '2026-09-07');
  assert.deepEqual(marked, { '2026-09-10': 'range', '2026-09-07': 'single' });
  assert.deepEqual(schedule.toggleDay(marked, '2026-09-07'), base);
  assert.deepEqual(base, { '2026-09-10': 'range' }, 'input is not mutated');
});

test('dragging creates an inclusive sequence in either direction and caps at ten years', () => {
  const forward = schedule.markInterval({}, '2026-09-10', '2026-09-12');
  assert.deepEqual(forward, { '2026-09-10': 'range', '2026-09-11': 'range', '2026-09-12': 'range' });
  assert.deepEqual(schedule.markInterval({ '2026-09-01': 'single' }, '2026-09-12', '2026-09-10'), { '2026-09-01': 'single', ...forward });
  assert.deepEqual(schedule.markInterval({}, '2026-10-31', '2026-11-01'), { '2026-10-31': 'range', '2026-11-01': 'range' }, 'crosses the month boundary');
  assert.throws(() => schedule.markInterval({}, '2016-01-01', '2026-10-23'), /10 anos/);
});

test('weekday headers mark every occurrence in the month and remove them when all are set', () => {
  const saturdays = schedule.toggleWeekday({ '2026-10-10': 'range' }, 2026, 10, 5);
  assert.deepEqual(Object.keys(saturdays).sort(), ['2026-10-03', '2026-10-10', '2026-10-17', '2026-10-24', '2026-10-31']);
  assert.equal(saturdays['2026-10-10'], 'range', 'existing sequence days keep their kind');
  assert.equal(saturdays['2026-10-03'], 'single');
  const weekends = schedule.toggleWeekday(saturdays, 2026, 10, 6);
  assert.equal(Object.keys(weekends).length, 9);
  assert.deepEqual(schedule.toggleWeekday(weekends, 2026, 10, 5), { '2026-10-04': 'single', '2026-10-11': 'single', '2026-10-18': 'single', '2026-10-25': 'single' });
});

test('bounds sync the smallest and largest dates and leave the end empty for a single day', () => {
  assert.deepEqual(schedule.bounds({}), { start: null, end: null });
  assert.deepEqual(schedule.bounds({ '2026-09-07': 'single' }), { start: '2026-09-07', end: null });
  assert.deepEqual(schedule.bounds({ '2026-09-10': 'range', '2026-09-07': 'single', '2026-11-01': 'range' }), { start: '2026-09-07', end: '2026-11-01' });
});

test('appearance distinguishes edges, middles, single days and future plans', () => {
  const days = { '2026-09-10': 'range', '2026-09-11': 'range', '2026-09-12': 'range', '2026-09-07': 'single', '2026-12-25': 'range' };
  const today = '2026-10-23';
  assert.equal(schedule.appearance(days, '2026-09-10', today), 'edge');
  assert.equal(schedule.appearance(days, '2026-09-11', today), 'middle');
  assert.equal(schedule.appearance(days, '2026-09-12', today), 'edge');
  assert.equal(schedule.appearance(days, '2026-09-07', today), 'single');
  assert.equal(schedule.appearance(days, '2026-12-25', today), 'future', 'future wins over every other style');
  assert.equal(schedule.appearance(days, '2026-09-08', today), 'empty');
  assert.equal(schedule.appearance({ '2026-10-23': 'range' }, '2026-10-23', today), 'edge', 'today is not future');
});

test('typed dates replace the selection with a continuous interval', () => {
  assert.deepEqual(schedule.scheduleFromDates('2026-09-10', '2026-09-11'), { '2026-09-10': 'range', '2026-09-11': 'range' });
  assert.deepEqual(schedule.scheduleFromDates('2026-09-10', null), { '2026-09-10': 'range' });
  assert.deepEqual(schedule.scheduleFromDates(null, '2026-09-10'), { '2026-09-10': 'range' });
  assert.deepEqual(schedule.scheduleFromDates(null, null), {});
  assert.deepEqual(schedule.scheduleFromDates('2026-09-12', '2026-09-10'), {}, 'inverted dates are left for the form validation');
});

test('month grid starts on Monday, handles leap years and month navigation limits', () => {
  const october = schedule.monthGrid(2026, 10);
  assert.deepEqual(october[0], [null, null, null, 1, 2, 3, 4]);
  assert.deepEqual(october[october.length - 1], [26, 27, 28, 29, 30, 31, null]);
  const february = schedule.monthGrid(2024, 2);
  assert.equal(february.flat().filter(Boolean).length, 29);
  assert.deepEqual(february[0], [null, null, null, 1, 2, 3, 4]);
  assert.equal(schedule.monthGrid(2026, 2).flat().filter(Boolean).length, 28);
  assert.deepEqual(schedule.shiftMonth(2026, 12, 1), { year: 2027, month: 1 });
  assert.deepEqual(schedule.shiftMonth(2026, 1, -1), { year: 2025, month: 12 });
  assert.deepEqual(schedule.shiftMonth(1900, 1, -1), { year: 1900, month: 1 });
  assert.equal(schedule.monthLabel(2026, 10), 'Outubro 2026');
  assert.equal(schedule.dayLabel('2026-10-23'), '23 de outubro de 2026');
});
