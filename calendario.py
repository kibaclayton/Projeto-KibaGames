"""Calendário local: dias avulsos, intervalos e seleção semanal por mês."""
import calendar
import json
from datetime import date, timedelta
import tkinter as tk
from tkinter import ttk

BG, PANEL, LIME, TEXT, MUTED = '#0b0e12', '#181e28', '#bcff36', '#f4f8ff', '#93a4b8'
MONTHS = ('Janeiro', 'Fevereiro', 'Março', 'Abril', 'Maio', 'Junho', 'Julho',
          'Agosto', 'Setembro', 'Outubro', 'Novembro', 'Dezembro')


class Schedule:
    def __init__(self, raw=None):
        self.days = {}
        if raw:
            values = json.loads(raw) if isinstance(raw, (str, bytes)) else raw
            if not isinstance(values, dict):
                raise ValueError('Cronograma inválido.')
            for key, kind in values.items():
                day = date.fromisoformat(key)
                if kind not in ('single', 'range'):
                    raise ValueError('Tipo de dia inválido.')
                self.days[day] = kind

    def dump(self):
        return json.dumps({day.isoformat(): kind for day, kind in sorted(self.days.items())})

    def toggle(self, day):
        if day in self.days:
            del self.days[day]
        else:
            self.days[day] = 'single'

    def interval(self, start, end):
        start, end = sorted((start, end))
        if (end - start).days > 3660:
            raise ValueError('Selecione um intervalo de até 10 anos.')
        for i in range((end - start).days + 1):
            self.days[start + timedelta(days=i)] = 'range'

    def weekday(self, year, month, weekday):
        days = [date(year, month, day) for day in range(1, calendar.monthrange(year, month)[1] + 1)
                if date(year, month, day).weekday() == weekday]
        remove = all(day in self.days for day in days)
        for day in days:
            if remove:
                self.days.pop(day, None)
            else:
                self.days.setdefault(day, 'single')

    def bounds(self):
        if not self.days:
            return None, None
        start, end = min(self.days), max(self.days)
        return start, end if start != end else None

    def appearance(self, day, today=None):
        kind = self.days.get(day)
        if not kind:
            return 'empty'
        if day > (today or date.today()):
            return 'future'
        if kind == 'single':
            return 'single'
        previous = day > date.min and self.days.get(day - timedelta(days=1)) == 'range'
        following = day < date.max and self.days.get(day + timedelta(days=1)) == 'range'
        return 'middle' if previous and following else 'edge'


