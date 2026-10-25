from datetime import datetime, timedelta, timezone
import hashlib
import hmac
import re
import secrets
import threading
import time

LEGACY_HASH = re.compile(r'^[0-9a-f]{32}:[0-9a-f]{64}$')
DEVICE_DAYS = 90
ROTATION_GRACE_SECONDS = 60


def utc_stamp(moment: datetime | None = None) -> str:
    moment = moment or datetime.now(timezone.utc)
    return moment.strftime('%Y-%m-%dT%H:%M:%S.') + f'{moment.microsecond // 1000:03d}Z'


def remember_device(conn, user_id: int, name: str) -> dict:
    """Credencial de longa duração para 'lembrar neste aparelho': só o hash fica no banco."""
    token = secrets.token_urlsafe(32)
    now = datetime.now(timezone.utc)
    cursor = conn.execute('INSERT INTO aparelhos(usuario_id,token_hash,nome,criado,ultimo_uso,expira) VALUES(?,?,?,?,?,?)',
                          (user_id, Sessions.digest(token), name[:80], utc_stamp(now), utc_stamp(now), utc_stamp(now + timedelta(days=DEVICE_DAYS))))
    return {'id': cursor.lastrowid, 'token': token}


def device_login(conn, token: str) -> dict | None:
    """Troca a credencial do aparelho por outra (rotação) e devolve o dono; expiradas são apagadas.

    Logo após uma rotação, a credencial anterior ainda vale por alguns segundos e devolve apenas uma sessão, sem
    credencial nova: cobre pedidos simultâneos, duas abas do mesmo aparelho e um app fechado no meio da troca.
    """
    digest = Sessions.digest(token)
    now = datetime.now(timezone.utc)
    row = conn.execute('SELECT id,usuario_id,expira FROM aparelhos WHERE token_hash=?', (digest,)).fetchone()
    if row:
        if row['expira'] <= utc_stamp(now):
            conn.execute('DELETE FROM aparelhos WHERE id=?', (row['id'],))
            return None
        fresh = secrets.token_urlsafe(32)
        conn.execute('UPDATE aparelhos SET token_hash=?,hash_anterior=?,rotacionado=?,ultimo_uso=?,expira=? WHERE id=?',
                     (Sessions.digest(fresh), digest, utc_stamp(now), utc_stamp(now), utc_stamp(now + timedelta(days=DEVICE_DAYS)), row['id']))
        return {'id': row['id'], 'user_id': row['usuario_id'], 'token': fresh}
    grace = conn.execute('SELECT id,usuario_id FROM aparelhos WHERE hash_anterior=? AND rotacionado>=? AND expira>?',
                         (digest, utc_stamp(now - timedelta(seconds=ROTATION_GRACE_SECONDS)), utc_stamp(now))).fetchone()
    if grace:
        return {'id': grace['id'], 'user_id': grace['usuario_id'], 'token': None}
    return None


def list_devices(conn, user_id: int) -> list[dict]:
    conn.execute('DELETE FROM aparelhos WHERE usuario_id=? AND expira<=?', (user_id, utc_stamp()))
    return [dict(r) for r in conn.execute('SELECT id,nome,criado,ultimo_uso,expira FROM aparelhos WHERE usuario_id=? ORDER BY ultimo_uso DESC', (user_id,))]


def forget_device(conn, user_id: int, device_id: int) -> bool:
    return conn.execute('DELETE FROM aparelhos WHERE id=? AND usuario_id=?', (device_id, user_id)).rowcount > 0


def forget_devices(conn, user_id: int):
    conn.execute('DELETE FROM aparelhos WHERE usuario_id=?', (user_id,))


def encode_password(password: str, salt: str | None = None) -> str:
    salt = salt or secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac('sha256', password.encode(), bytes.fromhex(salt), 600_000)
    return f'{salt}:{digest.hex()}'


def check_password(password: str, encoded: str) -> bool:
    if not LEGACY_HASH.fullmatch(encoded):
        return False
    return hmac.compare_digest(encode_password(password, encoded.split(':')[0]), encoded)


class Sessions:
    """Only token hashes are retained; password changes revoke every session of that user."""
    def __init__(self):
        self.lock = threading.RLock()
        self.entries: dict[str, tuple[int, float]] = {}
        self.failures: dict[int, list[float]] = {}

    def _prune(self):
        now = time.monotonic()
        self.entries = {k: v for k, v in self.entries.items() if v[1] > now}
        self.failures = {k: [t for t in v if now - t < 60] for k, v in self.failures.items() if v and now - v[-1] < 60}

    @staticmethod
    def digest(token):
        return hashlib.sha256(token.encode()).hexdigest()

    def create(self, user_id):
        with self.lock:
            self._prune()
            token = secrets.token_urlsafe(32)
            # Bounded session count per profile, including repeated logins.
            owned = [k for k, v in self.entries.items() if v[0] == user_id]
            for key in owned[:-7]:
                self.entries.pop(key, None)
            self.entries[self.digest(token)] = (user_id, time.monotonic() + 12 * 3600)
            return token

    def user(self, token):
        with self.lock:
            self._prune()
            value = self.entries.get(self.digest(token))
            return value[0] if value else None

    def revoke(self, token):
        with self.lock:
            self.entries.pop(self.digest(token), None)

    def revoke_user(self, user_id):
        with self.lock:
            self.entries = {k: v for k, v in self.entries.items() if v[0] != user_id}

    def revoke_all(self):
        with self.lock:
            self.entries = {}

    def allow_attempt(self, user_id):
        with self.lock:
            self._prune()
            attempts = self.failures.setdefault(user_id, [])
            if len(attempts) >= 5:
                return False
            attempts.append(time.monotonic())
            return True

    def clear_attempts(self, user_id):
        with self.lock:
            self.failures.pop(user_id, None)

