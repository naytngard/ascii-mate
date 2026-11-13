"""Yerel IPC yardımcıları: kullanıcıya özel authkey ve pipe'ı tüketmeyen varlık yoklaması."""

from __future__ import annotations

import os
import secrets
from multiprocessing.connection import Client
from pathlib import Path
from typing import Optional

from src.core.app_logging import app_data_dir, get_logger

log = get_logger("ipc")

PIPE_ADDRESS = r"\\.\pipe\ascii_mate_ipc" if os.name == "nt" else "/tmp/ascii_mate_ipc.sock"
PIPE_CLI_ADDRESS = r"\\.\pipe\ascii_mate_cli_ipc" if os.name == "nt" else "/tmp/ascii_mate_cli_ipc.sock"

_KEY_CACHE: Optional[bytes] = None


def get_authkey() -> bytes:
    """Kullanıcıya özel rastgele anahtarı okur; yoksa üretip yalnızca kullanıcıya yazılabilir dosyaya kaydeder.

    Anahtar %APPDATA%\\ASCII_Mate\\ipc.key içinde durur (kullanıcı profili ACL'i ile diğer kullanıcılardan korunur).
    Anahtarsız süreçler pickle tabanlı recv()'e ulaşamaz: bağlantı HMAC el sıkışmasında reddedilir.
    """
    global _KEY_CACHE
    if _KEY_CACHE is not None:
        return _KEY_CACHE
    path: Path = app_data_dir() / "ipc.key"
    try:
        if path.exists():
            raw = path.read_text(encoding="ascii").strip()
            if len(raw) >= 32:
                _KEY_CACHE = raw.encode("ascii")
                return _KEY_CACHE
        path.parent.mkdir(parents=True, exist_ok=True)
        key = secrets.token_hex(32)
        tmp = path.with_suffix(".tmp")
        tmp.write_text(key, encoding="ascii")
        try:
            os.chmod(tmp, 0o600)
        except OSError:
            pass
        try:
            tmp.replace(path)
        except OSError:
            # Yarışta başka süreç önce yazmış olabilir; onunkini oku
            if path.exists():
                key = path.read_text(encoding="ascii").strip() or key
        _KEY_CACHE = key.encode("ascii")
    except OSError:
        log.exception("IPC anahtarı okunamadı/yazılamadı; oturuma özel geçici anahtar kullanılıyor")
        _KEY_CACHE = secrets.token_hex(32).encode("ascii")
    return _KEY_CACHE


def pipe_exists(address: str) -> bool:
    """Named pipe'ın varlığını pipe'ı tüketmeden yoklar (WaitNamedPipe). Unix'te dosya var mı bakar."""
    if os.name != "nt":
        return os.path.exists(address)
    try:
        import ctypes

        kernel32 = ctypes.windll.kernel32
        if kernel32.WaitNamedPipeW(address, 1):
            return True
        err = ctypes.GetLastError()
        # 121 = ERROR_SEM_TIMEOUT: pipe var ama meşgul; 2 = FILE_NOT_FOUND: yok
        return err == 121
    except Exception:
        log.exception("WaitNamedPipe başarısız")
        return False


def connect(address: str) -> Client:
    return Client(address, authkey=get_authkey())
