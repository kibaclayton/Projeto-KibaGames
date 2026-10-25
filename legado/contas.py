"""Contas locais da biblioteca. Senhas protegidas com PBKDF2 e salt individual."""
import hashlib
import hmac
import secrets


def encode_password(password, salt=None):
    salt = salt or secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac('sha256', password.encode('utf-8'), bytes.fromhex(salt), 600_000)
    return salt + ':' + digest.hex()


def check_password(password, encoded):
    return hmac.compare_digest(encode_password(password, encoded.split(':')[0]), encoded)


def create_account(db, name, password):
    name = name.strip()
    if not 1 <= len(name) <= 60:
        raise ValueError('Use um nome entre 1 e 60 caracteres.')
    if len(password) < 8:
        raise ValueError('Escolha uma senha com pelo menos 8 caracteres.')
    encoded = encode_password(password)
    cursor = db.connection.cursor(dictionary=True)
    locked = False
    try:
        cursor.execute("SELECT GET_LOCK('biblioteca_gamer_accounts', 10) AS acquired")
        locked = cursor.fetchone()['acquired'] == 1
        if not locked:
            raise ValueError('Outra conta está sendo criada. Tente novamente.')
        cursor.execute('SELECT id FROM usuarios WHERE nome=%s', (name,))
        if cursor.fetchone():
            raise ValueError('Esse nome já está em uso. Escolha outro.')
        cursor.execute('SELECT COUNT(*) AS total FROM usuarios')
        first = cursor.fetchone()['total'] == 0
        cursor.execute('INSERT INTO usuarios (nome, senha_hash) VALUES (%s,%s)', (name, encoded))
        user_id = cursor.lastrowid
        if first:
            cursor.execute('UPDATE jogos SET usuario_id=%s WHERE usuario_id IS NULL', (user_id,))
        db.connection.commit()
        return {'id': user_id, 'nome': name}
    except Exception:
        db.connection.rollback()
        raise
    finally:
        if locked:
            cursor.execute("SELECT RELEASE_LOCK('biblioteca_gamer_accounts')")
            cursor.fetchone()
        cursor.close()


def authenticate(db, name, password):
    users = db.execute('SELECT id,nome,senha_hash FROM usuarios WHERE nome=%s', (name.strip(),), fetch=True)
    if not users or not check_password(password, users[0]['senha_hash']):
        raise ValueError('Nome ou senha incorretos.')
    return {'id': users[0]['id'], 'nome': users[0]['nome']}


def update_profile(db, user_id, avatar, current='', new='', confirmation=''):
    if current or new or confirmation:
        if len(new) < 8:
            raise ValueError('A nova senha deve ter pelo menos 8 caracteres.')
        if new != confirmation:
            raise ValueError('A confirmação da nova senha não confere.')
        users = db.execute('SELECT senha_hash FROM usuarios WHERE id=%s', (user_id,), fetch=True)
        if not users or not check_password(current, users[0]['senha_hash']):
            raise ValueError('A senha atual está incorreta.')
        db.execute('UPDATE usuarios SET avatar=%s,senha_hash=%s WHERE id=%s',
                   (avatar, encode_password(new), user_id))
    else:
        db.execute('UPDATE usuarios SET avatar=%s WHERE id=%s', (avatar, user_id))
