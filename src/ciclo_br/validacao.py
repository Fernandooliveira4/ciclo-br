"""Validação do classificador contra a cronologia oficial do CODACE.

**O que está sendo comparado — e o que não está.** O CODACE data *recessões*:
queda disseminada do nível de atividade, avaliada por um comitê olhando um
conjunto amplo de indicadores. O eixo de crescimento deste projeto é o momentum
de uma série só, comparado a um corte. São objetos diferentes, e o sinal fica
abaixo do corte bem mais vezes do que a economia entra em recessão.

Por isso a métrica principal é a **defasagem** — quantos meses o sinal se antecipa
ou atrasa em relação ao início e ao fim de cada recessão datada — e não taxa de
acerto. Taxa de acerto penalizaria o sinal por fazer exatamente aquilo para que
foi construído. Episódios de contração fora de recessão são contados e mostrados,
mas como característica medida, não como erro.

**Por que isso não vira um modelo.** A janela de validação tem três recessões:
2008, 2014-2016 e 2020. Três eventos não sustentam parâmetro estimado. O que a
validação faz é varrer as duas escolhas que o classificador tem — o corte do
eixo de crescimento e o prazo de persistência — e mostrar o que cada combinação
custa em atraso e o que compra em sossego. A escolha continua sendo de quem lê;
o que deixa de existir é a escolha no escuro. Foi assim que o corte passou da
mediana histórica para zero.

**Convenção de datação.** O pico é o último mês de expansão e o vale é o último
mês de recessão (o próprio CODACE define assim para os trimestres). Logo a
recessão ocupa `pico`+1 até `vale`. As defasagens seguem daí:

- defasagem no pico  = mês em que o sinal entra em contração − (`pico` + 1)
- defasagem no vale  = mês em que o sinal sai de contração − (`vale` + 1)

Negativo é antecipação, positivo é atraso, zero é acerto no mês. Antecipar não é
necessariamente melhor: um sinal que se antecipa sempre é um sinal que também
grita em falso. Os dois números precisam ser lidos junto com a contagem de
episódios fora de recessão.
"""

from __future__ import annotations

import datetime as dt
import logging

import pandas as pd

from . import regime
from .config import DIR_DADOS, RAIZ

log = logging.getLogger(__name__)

CAMINHO_CRONOLOGIA = RAIZ / "config" / "codace_cronologia.csv"
CAMINHO_DEFASAGENS = DIR_DADOS / "derivado" / "validacao_defasagens.csv"
CAMINHO_RESUMO = DIR_DADOS / "derivado" / "validacao_resumo.csv"

# Os dois quadrantes em que o eixo de crescimento está abaixo do seu corte.
QUADRANTES_CONTRACAO = ("Desaceleração", "Estagflação")

# Valores de persistência varridos. 1 equivale a não ter regra: a troca vale já
# no primeiro mês do novo sinal.
PERSISTENCIAS = (1, 2, 3, 4, 5, 6)

# Meses de histórico classificado exigidos antes do pico para que a defasagem
# medida seja confiável. Com menos que isso o sinal pode ter virado antes do
# início da série classificada, e o truncamento só encurta a antecipação
# aparente — nunca a alonga.
RUNWAY_MINIMO = 12


class CronologiaInvalida(ValueError):
    """A cronologia transcrita do CODACE está inconsistente."""


def carregar_cronologia(caminho=CAMINHO_CRONOLOGIA) -> pd.DataFrame:
    """Lê a transcrição do CODACE e recusa qualquer inconsistência."""
    bruto = pd.read_csv(caminho, comment="#", dtype=str).fillna("")
    if bruto.empty:
        raise CronologiaInvalida("cronologia vazia")

    faltando = {"recessao_id", "pico", "vale", "granularidade", "fonte"} - set(bruto.columns)
    if faltando:
        raise CronologiaInvalida(f"colunas ausentes: {sorted(faltando)}")

    crono = bruto.copy()
    for coluna in ("pico", "vale"):
        try:
            crono[coluna] = pd.PeriodIndex(crono[coluna], freq="M")
        except Exception as erro:  # noqa: BLE001 - queremos a mensagem original
            raise CronologiaInvalida(f"coluna {coluna} não é AAAA-MM: {erro}") from erro

    if not (crono["pico"] < crono["vale"]).all():
        ruins = crono.loc[crono["pico"] >= crono["vale"], "recessao_id"].tolist()
        raise CronologiaInvalida(f"pico não antecede o vale em: {ruins}")

    if not crono["pico"].is_monotonic_increasing:
        raise CronologiaInvalida("recessões fora de ordem cronológica")

    # Uma recessão não pode começar antes de a anterior terminar.
    picos = crono["pico"].reset_index(drop=True)
    vales = crono["vale"].reset_index(drop=True)
    if (picos[1:].to_numpy() <= vales[:-1].to_numpy()).any():
        raise CronologiaInvalida("recessões sobrepostas")

    invalidas = set(crono["granularidade"]) - {"mensal", "trimestral"}
    if invalidas:
        raise CronologiaInvalida(f"granularidade desconhecida: {sorted(invalidas)}")

    crono["inicio"] = crono["pico"] + 1
    crono["fim"] = crono["vale"]
    crono["duracao"] = (crono["fim"] - crono["inicio"]).apply(lambda d: d.n) + 1
    return crono.reset_index(drop=True)


