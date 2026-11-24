"""Roda o pipeline inteiro: CSV -> preparo -> features -> treino -> saídas.

Uso: uv run python rodar.py --csv caminho.csv [--saidas pasta] [--origem real|sintetico]
"""
import argparse
import json
from pathlib import Path

import sys

import matplotlib

matplotlib.use("Agg")
import matplotlib.dates as mdates
import matplotlib.pyplot as plt

from features import FUSO_LOCAL, HORIZONTE_MIN, LAGS_MIN, montar_features
from preparar import preparar
from treinar import treinar

# cores (paleta validada, superfície clara)
SUPERFICIE, TINTA, TINTA_2, GRADE = "#fcfcfb", "#0b0b0b", "#52514e", "#e1e0d9"
AZUL, LARANJA = "#2a78d6", "#eb6834"
NOMES = {"persistencia": "Persistência", "linear": "Regressão linear", "xgboost": "XGBoost"}


def detectar_origem(caminho, origem):
    """Origem dos dados: o argumento manda; senão, 'sintetico' no nome do arquivo."""
    if origem:
        return origem
    return "sintetico" if "sintetico" in Path(caminho).name.lower() else "real"


def estilo(ax):
    """Eixos discretos: sem moldura superior/direita, grade fina."""
    ax.set_facecolor(SUPERFICIE)
    for lado in ("top", "right"):
        ax.spines[lado].set_visible(False)
    for lado in ("left", "bottom"):
        ax.spines[lado].set_color(GRADE)
    ax.grid(axis="y", color=GRADE, linewidth=0.8)
    ax.tick_params(colors=TINTA_2)


def grafico_previsto_real(prev, origem, caminho):
    """Real x previsto no período de teste (hora local)."""
    prev = prev.tz_convert(FUSO_LOCAL)
    fig, ax = plt.subplots(figsize=(11, 4.5), facecolor=SUPERFICIE)
    estilo(ax)
    # quebra a linha nos buracos (NaN) para não ligar segmentos distintos
    quebrado = prev.asfreq("5min")
    ax.plot(quebrado.index, quebrado["real"], color=TINTA, lw=2, label="Real")
    ax.plot(quebrado.index, quebrado["persistencia"], color=LARANJA, lw=1.2, label="Persistência")
    ax.plot(quebrado.index, quebrado["linear"], color=TINTA_2, lw=1.2, ls="--", label="Regressão linear")
    ax.plot(quebrado.index, quebrado["xgboost"], color=AZUL, lw=1.5, label="XGBoost")
    ax.axhline(80, color=TINTA_2, lw=0.8, ls=":")
    ax.text(quebrado.index[-1], 80.2, "ITGU 80", color=TINTA_2, fontsize=8, va="bottom", ha="right")
    ax.set_ylim(top=quebrado["real"].max() + 2.5)  # espaço para a legenda dentro do gráfico
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%d/%m %Hh", tz=quebrado.index.tz))
    ax.set_ylabel(f"ITGU daqui a {HORIZONTE_MIN} min", color=TINTA_2)
    ax.set_title(f"Previsto x real no teste (dados {origem.upper()})", loc="left", color=TINTA)
    ax.legend(frameon=False, labelcolor=TINTA_2, ncol=4, loc="upper left")
    fig.autofmt_xdate()
    fig.tight_layout()
    fig.savefig(caminho, dpi=150, facecolor=SUPERFICIE)
    plt.close(fig)


def grafico_importancia(imp, origem, caminho, top=15):
    """Barras horizontais com as features mais importantes do XGBoost."""
    imp = imp.tail(top)
    fig, ax = plt.subplots(figsize=(8, 5), facecolor=SUPERFICIE)
    estilo(ax)
    ax.grid(axis="y", visible=False)
    ax.grid(axis="x", color=GRADE, linewidth=0.8)
    ax.barh(imp.index, imp.values, color=AZUL, height=0.65)
    ax.set_xlabel("Importância (ganho relativo)", color=TINTA_2)
    ax.set_title(f"Importância das features, XGBoost (dados {origem.upper()})",
                 loc="left", color=TINTA)
    fig.tight_layout()
    fig.savefig(caminho, dpi=150, facecolor=SUPERFICIE)
    plt.close(fig)


