"""Aplica as faixas de ITGU de POEDEIRAS (com fonte) e desativa as faixas EXEMPLO.

Uso: DATABASE_URL_API=postgresql://galpao_api:SENHA@localhost:5432/galpao python scripts/aplicar_faixas_poedeiras.py
(aceita também DATABASE_URL). Serve para o banco local e para o de produção.

- Idempotente: a faixa é identificada pelo nome; se já existe, não é recriada nem alterada
  (o admin pode ter ajustado pelo painel). Rodar duas vezes não duplica nada.
- Desativa (não apaga) as faixas "EXEMPLO..." e solta a faixa manual que apontava para elas.
- Tudo ou nada: se alguma faixa nova se sobrepõe em idade a outra faixa ativa, nada é alterado.
- Idade de 15 a 42 dias fica SEM faixa: não há ITGU publicado para essa fase.
- Limite None = não existe na literatura (precisa da migração db/005).

Referências:
  ANDRADE, R. R. et al. Engenharia Agrícola, v. 39, n. 1, p. 32-40, 2019.
  JÁCOME, I. M. T. D. et al. RBEAA, v. 11, n. 5, p. 527-531, 2007 (cita Tinôco, 1998: ITGU até 75 é conforto para poedeiras).
  BAÊTA, F. C.; SOUZA, C. F. Ambiência em edificações rurais: conforto animal. Viçosa: UFV, 2010.
"""
import os
import sys

import psycopg

IDADE_MAXIMA_DIAS = 1000  # o campo é obrigatório; poedeiras comerciais passam dos 600 dias

# (nome, idade início, idade fim, crítico mín., conforto mín., conforto máx., crítico máx.)
FAIXAS = [
    ("Poedeiras · Cria 1ª semana (Andrade et al., 2019)", 0, 7, None, 83.0, 89.0, None),
    ("Poedeiras · Cria 2ª semana (Andrade et al., 2019)", 8, 14, None, 77.0, 81.0, None),
    # sem faixa de 15 a 42 dias
    ("Poedeiras · Recria e produção (Tinôco, 1998; Baêta e Souza, 2010)", 43, IDADE_MAXIMA_DIAS, None, None, 75.0, 78.0),
]

SQL_DESATIVAR = "UPDATE galpao.faixas_itgu SET ativo = false WHERE ativo AND nome LIKE 'EXEMPLO%' RETURNING id"
SQL_SOLTAR_MANUAL = "UPDATE galpao.dispositivos SET faixa_manual_id = NULL WHERE faixa_manual_id = ANY(%s)"
SQL_EXISTE = "SELECT 1 FROM galpao.faixas_itgu WHERE nome = %s"
SQL_CONFLITO = (
    "SELECT nome FROM galpao.faixas_itgu "
    "WHERE ativo AND int4range(idade_inicio_dias, idade_fim_dias, '[]') && int4range(%s, %s, '[]')"
)
SQL_CRIAR = (
    "INSERT INTO galpao.faixas_itgu (nome, idade_inicio_dias, idade_fim_dias, critico_min, conforto_min, "
    "conforto_max, critico_max) VALUES (%s, %s, %s, %s, %s, %s, %s)"
)


def aplicar_faixas(conn) -> dict:
    """Desativa as EXEMPLO e cria as faixas de poedeiras que faltam. Devolve o que foi feito.

    Levanta ValueError (sem alterar nada além do que a transação do chamador desfaz) se uma faixa
    nova se sobrepõe em idade a uma faixa ativa de outro nome.
    """
    desativadas = [linha[0] for linha in conn.execute(SQL_DESATIVAR).fetchall()]
    if desativadas:
        conn.execute(SQL_SOLTAR_MANUAL, (desativadas,))

    criadas, mantidas = [], []
    for nome, inicio, fim, cmin, mmin, mmax, cmax in FAIXAS:
        if conn.execute(SQL_EXISTE, (nome,)).fetchone():
            mantidas.append(nome)
            continue
        conflitos = [c[0] for c in conn.execute(SQL_CONFLITO, (inicio, fim)).fetchall()]
        if conflitos:
            raise ValueError(f"'{nome}' ({inicio} a {fim} dias) se sobrepõe à(s) faixa(s) ativa(s): {', '.join(conflitos)}")
        conn.execute(SQL_CRIAR, (nome, inicio, fim, cmin, mmin, mmax, cmax))
        criadas.append(nome)
    return {"desativadas": len(desativadas), "criadas": criadas, "mantidas": mantidas}


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")  # acentos no console do Windows
    url = os.environ.get("DATABASE_URL_API") or os.environ.get("DATABASE_URL")
    if not url:
        sys.exit("DATABASE_URL_API (ou DATABASE_URL) não definida")
    try:
        with psycopg.connect(url) as conn:  # uma transação: ou aplica tudo, ou nada
            resultado = aplicar_faixas(conn)
    except ValueError as erro:
        sys.exit(f"nada foi alterado: {erro}")
    print(f"faixas EXEMPLO desativadas: {resultado['desativadas']}")
    print(f"faixas criadas: {len(resultado['criadas'])}")
    for nome in resultado["criadas"]:
        print(f"  + {nome}")
    for nome in resultado["mantidas"]:
        print(f"  = {nome} (já existia, mantida)")


if __name__ == "__main__":
    main()
