# Briefing de Crítica Especializada — miner-harness v0.5.23
**Data**: 2026-05-21
**Propósito**: Base para avaliação por geólogo exploracionista especialista

---

## O que o sistema faz hoje (v0.5.23)

### Fontes integradas
| Fonte | Conteúdo | Limitação |
|---|---|---|
| GeoSGB/Ocorrências | 36 campos por ponto | Sem geometria de corpo mineralizado |
| GeoSGB/Gravimetria | Anomalia Bouguer + ar livre | Sem inversão; densidade irregular |
| GeoSGB/Geoquímica | 51 campos analíticos, 9 layers | Sem normalização; sem razões isotópicas |
| GeoSGB/Geocronologia | U-Pb, Ar-Ar, idade Ma | Sparse; sem interpretação petrogenética |
| GeoSGB/Litoestratigrafia | Polígonos de formações | Escala 1:1.000.000 |
| GeoSGB/Aerogeofísica | **Apenas metadados** de projetos | Sem dados de grid |
| ANM/SIGMINE | Concessões: fase, titular, área | Sem dados técnicos da pesquisa |
| USGS Earthquakes | Magnitude, profundidade | Proxy fraco para Brasil cratônico |

### Pipeline
5 passos LLM (qwen3:8b local) → dashboard HTML com Leaflet + alvos ranqueados

---

## Gaps identificados vs. workflow profissional real

### GAP 1 — Geofísica sem dados (CRÍTICA)
Profissional: processa grids (RTP, Sinal Analítico, K/eTh, Euler). Sistema: LLM interpreta metadados (nome do projeto, ano, área km²).

### GAP 2 — Geoquímica sem normalização (ALTA)
Profissional: CF = valor/mediana_regional, PCA, pathfinder por sistema mineral. Sistema: valores brutos como texto XML ao LLM.

### GAP 3 — Sem sensoriamento remoto processado (ALTA)
Profissional: ASTER bandas 4/6/7 para alteração; SAR/LiDAR para lineamentos. Sistema: recomendações textuais (ADR-005).

### GAP 4 — Sem furos históricos (MÉDIA)
Profissional: cruza superfície com furos existentes. Sistema: endpoint `furos_sondagem` do GeoSGB não integrado.

### GAP 5 — Sem exportação GIS (MÉDIA)
Profissional: continua análise em QGIS, ArcGIS, Leapfrog. Sistema: output apenas HTML; nenhum GeoPackage/Shapefile.

### GAP 6 — Score de prospectividade não-auditável (MÉDIA)
Profissional: weighted overlay GIS ou Random Forest com pesos explícitos. Sistema: ranking subjetivo do EvaluatorAgent.

### GAP 7 — Confiança mal calibrada (MÉDIA)
Profissional: confiança reflete densidade e qualidade de dados. Sistema: `high/medium/low` autodeclarado pelo LLM.

### GAP 8 — Escala inadequada para campo (SITUACIONAL)
Litoestratigrafia a 1:1.000.000; alvos com radius_km 5–15. Não é escala de furo, é escala de reconhecimento regional.

---

## Perguntas que o especialista fará ao usar o sistema

1. "Qual anomalia magnética justifica esse alvo?" — Sistema não tem resposta quantitativa
2. "Qual é o background regional de Cu nesta Província?" — Não calculado
3. "Que razão K/eTh esse levantamento mostra sobre o alvo?" — Grid não está no sistema
4. "Que furos históricos existem na área?" — Endpoint GeoSGB não ativado
5. "Que lineamentos de Sentinel-2 confirmam essa zona de cisalhamento?" — Não processado
6. "Como vocês calcularam a prioridade 1 vs 2?" — Julgamento do LLM, sem score numérico
7. "Em que escala posso confiar para planejar campo?" — Regional (1:100.000–1:250.000)
8. "Posso exportar para QGIS?" — Não; apenas HTML

---

## Posicionamento atual

O sistema é equivalente a um **relatório de due diligence inicial de dados públicos com IA** — útil para triagem de áreas candidatas antes de contratar levantamento aerogeofísico dedicado ou comprar pacote de dados privados. Não substitui nenhum estágio subsequente da exploração.

→ PRD-002 define o roadmap para elevar o sistema ao nível de ferramenta analítica real.