def sinal_contracao(quadrantes: pd.Series) -> pd.Series:
    """True nos meses em que o eixo de crescimento está abaixo do corte."""
    return quadrantes.isin(QUADRANTES_CONTRACAO)


def episodios(sinal: pd.Series) -> list[tuple[pd.Period, pd.Period]]:
    """Blocos contíguos de meses em contração, como (primeiro, último)."""
    blocos: list[tuple[pd.Period, pd.Period]] = []
    inicio: pd.Period | None = None
    anterior: pd.Period | None = None

    for mes, ligado in sinal.items():
        if ligado and inicio is None:
            inicio = mes
        elif not ligado and inicio is not None:
            blocos.append((inicio, anterior))
            inicio = None
        anterior = mes

    if inicio is not None:
        blocos.append((inicio, anterior))
    return blocos


def _sobreposicao(a: tuple[pd.Period, pd.Period], b: tuple[pd.Period, pd.Period]) -> int:
    ini = max(a[0], b[0])
    fim = min(a[1], b[1])
    return max(0, (fim - ini).n + 1)


def defasagens(sinal: pd.Series, crono: pd.DataFrame) -> pd.DataFrame:
    """Uma linha por recessão datada, com a defasagem do sinal em cada ponta.

    O episódio associado a uma recessão é o de **maior sobreposição** com ela;
    empate resolve pelo mais antigo. Sem sobreposição nenhuma, a recessão conta
    como não detectada — não há busca por episódio "próximo", porque a régua de
    proximidade seria arbitrária e é justamente o que se quer medir.
    """
    blocos = episodios(sinal)
    primeiro_mes, ultimo_mes = sinal.index[0], sinal.index[-1]

    linhas = []
    for _, rec in crono.iterrows():
        janela = (rec["inicio"], rec["fim"])
        if rec["fim"] < primeiro_mes or rec["inicio"] > ultimo_mes:
            continue

        if rec["inicio"] < primeiro_mes or rec["fim"] > ultimo_mes:
            cobertura = "fora"
        elif (rec["pico"] - primeiro_mes).n < RUNWAY_MINIMO:
            cobertura = "parcial"
        else:
            cobertura = "completa"

        candidatos = [(b, _sobreposicao(b, janela)) for b in blocos]
        candidatos = [(b, s) for b, s in candidatos if s > 0]
        if not candidatos:
            linhas.append({
                "recessao_id": rec["recessao_id"], "granularidade": rec["granularidade"],
                "pico": str(rec["pico"]), "vale": str(rec["vale"]),
                "cobertura": cobertura, "detectada": False,
                "episodio_inicio": "", "episodio_fim": "",
                "defasagem_pico": pd.NA, "defasagem_pico_primeiro": pd.NA,
                "defasagem_vale": pd.NA,
                "meses_sobrepostos": 0, "cobertura_da_recessao": 0.0,
            })
            continue

        melhor, sobreposto = max(candidatos, key=lambda item: (item[1], -item[0][0].ordinal))
        # O sinal pode ligar, desligar e religar dentro da mesma recessão. A
        # regra escolhe o maior bloco, mas o primeiro bloco a tocar a recessão é
        # outra leitura legítima da mesma coisa, e fica na tabela em vez de virar
        # nota de rodapé: em 2014 os dois números são +11 e +1.
        primeiro = min(candidatos, key=lambda item: item[0][0].ordinal)[0]
        # O fim do episódio pode coincidir com o fim da série: aí o sinal ainda
        # não saiu de contração e a defasagem do vale é indeterminada.
        saiu = melhor[1] < ultimo_mes
        linhas.append({
            "recessao_id": rec["recessao_id"], "granularidade": rec["granularidade"],
            "pico": str(rec["pico"]), "vale": str(rec["vale"]),
            "cobertura": cobertura, "detectada": True,
            "episodio_inicio": str(melhor[0]), "episodio_fim": str(melhor[1]),
            "defasagem_pico": (melhor[0] - rec["inicio"]).n,
            "defasagem_pico_primeiro": (primeiro[0] - rec["inicio"]).n,
            "defasagem_vale": (melhor[1] - rec["vale"]).n if saiu else pd.NA,
            "meses_sobrepostos": sobreposto,
            "cobertura_da_recessao": round(sobreposto / rec["duracao"], 3),
        })

    return pd.DataFrame(linhas)


