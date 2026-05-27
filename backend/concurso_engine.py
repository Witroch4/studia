"""
Engine de simulação de concorrência em concurso público.

Implementa a lógica das cotas conforme a legislação federal vigente:

- Lei 15.142/2025 + Decreto 12.536/2025 (substituiu a Lei 12.990/2014):
  reserva total de 30% étnico-racial → 25% pretos/pardos, 3% indígenas,
  2% quilombolas.
- Decreto 9.508/2018 / Lei 8.112/90: PCD mínimo 5% (até 20%), em separado.
- Regra do deslocamento: todo cotista concorre também na ampla concorrência;
  se classificado dentro das vagas da ampla, NÃO ocupa vaga reservada — a
  fila da cota "sobe" e outro cotista é convocado em seu lugar.
- Quem se enquadra em mais de uma categoria é classificado na de maior
  percentual (negro > indígena > quilombola).

Módulo puro (somente stdlib) para ser facilmente testável.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Optional


# ─── Modelo de candidato (normalizado) ───────────────────


@dataclass
class Candidato:
    inscricao: str
    cargo: str
    polo: str
    macropolo: str
    pontos: float
    discursiva: float = 0.0
    tot_esp: float = 0.0   # conhecimento específico
    tot_bas: float = 0.0   # conhecimentos básicos
    l_port: float = 0.0    # língua portuguesa (desempate Petrobras)
    l_ing: float = 0.0     # língua inglesa (desempate Petrobras)
    nascimento: Optional[date] = None
    situacao: str = ""
    # Posições declaradas no arquivo (None = não concorre àquela lista)
    pos_ac: Optional[int] = None
    pos_pcd: Optional[int] = None
    pos_pn: Optional[int] = None
    pos_pi: Optional[int] = None
    pos_pq: Optional[int] = None
    extras: dict = field(default_factory=dict)

    @property
    def is_pcd(self) -> bool:
        return self.pos_pcd is not None

    @property
    def is_negro(self) -> bool:
        return self.pos_pn is not None

    @property
    def is_indigena(self) -> bool:
        return self.pos_pi is not None

    @property
    def is_quilombola(self) -> bool:
        return self.pos_pq is not None

    @property
    def cota_principal(self) -> Optional[str]:
        """Categoria de maior percentual em que o candidato se enquadra."""
        if self.is_negro:
            return "PN"
        if self.is_indigena:
            return "PI"
        if self.is_quilombola:
            return "PQ"
        return None


# ─── Configuração da simulação ───────────────────────────


@dataclass
class ConfigCotas:
    total_vagas: int = 10
    fator_cr: float = 3.0  # cadastro de reserva = vagas × fator
    pct_pn: float = 0.25   # pretos e pardos (negros)
    pct_pi: float = 0.03   # indígenas
    pct_pq: float = 0.02   # quilombolas
    pct_pcd: float = 0.05  # pessoas com deficiência
    # Modo de arredondamento por grupo: "MEIO" | "CIMA" | "BAIXO"
    arred_racial: str = "MEIO"   # Lei de cotas: fração ≥ 0,5 sobe
    arred_pcd: str = "CIMA"      # Decreto 9.508: arredonda para cima
    # Reserva étnico-racial só se aplica com nº mínimo de vagas
    limiar_racial: int = 2       # Lei 15.142/2025
    cap_pcd: float = 0.20        # teto legal PCD
    # Critério de classificação:
    #   "PONTOS"     → nota total (padrão CNU); desempate: discursiva, idade
    #   "ESPECIFICO" → só conhecimento específico (padrão Petrobras);
    #                  desempate: português, inglês, idade
    criterio: str = "PONTOS"
    max_esp: float = 40.0        # pontuação máxima da prova específica (= 100%)


def _round(valor: float, modo: str) -> int:
    if valor <= 0:
        return 0
    if modo == "CIMA":
        return math.ceil(valor)
    if modo == "BAIXO":
        return math.floor(valor)
    # MEIO: fração ≥ 0,5 sobe; senão desce
    base = math.floor(valor)
    return base + 1 if (valor - base) >= 0.5 else base


def calcular_distribuicao(cfg: ConfigCotas) -> dict:
    """Distribui o total de vagas entre ampla concorrência e as reservas."""
    total = max(0, int(cfg.total_vagas))

    aplica_racial = total >= cfg.limiar_racial
    n_pn = _round(total * cfg.pct_pn, cfg.arred_racial) if aplica_racial else 0
    n_pi = _round(total * cfg.pct_pi, cfg.arred_racial) if aplica_racial else 0
    n_pq = _round(total * cfg.pct_pq, cfg.arred_racial) if aplica_racial else 0

    n_pcd = _round(total * cfg.pct_pcd, cfg.arred_pcd)
    teto_pcd = math.floor(total * cfg.cap_pcd)
    if teto_pcd >= 1:
        n_pcd = min(n_pcd, teto_pcd)

    # As reservadas nunca podem exceder o total: reduz das menores primeiro
    grupos = {"PN": n_pn, "PI": n_pi, "PQ": n_pq, "PCD": n_pcd}
    while sum(grupos.values()) > total:
        maior = max(grupos, key=lambda k: grupos[k])
        grupos[maior] -= 1
    n_pn, n_pi, n_pq, n_pcd = grupos["PN"], grupos["PI"], grupos["PQ"], grupos["PCD"]

    reservadas = n_pn + n_pi + n_pq + n_pcd
    n_ac = max(0, total - reservadas)

    f = max(1.0, float(cfg.fator_cr))
    return {
        "total": total,
        "aplica_racial": aplica_racial,
        "vagas": {
            "AC": n_ac,
            "PN": n_pn,
            "PI": n_pi,
            "PQ": n_pq,
            "PCD": n_pcd,
        },
        "convocados": {
            "AC": int(round(n_ac * f)),
            "PN": int(round(n_pn * f)),
            "PI": int(round(n_pi * f)),
            "PQ": int(round(n_pq * f)),
            "PCD": int(round(n_pcd * f)),
        },
        "fator_cr": f,
        "reservadas": reservadas,
        "pct_reservado": round((reservadas / total * 100) if total else 0, 1),
    }


def _nota(c: Candidato, cfg: ConfigCotas) -> float:
    """Nota que vale para a classificação, conforme o critério."""
    return c.tot_esp if cfg.criterio == "ESPECIFICO" else c.pontos


def _pct(valor: Optional[float], cfg: ConfigCotas) -> Optional[float]:
    """Percentual da nota (só no critério específico, sobre max_esp)."""
    if valor is None or cfg.criterio != "ESPECIFICO" or cfg.max_esp <= 0:
        return None
    return round(valor / cfg.max_esp * 100, 1)


def _chave(c: Candidato, cfg: ConfigCotas):
    """Ordem de classificação + desempates conforme o critério."""
    nasc = c.nascimento or date(9999, 12, 31)
    if cfg.criterio == "ESPECIFICO":
        # Petrobras: só específica; desempate português, depois inglês, idade
        return (-c.tot_esp, -c.l_port, -c.l_ing, nasc.toordinal(), c.inscricao)
    # CNU/padrão: pontos totais; desempate discursiva, idade
    return (-c.pontos, -c.discursiva, nasc.toordinal(), c.inscricao)


GRUPOS = {
    "PN": ("is_negro", "Pretos e Pardos"),
    "PI": ("is_indigena", "Indígenas"),
    "PQ": ("is_quilombola", "Quilombolas"),
    "PCD": ("is_pcd", "Pessoas com Deficiência"),
}


def simular(candidatos: list[Candidato], cfg: ConfigCotas) -> dict:
    """
    Roda a simulação completa sobre um recorte de candidatos.

    Retorna distribuição de vagas, notas de corte por modalidade,
    estatísticas de deslocamento e a lista classificatória resolvida.
    """
    ordenados = sorted(candidatos, key=lambda c: _chave(c, cfg))
    dist = calcular_distribuicao(cfg)
    f = dist["fator_cr"]

    # Posição na classificação geral (ampla concorrência)
    for i, c in enumerate(ordenados):
        c.extras["_rank_geral"] = i + 1

    convocados_ac = dist["convocados"]["AC"]
    # Quem entra pela ampla concorrência (independente de cota)
    ac_set = set()
    for c in ordenados[:convocados_ac]:
        ac_set.add(id(c))

    nota_corte_ac = (
        _nota(ordenados[convocados_ac - 1], cfg)
        if 0 < convocados_ac <= len(ordenados) else None
    )
    nota_corte_ac_imediata = (
        _nota(ordenados[dist["vagas"]["AC"] - 1], cfg)
        if 0 < dist["vagas"]["AC"] <= len(ordenados) else None
    )

    resultado_grupos = {}
    for sigla, (attr, nome) in GRUPOS.items():
        membros = [c for c in ordenados if getattr(c, attr)]
        # Cotistas aprovados na ampla NÃO ocupam vaga reservada (fila sobe)
        deslocados = [c for c in membros if id(c) in ac_set]
        concorrem_reserva = [c for c in membros if id(c) not in ac_set]

        n_vagas = dist["vagas"][sigla]
        n_conv = dist["convocados"][sigla]
        admitidos = concorrem_reserva[:n_conv]

        nota_corte = (
            _nota(admitidos[-1], cfg)
            if admitidos and n_conv > 0 else None
        )
        nota_corte_imediata = (
            _nota(concorrem_reserva[n_vagas - 1], cfg)
            if 0 < n_vagas <= len(concorrem_reserva) else None
        )

        for pos, c in enumerate(admitidos, 1):
            c.extras[f"_rank_{sigla}"] = pos

        resultado_grupos[sigla] = {
            "sigla": sigla,
            "nome": nome,
            "total_inscritos": len(membros),
            "deslocados_ampla": len(deslocados),
            "concorrem_reserva": len(concorrem_reserva),
            "vagas": n_vagas,
            "convocados": n_conv,
            "preenchidas": len(admitidos),
            "nota_corte": nota_corte,
            "nota_corte_pct": _pct(nota_corte, cfg),
            "nota_corte_imediata": nota_corte_imediata,
            "ultimo_aprovado": _resumo(admitidos[-1]) if admitidos else None,
        }

    # Lista classificatória resolvida (como cada um entrou)
    classificacao = []
    for c in ordenados:
        modo = None
        if id(c) in ac_set:
            modo = "AC"
        else:
            for sigla in ("PN", "PI", "PQ", "PCD"):
                if c.extras.get(f"_rank_{sigla}"):
                    modo = sigla
                    break
        nota = _nota(c, cfg)
        classificacao.append({
            **_resumo(c),
            "rank_geral": c.extras["_rank_geral"],
            "entrou_por": modo,
            "nota": nota,
            "nota_pct": _pct(nota, cfg),
            "is_negro": c.is_negro,
            "is_pcd": c.is_pcd,
            "is_indigena": c.is_indigena,
            "is_quilombola": c.is_quilombola,
        })

    return {
        "distribuicao": dist,
        "criterio": cfg.criterio,
        "max_esp": cfg.max_esp,
        "nota_corte": {
            "AC": nota_corte_ac,
            "AC_imediata": nota_corte_ac_imediata,
            **{s: g["nota_corte"] for s, g in resultado_grupos.items()},
        },
        "nota_corte_pct": {
            "AC": _pct(nota_corte_ac, cfg),
            **{s: g["nota_corte_pct"] for s, g in resultado_grupos.items()},
        },
        "grupos": resultado_grupos,
        "total_candidatos": len(candidatos),
        "classificacao": classificacao,
    }


def simular_pessoal(
    candidatos: list[Candidato],
    cfg: ConfigCotas,
    minha_pontuacao: float,
    minhas_categorias: list[str],
) -> dict:
    """
    E se? Estima a posição do usuário em cada lista pela pontuação.

    O candidato SEMPRE concorre na ampla; e pode acumular várias cotas
    ao mesmo tempo (ex: PCD + negro). O sistema contabiliza cada lista
    selecionada de forma independente.
    """
    res = simular(candidatos, cfg)
    dist = res["distribuicao"]

    p = float(minha_pontuacao)
    a_frente_geral = sum(1 for c in candidatos if _nota(c, cfg) > p)
    pos_ac = a_frente_geral + 1
    conv_ac = dist["convocados"]["AC"]
    passa_ac = pos_ac <= conv_ac if conv_ac else False

    bloco = {
        "pontuacao": p,
        "pontuacao_pct": _pct(p, cfg),
        "categorias": list(minhas_categorias),
        "criterio": cfg.criterio,
        "max_esp": cfg.max_esp,
        "posicao_ac": pos_ac,
        "convocados_ac": conv_ac,
        "passa_ac": passa_ac,
        "nota_corte_ac": res["nota_corte"]["AC"],
        "falta_ac": (
            round(max(0.0, (res["nota_corte"]["AC"] or 0) - p), 2)
            if res["nota_corte"]["AC"] is not None and not passa_ac else 0.0
        ),
    }

    infos = []
    # Mantém a ordem canônica das listas
    for sigla in ("PN", "PI", "PQ", "PCD"):
        if sigla not in minhas_categorias:
            continue
        attr = GRUPOS[sigla][0]
        membros = [c for c in candidatos if getattr(c, attr)]
        a_frente = sum(1 for c in membros if _nota(c, cfg) > p)
        pos_g = a_frente + 1
        conv_g = dist["convocados"][sigla]
        nota_g = res["nota_corte"][sigla]
        infos.append({
            "sigla": sigla,
            "nome": GRUPOS[sigla][1],
            "posicao": pos_g,
            "convocados": conv_g,
            "passa": (pos_g <= conv_g) if conv_g else False,
            "nota_corte": nota_g,
            "falta": (
                round(max(0.0, (nota_g or 0) - p), 2)
                if nota_g is not None and not (conv_g and pos_g <= conv_g) else 0.0
            ),
        })
    bloco["categorias_info"] = infos

    return {"simulacao": bloco, "contexto": res}


def _resumo(c: Candidato) -> dict:
    return {
        "inscricao": c.inscricao,
        "cargo": c.cargo,
        "polo": c.polo,
        "macropolo": c.macropolo,
        "pontos": c.pontos,
        "discursiva": c.discursiva,
        "tot_esp": c.tot_esp,
        "tot_bas": c.tot_bas,
        "l_port": c.l_port,
        "l_ing": c.l_ing,
        "nascimento": c.nascimento.isoformat() if c.nascimento else None,
    }


# ─── Parser de CSV ───────────────────────────────────────


def _to_float(v: str) -> float:
    v = (v or "").strip().replace(",", ".")
    try:
        return float(v)
    except ValueError:
        return 0.0


def _to_pos(v: str) -> Optional[int]:
    v = (v or "").strip()
    if not v:
        return None
    try:
        return int(float(v.replace(",", ".")))
    except ValueError:
        return None


def _to_date(v: str) -> Optional[date]:
    v = (v or "").strip()
    for fmt in ("%d/%m/%Y", "%Y-%m-%d", "%d-%m-%Y"):
        try:
            return datetime.strptime(v, fmt).date()
        except ValueError:
            continue
    return None


def _norm(s: str) -> str:
    return (s or "").strip().upper().replace(" ", "")


def parse_csv(texto: str) -> list[Candidato]:
    """
    Parseia o CSV de concorrência. Mapeia colunas por nome normalizado,
    tolerante a acentos/variações. Espera ao menos PONTOS e AC.
    """
    import csv
    import io

    # Detecta delimitador
    sample = texto[:4096]
    delim = ";" if sample.count(";") > sample.count(",") else ","

    reader = csv.reader(io.StringIO(texto), delimiter=delim)
    rows = [r for r in reader if any(cell.strip() for cell in r)]
    if not rows:
        return []

    header = [_norm(h) for h in rows[0]]

    def idx(*nomes: str) -> Optional[int]:
        for n in nomes:
            n = _norm(n)
            if n in header:
                return header.index(n)
        return None

    i_cargo = idx("CARGO")
    i_polo = idx("POLO", "UF", "ESTADO")
    i_macro = idx("MACROPOLO", "REGIAO", "REGIÃO")
    i_insc = idx("INSCRICAO", "INSCRIÇÃO", "INSC")
    i_nasc = idx("D.NASCIMENTO", "DNASCIMENTO", "NASCIMENTO", "DATANASCIMENTO")
    i_pontos = idx("PONTOS", "TOTAL", "NOTA", "NOTAFINAL")
    i_esp = idx("TOT.ESP.", "TOT.ESP", "TOTESP", "C.ESPEC.", "C.ESPEC",
                "CESPEC", "ESPECIFICA", "ESPECIFICO",
                "CONHECIMENTOESPECIFICO", "CONH.ESPEC.")
    i_bas = idx("TOT.BAS.", "TOT.BAS", "TOTBAS", "BASICOS", "BASICO",
                "CONHECIMENTOSBASICOS")
    i_lport = idx("L.PORT.", "L.PORT", "LPORT", "PORTUGUES", "PORT",
                  "LINGUAPORTUGUESA", "P.PORT.")
    i_ling = idx("L.ING.", "L.ING", "LING", "INGLES",
                 "LINGUAINGLESA", "P.ING.")
    i_disc = idx("DISCURSIVA", "DISC")
    i_sit = idx("SITUACAO", "SITUAÇÃO", "STATUS")
    i_ac = idx("AC", "AMPLA")
    i_pcd = idx("PCD", "PD")
    i_pn = idx("PN", "PPP", "NEGROS", "PRETOS")
    i_pi = idx("PI", "INDIGENA", "INDÍGENA")
    i_pq = idx("PQ", "QUILOMBOLA")

    if i_pontos is None or i_ac is None:
        raise ValueError(
            "CSV inválido: não encontrei as colunas PONTOS e AC. "
            f"Cabeçalho lido: {rows[0]}"
        )

    out: list[Candidato] = []
    for r in rows[1:]:
        if len(r) < len(header):
            r = r + [""] * (len(header) - len(r))

        def cell(i):
            return r[i].strip() if i is not None and i < len(r) else ""

        cand = Candidato(
            inscricao=cell(i_insc) or f"row{len(out)+1}",
            cargo=cell(i_cargo) or "—",
            polo=(cell(i_polo) or "—").upper(),
            macropolo=(cell(i_macro) or "—").upper(),
            pontos=_to_float(cell(i_pontos)),
            discursiva=_to_float(cell(i_disc)),
            tot_esp=_to_float(cell(i_esp)),
            tot_bas=_to_float(cell(i_bas)),
            l_port=_to_float(cell(i_lport)),
            l_ing=_to_float(cell(i_ling)),
            nascimento=_to_date(cell(i_nasc)),
            situacao=cell(i_sit),
            pos_ac=_to_pos(cell(i_ac)),
            pos_pcd=_to_pos(cell(i_pcd)),
            pos_pn=_to_pos(cell(i_pn)),
            pos_pi=_to_pos(cell(i_pi)),
            pos_pq=_to_pos(cell(i_pq)),
        )
        out.append(cand)

    return out