class GameCalendar(ttk.Frame):
    def __init__(self, parent, schedule, changed):
        super().__init__(parent)
        self.schedule, self.changed = schedule, changed
        first = schedule.bounds()[0] or date.today()
        self.year, self.month = first.year, first.month
        self.anchor = None
        self.drag_end = None
        self.drag_base = None
        nav = ttk.Frame(self)
        nav.pack(fill='x')
        ttk.Button(nav, text='‹', width=3, command=lambda: self.navigate(-1)).pack(side='left')
        self.title = tk.Label(nav, bg=BG, fg=TEXT, font=('Segoe UI', 12, 'bold'))
        self.title.pack(side='left', expand=True)
        ttk.Button(nav, text='›', width=3, command=lambda: self.navigate(1)).pack(side='right')
        self.canvas = tk.Canvas(self, bg=PANEL, height=240, highlightthickness=1, highlightbackground='#343c48')
        self.canvas.pack(fill='x', pady=(8, 4))
        self.canvas.bind('<Configure>', lambda e: self.draw())
        self.canvas.bind('<ButtonPress-1>', self.press)
        self.canvas.bind('<B1-Motion>', self.motion)
        self.canvas.bind('<ButtonRelease-1>', self.release)
        legend = tk.Canvas(self, bg=BG, height=54, highlightthickness=0)
        legend.pack(fill='x')
        for x, y, kind, text in [(4, 5, 'edge', 'Início / fim de sequência'), (230, 5, 'middle', 'Entre datas'),
                                  (4, 31, 'single', 'Dia avulso'), (230, 31, 'future', 'Agendado / futuro')]:
            self.symbol(legend, x, y, x + 17, y + 17, kind)
            legend.create_text(x + 24, y + 8, text=text, anchor='w', fill=MUTED, font=('Segoe UI', 9))
        tk.Label(self, text='Clique: dia avulso • Arraste: sequência\nClique em Sáb e Dom: fins de semana deste mês',
                 bg=BG, fg=MUTED, justify='left', font=('Segoe UI', 9)).pack(anchor='w')
        ttk.Button(self, text='Limpar seleção', command=self.clear).pack(anchor='e', pady=(4, 0))
        self.draw()

    def clear(self):
        self.schedule.days.clear()
        self.changed()
        self.draw()

    def symbol(self, canvas, x1, y1, x2, y2, kind):
        if kind == 'single':
            canvas.create_oval(x1, y1, x2, y2, outline=LIME, width=1.5)
        elif kind == 'future':
            canvas.create_rectangle(x1, y1, x2, y2, outline=LIME, dash=(3, 3), width=1.5)
        elif kind == 'middle':
            canvas.create_rectangle(x1, y1, x2, y2, outline='#709332', fill='#293b20')
        elif kind == 'edge':
            canvas.create_rectangle(x1, y1, x2, y2, outline=LIME, fill=LIME)

    def navigate(self, amount):
        index = self.year * 12 + self.month - 1 + amount
        year, month = index // 12, index % 12 + 1
        if 1900 <= year <= 9998:
            self.year, self.month = year, month
            self.draw()

    def draw(self):
        self.title.config(text=f'{MONTHS[self.month - 1]} {self.year}')
        canvas = self.canvas
        canvas.delete('all')
        self.width = max(canvas.winfo_width(), 420) / 7
        self.weeks = calendar.Calendar(firstweekday=0).monthdayscalendar(self.year, self.month)
        for col, label in enumerate(('Seg', 'Ter', 'Qua', 'Qui', 'Sex', 'Sáb', 'Dom')):
            canvas.create_text((col + .5) * self.width, 18, text=label, fill=LIME, font=('Segoe UI', 10, 'bold'))
        for row, week in enumerate(self.weeks):
            for col, number in enumerate(week):
                if not number:
                    continue
                day = date(self.year, self.month, number)
                kind = self.schedule.appearance(day)
                x, y = (col + .5) * self.width, 52 + row * 33
                self.symbol(canvas, x - 15, y - 13, x + 15, y + 13, kind)
                canvas.create_text(x, y, text=str(number), fill=BG if kind == 'edge' else TEXT,
                                   font=('Segoe UI', 10, 'bold' if day == date.today() else 'normal'))

    def hit(self, event):
        col, row = int(event.x // self.width), int((event.y - 36) // 33)
        if not 0 <= col < 7 or not 0 <= row < len(self.weeks):
            return None
        number = self.weeks[row][col]
        return date(self.year, self.month, number) if number else None

    def press(self, event):
        if event.y < 36 and 0 <= event.x < self.width * 7:
            self.schedule.weekday(self.year, self.month, int(event.x // self.width))
            self.changed()
            self.draw()
            return
        self.anchor = self.hit(event)
        self.drag_end = self.anchor
        self.drag_base = dict(self.schedule.days)

    def motion(self, event):
        end = self.hit(event)
        if self.anchor and end:
            self.drag_end = end
            self.schedule.days = dict(self.drag_base)
            self.schedule.interval(self.anchor, end)
            self.draw()

    def release(self, event):
        if self.anchor:
            if self.drag_end == self.anchor:
                self.schedule.days = dict(self.drag_base)
                self.schedule.toggle(self.anchor)
            self.anchor = None
            self.changed()
            self.draw()
