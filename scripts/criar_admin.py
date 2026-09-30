"""Cria o primeiro usuário admin da API.

Uso: DATABASE_URL=postgresql://galpao_api:SENHA@localhost:5432/galpao python scripts/criar_admin.py
Pede email, nome e senha (duas vezes) no terminal. Se o email já existir, avisa e sai sem alterar.
"""
import getpass
import os
import sys
from pathlib import Path

import psycopg

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "api"))
from app.seguranca import hash_senha  # noqa: E402

SENHA_MIN = 10


def main() -> None:
    url = os.environ.get("DATABASE_URL")
    if not url:
        sys.exit("DATABASE_URL não definida")

    email = input("Email: ").strip().lower()
    nome = input("Nome: ").strip()
    if not email or not nome:
        sys.exit("email e nome são obrigatórios")

    senha = getpass.getpass("Senha: ")
    if len(senha) < SENHA_MIN:
        sys.exit(f"a senha precisa ter pelo menos {SENHA_MIN} caracteres")
    if getpass.getpass("Repita a senha: ") != senha:
        sys.exit("as senhas não conferem")

    with psycopg.connect(url, autocommit=True) as conn:
        if conn.execute("SELECT 1 FROM galpao.usuarios WHERE email = %s", (email,)).fetchone():
            sys.exit(f"o email {email} já existe; nada foi alterado")
        conn.execute(
            "INSERT INTO galpao.usuarios (email, nome, senha_hash, perfil) VALUES (%s, %s, %s, 'admin')",
            (email, nome, hash_senha(senha)),
        )
    print(f"admin {email} criado")


if __name__ == "__main__":
    main()
