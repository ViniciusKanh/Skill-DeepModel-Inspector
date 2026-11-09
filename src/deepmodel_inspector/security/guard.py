"""Proteções de segurança: validação de caminhos, limites e bloqueio de arquivos sensíveis.

Este módulo é autocontido (somente biblioteca padrão) para que possa ser
embutido nos scripts comerciais gerados por ``tools/build_skill.py``.
"""

from __future__ import annotations

import os
from pathlib import Path

# Nomes/extensões que nunca são lidos (credenciais e segredos).
SENSITIVE_NAMES = {
    ".env",
    ".netrc",
    ".pgpass",
    ".git-credentials",
    "credentials",
    "credentials.json",
    "id_rsa",
    "id_dsa",
    "id_ecdsa",
    "id_ed25519",
    "known_hosts",
    "authorized_keys",
    ".npmrc",
    ".pypirc",
    "secrets.json",
    "secrets.yaml",
    "secrets.yml",
    "token.json",
}
SENSITIVE_SUFFIXES = {".pem", ".key", ".p12", ".pfx", ".keystore", ".jks", ".kdbx"}
SENSITIVE_DIRS = {".ssh", ".aws", ".gnupg", ".azure", ".kube", ".docker", ".config/gcloud"}
# Formatos cuja leitura exigiria desserialização insegura (pickle) ou binários de pesos.
UNSAFE_DESERIALIZATION = {".pkl", ".pickle", ".pt", ".pth", ".ckpt", ".bin", ".joblib", ".npy", ".npz"}
DEFAULT_MAX_MB = 200.0


class SecurityError(Exception):
    """Erro levantado quando uma operação viola a política de segurança."""


def _roots(allowed_roots: list[str] | None) -> list[Path]:
    """Resolve as raízes autorizadas (padrão: somente o diretório corrente).

    Variáveis de ambiente não são lidas, por política de privacidade.
    """
    raw = list(allowed_roots or []) or [os.getcwd()]
    return [Path(r).expanduser().resolve() for r in raw]


def is_sensitive(path: Path) -> bool:
    """Indica se o caminho aponta para credenciais ou diretórios de segredos."""
    name = path.name.lower()
    if name in SENSITIVE_NAMES or name.startswith(".env.") and name != ".env.example":
        return True
    if path.suffix.lower() in SENSITIVE_SUFFIXES:
        return True
    parts = [p.lower() for p in path.parts]
    joined = "/".join(parts)
    return any(d in parts or f"/{d}/" in f"/{joined}/" for d in SENSITIVE_DIRS)


def within_roots(path: Path, roots: list[Path]) -> bool:
    """Verifica se ``path`` (já resolvido) está contido em alguma raiz autorizada."""
    for root in roots:
        try:
            path.relative_to(root)
            return True
        except ValueError:
            continue
    return False


def safe_input_path(
    path: str | os.PathLike[str],
    allowed_roots: list[str] | None = None,
    max_mb: float = DEFAULT_MAX_MB,
    allow_dir: bool = False,
) -> Path:
    """Valida um caminho de entrada (somente leitura) e devolve o caminho resolvido.

    Regras: deve existir, estar dentro das raízes autorizadas, não ser sensível,
    não exigir desserialização insegura e respeitar o limite de tamanho.
    """
    p = Path(path).expanduser().resolve()
    roots = _roots(allowed_roots)
    if not within_roots(p, roots):
        raise SecurityError(f"path outside authorized roots: {p}")
    if is_sensitive(p):
        raise SecurityError(f"refusing to read sensitive file: {p.name}")
    if not p.exists():
        raise FileNotFoundError(f"path not found: {p}")
    if p.is_dir():
        if not allow_dir:
            raise SecurityError(f"expected a file, got a directory: {p}")
        return p
    if p.suffix.lower() in UNSAFE_DESERIALIZATION:
        raise SecurityError(f"unsafe deserialization refused for {p.suffix} files: {p.name}")
    size_mb = p.stat().st_size / (1024 * 1024)
    if size_mb > max_mb:
        raise SecurityError(f"file exceeds size limit ({size_mb:.1f} MB > {max_mb} MB): {p.name}")
    return p


def safe_output_path(
    path: str | os.PathLike[str],
    inputs: list[Path] | None = None,
    allowed_roots: list[str] | None = None,
) -> Path:
    """Valida um caminho de saída: nunca sobrescreve entradas nem escreve fora das raízes."""
    p = Path(path).expanduser().resolve()
    roots = _roots(allowed_roots)
    if not within_roots(p, roots):
        raise SecurityError(f"output outside authorized roots: {p}")
    if is_sensitive(p):
        raise SecurityError(f"refusing to write sensitive path: {p.name}")
    for src in inputs or []:
        if p == src.resolve():
            raise SecurityError(f"refusing to overwrite an analyzed input: {p.name}")
    return p
