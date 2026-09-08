"""Biblioteca pessoal de jogos — Python, Tkinter e MySQL."""
import io
import queue
import threading
from capas import buscar_capas, baixar_capa
from contas import create_account, authenticate
from calendario import Schedule, GameCalendar
from conexao_segura import load_connection, save_connection
from biblioteca import highlights, trophy_values, artwork, mosaic
from contas import check_password, encode_password
from contas import update_profile
from datetime import datetime
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
from tkinter import simpledialog

import mysql.connector
from PIL import Image, ImageOps, ImageTk, UnidentifiedImageError

BG, PANEL, TEXT, MUTED, ACCENT = '#0b0e12', '#151b24', '#f4f8ff', '#93a4b8', '#bcff36'
PLATFORMS = ('PC', 'PS4', 'PS5', 'Xbox', 'Switch', 'Outro')


def game_status(game):
    return game.get('status_avancado') or ('Concluído' if game['progresso'] == 100 else
                                          'Na fila' if game['progresso'] == 0 else 'Jogando')


def group_games(games):
    groups = {}
    for game in games:
        title = (game.get('grupo') or '').strip()
        key = title.casefold()
        groups.setdefault(key, {'title': title, 'games': []})['games'].append(game)
    return [(group['title'], sorted(group['games'], key=lambda g: (
        g.get('ordem') or 1, g['nome'].casefold(), g['id'])))
        for key, group in sorted(groups.items(), key=lambda item: (not bool(item[0]), item[0]))]


def validate_group(group, order):
    group = group.strip()
    if len(group) > 150:
        raise ValueError('O nome do grupo deve ter até 150 caracteres.')
    try:
        order = int(order)
    except (TypeError, ValueError):
        raise ValueError('A ordem deve ser um número inteiro de 1 a 9999.')
    if not 1 <= order <= 9999:
        raise ValueError('A ordem deve ser um número inteiro de 1 a 9999.')
    return group, order


def format_date(value):
    return value.strftime('%d/%m/%Y') if value else ''


def parse_dates(start, end):
    try:
        dates = tuple(datetime.strptime(v.strip(), '%d/%m/%Y').date() if v.strip() else None
                      for v in (start, end))
    except ValueError:
        raise ValueError('Digite datas válidas no formato DD/MM/AAAA ou deixe em branco.')
    if all(dates) and dates[1] < dates[0]:
        raise ValueError('A data de término não pode ser anterior à data de início.')
    return dates


def cover_bytes(path):
    with Image.open(path) as original:
        picture = ImageOps.exif_transpose(original).convert('RGB')
        picture.thumbnail((900, 1200))
        buffer = io.BytesIO()
        picture.save(buffer, format='JPEG', quality=88)
        return buffer.getvalue()


class Database:
    def __init__(self, user, password):
        self.connection = mysql.connector.connect(
            host='127.0.0.1', port=3306, user=user, password=password,
            connection_timeout=5, charset='utf8mb4')
        try:
            self.execute('CREATE DATABASE IF NOT EXISTS biblioteca_gamer CHARACTER SET utf8mb4')
            self.connection.database = 'biblioteca_gamer'
            self.execute('''CREATE TABLE IF NOT EXISTS jogos (
                id INT AUTO_INCREMENT PRIMARY KEY,
                nome VARCHAR(150) NOT NULL,
                plataforma VARCHAR(30) NOT NULL,
                progresso INT NOT NULL DEFAULT 0 CHECK (progresso BETWEEN 0 AND 100),
                capa MEDIUMBLOB,
                atualizado TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
            )''')
            columns = {row['Field'] for row in self.execute('SHOW COLUMNS FROM jogos', fetch=True)}
            for column in ('data_inicio', 'data_termino'):
                if column not in columns:
                    self.execute(f'ALTER TABLE jogos ADD COLUMN {column} DATE NULL')
            if 'grupo' not in columns:
                self.execute("ALTER TABLE jogos ADD COLUMN grupo VARCHAR(150) NOT NULL DEFAULT ''")
            if 'ordem' not in columns:
                self.execute('ALTER TABLE jogos ADD COLUMN ordem INT NOT NULL DEFAULT 1')
            self.execute('''CREATE TABLE IF NOT EXISTS usuarios (
                id INT AUTO_INCREMENT PRIMARY KEY,
                nome VARCHAR(60) NOT NULL UNIQUE,
                senha_hash VARCHAR(180) NOT NULL
            )''')
            if 'usuario_id' not in columns:
                self.execute('ALTER TABLE jogos ADD COLUMN usuario_id INT NULL, ADD INDEX idx_usuario (usuario_id)')
            if 'favorito' not in columns:
                self.execute('ALTER TABLE jogos ADD COLUMN favorito BOOLEAN NOT NULL DEFAULT FALSE')
            self.execute('''CREATE TABLE IF NOT EXISTS colecoes (
                id INT AUTO_INCREMENT PRIMARY KEY, usuario_id INT NOT NULL,
                nome VARCHAR(150) NOT NULL, UNIQUE KEY nome_usuario (usuario_id,nome)
            )''')
            for column, definition in (('colecao_id', 'INT NULL'), ('trofeus_obtidos', 'INT NOT NULL DEFAULT 0'),
                                       ('trofeus_total', 'INT NOT NULL DEFAULT 0')):
                if column not in columns:
                    self.execute(f'ALTER TABLE jogos ADD COLUMN {column} {definition}')
            user_columns = {row['Field'] for row in self.execute('SHOW COLUMNS FROM usuarios', fetch=True)}
            if 'avatar' not in user_columns:
                self.execute('ALTER TABLE usuarios ADD COLUMN avatar MEDIUMBLOB NULL')
            for column, definition in (('status_avancado', "VARCHAR(40) NOT NULL DEFAULT ''"),
                                       ('notas', 'TEXT NULL'), ('cronograma', 'JSON NULL')):
                if column not in columns:
                    self.execute(f'ALTER TABLE jogos ADD COLUMN {column} {definition}')
        except Exception:
            self.connection.close()
            raise

    def execute(self, query, values=(), fetch=False):
        cursor = self.connection.cursor(dictionary=True)
        try:
            cursor.execute(query, values)
            rows = cursor.fetchall() if fetch else None
            self.connection.commit()
            return rows
        except Exception:
            self.connection.rollback()
            raise
        finally:
            cursor.close()


