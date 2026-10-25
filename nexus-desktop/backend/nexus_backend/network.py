"""Acesso pela rede local: autoridade de certificação própria, listener HTTPS opcional e política de hosts.

Desligado por padrão. Quando ligado, o mesmo aplicativo FastAPI passa a escutar também em HTTPS num endereço da
rede local, com um certificado emitido por uma autoridade criada neste computador. A chave da autoridade nunca
sai da pasta de dados; o telefone instala apenas o certificado público da autoridade (nexus-ca.crt).
"""
import datetime as dt
import ipaddress
import json
import logging
import os
import re
import socket
import threading
import time
from pathlib import Path

DEFAULT_PORT = 8443
SETTINGS_FILE = 'acesso-rede.json'
CA_DAYS = 3650
LEAF_DAYS = 820  # Apple só confia em certificados de servidor com validade de até 825 dias.
RENEW_BEFORE_DAYS = 30
LOOPBACK = {'127.0.0.1', '::1'}
HOSTNAME_PATTERN = re.compile(r'^[a-z0-9][a-z0-9.-]{0,252}$')
log = logging.getLogger('nexus.rede')


def private_addresses() -> list[str]:
    """Endereços IPv4 privados deste computador; o da rota padrão vem primeiro."""
    found: list[str] = []

    def add(value):
        try:
            ip = ipaddress.ip_address(value)
        except ValueError:
            return
        if ip.version == 4 and ip.is_private and not ip.is_loopback and not ip.is_link_local and value not in found:
            found.append(value)

    probe = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        probe.connect(('10.255.255.255', 1))  # UDP não envia nada aqui; só escolhe a interface de saída.
        add(probe.getsockname()[0])
    except OSError:
        pass
    finally:
        probe.close()
    try:
        for info in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET):
            add(info[4][0])
    except socket.gaierror:
        pass
    return found


def local_hostnames() -> list[str]:
    name = socket.gethostname().lower()
    return [name] if HOSTNAME_PATTERN.match(name) else []


def load_settings(directory: Path) -> dict:
    settings = {'ativo': False, 'porta': DEFAULT_PORT}
    path = Path(directory) / SETTINGS_FILE
    try:
        stored = json.loads(path.read_text(encoding='utf-8'))
    except (OSError, ValueError):
        return settings
    if isinstance(stored, dict):
        settings['ativo'] = stored.get('ativo') is True
        port = stored.get('porta')
        if isinstance(port, int) and 1024 <= port <= 65535:
            settings['porta'] = port
    return settings


def save_settings(directory: Path, settings: dict):
    path = Path(directory) / SETTINGS_FILE
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix('.tmp')
    temporary.write_text(json.dumps(settings, ensure_ascii=False, indent=2), encoding='utf-8')
    os.replace(temporary, path)


