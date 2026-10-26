import { useEffect, useId, useMemo, useRef, useState, type KeyboardEvent, type PointerEvent } from 'react';
import { ChevronLeft, ChevronRight, Eraser } from 'lucide-react';
import { Button } from '../../components/ui';
import { APPEARANCE_LABELS, WEEKDAYS, WEEKDAY_NAMES, addDays, appearance, bounds, dayLabel, daysInMonth, markInterval, monthGrid, monthLabel, monthOf, shiftMonth, todayIso, toggleDay, toggleWeekday, type Journey, type Schedule } from './schedule';

const pad = (value: number) => String(value).padStart(2, '0');
const MOVES: Record<string, number> = { ArrowLeft: -1, ArrowRight: 1, ArrowUp: -7, ArrowDown: 7 };

/** Calendário de sessões: clique marca um dia, arraste cria sequência, cabeçalho marca o dia da semana no mês. */
export function GameCalendar({ schedule, onChange, jump, journey }: { schedule: Schedule; onChange: (next: Schedule) => void; jump?: { iso: string | null; key: number }; journey?: Journey }) {
  const hintId = useId();
  const today = useMemo(todayIso, []);
  const [view, setView] = useState(() => monthOf(bounds(schedule).start ?? journey?.start ?? today));
  const [focused, setFocused] = useState(bounds(schedule).start ?? journey?.start ?? today);
  const [preview, setPreview] = useState<Schedule | null>(null);
  const [pendingFocus, setPendingFocus] = useState<string | null>(null);
  const [notice, setNotice] = useState('');
  const drag = useRef<{ anchor: string; end: string } | null>(null);
  const suppressClick = useRef(false);
  const keyboardAnchor = useRef<string | null>(null);
  const grid = useRef<HTMLDivElement>(null);

  useEffect(() => { if (jump?.iso) { setView(monthOf(jump.iso)); setFocused(jump.iso); } }, [jump?.key, jump?.iso]);
  useEffect(() => {
    if (!pendingFocus) return;
    grid.current?.querySelector<HTMLButtonElement>(`[data-day="${pendingFocus}"]`)?.focus();
    setPendingFocus(null);
  }, [pendingFocus]);

  const shown = preview ?? schedule;
  const weeks = monthGrid(view.year, view.month);
  const title = monthLabel(view.year, view.month);
  const iso = (day: number) => `${view.year}-${pad(view.month)}-${pad(day)}`;
  const prefix = `${view.year}-${pad(view.month)}`;
  const tabStop = focused.startsWith(prefix) ? focused : today.startsWith(prefix) ? today : iso(1);

  function commit(build: () => Schedule) {
    try { onChange(build()); setNotice(''); }
    catch (cause) { setNotice(cause instanceof Error ? cause.message : 'Não foi possível atualizar o calendário.'); }
  }
  function moveFocus(target: string) { setFocused(target); setView(monthOf(target)); setPendingFocus(target); }

  function pointerDown(event: PointerEvent<HTMLButtonElement>, day: string) {
    if (event.button !== 0) return;
    event.currentTarget.setPointerCapture(event.pointerId);
    suppressClick.current = false;
    drag.current = { anchor: day, end: day };
  }
  function pointerMove(event: PointerEvent<HTMLButtonElement>) {
    const current = drag.current;
    if (!current) return;
    const target = document.elementFromPoint(event.clientX, event.clientY)?.closest<HTMLElement>('[data-day]')?.dataset.day;
    if (!target || target === current.end) return;
    current.end = target;
    try { setPreview(markInterval(schedule, current.anchor, target)); } catch { setPreview(null); }
  }
  function pointerUp() {
    const current = drag.current;
    drag.current = null;
    setPreview(null);
    if (!current || current.end === current.anchor) return;
    suppressClick.current = true;
    keyboardAnchor.current = current.end;
    setFocused(current.end);
    commit(() => markInterval(schedule, current.anchor, current.end));
  }
  function click(day: string) {
    if (suppressClick.current) { suppressClick.current = false; return; }
    setFocused(day);
    keyboardAnchor.current = day;
    commit(() => toggleDay(schedule, day));
  }
  function keyDown(event: KeyboardEvent<HTMLDivElement>) {
    const day = (event.target as HTMLElement).dataset.day;
    if (!day) return;
    let target: string | null = null;
    if (event.key in MOVES) target = addDays(day, MOVES[event.key]);
    else if (event.key === 'Home') target = iso(1);
    else if (event.key === 'End') target = iso(daysInMonth(view.year, view.month));
    else if (event.key === 'PageUp' || event.key === 'PageDown') {
      const next = shiftMonth(view.year, view.month, event.key === 'PageUp' ? -1 : 1);
      target = `${next.year}-${pad(next.month)}-${pad(Math.min(Number(day.slice(8)), daysInMonth(next.year, next.month)))}`;
    } else if ((event.key === 'Enter' || event.key === ' ') && event.shiftKey) {
      event.preventDefault();
      const anchor = keyboardAnchor.current ?? day;
      keyboardAnchor.current = day;
      commit(() => markInterval(schedule, anchor, day));
      return;
    }
    if (target) { event.preventDefault(); moveFocus(target); }
  }

  return <div className="calendar">
    <div className="calendar-nav">
      <Button variant="ghost" aria-label="Mês anterior" onClick={() => setView(current => shiftMonth(current.year, current.month, -1))}><ChevronLeft size={18} /></Button>
      <h4 aria-live="polite">{title}</h4>
      <Button variant="ghost" aria-label="Próximo mês" onClick={() => setView(current => shiftMonth(current.year, current.month, 1))}><ChevronRight size={18} /></Button>
    </div>
    <div className="calendar-grid" role="grid" aria-label="Calendário de sessões de jogo" aria-describedby={hintId} ref={grid} onKeyDown={keyDown}>
      <div role="row" className="calendar-row">
        {WEEKDAYS.map((label, index) => <div role="columnheader" key={label}><button type="button" className="calendar-weekday" aria-label={`Marcar ou desmarcar todas as ${WEEKDAY_NAMES[index]}s de ${title}`} onClick={() => commit(() => toggleWeekday(schedule, view.year, view.month, index))}>{label}</button></div>)}
      </div>
      {weeks.map((week, row) => <div role="row" className="calendar-row" key={row}>
        {week.map((day, column) => {
          if (!day) return <div role="gridcell" key={column} className="calendar-empty" />;
          const value = iso(day), state = appearance(shown, value, today, journey);
          return <div role="gridcell" key={column}>
            <button type="button" className={`calendar-day ${value === today ? 'is-today' : ''}`} data-day={value} data-state={state} aria-label={`${dayLabel(value)}, ${APPEARANCE_LABELS[state]}`} aria-pressed={state !== 'empty'} tabIndex={value === tabStop ? 0 : -1}
              onPointerDown={event => pointerDown(event, value)} onPointerMove={pointerMove} onPointerUp={pointerUp} onPointerCancel={() => { drag.current = null; setPreview(null); }} onClick={() => click(value)} onFocus={() => setFocused(value)}>{day}</button>
          </div>;
        })}
      </div>)}
    </div>
    {notice && <p role="alert" className="form-error">{notice}</p>}
    <div className="calendar-legend" aria-hidden="true">
      <span><i data-state="single" /> Dia em que joguei</span><span><i data-state="edge" /> Início / fim de sequência</span><span><i data-state="middle" /> Entre datas</span><span><i data-state="journey" /> Jornada (sem sessão)</span><span><i data-state="future" /> Agendado / futuro</span>
    </div>
    <p id={hintId} className="calendar-hint">Clique marca um dia em que você jogou (conta em "dias em que joguei"); arraste cria uma sequência de planejamento; Sáb e Dom no cabeçalho marcam os fins de semana do mês. Dias futuros não contam como jogados. Pelo teclado: setas movem o foco, Enter marca e Shift+Enter cria uma sequência desde o último dia marcado.</p>
    <div className="calendar-actions"><Button disabled={!Object.keys(schedule).length} onClick={() => commit(() => ({}))}><Eraser size={15} /> Limpar seleção</Button></div>
  </div>;
}
