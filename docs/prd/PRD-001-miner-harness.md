# PRD-001: miner-harness — Sistema de Prospecção Mineral Inteligente

**Status**: APPROVED (revisado pós-Fase 1)
**Autor**: Victor Augusto
**Data**: 2026-05-11
**Fase ASO**: 2 — PRD Executável

---

## Objetivo

Criar um sistema desktop de prospecção mineral que utiliza agentes de IA especializados em geologia e geofísica para analisar dados da base GeoSGB, identificar alvos de exploração e reduzir incerteza na prospecção mineral no Brasil.

## Contexto

O Brasil é subexplorado em profundidade e extremamente fértil tectonicamente. A limitação principal não é potencial geológico, mas sim investimento e integração tecnológica. A base GeoSGB (Serviço Geológico do Brasil) contém dados geológicos, geoquímicos e geofísicos públicos que, quando integrados com IA, podem acelerar significativamente a identificação de alvos minerais.

Atualmente, a análise desses dados é manual, fragmentada e depende de especialistas caros e escassos. Um sistema inteligente que rode localmente — com privacidade de dados e sem dependência de nuvem — democratiza o acesso a análise de prospecção de alto nível.

## Problema

1. Dados geológicos brasileiros (GeoSGB) são subutilizados por falta de ferramentas integradas de análise
2. Prospecção mineral depende de integração multidisciplinar (geologia + geofísica + geoquímica + sensoriamento remoto) que poucos profissionais dominam simultaneamente
3. Não existe ferramenta local, privada, que combine IA com expertise geológica para prospecção mineral
4. Custo de consultoria especializada em prospecção é proibitivo para pequenas mineradoras e prospectores independentes

## Hipótese

Se combinarmos agentes de IA especializados (emulando a expertise de um geólogo exploracionista sênior como Dr. Augusto Valen) com dados públicos da GeoSGB e LLMs rodando localmente, podemos fornecer análise de prospecção mineral de alta qualidade a baixo custo, acessível a qualquer prospector com um computador.

## Escopo

### Incluído
- Integração com base de dados GeoSGB (download, parsing, indexação)
- Agentes especialistas: geólogo estrutural, geofísico, geoquímico, sensoriamento remoto
- Orquestrador de agentes seguindo o framework analítico Dr. Augusto Valen
- LLMs embarcados rodando localmente (sem dependência de API externa)
- Wizard de instalação para download e setup guiado
- Interface de consulta e visualização de resultados
- Análise integrada multi-dados (geologia + geofísica + geoquímica)
- Geração de relatórios de prospecção

### Fora de Escopo
- Processamento de dados de campo em tempo real
- Integração com dados proprietários de empresas [NEEDS CLARIFICATION — considerar para v2?]
- Modelagem 3D geológica completa (pode usar Leapfrog como ferramenta complementar)
- Plataforma web/cloud (o foco é instalação local)
- Venda de dados ou marketplace

## Critérios de Aceitação

1. Usuário consegue instalar o sistema via wizard em < 15 minutos
2. Sistema carrega e indexa dados GeoSGB de pelo menos uma província mineral
3. Agentes conseguem analisar dados e gerar relatório de prospecção integrado
4. LLM roda localmente sem conexão à internet após instalação
5. Análise segue o framework de 5 passos do Dr. Augusto Valen (história tectônica → arquitetura estrutural → fertilidade magmática → evidências indiretas → integração total)
6. Sistema gera mapa de alvos com ranking de prioridade

## Métricas e Baseline

| Métrica | Baseline (sem sistema) | Target |
|---|---|---|
| Tempo para análise regional | 2-4 semanas (manual) | < 1 dia |
| Custo por análise | R$ 50-200k (consultoria) | R$ 0 (após instalação) |
| Cobertura de dados integrados | 1-2 disciplinas | 4-5 disciplinas |
| Acessibilidade | Poucos especialistas | Qualquer prospector |

## Decisões Resolvidas

### Acesso aos Dados GeoSGB — RESOLVIDO
~~`[NEEDS CLARIFICATION]` — Formato e API de acesso aos dados GeoSGB~~

**Decisão**: ArcGIS Server REST API pública (sem autenticação) como acesso primário.
- Base URL: `https://geoportal.sgb.gov.br/server/rest/services`
- 50+ serviços mapeados: geologia, geofísica, geoquímica (FeatureServer + MapServer)
- Retorno em JSON/GeoJSON com filtros espaciais e atributivos
- Secundário: WMS/WFS (OGC) e download de shapefiles via opendata.sgb.gov.br
- Ver ADR completo: [`../adr/ADR-002-geosgb-data-access.md`](../adr/ADR-002-geosgb-data-access.md)

### Licenciamento GeoSGB — RESOLVIDO
~~`[NEEDS CLARIFICATION]` — Licenciamento dos dados GeoSGB para uso em aplicação~~

**Decisão**: Dados são efetivamente de uso livre.
- SGB não possui Plano de Dados Abertos formal (fora do escopo do Decreto 8.777/2016)
- Porém, a Lei de Acesso à Informação (Lei 12.527/2011) garante publicidade dos dados governamentais
- INDE (Decreto 6.666/2008) determina compartilhamento de dados geoespaciais
- SGB disponibiliza tudo via API pública e participa do OneGeology (UNESCO)
- **Requisito**: citar "Dados: Serviço Geológico do Brasil (SGB/CPRM) — GeoSGB"