class Certificates:
    """Autoridade local (10 anos) e certificado de servidor (até 820 dias), ambos em PEM."""

    def __init__(self, directory: Path):
        self.directory = Path(directory)
        self.ca_cert = self.directory / 'nexus-ca.crt'
        self.ca_key = self.directory / 'nexus-ca.key'
        self.server_cert = self.directory / 'servidor.crt'
        self.server_key = self.directory / 'servidor.key'

    def ensure(self, addresses: list[str], hostnames: list[str]) -> dict:
        from cryptography import x509
        from cryptography.hazmat.primitives import hashes, serialization
        from cryptography.hazmat.primitives.asymmetric import rsa
        from cryptography.x509.oid import ExtendedKeyUsageOID, NameOID

        self.directory.mkdir(parents=True, exist_ok=True)
        now = dt.datetime.now(dt.timezone.utc)

        def write_key(path, key):
            path.write_bytes(key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()))

        def load_pair(cert_path, key_path):
            try:
                return x509.load_pem_x509_certificate(cert_path.read_bytes()), serialization.load_pem_private_key(key_path.read_bytes(), None)
            except (OSError, ValueError, TypeError):
                return None, None

        ca, ca_key = load_pair(self.ca_cert, self.ca_key)
        if ca is None or ca.not_valid_after_utc <= now + dt.timedelta(days=RENEW_BEFORE_DAYS):
            ca_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
            name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "Nexus Wolf's — autoridade local"), x509.NameAttribute(NameOID.ORGANIZATION_NAME, "Nexus Wolf's")])
            ca = (x509.CertificateBuilder().subject_name(name).issuer_name(name).public_key(ca_key.public_key())
                  .serial_number(x509.random_serial_number()).not_valid_before(now - dt.timedelta(minutes=5)).not_valid_after(now + dt.timedelta(days=CA_DAYS))
                  .add_extension(x509.BasicConstraints(ca=True, path_length=0), critical=True)
                  .add_extension(x509.KeyUsage(digital_signature=True, key_cert_sign=True, crl_sign=True, content_commitment=False, key_encipherment=False,
                                               data_encipherment=False, key_agreement=False, encipher_only=False, decipher_only=False), critical=True)
                  .add_extension(x509.SubjectKeyIdentifier.from_public_key(ca_key.public_key()), critical=False)
                  .sign(ca_key, hashes.SHA256()))
            write_key(self.ca_key, ca_key)
            self.ca_cert.write_bytes(ca.public_bytes(serialization.Encoding.PEM))
            self.server_cert.unlink(missing_ok=True)

        wanted_ips = {ipaddress.ip_address(a) for a in addresses}
        wanted_names = [h for h in hostnames if HOSTNAME_PATTERN.match(h)]
        leaf, leaf_key = load_pair(self.server_cert, self.server_key)
        reuse = False
        if leaf is not None:
            try:
                san = leaf.extensions.get_extension_for_class(x509.SubjectAlternativeName).value
                authority = leaf.extensions.get_extension_for_class(x509.AuthorityKeyIdentifier).value.key_identifier
                issuer_key = ca.extensions.get_extension_for_class(x509.SubjectKeyIdentifier).value.digest
                reuse = (set(san.get_values_for_type(x509.IPAddress)) == wanted_ips and san.get_values_for_type(x509.DNSName) == wanted_names
                         and authority == issuer_key and leaf.not_valid_after_utc > now + dt.timedelta(days=RENEW_BEFORE_DAYS))
            except x509.ExtensionNotFound:
                reuse = False
        if not reuse:
            leaf_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
            subject = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "Nexus Wolf's"), x509.NameAttribute(NameOID.ORGANIZATION_NAME, "Nexus Wolf's")])
            names = [x509.IPAddress(ip) for ip in sorted(wanted_ips)] + [x509.DNSName(h) for h in wanted_names]
            leaf = (x509.CertificateBuilder().subject_name(subject).issuer_name(ca.subject).public_key(leaf_key.public_key())
                    .serial_number(x509.random_serial_number()).not_valid_before(now - dt.timedelta(minutes=5)).not_valid_after(now + dt.timedelta(days=LEAF_DAYS))
                    .add_extension(x509.BasicConstraints(ca=False, path_length=None), critical=True)
                    .add_extension(x509.KeyUsage(digital_signature=True, key_encipherment=True, key_cert_sign=False, crl_sign=False, content_commitment=False,
                                                 data_encipherment=False, key_agreement=False, encipher_only=False, decipher_only=False), critical=True)
                    .add_extension(x509.ExtendedKeyUsage([ExtendedKeyUsageOID.SERVER_AUTH]), critical=False)
                    .add_extension(x509.SubjectAlternativeName(names), critical=False)
                    .add_extension(x509.AuthorityKeyIdentifier.from_issuer_public_key(ca_key.public_key()), critical=False)
                    .add_extension(x509.SubjectKeyIdentifier.from_public_key(leaf_key.public_key()), critical=False)
                    .sign(ca_key, hashes.SHA256()))
            write_key(self.server_key, leaf_key)
            self.server_cert.write_bytes(leaf.public_bytes(serialization.Encoding.PEM))
        fingerprint = ca.fingerprint(hashes.SHA256()).hex().upper()
        return {'serie': format(leaf.serial_number, 'x'), 'validade': leaf.not_valid_after_utc.date().isoformat(),
                'enderecos': [str(ip) for ip in sorted(wanted_ips)], 'nomes': wanted_names,
                'ca_impressao': ' '.join(fingerprint[i:i + 4] for i in range(0, len(fingerprint), 4)), 'ca_validade': ca.not_valid_after_utc.date().isoformat()}


