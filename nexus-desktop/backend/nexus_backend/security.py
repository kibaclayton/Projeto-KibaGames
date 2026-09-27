import hashlib
import hmac
import re
import secrets
import threading
import time

LEGACY_HASH = re.compile(r'^[0-9a-f]{32}:[0-9a-f]{64}$')


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