### Modelos LLM Locais — RESOLVIDO
~~`[NEEDS CLARIFICATION]` — Tamanho dos modelos LLM que rodam em hardware doméstico~~

**Decisão**: Modelos 4B-8B com quantização Q4_K_M como padrão. Revisado na Fase 1 com benchmark geocientífico.

| Modelo | Parâmetros | VRAM (Q4) | Score | Uso no miner-harness |
|---|---|---|---|---|
| Qwen 3 4B | 4B | ~3GB | 7.8/10 | Padrão — melhor PT técnico, thinking mode |
| Qwen 3 8B | 8B | ~5.5GB | 7.4/10 | Intermediário — sweet spot para 8GB VRAM |
| Gemma 3 4B | 4B | ~3GB | 7.3/10 | Alternativa — multimodal (imagens de mapas) |

Estratégia: wizard detecta hardware e recomenda modelo adequado. Arquitetura híbrida possível (SLM local 95% + LLM cloud 5% para consultas complexas, opt-in desabilitado por padrão).

### Requisitos de Hardware — RESOLVIDO
~~`[NEEDS CLARIFICATION]` — Requisitos mínimos de hardware para o usuário final~~

**Hardware de referência (máquina do desenvolvedor)**: Intel Core i5-9600KF @ 3.70GHz · NVIDIA RTX 2070 Super 8GB GDDR6

**Requisitos definidos**:

| Tier | CPU | RAM | GPU | Storage | Modelo LLM |
|---|---|---|---|---|---|
| Mínimo | 4 cores, 3GHz+ | 8GB | Sem GPU (CPU-only) | 20GB livre | Qwen 3 4B (Q4) — 2-5 tok/s |
| Recomendado | 6 cores, 3.5GHz+ | 16GB | 8GB VRAM (RTX 3060) | 50GB livre | Qwen 3 8B (Q4) — 22+ tok/s |
| Premium | 8+ cores | 32GB | 12GB+ VRAM (RTX 4070+) | 100GB livre | Qwen 3 14B (Q4) ou cloud fallback |

CPU-only é viável para modelos 3-4B com Q4 (2-5 tok/s, suficiente para análise não-interativa).

## Pipeline Validado (Fase 1)

```
Entrada: região (bbox) + substância + escala
    │
    ▼
[A] Coleta ─── MapServer/identify (primário) + FeatureServer (gravimetria)
    │
    ▼
[B] Processamento ─── Pydantic models + SQLite/GeoPackage cache + embeddings RAG
    │
    ▼
[C] Agentes (5 passos Dr. Valen)
    ├── 1. História tectônica
    ├── 2. Arquitetura estrutural
    ├── 3. Fertilidade magmática
    ├── 4. Evidências indiretas (limitado na v1 — sem imagens orbitais)
    └── 5. Integração total
    │
    ▼
[D] Validação ─── Evaluator-Optimizer
    │
    ▼
[E] Output ─── Relatório Markdown + GeoPackage para QGIS + mapa Folium (HTML)
```

**Interface**: Textual (CLI interativa) — ver ADR-004.
**Sensoriamento remoto**: escopo reduzido na v1, recomendações textuais — ver ADR-005.
**Região piloto**: Carajás (PA) — 611 ocorrências, bbox -51.5,-7.0,-49.0,-5.0.

## Riscos Atualizados (pós-Fase 1)

| Risco | Severidade | Status | Mitigação |
|---|---|---|---|
| FeatureServer bloqueia queries | Alta | ✅ Confirmado | MapServer/identify como primário |
| Alucinação de LLMs locais em geociência | Alta | Provável | RAG + Evaluator + score confiança |
| Litoestratigrafia timeout | Média | ✅ Confirmado | Download shapefile + cache permanente |
| Sensoriamento remoto ausente no GeoSGB | Média | ✅ Confirmado | v1: recomendações textuais; v2: ESA/NASA |
| API mudar sem aviso | Média | Possível | Testes de contrato + cache + versionamento |
| Rate limiting não documentado | Baixa | ❌ Não detectado | Throttling conservador mantido |

## Correlação

- Persona: [`../personas/dr-augusto-valen.md`](../personas/dr-augusto-valen.md)
- ADR GeoSGB: [`../adr/ADR-002-geosgb-data-access.md`](../adr/ADR-002-geosgb-data-access.md)
- ADR Stack: [`../adr/ADR-001-stack-decision.md`](../adr/ADR-001-stack-decision.md)
- ADR Interface: [`../adr/ADR-004-user-interface.md`](../adr/ADR-004-user-interface.md)
- ADR Sensoriamento: [`../adr/ADR-005-remote-sensing-strategy.md`](../adr/ADR-005-remote-sensing-strategy.md)
- Arquitetura: [`../architecture/system-overview.md`](../architecture/system-overview.md)
- Discovery: [`../architecture/fase-1-discovery-report.md`](../architecture/fase-1-discovery-report.md)
- Templates ASO: `../../entrai-docs/docs/agentic-os/templates/README.md`
- Próximo artefato: RFC de arquitetura técnica → `../rfc/RFC-001-geosgb-connector.md`