class NetworkAccess:
    """Listener HTTPS opcional do mesmo aplicativo, controlado pelo computador e persistido na pasta de dados."""

    def __init__(self, app, directory: Path, host: str = '0.0.0.0'):
        self.app = app
        self.directory = Path(directory)
        self.host = host
        self.address_source = private_addresses
        self.hostnames: list[str] | None = None
        self.certificates = Certificates(self.directory / 'certificados')
        self.settings = load_settings(self.directory)
        self.lock = threading.RLock()
        self.server = None
        self.thread = None
        self.listener = None
        self.port: int | None = None
        self.addresses: list[str] = []
        self.certificate: dict = {}
        self.error = ''

    @property
    def running(self) -> bool:
        return self.server is not None and self.thread is not None and self.thread.is_alive()

    def names(self) -> list[str]:
        return self.hostnames if self.hostnames is not None else local_hostnames()

    def allowed_hosts(self) -> set[str]:
        if not self.running:
            return set()
        return set(self.addresses) | set(self.certificate.get('nomes', []))

    def status(self) -> dict:
        running = self.running
        port = self.port if running else self.settings['porta']
        hosts = (self.addresses + self.certificate.get('nomes', [])) if running else []
        return {'ativo': self.settings['ativo'], 'porta': port, 'executando': running, 'erro': self.error,
                'enderecos': [f'https://{host}:{port}' for host in hosts], 'enderecos_atuais': list(self.address_source()),
                'certificado': {k: self.certificate.get(k) for k in ('validade', 'ca_impressao', 'ca_validade')} if self.certificate else None,
                'ca_disponivel': self.certificates.ca_cert.is_file()}

    def start(self, port: int):
        with self.lock:
            if self.running and self.port == port:
                return
            self.stop()
            addresses = list(self.address_source())
            if not addresses:
                raise RuntimeError('Nenhuma rede local foi encontrada neste computador.')
            self.certificate = self.certificates.ensure(addresses, self.names())
            listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            try:
                listener.bind((self.host, port))
                listener.listen(64)
            except OSError as exc:
                listener.close()
                raise RuntimeError(f'A porta {port} já está em uso. Escolha outra porta.') from exc
            import uvicorn
            config = uvicorn.Config(self.app, host=self.host, port=port, ssl_certfile=str(self.certificates.server_cert), ssl_keyfile=str(self.certificates.server_key),
                                    access_log=False, log_config=None, log_level='warning')
            server = uvicorn.Server(config)
            thread = threading.Thread(target=lambda: server.run(sockets=[listener]), name='nexus-rede', daemon=True)
            thread.start()
            deadline = time.monotonic() + 15
            while not server.started:
                if not thread.is_alive() or time.monotonic() > deadline:
                    listener.close()
                    raise RuntimeError('O acesso pela rede não iniciou. Consulte runtime.log na pasta de dados.')
                time.sleep(.05)
            self.server, self.thread, self.listener, self.port, self.addresses, self.error = server, thread, listener, port, addresses, ''
            log.warning('Acesso pela rede ligado em %s', ', '.join(f'https://{a}:{port}' for a in addresses))

    def stop(self):
        with self.lock:
            server, thread, listener = self.server, self.thread, self.listener
            self.server = self.thread = self.listener = None
            if server is not None:
                server.should_exit = True
            if thread is not None:
                thread.join(timeout=10)
            if listener is not None:
                listener.close()
            if server is not None:
                log.warning('Acesso pela rede desligado')

    def enable(self, port: int):
        with self.lock:
            try:
                self.start(port)
            except RuntimeError as exc:
                self.error = str(exc)
                raise
            self.settings = {'ativo': True, 'porta': port}
            save_settings(self.directory, self.settings)

    def disable(self):
        with self.lock:
            self.stop()
            self.settings = {'ativo': False, 'porta': self.settings['porta']}
            self.error = ''
            save_settings(self.directory, self.settings)

    def start_if_enabled(self):
        if not self.settings['ativo']:
            return
        try:
            self.start(self.settings['porta'])
        except Exception as exc:  # noqa: BLE001 - a falha fica visível na interface, sem derrubar o aplicativo.
            self.error = str(exc)
            log.warning('Acesso pela rede não iniciou: %s', exc)