def caracteristicas(sinal: pd.Series, crono: pd.DataFrame) -> dict:
    """O que o sinal faz além de acertar as datas: largura e falsos episódios.

    A contagem de episódios fora de recessão só vale dentro da janela em que o
    CODACE já se pronunciou. Depois do último vale datado, a ausência de um novo
    pico não significa ausência de recessão: o comitê anuncia com anos de atraso
    — o vale de 2020 só foi datado em janeiro de 2023. Episódios nessa ponta são
    contados à parte, como não avaliáveis.

    `maior_episodio_meses` não é decoração. Um prazo de confirmação longo demais
    faz o sinal virar um único bloco que cobre tudo: ele "detecta" todas as
    recessões e não tem nenhum falso alarme, porque nunca desliga. Sem essa
    coluna, a degeneração apareceria na tabela como o melhor resultado.
    """
    janelas = [(r["inicio"], r["fim"]) for _, r in crono.iterrows()]
    ultimo_vale = crono["vale"].max()
    blocos = episodios(sinal)

    avaliaveis, nao_avaliaveis, meses_falsos = 0, 0, 0
    for bloco in blocos:
        if any(_sobreposicao(bloco, j) > 0 for j in janelas):
            continue
        if bloco[0] > ultimo_vale:
            nao_avaliaveis += 1
        else:
            avaliaveis += 1
            meses_falsos += (bloco[1] - bloco[0]).n + 1

    janela = (sinal.index[0], min(sinal.index[-1], ultimo_vale))
    meses_janela = (janela[1] - janela[0]).n + 1
    return {
        "episodios_fora_de_recessao": avaliaveis,
        "meses_fora_de_recessao": meses_falsos,
        "episodios_apos_ultimo_vale": nao_avaliaveis,
        "episodios_totais": len(blocos),
        "maior_episodio_meses": max(((b[1] - b[0]).n + 1 for b in blocos), default=0),
        "meses_da_janela": meses_janela,
        "meses_com_sinal_na_janela": sum(_sobreposicao(b, janela) for b in blocos),
        "meses_de_recessao_na_janela": sum(_sobreposicao(j, janela) for j in janelas),
        # Sem esta fração, "detectou 3 de 3 recessões" não quer dizer nada: um
        # sinal ligado na maior parte dos meses acerta todas por construção.
        "fracao_da_janela_com_sinal": round(
            sum(_sobreposicao(b, janela) for b in blocos) / meses_janela, 3
        ),
    }


