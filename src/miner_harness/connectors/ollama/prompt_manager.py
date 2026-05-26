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
        "GUIA DE INTERPRETAÇÃO DE TMA (aeromag_grid):\n"
        "- TMA positivo (+100 a +500 nT) → rochas magnéticas (basalto, gabbro, "
        "magnetita, magnetita-magnetite em IOCG) — possível intrusivo ou lâmina máfica\n"
        "- TMA negativo (−100 a −500 nT) → rochas não-magnéticas (granito evoluído, "
        "sedimentos) ou zona de destruição de magnetita (alteração hidrotermal: "
        "cloritização, carbonatação destroem magnetita)\n"
        "- HGM máximo (nT/km) → borda de corpo magnético (contato litológico ou falha)\n"
        "- Gradiente elevado sobre ocorrência mineral → contato controlando mineralização\n"
        "- Anomalia TMA positiva + HGM alto + anomalia Bouguer positiva → intrusivo denso e "
        "magnético (candidato a IOCG ou pórfiro Cu-Au)\n"
        "- Anomalia TMA negativa sobre região com Au orogênico → zona de cisalhamento com "
        "alteração destruiu magnetita (halo de alteração regional)\n\n"
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
        "Quando houver dados Sentinel-2 (sentinel2_indices), use os índices "
        "espectrais quantitativos como evidência primária: NDVI baixo indica "
        "solo alterado/mineralizado; BSI alto indica rocha exposta; Clay Index "
        "alto revela argilominerais (sericita, caolinita); Iron Oxide alto "
        "indica gossã ou cap ferrugíneo sobre sulfetos oxidados. "
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
        "Coordenadas inventadas ou fora da região são INVÁLIDAS.\n"
        "REGRA ESPACIAL: Cada alvo deve estar a pelo menos 15 km de distância dos demais. "
        "Alvos muito próximos (<15 km) indicam incerteza — gere apenas 1 alvo nessa área. "
        "Priorize diversidade geográfica: distribua os alvos pelo bbox em vez de agrupá-los."
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
        "- Profundidade focal indica o nível crustal de deformação atual\n"
        "Se houver derivadas gravimétricas (bouguer_gradient) no contexto:\n"
        "- LINEAMENTOS ESTRUTURAIS INFERIDOS = células com HGM acima do limiar (média+1σ):\n"
        "  máximos de gradiente horizontal coincidem com bordas de corpos e falhas\n"
        "- Correlacione os lineamentos gravimétricos com os lineamentos de outros métodos\n"
        "- HGM elevado sobre ocorrência mineral = contato litológico controlando a mineralização\n"
        "Se houver furos do usuário (user_drillholes) no contexto:\n"
        "- PRIORIDADE MÁXIMA: dados de campo proprietários com litologia e teores reais\n"
        "- Use as coordenadas X/Y para inferir a orientação espacial das estruturas investigadas\n"
        "- Litologia e alteração interceptadas revelam o estilo mineralização e controle estrutural"
    ),
    AnalysisStep.MAGMATIC_FERTILITY: (
        "PASSO 3 — FERTILIDADE MAGMÁTICA\n"
        "Analise dados geoquímicos e geofísicos para fertilidade magmática.\n\n"
        "INTERPRETAÇÃO DAS FONTES:\n"
        "- geoquimica → valores brutos por amostra (quando disponíveis)\n"
        "- geoquimica_normalizada → CF (Fator de Concentração = valor/mediana regional),\n"
        "  anomalias (CF > 2.0) e pathfinders por sistema: USE ESTA ANÁLISE COMO PRIORIDADE\n"
        "- gravimetria → anomalias Bouguer: inferir corpos densos (intrusivos, mineralização)\n"
        "- bouguer_gradient → derivadas gravimétricas calculadas:\n"
        "  ANOMALIAS POSITIVAS = corpos densos (intrusivos, Fe, Cu); "
        "  ANOMALIAS NEGATIVAS = bacias ou granitos evoluídos\n"
        "- aeromag_grid → Anomalia Magnética Total (TMA) e HGM calculados do Atlas SGB:\n"
        "  TMA positivo = rochas magnéticas (máficas, IOCG); "
        "  TMA negativo = granito evoluído ou destruição de magnetita por alteração;\n"
        "  HGM máximo = borda de corpo (contato ou falha); "
        "  correlacione TMA com gravimetria para definir tipo de intrusivo\n"
        "- ocorrencias → tipo e localização das ocorrências: validar assinatura magmática\n"
        "- anm/concessões → fase e substâncias: confirmar mineralização econômica existente\n"
        "- usgs (sismicidade) → cluster sísmico raso próximo a intrusões: magmatismo recente\n\n"
        "Identifique:\n"
        "- Intrusões com assinatura fértil (anomalias de Cu, Au, Mo, etc.)\n"
        "- Anomalias gravimétricas positivas associadas a corpos intrusivos\n"
        "- Anomalias gravimétricas negativas associadas a granitos evoluídos (Sn, W, Li)\n"
        "- Correlação entre TMA (aeromag_grid) e derivadas gravimétricas (bouguer_gradient)\n"
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
        "- geoquimica_normalizada → CF com pathfinders por sistema mineral identificados:\n"
        "  anomalias com CF_máx, intensidade (FORTE/MODERADA/FRACA) e sistema sugerido;\n"
        "  USE como base para identificar halos de alteração e zonas de dispersão\n"
        "- gravimetria + aerogeofisica → anomalias sutis não explicadas por geologia:\n"
        "  inferir corpos mineralizados ou zonas de alteração em profundidade\n"
        "- aeromag_grid → TMA e HGM do Atlas Aerogeofísico SGB: evidência direta de corpos\n"
        "  magnéticos; anomalia TMA negativa em zona de mineralização Au = halo de alteração\n"
        "  (destruição de magnetita); gradiente HGM alto sobre ocorrência = controle estrutural;\n"
        "  correlacione com bouguer_gradient para assinatura geofísica integrada\n"
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
        "- Sismicidade rasa pode indicar sistemas hidrotermais ativos\n"
        "Se houver índices Sentinel-2 (sentinel2_indices) no contexto:\n"
        "- NDVI < 0.2 (alta anomalia) → vegetação inibida: solo alterado/mineralizado, "
        "possível gossã ou cap de óxidos que inibe crescimento vegetal\n"
        "- BSI > 0.1 (alta anomalia) → rocha exposta ou solo alterado sem vegetação: "
        "ideal para mapeamento litológico direto\n"
        "- Clay Index > 1.5 (alta anomalia) → argilominerais (sericita, caolinita, alunita): "
        "halo de alteração argílica/sericítica em sistemas Au-pórfiro ou epitermal\n"
        "- Iron Oxide > 2.0 (alta anomalia) → óxidos de ferro (hematita, goethita): "
        "gossã superficial, cap ferrugíneo — marcador direto de sulfetos oxidados\n"
        "- area_anomalous_pct ≥ 20% = anomalia espectral de alto impacto geoespacial\n"
        "- Correlacione as anomalias espectrais com localização de ocorrências minerais"
    ),
    AnalysisStep.TOTAL_INTEGRATION: (
        "PASSO 5 — INTEGRAÇÃO TOTAL\n"
        "Integre os resultados dos 4 passos anteriores em uma síntese multidisciplinar.\n"
        'OBRIGATÓRIO: gere entre 1 e 5 alvos de prospecção no campo "targets".\n'
        "Para cada alvo:\n"
        "- Use coordenadas reais extraídas dos dados (longitude/latitude WGS84 do Brasil)\n"
        '- Liste as commodities concretas (ex: ["Au", "Cu"], nunca ["Indeterminado"])\n'
        "- NOMEAÇÃO OBRIGATÓRIA: combine uma referência geográfica real da região "
        "(serra, cinturão, bacia, rio, município) com o sistema mineral identificado. "
        "Exemplos corretos: 'Serra Pelada Norte — Ouro Orogênico', "
        "'Cinturão Itacaiúnas SW — IOCG', 'Alto Tapajós — Pórfiro Cu-Au'. "
        "PROIBIDO: 'Alvo 1', 'Alvo Principal', 'Prospecto A', 'Target Norte'.\n"
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
        "Se houver score de prospectividade (prospectivity_score) no contexto:\n"
        "- Use as coordenadas das TOP CÉLULAS como candidatos geoespaciais para alvos\n"
        "- Score ≥ 70 = ALTA prospectividade — priorize alvos nessas células\n"
        "- O score integra: densidade de ocorrências, anomalia Bouguer, anomalias "
        "geoquímicas e proximidade estrutural — é uma síntese quantitativa independente\n"
        "- Alvos do LLM que coincidem com células de alta prospectividade têm maior "
        "confiança; se divergirem, explique o motivo no rationale\n"
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
        "- Correlacione alvos com clusters sísmicos — indicador de permeabilidade crustal\n"
        "Se houver furos do usuário (user_drillholes) no contexto:\n"
        "- EVIDÊNCIA MAIS DIRETA DISPONÍVEL: teores interceptados confirmam mineralização real\n"
        "- Priorize OBRIGATORIAMENTE alvos próximos a furos com teores significativos\n"
        "- Use as coordenadas X/Y dos furos como âncoras geoespaciais para posicionar alvos\n"
        "- Em recommended_followup inclua: 'Aprofundar sondagem além do intercepto mineralizado'\n"
        "Se houver índices Sentinel-2 (sentinel2_indices) no contexto:\n"
        "- Anomalias Iron Oxide + Clay Index co-localizadas com ocorrências = evidência forte\n"
        "- NDVI e BSI anômalos validam que a região tem exposição geológica favorável ao SR\n"
        "- Se area_anomalous_pct ≥ 20% em ≥2 índices: mencione 'assinatura espectral multi-índice' "
        "na síntese e eleve a confiança do alvo correspondente\n"
        "Se houver score ML de prospectividade (ml_prospectivity_score) no contexto:\n"
        "- O RandomForest integra 15 features: geoquímica (CF), gravimetria (HGM), S2 (anomalia%) "
        "e densidade de ocorrências — é uma síntese quantitativa independente do LLM\n"
        "- Score ≥ 70/100 → ALTA probabilidade de mineralização: eleve prioridade dos alvos\n"
        "- Score 45–69/100 → MODERADA: mantenha confiança baseada nas evidências geológicas\n"
        "- Score < 45/100 → BAIXA: justifique os alvos com evidências qualitativas específicas\n"
        "- Cite as top-3 variáveis preditoras listadas pelo RF para contextualizar a decisão\n"
        "- O RF é um modelo semente treinado em dados sintéticos; use como indicador auxiliar, "
        "não como substituto do julgamento geológico"
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
  "data_sources_used": ["ocorrencias", "gravimetria"],
  "data_gaps": ["dado faltante 1", "dado faltante 2"],
  "targets": []
}
Em "data_sources_used", use APENAS os nomes canônicos das fontes disponíveis: \
ocorrencias, gravimetria, geoquimica, geocronologia, litoestratigrafia, aerogeofisica, \
furos, anm, usgs, rag_context, geoquimica_normalizada, prospectivity_grid, \
bouguer_gradient, user_drillholes, sentinel2_indices, ml_prospectivity.
Nos passos 1-4, "targets" deve ser uma lista vazia."""

_RESPONSE_FORMAT_EVALUATOR = """\
Responda OBRIGATORIAMENTE neste formato JSON (sem texto fora do JSON):
{
  "summary": "Síntese multidisciplinar (3-5 frases)",
  "findings": ["Evidência integrada 1", "Evidência integrada 2", ...],
  "confidence": "high|medium|low|insufficient",
  "data_sources_used": ["ocorrencias", "gravimetria", "geoquimica"],
  "data_gaps": ["lacuna 1", "lacuna 2"],
  "targets": [
    {
      "name": "Referência geográfica + sistema mineral (ex: 'Serra Pelada Norte — Ouro Orogênico')",
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
- "mineral_system": IOCG, Ouro Orogênico, Pórfiro Cu-Au, BIF, VMS, Epithermal, etc.
- "name": OBRIGATÓRIO usar referência geográfica real da região + sistema mineral. \
  NUNCA use nomes genéricos como "Alvo 1", "Alvo Principal", "Prospecto A", "Target Norte".
Em "data_sources_used", use APENAS os nomes canônicos: \
ocorrencias, gravimetria, geoquimica, geocronologia, litoestratigrafia, aerogeofisica, \
furos, anm, usgs, rag_context, geoquimica_normalizada, prospectivity_grid, \
bouguer_gradient, user_drillholes, sentinel2_indices, ml_prospectivity."""


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