class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title('Minha Biblioteca • Jogos')
        self.geometry('1280x820')
        self.minsize(1050, 650)
        self.configure(bg=BG)
        self.db = None
        self.photos = []
        self.protocol('WM_DELETE_WINDOW', self.close)
        style = ttk.Style(self)
        style.theme_use('clam')
        style.configure('TFrame', background=BG)
        style.configure('TLabel', background=BG, foreground=TEXT, font=('Segoe UI', 11))
        style.configure('TButton', font=('Segoe UI', 10), padding=9)
        style.configure('TButton', background=PANEL, foreground=TEXT, borderwidth=0)
        style.map('TButton', background=[('active', '#29384a')], foreground=[('disabled', MUTED)])
        style.configure('Accent.TButton', background=ACCENT, foreground=BG)
        style.map('Accent.TButton', background=[('active', '#d5ff83')])
        style.configure('TEntry', padding=8, fieldbackground=PANEL, foreground=TEXT, insertcolor=TEXT)
        style.configure('TCombobox', padding=7, fieldbackground=PANEL, foreground=TEXT)
        style.map('TCombobox', fieldbackground=[('readonly', PANEL)], foreground=[('readonly', TEXT)])
        style.configure('TSpinbox', fieldbackground=PANEL, foreground=TEXT, padding=7)
        style.configure('Game.Horizontal.TProgressbar', troughcolor='#373946', background=ACCENT)
        self.after(50, self.startup)

    def label(self, parent, text, size=11, color=TEXT, bg=BG):
        return tk.Label(parent, text=text, font=('Segoe UI', size), fg=color, bg=bg)

    def startup(self):
        self.connection_notice = ''
        try:
            saved = load_connection()
            if saved:
                self.db = Database(saved['user'], saved['password'])
                saved.clear()
        except (OSError, ValueError, mysql.connector.Error) as error:
            self.connection_notice = 'Não foi possível conectar. Confira o MySQL em Configurar conexão.'
        self.account_screen()

    def configure_connection(self):
        dialog = tk.Toplevel(self)
        dialog.title('Configurar conexão • NEXUS')
        dialog.configure(bg=BG)
        dialog.geometry('500x350')
        dialog.transient(self)
        dialog.grab_set()
        body = ttk.Frame(dialog, padding=28)
        body.pack(fill='both', expand=True)
        self.label(body, 'Conectar sua biblioteca', 20).pack(anchor='w', pady=(0, 12))
        self.label(body, 'Configure uma vez neste usuário do Windows.', color=MUTED).pack(anchor='w')
        self.label(body, 'Usuário MySQL').pack(anchor='w', pady=(16, 4))
        user = ttk.Entry(body)
        user.insert(0, 'root')
        user.pack(fill='x')
        self.label(body, 'Senha MySQL').pack(anchor='w', pady=(12, 4))
        password = ttk.Entry(body, show='•')
        password.pack(fill='x')
        self.label(body, 'A conexão será salva com a proteção do Windows.', 9, MUTED).pack(anchor='w', pady=10)
        def connect():
            try:
                database = Database(user.get().strip(), password.get())
            except mysql.connector.Error as error:
                messagebox.showerror('Conexão', 'Confira a senha e o serviço MySQL84.\n\n' + str(error), parent=dialog)
                return
            try:
                save_connection(user.get().strip(), password.get())
                self.connection_notice = ''
            except (OSError, ValueError) as error:
                messagebox.showwarning('Conexão não salva', 'Conectado nesta sessão, mas o Windows não permitiu salvar a conexão protegida.', parent=dialog)
                self.connection_notice = 'Conexão disponível apenas nesta sessão.'
            password.delete(0, 'end')
            if self.db:
                self.db.connection.close()
            self.db = database
            dialog.destroy()
            self.account_screen()
        ttk.Button(body, text='Salvar conexão e mostrar perfis', style='Accent.TButton', command=connect).pack(fill='x')
        password.bind('<Return>', lambda e: connect())
        password.focus_set()

    def account_screen(self):
        self.unbind('<MouseWheel>')
        for child in self.winfo_children():
            child.destroy()
        self.photos.clear()
        self.games = []
        self.account = None
        panel = ttk.Frame(self, padding=35)
        panel.pack(fill='both', expand=True)
        self.label(panel, 'NEXUS / PLAY', 24, ACCENT).pack(anchor='w')
        self.label(panel, 'Quem vai jogar?', 34).pack(pady=(35, 6))
        self.label(panel, 'Escolha seu perfil para continuar sua jornada.', 12, MUTED).pack(pady=(0, 25))
        profiles = []
        if self.db:
            try:
                profiles = self.db.execute('SELECT id,nome,avatar FROM usuarios ORDER BY nome', fetch=True)
            except mysql.connector.Error:
                self.connection_notice = 'MySQL indisponível. Use Tentar novamente ou Configurar conexão.'
                self.db.connection.close()
                self.db = None
        if not self.db:
            self.label(panel, self.connection_notice or 'Configure a conexão uma vez para carregar seus perfis.', color=MUTED).pack(pady=30)
        elif not profiles:
            self.label(panel, 'Crie seu primeiro perfil. Ele receberá os jogos já cadastrados.', color=MUTED).pack(pady=20)
        area = ttk.Frame(panel)
        area.pack(fill='both', expand=True)
        canvas = tk.Canvas(area, bg=BG, highlightthickness=0)
        scroll = ttk.Scrollbar(area, orient='vertical', command=canvas.yview)
        scroll.pack(side='right', fill='y')
        canvas.pack(side='left', fill='both', expand=True)
        canvas.configure(yscrollcommand=scroll.set)
        tiles = ttk.Frame(canvas)
        window = canvas.create_window((0, 0), window=tiles, anchor='nw')
        canvas.bind('<Configure>', lambda e: canvas.itemconfigure(window, width=e.width))
        tiles.bind('<Configure>', lambda e: canvas.configure(scrollregion=canvas.bbox('all')))
        for col in range(5):
            tiles.columnconfigure(col, weight=1, uniform='profiles')
        colors = ('#258798', '#724aac', '#ad6540', '#3b8759', '#4261a6')
        for index, profile in enumerate(profiles):
            tile = ttk.Frame(tiles, padding=12)
            tile.grid(row=index // 5, column=index % 5, sticky='n')
            avatar = tk.Canvas(tile, width=132, height=132, bg=colors[profile['id'] % len(colors)],
                               highlightthickness=2, highlightbackground=PANEL, cursor='hand2', takefocus=True)
            avatar.pack()
            avatar.create_oval(32, 39, 44, 51, fill='white', outline='')
            avatar.create_oval(88, 39, 100, 51, fill='white', outline='')
            avatar.create_arc(34, 53, 99, 103, start=190, extent=155, style='arc', outline='white', width=4)
            if profile.get('avatar'):
                photo=ImageTk.PhotoImage(artwork(profile['avatar'],(128,128),circle=True))
                self.photos.append(photo);avatar.create_image(66,66,image=photo)
            avatar.bind('<Enter>', lambda e: e.widget.config(highlightbackground=ACCENT))
            avatar.bind('<Leave>', lambda e: e.widget.config(highlightbackground=PANEL))
            avatar.bind('<Button-1>', lambda e, p=profile: self.profile_login(p))
            avatar.bind('<Return>', lambda e, p=profile: self.profile_login(p))
            caption = self.label(tile, profile['nome'], 13)
            caption.config(wraplength=155)
            caption.pack(pady=(10, 0))
            caption.bind('<Button-1>', lambda e, p=profile: self.profile_login(p))
        bottom = ttk.Frame(panel)
        bottom.pack(pady=20)
        ttk.Button(bottom, text='+ Criar perfil', command=lambda: self.profile_login(None),
                   state='normal' if self.db else 'disabled').pack(side='left', padx=8)
        ttk.Button(bottom, text='Configurar conexão', command=self.configure_connection).pack(side='left', padx=8)
        if not self.db:
            ttk.Button(bottom, text='Tentar novamente', command=self.startup).pack(side='left', padx=8)

    def profile_login(self, profile):
        dialog = tk.Toplevel(self)
        dialog.title('Entrar no perfil' if profile else 'Criar perfil')
        dialog.configure(bg=BG)
        dialog.geometry('460x400')
        dialog.transient(self)
        dialog.grab_set()
        body = ttk.Frame(dialog, padding=30)
        body.pack(fill='both', expand=True)
        self.label(body, profile['nome'] if profile else 'Novo perfil', 22, ACCENT).pack(pady=(0, 20))
        name = tk.StringVar(value=profile['nome'] if profile else '')
        password, confirmation = tk.StringVar(), tk.StringVar()
        if not profile:
            self.label(body, 'Nome do perfil').pack(anchor='w')
            ttk.Entry(body, textvariable=name).pack(fill='x', pady=(4, 12))
        self.label(body, 'Senha do perfil').pack(anchor='w')
        field = ttk.Entry(body, textvariable=password, show='•')
        field.pack(fill='x', pady=(4, 12))
        if not profile:
            self.label(body, 'Confirme a senha (mínimo 8 caracteres)').pack(anchor='w')
            ttk.Entry(body, textvariable=confirmation, show='•').pack(fill='x', pady=(4, 12))
        def enter():
            try:
                if profile:
                    account = authenticate(self.db, profile['nome'], password.get())
                else:
                    if password.get() != confirmation.get():
                        raise ValueError('As senhas não conferem.')
                    account = create_account(self.db, name.get(), password.get())
            except (ValueError, mysql.connector.Error) as error:
                messagebox.showerror('Perfil', str(error), parent=dialog)
                return
            password.set('')
            confirmation.set('')
            dialog.destroy()
            for child in self.winfo_children():
                child.destroy()
            self.account = account
            self.library()
        ttk.Button(body, text='Entrar' if profile else 'Criar perfil', style='Accent.TButton', command=enter).pack(fill='x', pady=10)
        field.bind('<Return>', lambda e: enter())
        if profile:
            field.focus_set()

    def library(self):
        self.section = 'Todos'
        self.active_collection = None
        self.gallery_width = 0
        self.resize_job = None
        sidebar = tk.Frame(self, bg='#10151c', width=200, padx=18, pady=28)
        sidebar.pack(side='left', fill='y')
        sidebar.pack_propagate(False)
        self.label(sidebar, 'NEXUS', 26, ACCENT, '#10151c').pack(anchor='w')
        self.label(sidebar, 'P L A Y   L I B R A R Y', 9, MUTED, '#10151c').pack(anchor='w', pady=(2, 35))
        ttk.Button(sidebar, text=self.account['nome'] + '  ⚙', command=self.profile_settings).pack(fill='x', pady=(0, 22))
        for section, caption in [('Todos', '◈  Biblioteca'), ('Favoritos', '★  Favoritos'), ('Jogando', '▶  Em andamento'), ('Concluídos', '✓  Concluídos'), ('Não iniciados', '○  Para jogar')]:
            ttk.Button(sidebar, text=caption, command=lambda s=section: self.set_section(s)).pack(fill='x', pady=5)
        ttk.Button(sidebar, text='Trocar usuário', command=self.account_screen).pack(side='bottom', fill='x', pady=8)
        self.label(sidebar, 'SUA JORNADA\nEM UM SÓ LUGAR', 10, MUTED, '#10151c').pack(side='bottom', pady=25)
        content = ttk.Frame(self)
        content.pack(side='left', fill='both', expand=True)
        header = ttk.Frame(content, padding=(28, 22))
        header.pack(fill='x')
        self.label(header, 'Sua central de jogos', 24).pack(side='left')
        ttk.Button(header, text='+ Adicionar jogo', style='Accent.TButton', command=self.editor).pack(side='right')
        self.stats = self.label(content, '', color=MUTED)
        self.stats.pack(anchor='w', padx=30, pady=(0, 15))
        bar = ttk.Frame(content, padding=(28, 0, 28, 20))
        bar.pack(fill='x')
        self.search = tk.StringVar()
        self.label(bar, 'Buscar jogo:').pack(side='left', padx=(0, 8))
        ttk.Entry(bar, textvariable=self.search, width=30).pack(side='left')
        self.filter = tk.StringVar(value='Todas as plataformas')
        ttk.Combobox(bar, textvariable=self.filter, state='readonly',
                     values=('Todas as plataformas',) + PLATFORMS, width=23).pack(side='right')
        self.search.trace_add('write', lambda *args: self.render())
        self.filter.trace_add('write', lambda *args: self.render())
        area = ttk.Frame(content)
        area.pack(fill='both', expand=True, padx=25, pady=(0, 15))
        self.canvas = tk.Canvas(area, bg=BG, highlightthickness=0)
        scroll = ttk.Scrollbar(area, orient='vertical', command=self.canvas.yview)
        scroll.pack(side='right', fill='y')
        self.canvas.pack(side='left', fill='both', expand=True)
        self.canvas.configure(yscrollcommand=scroll.set)
        self.cards = tk.Frame(self.canvas, bg=BG)
        self.window = self.canvas.create_window((0, 0), window=self.cards, anchor='nw')
        self.canvas.bind('<Configure>', self.resize_gallery)
        self.cards.bind('<Configure>', lambda e: self.canvas.configure(scrollregion=self.canvas.bbox('all')))
        self.bind('<MouseWheel>', lambda e: self.canvas.yview_scroll(int(-e.delta / 120), 'units') if self.focus_get() and self.focus_get().winfo_toplevel() == self else None)
        self.refresh()

    def toggle_favorite(self, game):
        try:
            self.db.execute('UPDATE jogos SET favorito=%s WHERE id=%s AND usuario_id=%s',
                            (not bool(game.get('favorito')), game['id'], self.account['id']))
        except mysql.connector.Error as error:
            messagebox.showerror('Favoritos', str(error))
            return
        game['favorito'] = not bool(game.get('favorito'))
        self.refresh()

    def set_section(self, section):
        self.section = section
        self.active_collection = None
        self.render()

    def resize_gallery(self, event):
        self.canvas.itemconfigure(self.window, width=event.width)
        if self.gallery_width != event.width:
            self.gallery_width = event.width
            if self.resize_job:
                self.after_cancel(self.resize_job)
            self.resize_job = self.after(120, self.render)

    def refresh(self):
        try:
            # Convert the previous groups once per game without deleting any games.
            self.db.execute("""INSERT IGNORE INTO colecoes (usuario_id,nome)
                SELECT DISTINCT usuario_id, TRIM(grupo) FROM jogos
                WHERE usuario_id=%s AND colecao_id IS NULL AND TRIM(grupo)<>''""", (self.account['id'],))
            self.db.execute("""UPDATE jogos j JOIN colecoes c ON c.usuario_id=j.usuario_id AND c.nome=TRIM(j.grupo)
                SET j.colecao_id=c.id, j.grupo='' WHERE j.usuario_id=%s AND j.colecao_id IS NULL AND TRIM(j.grupo)<>''""", (self.account['id'],))
            self.games = self.db.execute('SELECT id,nome,plataforma,progresso,capa,status_avancado,favorito,colecao_id,ordem FROM jogos WHERE usuario_id=%s ORDER BY ordem,nome,id', (self.account['id'],), fetch=True)
            self.collections = self.db.execute('SELECT id,nome FROM colecoes WHERE usuario_id=%s ORDER BY nome', (self.account['id'],), fetch=True)
        except mysql.connector.Error as error:
            messagebox.showerror('Erro ao carregar biblioteca', str(error))
            return
        self.render()

    def render(self):
        self.resize_job = None
        if not hasattr(self, 'cards') or not self.cards.winfo_exists() or not self.account:
            return
        for child in self.cards.winfo_children():
            child.destroy()
        self.photos.clear()
        self.stats.config(text='Arraste uma capa até uma coleção. Clique na capa para abrir os detalhes.')
        width = max(self.canvas.winfo_width()-20, 650)
        cols = max(3, int(width // 170))
        games = [g for g in self.games if self.search.get().casefold() in g['nome'].casefold()
                 and (self.filter.get() == 'Todas as plataformas' or g['plataforma'] == self.filter.get())
                 and (self.section == 'Todos' or self.section == 'Favoritos' and g.get('favorito')
                      or self.section == 'Jogando' and game_status(g)=='Jogando'
                      or self.section == 'Concluídos' and game_status(g)=='Concluído'
                      or self.section == 'Não iniciados' and game_status(g)=='Na fila')]
        featured = highlights(games)[:4]
        if featured and not self.active_collection:
            self.label(self.cards, 'EM DESTAQUE', 12, ACCENT).pack(anchor='w', padx=8, pady=(12, 8))
            hero = ttk.Frame(self.cards)
            hero.pack(fill='x')
            for i,g in enumerate(featured[:max(1,int(width//192))]):
                self.cover_tile(hero, g, (180,115)).grid(row=0,column=i,padx=6,pady=4)
        line = ttk.Frame(self.cards)
        line.pack(fill='x', pady=(20,8))
        self.label(line, 'COLEÇÕES', 12, MUTED).pack(side='left',padx=8)
        ttk.Button(line, text='+ Criar coleção', command=self.create_collection).pack(side='right')
        folders = ttk.Frame(self.cards)
        folders.pack(fill='x')
        for i, collection in enumerate(self.collections):
            members = [g for g in self.games if g.get('colecao_id')==collection['id']]
            card = tk.Frame(folders,bg=PANEL,highlightbackground=ACCENT if self.active_collection==collection['id'] else '#343e4b',highlightthickness=1,padx=6,pady=6)
            card.grid(row=i//cols,column=i%cols,padx=6,pady=6,sticky='n')
            card.drop_id = collection['id']
            photo=ImageTk.PhotoImage(mosaic(members,140)); self.photos.append(photo)
            cover=tk.Label(card,image=photo,bg=PANEL,cursor='hand2');cover.pack()
            label=self.label(card,f"{collection['nome']} ({len(members)})",10,bg=PANEL)
            label.config(wraplength=140);label.pack(pady=6)
            for widget in (card,cover,label):
                widget.bind('<Button-1>',lambda e,c=collection:self.open_collection(c['id']))
                widget.bind('<Button-3>',lambda e,c=collection:self.collection_menu(e,c))
        line=ttk.Frame(self.cards);line.pack(fill='x',pady=(18,8))
        if self.active_collection:
            collection=next((c for c in self.collections if c['id']==self.active_collection),None)
            if collection:
                self.label(line,collection['nome'],16).pack(side='left',padx=8)
            ttk.Button(line,text='← Toda a biblioteca',command=lambda:self.open_collection(None)).pack(side='right')
            games=[g for g in games if g.get('colecao_id')==self.active_collection]
        else:
            self.label(line,'BIBLIOTECA',12,MUTED).pack(side='left',padx=8)
        gallery=ttk.Frame(self.cards);gallery.pack(fill='x')
        for i,g in enumerate(games):
            self.cover_tile(gallery,g,(145,195)).grid(row=i//cols,column=i%cols,padx=7,pady=9)
        if not games:
            self.label(gallery,'Nenhum jogo nesta seleção.',color=MUTED).pack(pady=25)

    def cover_tile(self,parent,game,size):
        photo=ImageTk.PhotoImage(artwork(game.get('capa'),size));self.photos.append(photo)
        tile=tk.Label(parent,image=photo,bg=PANEL,cursor='hand2',highlightthickness=1,highlightbackground='#253141',takefocus=True)
        drag={'start':None,'moved':False,'target':None}
        def begin(e):
            drag.update(start=(e.x_root,e.y_root),moved=False,target=None)
        def motion(e):
            if not drag['start']: return
            if abs(e.x_root-drag['start'][0])+abs(e.y_root-drag['start'][1])>7:
                drag['moved']=True;tile.config(cursor='fleur')
            if drag['target']:
                drag['target'].config(highlightbackground='#343e4b')
                drag['target']=None
            target=self.winfo_containing(e.x_root,e.y_root)
            while target and not hasattr(target,'drop_id'): target=target.master
            if target:
                drag['target']=target;target.config(highlightbackground=ACCENT)
            if drag['moved'] and e.y_root < self.canvas.winfo_rooty()+25:
                self.canvas.yview_scroll(-1,'units')
        def release(e):
            tile.config(cursor='hand2')
            if drag['moved']:
                target=drag['target']
                if target:
                    self.assign_collection(game,target.drop_id)
            else:
                self.editor(game)
            drag['start']=None
        tile.bind('<Button-1>',begin);tile.bind('<B1-Motion>',motion);tile.bind('<ButtonRelease-1>',release)
        tile.bind('<Return>',lambda e:self.editor(game))
        return tile

    def open_collection(self,collection_id):
        self.active_collection=collection_id
        self.render()

    def create_collection(self):
        name=simpledialog.askstring('Criar coleção','Nome da coleção:',parent=self)
        if name is None:return
        self.save_collection_name(None,name)

    def save_collection_name(self,collection,name):
        name=name.strip()
        if not 1<=len(name)<=150:
            messagebox.showwarning('Coleção','Use um nome entre 1 e 150 caracteres.');return
        try:
            if collection:
                self.db.execute('UPDATE colecoes SET nome=%s WHERE id=%s AND usuario_id=%s',(name,collection['id'],self.account['id']))
            else:
                self.db.execute('INSERT INTO colecoes (nome,usuario_id) VALUES (%s,%s)',(name,self.account['id']))
        except mysql.connector.Error as error:
            messagebox.showerror('Coleção','Não foi possível salvar. Verifique se o nome já existe.\n'+str(error));return
        self.refresh()

    def collection_menu(self,event,collection):
        menu=tk.Menu(self,tearoff=False,bg=PANEL,fg=TEXT)
        def rename():
            name=simpledialog.askstring('Editar coleção','Nome:',initialvalue=collection['nome'],parent=self)
            if name is not None:self.save_collection_name(collection,name)
        def delete():
            if not messagebox.askyesno('Excluir coleção','Excluir a coleção? Os jogos serão mantidos na biblioteca.'):return
            cursor=self.db.connection.cursor()
            try:
                cursor.execute("UPDATE jogos SET colecao_id=NULL,grupo='' WHERE colecao_id=%s AND usuario_id=%s",(collection['id'],self.account['id']))
                cursor.execute('DELETE FROM colecoes WHERE id=%s AND usuario_id=%s',(collection['id'],self.account['id']))
                self.db.connection.commit()
            except mysql.connector.Error as error:
                self.db.connection.rollback();messagebox.showerror('Coleção',str(error));return
            finally:cursor.close()
            if self.active_collection==collection['id']:self.active_collection=None
            self.refresh()
        menu.add_command(label='Editar nome da coleção',command=rename)
        menu.add_command(label='Excluir coleção',command=delete)
        try:menu.tk_popup(event.x_root,event.y_root)
        finally:menu.grab_release()

    def assign_collection(self,game,collection_id):
        try:
            if collection_id is None:
                self.db.execute("UPDATE jogos SET colecao_id=NULL,grupo='' WHERE id=%s AND usuario_id=%s",(game['id'],self.account['id']))
            else:
                self.db.execute("""UPDATE jogos SET colecao_id=%s,grupo='' WHERE id=%s AND usuario_id=%s
                    AND EXISTS (SELECT 1 FROM colecoes WHERE id=%s AND usuario_id=%s)""",
                    (collection_id,game['id'],self.account['id'],collection_id,self.account['id']))
        except mysql.connector.Error as error:
            messagebox.showerror('Mover jogo',str(error));return
        self.refresh()

    def profile_settings(self):
        try:
            users=self.db.execute('SELECT avatar FROM usuarios WHERE id=%s',(self.account['id'],),fetch=True)
        except mysql.connector.Error as error:
            messagebox.showerror('Perfil',str(error));return
        if not users:return
        dialog=tk.Toplevel(self);dialog.title('Configurações de Conta');dialog.configure(bg=BG)
        dialog.geometry('490x620');dialog.transient(self);dialog.grab_set()
        body=ttk.Frame(dialog,padding=25);body.pack(fill='both',expand=True)
        self.label(body,'Configurações de Conta',22,ACCENT).pack(pady=(0,15))
        selected=[users[0].get('avatar')]
        preview=self.label(body,'');preview.pack()
        def redraw():
            photo=ImageTk.PhotoImage(artwork(selected[0],(112,112),circle=True))
            preview.config(image=photo);preview.image=photo
        redraw()
        def choose():
            path=filedialog.askopenfilename(parent=dialog,title='Foto do perfil',filetypes=[('Imagens','*.png *.jpg *.jpeg *.webp *.bmp')])
            if path:
                try:selected[0]=cover_bytes(path);redraw()
                except (OSError,ValueError,Image.DecompressionBombError) as error:
                    messagebox.showerror('Avatar',str(error),parent=dialog)
        ttk.Button(body,text='Escolher foto do perfil',command=choose).pack(fill='x',pady=10)
        self.label(body,'Alterar senha',16).pack(anchor='w',pady=(10,8))
        current,new,confirmation=tk.StringVar(),tk.StringVar(),tk.StringVar()
        for label,var in [('Senha Atual',current),('Nova Senha',new),('Confirmar Nova Senha',confirmation)]:
            self.label(body,label).pack(anchor='w')
            ttk.Entry(body,textvariable=var,show='•').pack(fill='x',pady=(4,10))
        self.label(body,'Para alterar só a foto, deixe as senhas em branco.',9,MUTED).pack(anchor='w')
        def save():
            try:
                update_profile(self.db,self.account['id'],selected[0],current.get(),new.get(),confirmation.get())
            except (ValueError,mysql.connector.Error) as error:
                messagebox.showerror('Perfil',str(error),parent=dialog);return
            current.set('');new.set('');confirmation.set('')
            dialog.destroy()
            messagebox.showinfo('Perfil','Alterações salvas. A foto aparecerá na seleção de perfis.')
        ttk.Button(body,text='Salvar perfil',style='Accent.TButton',command=save).pack(fill='x',pady=15)

    def editor(self, game=None):
        if game:
            try:
                rows=self.db.execute('SELECT * FROM jogos WHERE id=%s AND usuario_id=%s',(game['id'],self.account['id']),fetch=True)
            except mysql.connector.Error as error:
                messagebox.showerror('Detalhes do jogo',str(error));return
            if not rows:
                self.refresh();return
            game=rows[0]
        dialog = tk.Toplevel(self)
        dialog.title('Editar jogo' if game else 'Adicionar jogo')
        dialog.configure(bg=BG)
        dialog.geometry(f"1120x{min(900, self.winfo_screenheight() - 80)}")
        dialog.minsize(980, 620)
        dialog.transient(self)
        dialog.grab_set()
        titlebar = tk.Frame(dialog, bg='#eef0f2', padx=18, pady=10)
        titlebar.pack(fill='x')
        feather = tk.Canvas(titlebar, width=26, height=28, bg='#eef0f2', highlightthickness=0)
        feather.pack(side='left', padx=(0, 10))
        feather.create_oval(9, 2, 21, 22, fill='#a5bdd0', outline='#354d60')
        feather.create_line(6, 27, 17, 6, fill='#354d60', width=2)
        feather.create_line(12, 16, 20, 10, fill='#354d60')
        self.label(titlebar, 'Editar jogo' if game else 'Adicionar jogo', 16, '#20262d', '#eef0f2').pack(side='left')
        tk.Button(titlebar, text='×', font=('Segoe UI', 21), bd=0, bg='#eef0f2', command=dialog.destroy).pack(side='right')
        footer = ttk.Frame(dialog, padding=(22, 12))
        footer.pack(side='bottom', fill='x')
        editor_canvas = tk.Canvas(dialog, bg=BG, highlightthickness=0)
        editor_scroll = ttk.Scrollbar(dialog, orient='vertical', command=editor_canvas.yview)
        editor_scroll.pack(side='right', fill='y')
        editor_canvas.pack(side='left', fill='both', expand=True)
        editor_canvas.configure(yscrollcommand=editor_scroll.set)
        content = ttk.Frame(editor_canvas, padding=24)
        body_window = editor_canvas.create_window((0, 0), window=content, anchor='nw')
        content.bind('<Configure>', lambda e: editor_canvas.configure(scrollregion=editor_canvas.bbox('all')))
        editor_canvas.bind('<Configure>', lambda e: editor_canvas.itemconfigure(body_window, width=e.width))
        dialog.bind('<MouseWheel>', lambda e: editor_canvas.yview_scroll(int(-e.delta / 120), 'units') if not isinstance(e.widget, tk.Text) else None)
        content.columnconfigure(0, weight=1, uniform='editor')
        content.columnconfigure(2, weight=1, uniform='editor')
        body = ttk.Frame(content)
        body.grid(row=0, column=0, sticky='nsew', padx=(0, 22))
        tk.Frame(content, bg='#303844', width=1).grid(row=0, column=1, sticky='ns')
        right = ttk.Frame(content)
        right.grid(row=0, column=2, sticky='nsew', padx=(22, 0))
        name = tk.StringVar(value=game['nome'] if game else '')
        platform = tk.StringVar(value=game['plataforma'] if game else 'PC')
        group = tk.StringVar(value=game.get('grupo', '') if game else '')
        order = tk.StringVar(value=str(game.get('ordem', 1)) if game else '1')
        progress = tk.IntVar(value=game['progresso'] if game else 0)
        start = tk.StringVar(value=format_date(game.get('data_inicio')) if game else '')
        end = tk.StringVar(value=format_date(game.get('data_termino')) if game else '')
        status = tk.StringVar(value=game.get('status_avancado', '') if game else '')
        selected = [game['capa'] if game else None]
        self.label(body, 'Informações do jogo', 18).pack(anchor='w', pady=(0, 18))
        self.label(body, 'Nome do jogo').pack(anchor='w')
        entry = ttk.Entry(body, textvariable=name)
        entry.pack(fill='x', pady=(5, 16))
        entry.focus_set()
        self.label(body, 'Plataforma').pack(anchor='w')
        ttk.Combobox(body, textvariable=platform, values=PLATFORMS, state='readonly').pack(fill='x', pady=(5, 16))
        collection_name = next((c['nome'] for c in self.collections if game and c['id']==game.get('colecao_id')), 'Sem coleção')
        self.label(body, 'Coleção: ' + collection_name, color=MUTED).pack(anchor='w',pady=(4,12))
        self.label(body, 'Ordem na coleção').pack(anchor='w')
        ttk.Spinbox(body, from_=1, to=9999, textvariable=order).pack(fill='x', pady=(5, 16))
        percentage = self.label(body, f'Progresso: {progress.get()}%', 14, ACCENT)
        percentage.pack(anchor='w')
        tk.Scale(body, from_=0, to=100, orient='horizontal', variable=progress,
                 command=lambda v: percentage.config(text=f'Progresso: {int(float(v))}%'),
                 bg=BG, fg=TEXT, activebackground=ACCENT, troughcolor=PANEL,
                 highlightthickness=0, sliderrelief='flat').pack(fill='x', pady=(0, 15))
        self.label(body, 'Status avançado').pack(anchor='w')
        placeholder = 'Selecione Jogando, Na fila, etc.'
        if not status.get():
            status.set(placeholder)
        ttk.Combobox(body, textvariable=status, state='readonly', values=(placeholder,
            'Jogando', 'Na fila', 'Pausado', 'Concluído', 'Abandonado')).pack(fill='x', pady=(5, 16))
        self.label(body, 'Notas').pack(anchor='w')
        notes = tk.Text(body, height=8, width=30, wrap='word', bg=PANEL, fg=TEXT,
                        insertbackground=ACCENT, relief='solid', bd=1, font=('Segoe UI', 11),
                        highlightbackground='#454d58', highlightcolor=ACCENT, highlightthickness=1, padx=10, pady=10)
        notes.pack(fill='both', expand=True, pady=(5, 0))
        notes.insert('1.0', (game.get('notas') or '') if game else '')
        self.label(body,'Conquistas / Troféus',16,ACCENT).pack(anchor='w',pady=(18,8))
        trophies=ttk.Frame(body);trophies.pack(fill='x')
        obtained=tk.StringVar(value=str(game.get('trofeus_obtidos',0)) if game else '0')
        total=tk.StringVar(value=str(game.get('trofeus_total',0)) if game else '0')
        self.label(trophies,'Troféus Obtidos').grid(row=0,column=0,sticky='w')
        self.label(trophies,'Total de Troféus').grid(row=0,column=1,sticky='w',padx=10)
        ttk.Spinbox(trophies,from_=0,to=1000000,textvariable=obtained,width=12).grid(row=1,column=0,sticky='ew')
        ttk.Spinbox(trophies,from_=0,to=1000000,textvariable=total,width=12).grid(row=1,column=1,sticky='ew',padx=10)
        trophy_bar=ttk.Progressbar(body,maximum=100,style='Game.Horizontal.TProgressbar')
        trophy_bar.pack(fill='x',pady=(10,4))
        trophy_label=self.label(body,'',10,MUTED);trophy_label.pack(anchor='w')
        def update_trophies(*args):
            try:
                done,count,percent=trophy_values(obtained.get(),total.get())
                trophy_bar.config(value=percent)
                trophy_label.config(text=f'{percent:.0f}% • {count-done} faltantes' if count else 'Informe o total de troféus')
            except ValueError as error:
                trophy_bar.config(value=0);trophy_label.config(text=str(error))
        obtained.trace_add('write',update_trophies);total.trace_add('write',update_trophies)
        update_trophies()
        self.label(right, 'Cronograma de Jogo e Capa', 18).pack(anchor='w', pady=(0, 14))
        self.label(right, 'Calendário de Jogo', 13).pack(anchor='w', pady=(0, 8))
        try:
            schedule = Schedule(game.get('cronograma') if game else None)
        except (ValueError, TypeError):
            messagebox.showerror('Cronograma inválido', 'Não foi possível ler o cronograma salvo. Nenhum dado foi alterado.', parent=dialog)
            dialog.destroy()
            return
        if not schedule.days:
            initial_start, initial_end = parse_dates(start.get(), end.get())
            if initial_start:
                schedule.days[initial_start] = 'range'
            if initial_end:
                schedule.days[initial_end] = 'range'
        syncing = [False]
        def calendar_changed():
            syncing[0] = True
            first, last = schedule.bounds()
            start.set(format_date(first))
            end.set(format_date(last))
            syncing[0] = False
        cal = GameCalendar(right, schedule, calendar_changed)
        cal.pack(fill='x')
        dates_row = ttk.Frame(right)
        dates_row.pack(fill='x', pady=(12, 0))
        dates_row.columnconfigure(0, weight=1)
        dates_row.columnconfigure(1, weight=1)
        self.label(dates_row, 'Início').grid(row=0, column=0, sticky='w')
        self.label(dates_row, 'Término').grid(row=0, column=1, sticky='w', padx=(12, 0))
        start_entry = ttk.Entry(dates_row, textvariable=start)
        start_entry.grid(row=1, column=0, sticky='ew', pady=5)
        end_entry = ttk.Entry(dates_row, textvariable=end)
        end_entry.grid(row=1, column=1, sticky='ew', padx=(12, 0), pady=5)
        self.label(right, 'DD/MM/AAAA • datas futuras representam planejamento', 9, MUTED).pack(anchor='w')
        self.label(right, 'Editar as datas substitui a seleção por um intervalo contínuo.', 9, MUTED).pack(anchor='w')
        synced_dates = [start.get(), end.get()]
        def dates_changed(event=None, strict=False):
            if syncing[0] or [start.get(), end.get()] == synced_dates:
                return
            try:
                first, last = parse_dates(start.get(), end.get())
                updated = Schedule()
                if first and last:
                    updated.interval(first, last)
                elif first or last:
                    updated.days[first or last] = 'range'
            except ValueError:
                if strict:
                    raise
                return
            schedule.days = updated.days
            synced_dates[:] = [start.get(), end.get()]
            if first or last:
                cal.year, cal.month = (first or last).year, (first or last).month
            cal.draw()
        # Changes from the calendar already describe the exact selected days.
        def remember_dates(*args):
            if syncing[0]:
                synced_dates[:] = [start.get(), end.get()]
        start.trace_add('write', remember_dates)
        end.trace_add('write', remember_dates)
        start_entry.bind('<FocusOut>', dates_changed)
        end_entry.bind('<FocusOut>', dates_changed)
        cover_status = self.label(right, 'Capa salva' if selected[0] else 'Nenhuma capa selecionada', color=MUTED)
        cover_status.pack(anchor='w', pady=(14, 5))
        cover_preview = self.label(right, '', bg=PANEL)
        cover_preview.pack(fill='x')
        def update_cover_preview():
            if selected[0]:
                try:
                    with Image.open(io.BytesIO(selected[0])) as source:
                        photo = ImageTk.PhotoImage(ImageOps.pad(source.convert('RGB'), (300, 120), color=PANEL))
                    cover_preview.configure(image=photo, text='', height=0)
                    cover_preview.image = photo
                    return
                except (OSError, ValueError):
                    pass
            cover_preview.configure(image='', text='SEM CAPA', height=5)
            cover_preview.image = None
        update_cover_preview()
        cover_buttons = ttk.Frame(right)
        cover_buttons.pack(fill='x', pady=(8, 0))
        for col in range(3):
            cover_buttons.columnconfigure(col, weight=1, uniform='cover')

        last_search = ['']
        busy = [False]

        def search_cover(automatic=False):
            query = name.get().strip()
            if busy[0] or not query or (automatic and (selected[0] or last_search[0] == query)):
                return
            last_search[0] = query
            busy[0] = True
            cover_status.config(text='Buscando capa na internet...')
            messages = queue.Queue()

            def worker():
                try:
                    results = buscar_capas(query)
                    messages.put((results, None))
                except Exception as error:
                    messages.put((None, str(error)))

            def poll():
                if not dialog.winfo_exists():
                    return
                try:
                    results, error = messages.get_nowait()
                except queue.Empty:
                    dialog.after(100, poll)
                    return
                busy[0] = False
                if name.get().strip() != query:
                    cover_status.config(text='Nome alterado. Clique em Buscar capa na internet.')
                    return
                if error or not results:
                    cover_status.config(text='Busca indisponível.' if error else 'Nenhuma imagem encontrada.')
                    if not automatic:
                        messagebox.showinfo('Busca de capas', error or 'Tente o nome completo do jogo ou escolha uma imagem local.', parent=dialog)
                    return
                picker = tk.Toplevel(dialog)
                picker.title('Escolha a imagem do jogo')
                picker.geometry('470x550')
                picker.configure(bg=BG)
                picker.transient(dialog)
                picker.grab_set()
                self.label(picker, 'Resultados da Wikipedia • confira o jogo', color=MUTED).pack(pady=12)
                choices = ttk.Combobox(picker, state='readonly', values=[r['title'] for r in results], width=46)
                choices.pack(padx=15, fill='x')
                choices.current(0)
                preview = self.label(picker, 'Carregando imagem...')
                preview.pack(pady=15, expand=True)
                current = [None]
                generation = [0]

                def accept():
                    if current[0]:
                        selected[0] = current[0]
                        update_cover_preview()
                        cover_status.config(text='Capa da internet selecionada • salve o jogo')
                        picker.destroy()
                        dialog.grab_set()

                button = ttk.Button(picker, text='Usar esta imagem', command=accept, state='disabled')
                button.pack(fill='x', padx=20, pady=15)

                def load_preview(event=None):
                    generation[0] += 1
                    request_id = generation[0]
                    current[0] = None
                    button.config(state='disabled')
                    preview.config(image='', text='Carregando imagem...')
                    downloads = queue.Queue()
                    url = results[choices.current()]['url']

                    def fetch():
                        try:
                            downloads.put((baixar_capa(url), None))
                        except Exception as error:
                            downloads.put((None, str(error)))

                    def check():
                        if not picker.winfo_exists() or request_id != generation[0]:
                            return
                        try:
                            data, error = downloads.get_nowait()
                        except queue.Empty:
                            picker.after(100, check)
                            return
                        if error:
                            preview.config(text='Não foi possível baixar. Escolha outro resultado.')
                            return
                        with Image.open(io.BytesIO(data)) as picture:
                            photo = ImageTk.PhotoImage(ImageOps.pad(picture, (280, 330), color=BG))
                        preview.config(image=photo, text='')
                        preview.image = photo
                        current[0] = data
                        button.config(state='normal')

                    threading.Thread(target=fetch, daemon=True).start()
                    picker.after(100, check)

                choices.bind('<<ComboboxSelected>>', load_preview)
                picker.protocol('WM_DELETE_WINDOW', lambda: (picker.destroy(), dialog.grab_set()))
                cover_status.config(text='Confira a imagem encontrada antes de salvar.')
                load_preview()

            threading.Thread(target=worker, daemon=True).start()
            dialog.after(100, poll)

        entry.bind('<FocusOut>', lambda event: search_cover(automatic=True))
        ttk.Button(cover_buttons, text='Buscar capa\nna internet', command=search_cover).grid(row=0, column=0, sticky='ew', padx=(0, 4))

        def choose_cover():
            path = filedialog.askopenfilename(parent=dialog, title='Escolha a capa do jogo',
                filetypes=[('Imagens', '*.jpg *.jpeg *.png *.webp *.bmp')])
            if path:
                try:
                    selected[0] = cover_bytes(path)
                    update_cover_preview()
                    cover_status.config(text='Nova capa selecionada • pronta para salvar')
                except (OSError, ValueError, Image.DecompressionBombError) as error:
                    messagebox.showerror('Imagem inválida', str(error), parent=dialog)

        def remove_cover():
            selected[0] = None
            update_cover_preview()
            cover_status.config(text='Sem capa • salve para confirmar')

        ttk.Button(cover_buttons, text='Escolher imagem\nda capa', command=choose_cover).grid(row=0, column=1, sticky='ew', padx=4)
        ttk.Button(cover_buttons, text='Remover\ncapa', command=remove_cover).grid(row=0, column=2, sticky='ew', padx=(4, 0))

        def save():
            title = name.get().strip()
            if not title or len(title) > 150:
                messagebox.showwarning('Nome do jogo', 'Digite um nome entre 1 e 150 caracteres.', parent=dialog)
                return
            try:
                dates_changed(strict=True)
                dates = parse_dates(start.get(), end.get())
                group_values = validate_group('', order.get())
                trophy_counts = trophy_values(obtained.get(), total.get())[:2]
            except ValueError as error:
                messagebox.showwarning('Confira os campos', str(error), parent=dialog)
                return
            note_text = notes.get('1.0', 'end-1c')
            if len(note_text.encode('utf-8')) > 60000:
                messagebox.showwarning('Notas muito longas', 'Reduza o texto das notas.', parent=dialog)
                return
            values = (title, platform.get(), progress.get(), selected[0]) + dates + group_values + (
                '' if status.get() == placeholder else status.get(), note_text, schedule.dump()) + trophy_counts
            try:
                if game:
                    self.db.execute('UPDATE jogos SET nome=%s, plataforma=%s, progresso=%s, capa=%s, data_inicio=%s, data_termino=%s, grupo=%s, ordem=%s, status_avancado=%s, notas=%s, cronograma=%s, trofeus_obtidos=%s, trofeus_total=%s WHERE id=%s AND usuario_id=%s', values + (game['id'], self.account['id']))
                else:
                    self.db.execute('INSERT INTO jogos (nome, plataforma, progresso, capa, data_inicio, data_termino, grupo, ordem, status_avancado, notas, cronograma, trofeus_obtidos, trofeus_total, usuario_id) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)', values + (self.account['id'],))
            except mysql.connector.Error as error:
                messagebox.showerror('Não foi possível salvar', str(error), parent=dialog)
                return
            dialog.destroy()
            self.refresh()

        def delete():
            if messagebox.askyesno('Excluir jogo', f"Excluir {game['nome']} da biblioteca?", parent=dialog):
                try:
                    self.db.execute('DELETE FROM jogos WHERE id=%s AND usuario_id=%s', (game['id'], self.account['id']))
                except mysql.connector.Error as error:
                    messagebox.showerror('Não foi possível excluir', str(error), parent=dialog)
                    return
                dialog.destroy()
                self.refresh()

        ttk.Button(footer, text='Salvar alterações', style='Accent.TButton', command=save).pack(side='right')
        ttk.Button(footer, text='Cancelar', command=dialog.destroy).pack(side='right', padx=10)
        if game:
            favorite_button=ttk.Button(footer,text='★ Favorito' if game.get('favorito') else '☆ Favoritar')
            def favorite():
                self.toggle_favorite(game)
                favorite_button.config(text='★ Favorito' if game.get('favorito') else '☆ Favoritar')
            favorite_button.config(command=favorite);favorite_button.pack(side='left',padx=8)
            if game.get('colecao_id'):
                def unlink():
                    self.assign_collection(game,None);dialog.destroy()
                ttk.Button(footer,text='Remover da coleção',command=unlink).pack(side='left',padx=8)
            ttk.Button(footer, text='Excluir jogo' , command=delete).pack(side='left')

    def close(self):
        if self.db:
            self.db.connection.close()
        self.destroy()


if __name__ == '__main__':
    App().mainloop()