def varrer(reg: pd.DataFrame, crono: pd.DataFrame, persistencias=PERSISTENCIAS,
           cortes=regime.CORTES_CRESCIMENTO) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Repete a medição para cada combinação de corte e prazo de persistência.

    Reaplica a regra sobre os sinais brutos dos dois eixos, que a camada de
    regime guarda exatamente para isto. Persistência 1 equivale a não ter regra.

    Os dois cortes entram na varredura, e é isso que torna a escolha entre eles
    verificável: a pergunta "o corte escolhido é o que está atrapalhando?" só tem
    resposta se as duas versões forem medidas com a mesma régua, lado a lado e
    versionadas. Foi assim que a mediana expansiva perdeu para o zero — e a
    tabela com o resultado das duas continua no repositório, não só a da
    vencedora.
    """
    grade = [(c, m) for c in cortes for m in persistencias]

    tabelas, resumos = [], []
    for corte, meses in grade:
        acima_g, acima_i = regime.sinais(reg, corte_crescimento=corte)
        vigente = regime.aplicar_persistencia(acima_g, acima_i, meses=meses)["quadrante"]
        sinal = sinal_contracao(vigente)

        tabela = defasagens(sinal, crono)
        tabela.insert(0, "persistencia", meses)
        tabela.insert(0, "corte_crescimento", corte)
        tabelas.append(tabela)

        completas = tabela[tabela["cobertura"].isin(("completa", "parcial"))]
        detectadas = completas[completas["detectada"]]
        trocas = int((vigente != vigente.shift()).sum() - 1)
        resumos.append({
            "corte_crescimento": corte,
            "persistencia": meses,
            "recessoes_avaliadas": len(completas),
            "recessoes_detectadas": int(detectadas["detectada"].sum()),
            "defasagem_pico_mediana": (
                float(detectadas["defasagem_pico"].median()) if not detectadas.empty else pd.NA
            ),
            "defasagem_vale_mediana": (
                float(detectadas["defasagem_vale"].dropna().median())
                if not detectadas["defasagem_vale"].dropna().empty else pd.NA
            ),
            "defasagem_pico_max": (
                int(detectadas["defasagem_pico"].max()) if not detectadas.empty else pd.NA
            ),
            "trocas_de_quadrante": trocas,
            **caracteristicas(sinal, crono),
        })

    return pd.concat(tabelas, ignore_index=True), pd.DataFrame(resumos)


def construir() -> tuple[pd.DataFrame, pd.DataFrame]:
    reg = regime.carregar()
    if reg.empty:
        log.warning("regime vazio — rode `ciclo-regime` antes")
        return pd.DataFrame(), pd.DataFrame()
    return varrer(reg, carregar_cronologia())


def salvar(defas: pd.DataFrame, resumo: pd.DataFrame) -> bool:
    """Grava as duas tabelas como CSV.

    CSV e não Parquet aqui de propósito: este é o resultado que um leitor do
    repositório vai querer conferir, e um CSV de cinquenta linhas é legível
    direto no GitHub e produz diff honesto quando um número muda. Parquet
    continua sendo o formato das séries, onde o volume justifica o binário.
    """
    CAMINHO_DEFASAGENS.parent.mkdir(parents=True, exist_ok=True)
    mudou = False
    for caminho, tabela in ((CAMINHO_DEFASAGENS, defas), (CAMINHO_RESUMO, resumo)):
        novo = texto(tabela)
        atual = caminho.read_text(encoding="utf-8") if caminho.exists() else None
        if novo != atual:
            caminho.write_text(novo, encoding="utf-8")
            mudou = True
    return mudou


def texto(tabela: pd.DataFrame) -> str:
    return tabela.to_csv(index=False, lineterminator="\n")


def carregar() -> tuple[pd.DataFrame, pd.DataFrame]:
    if not (CAMINHO_DEFASAGENS.exists() and CAMINHO_RESUMO.exists()):
        return pd.DataFrame(), pd.DataFrame()
    return pd.read_csv(CAMINHO_DEFASAGENS), pd.read_csv(CAMINHO_RESUMO)


def em_dia(defas: pd.DataFrame, resumo: pd.DataFrame) -> bool:
    """Compara com o texto gravado, e não com o CSV relido.

    Reler o CSV e comparar DataFrames introduziria diferença onde não há: o
    round-trip muda dtype de coluna com vazio. O que interessa é se o arquivo
    versionado é byte a byte o que o código produz hoje.
    """
    for caminho, tabela in ((CAMINHO_DEFASAGENS, defas), (CAMINHO_RESUMO, resumo)):
        if not caminho.exists() or caminho.read_text(encoding="utf-8") != texto(tabela):
            return False
    return True


def main(argv: list[str] | None = None) -> int:
    import argparse

    parser = argparse.ArgumentParser(
        description="Mede a defasagem do classificador contra a datação do CODACE")
    parser.add_argument("--verificar", action="store_true",
                        help="não grava; reprova se o versionado estiver desatualizado")
    parser.add_argument("--verboso", action="store_true")
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=logging.DEBUG if args.verboso else logging.INFO,
        format="%(asctime)s %(levelname)-7s %(message)s", datefmt="%H:%M:%S",
    )

    defas, resumo = construir()
    if defas.empty:
        log.error("não foi possível validar: camada de regime indisponível")
        return 1

    if args.verificar:
        if not em_dia(defas, resumo):
            log.error("validação desatualizada: rode `ciclo-validar` e versione "
                      "data/derivado/validacao_*.csv")
            return 1
        log.info("validação em dia com a camada de regime")
        return 0

    mudou = salvar(defas, resumo)
    log.info("validação gravada%s", "" if mudou else " (sem alteração)")
    escolhido = resumo[
        (resumo["persistencia"] == regime.MESES_PERSISTENCIA)
        & (resumo["corte_crescimento"] == regime.CORTE_CRESCIMENTO)
    ]
    if not escolhido.empty:
        linha = escolhido.iloc[0]
        log.info("persistência %d: %d/%d recessões detectadas, defasagem mediana "
                 "%+.1f mês no pico e %+.1f no vale, %d episódio(s) fora de recessão",
                 linha["persistencia"], linha["recessoes_detectadas"],
                 linha["recessoes_avaliadas"], linha["defasagem_pico_mediana"],
                 linha["defasagem_vale_mediana"], linha["episodios_fora_de_recessao"])
    log.info("gerado em %s", dt.date.today().isoformat())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