def montar_resumo(csv, origem, info, res):
    """Texto em Markdown pronto para copiar para o relatório."""
    m = res["metricas"]
    fmt = lambda t: t.tz_convert(FUSO_LOCAL).strftime("%d/%m/%Y %H:%M")
    linhas = [f"# Previsão do ITGU a {HORIZONTE_MIN} min: resumo", ""]
    if origem == "sintetico":
        linhas += ["> **ATENÇÃO: DADOS SINTÉTICOS.** Os números abaixo só validam o pipeline "
                   "e não são resultado do projeto.", ""]
    linhas += [
        "## Origem dos dados",
        f"- Origem: **{origem}**",
        f"- Arquivo: `{Path(csv).name}`",
        f"- Período (horário de Recife): {fmt(info['inicio'])} a {fmt(info['fim'])}",
        f"- Leituras brutas: {info['leituras_brutas']}",
        f"- Leituras com ts de origem `servidor` (hora de chegada, não da medição): "
        f"**{info['pct_servidor']:.2f}%** (mantidas)",
        f"- Janelas de 5 min: {info['janelas']} ({info['janelas_preenchidas']} preenchidas "
        "por repetição do último valor, só em faltas de até 15 min)",
        f"- Segmentos contínuos: {info['segmentos']}; buracos > 15 min: {len(info['buracos'])} "
        "(não interpolados)",
    ]
    for _, b in info["buracos"].iterrows():
        linhas.append(f"  - {fmt(b['inicio'])} a {fmt(b['fim'])} ({b['duracao_min']:.0f} min sem dados)")
    linhas += [
        "",
        "## Método",
        f"- Alvo: ITGU daqui a {HORIZONTE_MIN} min. Lags de {', '.join(map(str, LAGS_MIN))} min "
        "para ITGU e variáveis, mais hora do dia (seno/cosseno), sem lag atravessando buraco.",
        f"- Divisão temporal sem embaralhar: treino {fmt(res['treino_inicio'])} a "
        f"{fmt(res['treino_fim'])} ({res['n_treino']} amostras); teste {fmt(res['teste_inicio'])} a "
        f"{fmt(res['teste_fim'])} ({res['n_teste']} amostras, últimos 20%).",
        "",
        "## Resultado no teste (unidades de ITGU)",
        "",
        "| Modelo | MAE | RMSE |",
        "|---|---|---|",
    ]
    for chave in ("persistencia", "linear", "xgboost"):
        linhas.append(f"| {NOMES[chave]} | {m[chave]['mae']:.3f} | {m[chave]['rmse']:.3f} |")
    melhor = min(m, key=lambda k: m[k]["rmse"])
    linhas += ["", f"Menor RMSE: **{NOMES[melhor]}**.", "",
               "Gráficos: `previsto_x_real.png`, `importancia_xgb.png`.", ""]
    return "\n".join(linhas)


def main():
    sys.stdout.reconfigure(encoding="utf-8")  # acentos no console do Windows
    pasta = Path(__file__).parent
    ap = argparse.ArgumentParser(description="Pipeline de previsão do ITGU.")
    ap.add_argument("--csv", required=True, help="CSV exportado de /leituras/csv (agregacao=bruto)")
    ap.add_argument("--saidas", default=str(pasta / "saidas"))
    ap.add_argument("--origem", choices=["real", "sintetico"],
                    help="padrão: 'sintetico' se o nome do arquivo contiver isso, senão 'real'")
    args = ap.parse_args()

    origem = detectar_origem(args.csv, args.origem)
    saidas = Path(args.saidas)
    saidas.mkdir(parents=True, exist_ok=True)

    df, info = preparar(args.csv)
    X, y = montar_features(df)
    if len(X) < 100:
        raise SystemExit(f"Poucas amostras válidas ({len(X)}): dados insuficientes para treinar.")
    res = treinar(X, y)

    metricas = {
        "origem": origem, "arquivo": Path(args.csv).name,
        "horizonte_min": HORIZONTE_MIN, "lags_min": LAGS_MIN,
        "pct_leituras_servidor": info["pct_servidor"],
        "leituras_brutas": info["leituras_brutas"], "segmentos": info["segmentos"],
        "buracos": len(info["buracos"]),
        "n_treino": res["n_treino"], "n_teste": res["n_teste"],
        "teste_inicio": res["teste_inicio"].isoformat(), "teste_fim": res["teste_fim"].isoformat(),
        "metricas": res["metricas"],
    }
    (saidas / "metricas.json").write_text(json.dumps(metricas, indent=2, ensure_ascii=False),
                                          encoding="utf-8")
    grafico_previsto_real(res["previsoes"], origem, saidas / "previsto_x_real.png")
    grafico_importancia(res["importancias"], origem, saidas / "importancia_xgb.png")
    (saidas / "resumo.md").write_text(montar_resumo(args.csv, origem, info, res), encoding="utf-8")

    print(f"Origem dos dados: {origem}")
    for k, v in res["metricas"].items():
        print(f"  {NOMES[k]:<17} MAE {v['mae']:.3f}  RMSE {v['rmse']:.3f}")
    print(f"Saídas em {saidas}")


if __name__ == "__main__":
    main()
