"""Gancho de execução do PyInstaller: garante o `ssl.SSLContext` padrão do CPython dentro do executável.

Por quê: o Python usado para compilar pode ter a biblioteca padrão alterada pelo ambiente de desenvolvimento (em 26/10/2026
o `ssl.py` do runtime passou a carregar um arquivo `codex-rejected-cas.pem` ao lado da própria `Lib/`). Dentro do aplicativo
empacotado esse arquivo não existe e toda criação de contexto TLS falhava com FileNotFoundError, derrubando o autoteste, a
busca de capas e a sincronização de troféus. Este gancho roda antes do `desktop.py` e devolve a implementação original,
sem arquivos externos; nada muda para quem compila com um Python intacto.
"""
import ssl
import _ssl
import warnings


def _stock_new(cls, protocol=None, *args, **kwargs):
    if protocol is None:
        warnings.warn('ssl.SSLContext() without protocol argument is deprecated.', category=DeprecationWarning, stacklevel=2)
        protocol = ssl.PROTOCOL_TLS
    return _ssl._SSLContext.__new__(cls, protocol)


ssl.SSLContext.__new__ = staticmethod(_stock_new)
