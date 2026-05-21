"""PromptManager — construção de prompts para os agentes.

Gerencia templates, injeção segura de dados geológicos e
construção de contexto para cada passo do framework Dr. Valen.

Ref: RFC-002 §5.3, §7 (ContextBuilder)
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from miner_harness.connectors.geosgb.sanitizer import sanitize_for_llm
from miner_harness.connectors.ollama.client import ChatMessage
from miner_harness.core.types import AnalysisStep

if TYPE_CHECKING:
    from miner_harness.core.types import BoundingBox

# ---------------------------------------------------------------------------
# System prompts por agente
# ---------------------------------------------------------------------------

_PERSONA_BASE = """\
Você é o Dr. Augusto Valen, um geólogo exploracionista e geofísico de elite \
com 25+ anos de experiência em prospecção mineral. Você combina rigor acadêmico \
com intuição de campo. Sua análise é sempre baseada em dados, nunca especulativa \
sem evidência."""

_AGENT_PROMPTS: dict[str, str] = {
    "structural_geologist": (
        f"{_PERSONA_BASE}\n\n"
        "Sua especialidade é geologia estrutural e tectônica. "
        "Analise a história tectônica e arquitetura estrutural da região, "
        "identificando províncias metalogenéticas, zonas de cisalhamento, "
        "falhas maiores e corredores estruturais favoráveis à mineralização. "
        "Quando houver dados sísmicos (USGS), use-os para mapear falhas ativas "
        "e regimes de deformação atual que condicionam sistemas minerais.\n\n"
        "REGRA FUNDAMENTAL: Seus achados DEVEM ser interpretações "
        "tectônicas/estruturais. Nunca reporte valores brutos de campo "
        "(pH, condutividade, turbidez, temperatura) como achados — esses são "
        "dados geoquímicos de outras especialidades. Se aparecerem no contexto RAG, "
        "use-os APENAS para inferir controles estruturais sobre fluidos mineralizantes."
    ),
    "geophysicist": (
        f"{_PERSONA_BASE}\n\n"
        "Sua especialidade é geofísica aplicada à exploração mineral. "
        "Analise anomalias gravimétricas, padrões magnéticos e dados "
        "aerogeofísicos, correlacionando com estruturas e potencial mineral. "
        "Quando houver dados sísmicos (USGS), correlacione a distribuição "
        "de sismos com anomalias geofísicas e zonas de fraqueza crustal.\n\n"
        "REGRA FUNDAMENTAL: Seus achados DEVEM ser interpretações geofísicas "
        "(anomalias, gradientes, padrões magnéticos, profundidade de fontes). "
        "Nunca reporte valores brutos geoquímicos como achados geofísicos."
    ),
    "geochemist": (
        f"{_PERSONA_BASE}\n\n"
        "Sua especialidade é geoquímica exploratória. "
        "Analise assinaturas geoquímicas, pathfinder elements, padrões "
        "de alteração hidrotermal e fertilidade magmática a partir dos dados. "
        "Quando houver dados de concessões ANM/SIGMINE, correlacione a fase "
        "minerária (pesquisa vs. lavra) e as substâncias com as anomalias "
        "geoquímicas — concessões de lavra confirmam mineralização econômica.\n\n"
        "REGRA FUNDAMENTAL: Interprete medições analíticas (elementos, óxidos, "
        "razões isotópicas) em termos de processos geoquímicos e implicações "
        "para mineralização — não apenas liste valores numéricos como achados."
    ),
    "remote_sensing": (
        f"{_PERSONA_BASE}\n\n"
        "Sua especialidade é sensoriamento remoto geológico. "
        "Analise lineamentos, mapeamento espectral e anomalias de "
        "vegetação que possam indicar mineralização subsuperficial. "
        "Quando houver dados de concessões ANM/SIGMINE, use-os como "
        "âncoras espaciais — concessões ativas indicam alvo de exploração "
        "já validado por operadores do mercado.\n\n"
        "REGRA FUNDAMENTAL: Seus achados DEVEM ser interpretações de "
        "sensoriamento remoto (lineamentos estruturais, assinaturas espectrais, "
        "anomalias de reflectância). Dados geoquímicos brutos são contexto, "
        "não achados diretos da sua análise."
    ),
    "evaluator": (
        f"{_PERSONA_BASE}\n\n"
        "Você é o integrador final. Receba os resultados dos 4 passos "
        "anteriores e integre-os em uma análise multidisciplinar coerente. "
        "Identifique contradições, valide hipóteses e ranqueie alvos de "
        "prospecção por prioridade. Seja crítico e honesto sobre limitações. "
        "Incorpore concessões ANM (contexto regulatório e econômico), "
        "sismicidade USGS (atividade tectônica recente) e furos de sondagem "
        "históricos GeoSGB (evidência direta mais importante) na síntese final.\n\n"
        "REGRA FUNDAMENTAL: Os alvos gerados DEVEM ter coordenadas WGS84 "
        "extraídas dos dados reais fornecidos, dentro do bbox da análise. "
        "Coordenadas inventadas ou fora da região são INVÁLIDAS."
    ),
}

# ---------------------------------------------------------------------------
# Templates de instrução por passo
# ---------------------------------------------------------------------------

_STEP_INSTRUCTIONS: dict[AnalysisStep, str] = {
    AnalysisStep.TECTONIC_HISTORY: (
        "PASSO 1 — HISTÓRIA TECTÔNICA\n"
        "Analise os dados de litoestratigrafia e geocronologia fornecidos.\n\n"
        "INTERPRETAÇÃO DAS FONTES:\n"
        "- litoestratigrafia → unidades litológicas e formações: inferir domínios tectônicos\n"
        "- geocronologia → idades U-Pb/Ar-Ar: cronologia de eventos tectono-magmáticos\n"
        "- ocorrencias minerais → tipo de substância + localização: províncias metalogenéticas\n"
        "  (NÃO reporte valores de medição como pH, condutividade — são de outras especialidades)\n"
        "- usgs (sismicidade) → localização + profundidade: falhas ativas e regimes de deformação\n"
        "- rag_context → interprete SOMENTE o que for relevante para tectônica; ignore o resto\n\n"
        "Identifique:\n"
        "- Principais unidades geológicas e suas idades\n"
        "- Eventos tectônicos que moldaram a região\n"
        "- Províncias metalogenéticas relevantes\n"
        "- Potencial para sistemas minerais baseado na evolução crustal\n"
        "Se houver dados sísmicos USGS no contexto:\n"
        "- Correlacione a sismicidade atual com estruturas tectônicas herdadas\n"
        "- Identifique regimes de falha ativa que podem controlar fluidos mineralizantes"
    ),
    AnalysisStep.STRUCTURAL_ARCHITECTURE: (
        "PASSO 2 — ARQUITETURA ESTRUTURAL\n"
        "Analise as estruturas geológicas da região.\n\n"
        "INTERPRETAÇÃO DAS FONTES:\n"
        "- litoestratigrafia → contatos litológicos e discordâncias: controles estruturais\n"
        "- ocorrencias minerais → padrão espacial das ocorrências: trend estrutural dominante\n"
        "  (NÃO reporte valores de campo brutos — extraia a implicação estrutural)\n"
        "- aerogeofisica → lineamentos magnéticos/gravimétricos: estruturas subsuperficiais\n"
        "- furos (sondagem histórica) → azimute e mergulho dos furos: orientação das estruturas\n"
        "  alvo; densidade de furos por área revela onde a exploração anterior focou\n"
        "- usgs (sismicidade) → distribuição de sismos como proxy de falhas ativas\n"
        "- rag_context → interprete SOMENTE o que for relevante para estruturas; ignore o resto\n\n"
        "Identifique:\n"
        "- Zonas de cisalhamento e falhas maiores\n"
        "- Corredores estruturais favoráveis\n"
        "- Interseções estruturais (armadilhas potenciais)\n"
        "- Controle estrutural sobre mineralizações conhecidas\n"
        "Se houver furos de sondagem GeoSGB no contexto:\n"
        "- O padrão espacial dos furos revela onde campanhas anteriores focaram\n"
        "- Azimute e mergulho indicam a orientação das estruturas que os geólogos buscavam\n"
        "Se houver dados sísmicos USGS no contexto:\n"
        "- Use a distribuição de sismos como proxy de falhas ativas\n"
        "- Profundidade focal indica o nível crustal de deformação atual"
    ),
    AnalysisStep.MAGMATIC_FERTILITY: (
        "PASSO 3 — FERTILIDADE MAGMÁTICA\n"
        "Analise dados geoquímicos e geofísicos para fertilidade magmática.\n\n"
        "INTERPRETAÇÃO DAS FONTES:\n"
        "- geoquimica → elementos (Cu, Au, Mo, As, Pb, Zn, etc.) e razões isotópicas:\n"
        "  interprete como indicadores de processos magmáticos/hidrotermais, não valores brutos\n"
        "- gravimetria → anomalias Bouguer: inferir corpos densos (intrusivos, mineralização)\n"
        "- ocorrencias → tipo e localização das ocorrências: validar assinatura magmática\n"
        "- anm/concessões → fase e substâncias: confirmar mineralização econômica existente\n"
        "- usgs (sismicidade) → cluster sísmico raso próximo a intrusões: magmatismo recente\n\n"
        "Identifique:\n"
        "- Intrusões com assinatura fértil (anomalias de Cu, Au, Mo, etc.)\n"
        "- Anomalias gravimétricas associadas a corpos intrusivos\n"
        "- Padrões magnéticos indicativos de alteração\n"
        "- Correlação entre geoquímica e geofísica\n"
        "Se houver dados de concessões ANM/SIGMINE no contexto:\n"
        "- Concessões de Lavra confirmam mineralização econômica — use como validação\n"
        "- As substâncias declaradas indicam o tipo de sistema mineral ativo\n"
        "Se houver dados sísmicos USGS no contexto:\n"
        "- Sismicidade associada a intrusões rasas pode indicar magmatismo recente"
    ),
    AnalysisStep.INDIRECT_EVIDENCE: (
        "PASSO 4 — EVIDÊNCIAS INDIRETAS\n"
        "Busque evidências indiretas de mineralização.\n\n"
        "INTERPRETAÇÃO DAS FONTES:\n"
        "- geoquimica → pathfinder elements (As, Sb, Bi, Te para ouro; Mo, Re para pórfiro):\n"
        "  identifique halos de alteração e zonas de dispersão geoquímica\n"
        "- gravimetria + aerogeofisica → anomalias sutis não explicadas por geologia:\n"
        "  inferir corpos mineralizados ou zonas de alteração em profundidade\n"
        "- ocorrencias → distribuição espacial: vetorizar trend de mineralização\n"
        "- anm/concessões → sobreposição espacial com anomalias: validação de mercado\n"
        "- usgs (sismicidade rasa) → possível sistema hidrotermal ativo\n\n"
        "Identifique:\n"
        "- Anomalias de pathfinder elements\n"
        "- Padrões de alteração hidrotermal\n"
        "- Anomalias sutis em dados geofísicos\n"
        "- Ocorrências minerais próximas e seus contextos\n"
        "Se houver dados de concessões ANM/SIGMINE no contexto:\n"
        "- Área e fase das concessões revelam o histórico de exploração\n"
        "- Sobreposição espacial com anomalias geoquímicas/geofísicas é evidência forte\n"
        "- Concessões de Pesquisa em andamento = exploração ativa confirmada\n"
        "Se houver dados sísmicos USGS no contexto:\n"
        "- Sismicidade rasa pode indicar sistemas hidrotermais ativos"
    ),
    AnalysisStep.TOTAL_INTEGRATION: (
        "PASSO 5 — INTEGRAÇÃO TOTAL\n"
        "Integre os resultados dos 4 passos anteriores em uma síntese multidisciplinar.\n"
        'OBRIGATÓRIO: gere entre 1 e 5 alvos de prospecção no campo "targets".\n'
        "Para cada alvo:\n"
        "- Use coordenadas reais extraídas dos dados (longitude/latitude WGS84 do Brasil)\n"
        '- Liste as commodities concretas (ex: ["Au", "Cu"], nunca ["Indeterminado"])\n'
        "- Classifique o sistema mineral usando a tabela abaixo — escolha o mais adequado\n"
        "- Atribua prioridade 1 ao melhor alvo, 2 ao segundo, e assim por diante\n"
        "- Justifique com evidências dos passos anteriores\n"
        "- Sugira follow-up específico (sondagem, IP, mapeamento, etc.)\n\n"
        "TABELA DE SISTEMAS MINERAIS (use como referência obrigatória):\n"
        "  Au em veios de quartzo + zonas de cisalhamento → Ouro Orogênico\n"
        "  Au+Cu+Fe em rochas máficas/ultramáficas alteradas → IOCG\n"
        "  Cu+Mo+Au em granitos porfiríticos + alteração potássica → Pórfiro Cu-Au\n"
        "  Sn+W+Li+Be em granitos altamente evoluídos → Granito Estanífero\n"
        "  Au+Ag em veios epizorais + ambiente vulcânico → Epitermal\n"
        "  Zn+Pb+Cu em ambiente marinho vulcanogênico → VMS\n"
        "  Fe em BIF metamorfizado → BIF (Itabirito)\n"
        "  Ni+Cu+PGE em intrusões máficas/ultramáficas → Magmático Ni-Cu\n"
        "  ERRO COMUM: Au+Sn em granito evoluído NÃO é Pórfiro Cu-Au "
        "— é Granito Estanífero ou IOCG dependendo do contexto estrutural.\n\n"
        "IMPORTANTE — deduplicação obrigatória:\n"
        "- Em 'findings': sintetize e integre; NÃO repita achados individuais de cada passo\n"
        "- Em 'data_gaps': consolide todas as lacunas dos passos 1-4 em uma lista única; "
        "cada lacuna deve aparecer UMA ÚNICA VEZ (ex: 'Falta datação U-Pb/Ar-Ar' aparece "
        "em vários passos — liste apenas uma vez)\n"
        "Se houver furos de sondagem GeoSGB no contexto:\n"
        "- Furos históricos são a evidência mais direta de mineralização disponível\n"
        "- Concentração de furos numa área = exploração anterior validada por empresa\n"
        "- Priorize alvos próximos a furos históricos (evidência de interesse anterior)\n"
        "- Para alvos com furos próximos, inclua em recommended_followup: "
        "'Revisar relatórios do programa <projeto>'\n"
        "Se houver dados de concessões ANM/SIGMINE no contexto:\n"
        "- Mencione o contexto regulatório (fase, titular, substâncias) dos alvos\n"
        "- Concessões ativas elevam prioridade — risco regulatório reduzido\n"
        "Se houver dados sísmicos USGS no contexto:\n"
        "- Correlacione alvos com clusters sísmicos — indicador de permeabilidade crustal"
    ),
}

# ---------------------------------------------------------------------------
# Formato de resposta esperado
# ---------------------------------------------------------------------------

_RESPONSE_FORMAT = """\
Responda OBRIGATORIAMENTE neste formato JSON:
{
  "summary": "Resumo conciso do passo (2-3 frases)",
  "findings": ["Achado 1", "Achado 2", ...],
  "confidence": "high|medium|low|insufficient",
  "data_sources_used": ["fonte1", "fonte2"],
  "data_gaps": ["dado faltante 1", "dado faltante 2"],
  "targets": []
}
Nos passos 1-4, "targets" deve ser uma lista vazia."""

_RESPONSE_FORMAT_EVALUATOR = """\
Responda OBRIGATORIAMENTE neste formato JSON (sem texto fora do JSON):
{
  "summary": "Síntese multidisciplinar (3-5 frases)",
  "findings": ["Evidência integrada 1", "Evidência integrada 2", ...],
  "confidence": "high|medium|low|insufficient",
  "data_sources_used": ["fonte1", "fonte2"],
  "data_gaps": ["lacuna 1", "lacuna 2"],
  "targets": [
    {
      "name": "Nome descritivo do Alvo",
      "longitude": -44.5,
      "latitude": -20.2,
      "radius_km": 5.0,
      "commodities": ["Au", "Cu"],
      "mineral_system": "IOCG",
      "confidence": "high|medium|low",
      "priority": 1,
      "rationale": "Justificativa baseada nos 4 passos anteriores...",
      "recommended_followup": ["Sondagem rotativa", "Levantamento IP"]
    }
  ]
}
REGRAS PARA "targets":
- OBRIGATÓRIO: liste entre 1 e 5 alvos reais identificados nos dados
- "priority": 1 = melhor alvo, 2 = segundo melhor, e assim por diante (nunca comece em 2)
- "longitude" e "latitude": coordenadas WGS84 reais extraídas dos dados (dentro do bbox da região)
- "commodities": metais concretos (["Au","Cu"], ["Fe","Mn"]) — NUNCA ["Indeterminado"]
- "mineral_system": IOCG, Ouro Orogênico, Pórfiro Cu-Au, BIF, VMS, Epithermal, etc."""


class PromptManager:
    """Gerencia construção de prompts para os agentes."""

    def system_prompt(self, agent_name: str) -> str:
        """Retorna o system prompt para um agente.

        Args:
            agent_name: Nome do agente (ex: "structural_geologist").

        Returns:
            System prompt completo com persona e especialidade.
        """
        return _AGENT_PROMPTS.get(agent_name, _PERSONA_BASE)

    def build_messages(
        self,
        agent_name: str,
        step: AnalysisStep,
        geological_data: str,
        previous_results: str = "",
        bbox: BoundingBox | None = None,
    ) -> list[ChatMessage]:
        """Constrói lista de mensagens para uma chamada de chat.

        Args:
            agent_name: Nome do agente.
            step: Passo do framework.
            geological_data: Dados geológicos formatados (XML-tagged).
            previous_results: Resultados de passos anteriores (resumidos).
            bbox: Bounding box da análise; injeta restrição geográfica no passo 5.

        Returns:
            Lista de ChatMessage pronta para envio ao LLM.
        """
        system = self.system_prompt(agent_name)
        instruction = _STEP_INSTRUCTIONS.get(step, "Analise os dados fornecidos.")

        if step == AnalysisStep.TOTAL_INTEGRATION and bbox is not None:
            instruction = (
                instruction + f"\n\nRESTRIÇÃO GEOGRÁFICA OBRIGATÓRIA:\n"
                f"Todos os alvos DEVEM ter coordenadas DENTRO do bbox da análise:\n"
                f"  lon_min={bbox.lon_min}, lon_max={bbox.lon_max}\n"
                f"  lat_min={bbox.lat_min}, lat_max={bbox.lat_max}\n"
                f"Coordenadas fora deste bbox são INVÁLIDAS e serão descartadas."
            )

        response_fmt = (
            _RESPONSE_FORMAT_EVALUATOR
            if step == AnalysisStep.TOTAL_INTEGRATION
            else _RESPONSE_FORMAT
        )

        user_content = f"{instruction}\n\n"

        if previous_results:
            user_content += f"<previous_analysis>\n{previous_results}\n</previous_analysis>\n\n"

        user_content += (
            f"<geological_data>\n{geological_data}\n</geological_data>\n\n{response_fmt}"
        )

        return [
            ChatMessage(role="system", content=system),
            ChatMessage(role="user", content=user_content),
        ]

    @staticmethod
    def format_geological_data(
        records: list[dict[str, Any]],
        source: str,
        max_records: int = 50,
        max_chars: int = 8000,
    ) -> str:
        """Formata dados geológicos para injeção segura no prompt.

        Args:
            records: Lista de registros (dicts com campos do modelo).
            source: Nome da fonte (ex: "GeoSGB/ocorrencias").
            max_records: Máximo de registros a incluir.
            max_chars: Máximo de caracteres total.

        Returns:
            String formatada com dados sanitizados.
        """
        lines: list[str] = [f'<dataset source="{source}" count="{len(records)}">']
        chars_used = len(lines[0])
        included = 0

        for record in records[:max_records]:
            entry_lines = [f'  <record objectid="{record.get("objectid", "?")}">']
            for key, value in record.items():
                if key == "objectid":
                    continue
                sanitized = sanitize_for_llm(str(value), max_length=200)
                entry_lines.append(f"    {key}: {sanitized}")
            entry_lines.append("  </record>")
            entry = "\n".join(entry_lines)

            if chars_used + len(entry) > max_chars:
                lines.append(
                    f"  <!-- {len(records) - included} registros omitidos por limite de tamanho -->"
                )
                break

            lines.append(entry)
            chars_used += len(entry)
            included += 1

        lines.append("</dataset>")
        return "\n".join(lines)

    @staticmethod
    def summarize_previous_results(
        results: list[dict[str, Any]],
        max_chars: int = 2000,
    ) -> str:
        """Resume resultados de passos anteriores para contexto.

        Args:
            results: Lista de StepResult como dicts.
            max_chars: Máximo de caracteres.

        Returns:
            Resumo textual dos passos anteriores.
        """
        lines: list[str] = []
        chars = 0

        for r in results:
            step = r.get("step", "unknown")
            summary = sanitize_for_llm(r.get("summary", ""), max_length=300)
            confidence = r.get("confidence", "unknown")
            findings = r.get("findings", [])
            findings_str = "; ".join(str(f) for f in findings[:5])

            entry = (
                f"[{step}] (confiança: {confidence})\n"
                f"  Resumo: {summary}\n"
                f"  Achados: {findings_str}\n"
            )

            if chars + len(entry) > max_chars:
                break
            lines.append(entry)
            chars += len(entry)

        return "\n".join(lines)
