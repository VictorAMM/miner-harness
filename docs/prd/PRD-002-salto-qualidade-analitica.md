# PRD-002: miner-harness — Salto de Qualidade Analítica (v0.6–v1.0)

**Status**: DRAFT
**Autor**: Victor Augusto
**Data**: 2026-05-21
**Fase ASO**: 2 — PRD Executável
**Versão de entrada**: v0.5.23
**Versão-alvo**: v1.0

---

## Objetivo

Elevar o miner-harness do nível de **compilador de dados públicos com IA** para o nível de **ferramenta analítica quantitativa** que um geólogo exploracionista profissional reconhece como útil no seu workflow real de geração de alvos (Estágio 1 da exploração mineral).

## Contexto e Motivação

O PRD-001 definiu o sistema como prova de conceito funcional que integra dados GeoSGB com agentes LLM. O v0.5.23 cumpriu esse objetivo: o sistema roda localmente, integra 8 fontes de dados, gera alvos ranqueados e exibe um dashboard HTML interativo.

Uma análise crítica realizada em 2026-05-21 — embasada no fluxo de trabalho profissional de geólogos exploracionistas, em vagas abertas do mercado (Centerra Gold, LXML Sepon, KoBold Metals, New Pacific Metals) e em metodologias de referência (Geoscience Australia mineral systems approach, SEG, AusIMM) — identificou gaps estruturais que limitam a credibilidade do sistema perante um especialista:

| Gap | Severidade | Impacto |
|---|---|---|
| LLM interpreta geofísica sem ver nenhum dado geofísico real (só metadados) | CRÍTICA | Agente geofísico gera texto sem fundamento quantitativo |
| Geoquímica sem normalização — valores brutos sem background regional | ALTA | Impossível distinguir anomalia de variação litológica |
| Sensoriamento remoto apenas recomendações textuais (ADR-005) | ALTA | Passo 4 sub-alimentado; evidências indiretas incompletas |
| Alvos sem score quantitativo rastreável | MÉDIA | Priorização não-reprodutível; ranking subjetivo do LLM |
| Nenhuma exportação para ferramentas profissionais (QGIS, ArcGIS) | MÉDIA | Geólogo não consegue continuar o trabalho em seu toolset |
| Sem dados de furos históricos (GeoSGB tem endpoint `furos_sondagem`) | MÉDIA | Ignora evidência mais direta para áreas com histórico |
| Confiança do LLM não calibrada contra densidade de dados | MÉDIA | Badge `low/medium/high` sem base estatística |

Este PRD define o roadmap para fechar esses gaps em ciclos de entrega incrementais.

## Problema (versão atualizada)

1. Os agentes LLM interpretam geofísica sem processar nenhum dado geofísico — o agente `geophysicist` nunca viu um valor de campo magnético ou Bouguer; apenas metadados de projetos
2. A geoquímica chega ao LLM como valores absolutos sem contexto de background regional — `Cu=45 ppm` não significa nada sem saber se o background da região é 20 ou 80 ppm
3. O sistema não produz output consumível pelo toolset padrão da indústria — um geólogo não consegue abrir os alvos diretamente no QGIS ou Leapfrog
4. A análise de prospectividade é textual e não-reprodutível — dois analistas com os mesmos dados podem obter rankings diferentes; não há score auditável
5. Furos de sondagem históricos existem no GeoSGB mas não são integrados — são a evidência mais direta de mineralização disponível

## Hipótese

Se adicionarmos camadas de processamento **quantitativo** entre os dados brutos e os agentes LLM — normalização geoquímica, derivadas geofísicas calculadas, score de prospectividade por weighted overlay, exportação GIS e integração de furos históricos — o sistema passará de "assistente de pesquisa bibliográfica geológica" para "ferramenta analítica de geração de alvos que complementa o workflow profissional".

## Escopo

### Incluído neste PRD

#### v0.6 — Fundação Quantitativa

**F1 — Exportação GIS** (P0, esforço baixo, valor alto)
- Exportar alvos em GeoJSON (nativo) e GeoPackage (com camadas de ocorrências, gravimetria, targets)
- Comando CLI: `miner analyze ... --output-gis targets.gpkg`
- Compatível com QGIS, ArcGIS, geopandas
- Cada alvo como polígono de buffer (`radius_km`) + ponto central + todos os atributos do `MineralTarget`

**F2 — Normalização geoquímica regional** (P0, esforço médio, valor alto)
- Calcular background regional (mediana + MAD) dos elementos analíticos usando os próprios dados do bbox expandido (1.5× área)
- Calcular fator de concentração (CF = valor / mediana_regional) para elementos-chave
- Definir threshold automático de anomalia (CF > 2× ou percentil > 90%) por elemento
- Destacar pathfinder elements por sistema mineral candidato (Au→As,Sb,Bi,Te; Cu pórfiro→Mo,Re; IOCG→Cu,Co,U; Ni-Cu→Ni,Cr,Co)
- Injetar no prompt do `GeochemistAgent`: dados normalizados, CFs calculados, lista de anomalias reais — não valores brutos

**F3 — Score quantitativo de prospectividade** (P0, esforço médio, valor alto)
- Calcular weighted overlay score para cada célula de 1 km² do bbox, baseado em:
  - Densidade de ocorrências minerais (peso configurável)
  - Anomalia Bouguer normalizada (peso configurável)
  - Densidade de anomalias geoquímicas (CF > threshold)
  - Proximidade a lineamentos estruturais conhecidos (distância inversa)
- Score final de 0–100 por célula; top-N células como candidatos a alvo
- O `EvaluatorAgent` recebe o mapa de score como dado adicional, não apenas texto dos agentes anteriores
- Dashboard: camada de heatmap de prospectividade no Leaflet

**F4 — Integração de furos históricos GeoSGB** (P1, esforço médio, valor alto)
- Endpoint `furos_sondagem` do GeoSGB já mapeado no ADR-002 — ativar coleta via MapServer/identify
- Modelo `FuroSondagem`: objectid, projeto, profundidade, azimute, mergulho, coordenada, resultados
- Exibir furos no mapa (marcadores cilíndricos) com popup de resultado
- Injetar dados de furos no `StructuralGeoAgent` (Passo 2) e `EvaluatorAgent` (Passo 5)
- Novo campo em `MineralTarget.recommended_followup`: sugestão contextualizada com base em furos próximos

#### v0.7 — Geofísica Real

**F5 — Download de grids aerogeofísicos SGB** (P1, esforço alto, valor crítico)
- Identificar e baixar grids de magnetometria total e gamaespectrometria (K, Th, U) do SGB para bbox solicitado
  - Os projetos já estão mapeados (atlas aerogeofísico no dashboard); o dado existe no portal SGB
  - Investigar endpoints de download de arquivo via `aerogeofisica` ou link direto no metadado do projeto
- Processar grids com `rasterio` + `numpy`:
  - Calcular **Sinal Analítico** da magnetometria (delinear bordas de corpos)
  - Calcular **Razão K/eTh** (anomalia de K relativo — indicador de alteração potássica)
  - Calcular **Razão eTh/eU** (discriminar alteração vs. litologia background)
  - Calcular **Gradiente Horizontal Total** (mapear contatos e falhas)
- Injetar derivadas calculadas (não o grid bruto) no prompt do `GeophysicistAgent`: "Sinal analítico mostra anomalia de 0.08 nT/m centrada em (-50.2, -6.1); K/eTh = 1.8 (fundo = 0.9)"
- Dashboard: camada de sinal analítico e K/eTh como overlay raster no Leaflet

**F6 — Sensoriamento remoto básico (ADR-005 v2)** (P1, esforço alto, valor alto)
- Integração com ESA Copernicus Data Space (Sentinel-2, gratuito, API pública)
- Download de cena Sentinel-2 L2A para bbox (banda 8A, 11, 12 para SWIR)
- Calcular índice de alteração argilítica: SWIR1/SWIR2 (bandas 11/12)
- Calcular índice de lineamentos via filtro Sobel em banda pancromática
- Armazenamento local em GeoTIFF (~50–200 MB por cena)
- Injetar análise no `RemoteSensingAgent`: "Índice argilítico elevado (0.72, fundo=0.45) em 3 km²; lineamentos NE-SW com 4 ocorrências na interseção"
- Dashboard: overlay do índice de alteração no mapa

#### v1.0 — Integração com Dados Proprietários e ML

**F7 — Ingestão de dados de sondagem do usuário** (P2, esforço médio, valor alto)
- Formato de entrada: CSV com colunas `hole_id, x, y, z, from_m, to_m, lithology, alteration, [elementos analíticos]`
- Comandos CLI: `miner index drillholes arquivo.csv` / `miner analyze ... --drillholes arquivo.csv`
- Integração no ContextBuilder: furos do usuário têm precedência sobre dados GeoSGB
- Dashboard: seção "Dados do Usuário" separada de dados públicos; furos exibidos no mapa
- Dados ficam apenas locais; nunca enviados a nenhuma API

**F8 — Modelo de prospectividade com ML** (P2, esforço médio, valor alto)
- Random Forest treinado em dados sintéticos de sistemas minerais conhecidos do Brasil
  - Features: densidade de ocorrências, anomalias Bouguer, CF geoquímico, distância a lineamentos, sinal analítico mag, K/eTh
  - Labels: sistema mineral confirmado (IOCG, Ouro Orogênico, Pórfiro, etc.) por célula 1 km²
- Modelo serializado (joblib) embarcado no pacote (sem treinamento em tempo de execução)
- Substituir/complementar weighted overlay do F3 com probabilidade por classe de sistema mineral
- Dashboard: "Probabilidade de sistema mineral por célula" como layer extra

**F9 — Exportação de relatório técnico** (P2, esforço baixo, valor médio)
- Gerar PDF ou DOCX estruturado com: sumário executivo, tabela de alvos, mapa estático (PNG), justificativa por alvo, data gaps, referências de dados
- Formato compatível com relatórios JORC-preliminares e due diligence
- Ferramenta: `weasyprint` (PDF) ou `python-docx`

### Fora de Escopo neste PRD

- Estimativa de recursos (JORC/NI43-101) — requer dados de sondagem de definição
- Modelagem 3D geológica de corpos (Leapfrog, GOCAD) — fora do paradigma local/Python
- Aquisição de dados proprietários de empresas
- Interface web/cloud
- Dados de IP/resistividade (nenhuma fonte pública disponível)
- Integração ASTER/TIR (bandas térmicas requerem download de cenas completas ~700 MB)

## Critérios de Aceitação

### v0.6
1. `miner analyze ... --output-gis targets.gpkg` gera GeoPackage abrível no QGIS com camadas: `targets`, `ocorrencias`, `gravimetria`
2. O agente `GeochemistAgent` recebe — por passo 3 e 4 — uma tabela de elementos com CF calculado e flag de anomalia, não apenas valores brutos
3. O dashboard exibe uma camada de heatmap de prospectividade (score 0–100) sobreposta ao mapa de alvos
4. Furos GeoSGB aparecem no mapa e são mencionados no `EvaluatorAgent` quando existem dentro do bbox

### v0.7
5. Para ao menos um projeto aerogeofísico dentro do bbox, o sistema baixa e processa o grid de magnetometria, calculando Sinal Analítico e K/eTh — os valores calculados aparecem no prompt do `GeophysicistAgent`
6. O `RemoteSensingAgent` recebe índice de alteração argilítica calculado de cena Sentinel-2 real — não mais apenas recomendações textuais
7. O campo `confidence` dos passos 3, 4 e 5 reflete a cobertura de dados calculados vs. apenas texto: `high` somente quando geofísica processada E geoquímica normalizada estão disponíveis

### v1.0
8. Usuário pode ingerir CSV de furos próprios e vê-los integrados na análise e no mapa
9. O mapa de prospectividade mostra probabilidade por classe de sistema mineral (Random Forest), não apenas score por weighted overlay
10. Sistema gera relatório técnico em PDF/DOCX com mapa estático e tabela de alvos

## Métricas e Baseline

| Métrica | Baseline v0.5.23 | Target v0.6 | Target v1.0 |
|---|---|---|---|
| Dados quantitativos injetados no `GeochemistAgent` | 0% (valores brutos) | 100% (CF + anomalias) | 100% |
| Dados quantitativos no `GeophysicistAgent` | 0% (apenas metadados) | 0% | 100% (derivadas calculadas) |
| Output exportável para GIS | Não | GeoPackage | GeoPackage + PDF/DOCX |
| Score de prospectividade auditável | Não | Weighted overlay | ML (Random Forest) |
| Furos históricos integrados | Não | GeoSGB (público) | GeoSGB + dados do usuário |
| Confiança calibrada por cobertura | Subjetiva (LLM) | Semi-calibrada | Calibrada por métrica de cobertura |

## Plano de Releases

### v0.6.x — Fundação Quantitativa
```
v0.6.0 — F1 (Exportação GIS) + F4 (Furos GeoSGB)
v0.6.1 — F2 (Normalização geoquímica)
v0.6.2 — F3 (Score de prospectividade + heatmap no dashboard)
```

### v0.7.x — Geofísica Real
```
v0.7.0 — F5 (Download + processamento de grids aerogeofísicos)
v0.7.1 — F6 (Sentinel-2 + índice de alteração)
v0.7.2 — Recalibração de confiança com cobertura de dados
```

### v1.0 — Integração Completa
```
v0.9.0 — F7 (Ingestão de furos do usuário)
v0.9.1 — F8 (Modelo de prospectividade ML)
v1.0.0 — F9 (Relatório técnico PDF/DOCX) + estabilização + documentação
```

## Decisões em Aberto

### Download de Grids Aerogeofísicos SGB — `[NEEDS CLARIFICATION]`
O ADR-002 registra o endpoint `aerogeofisica` como `FS timeout, MS info ok`. Os grids de dados em si não estão na API REST — são arquivos binários (`.grd`, `.ers`, `.xyz`) hospedados no portal. É necessário investigar:
- O link de download de arquivo está disponível nos metadados do projeto via MapServer/identify?
- Os grids estão disponíveis via FTP/HTTP direto no portal SGB?
- Há parceria ou convênio necessário?
→ Bloqueia F5. Investigar antes de iniciar v0.7.

### Cobertura de Sentinel-2 no Brasil — `[NEEDS CLARIFICATION]`
- Qual a revisita do Sentinel-2 sobre biomas tropicais com cobertura de nuvem? (Amazônia: alta cobertura)
- O Copernicus Data Space tem cobertura completa do Brasil histórica?
- Tamanho típico de cena L2A para bbox 2°×2°? (estimativa: 200–500 MB)
→ Avaliar antes de comprometer armazenamento no wizard para v0.7.

### Modelo ML de Prospectividade — `[NEEDS CLARIFICATION]`
- Existem datasets de treinamento de qualidade para sistemas minerais brasileiros conhecidos?
  - GeoSGB tem dados de depósitos confirmados que podem servir como labels positivos?
  - Usar MRDS (USGS) com coordenadas brasileiras?
- Risco: modelo treinado em depósitos conhecidos pode ter viés de confirmação (só "aprende" a reconhecer o que já é conhecido)
→ Avaliar antes de F8.

## Riscos

| Risco | Severidade | Mitigação |
|---|---|---|
| Grids aerogeofísicos não disponíveis via download automatizado | Alta | F5 depende de investigação prévia; fallback = processamento de WMS rasterizado (qualidade menor) |
| Cobertura de nuvem impede uso de Sentinel-2 na Amazônia | Alta | Composites temporais (múltiplas cenas); fallback = Landsat-8 com menor resolução |
| Background geoquímico calculado sobre dados escassos no bbox | Média | Usar bbox expandido para background; flag quando n < 30 amostras |
| Modelo ML com baixa generalização para novas regiões | Média | Ensemble com weighted overlay determinístico como fallback |
| Processamento raster aumenta requisitos de storage (50–200 GB para uso intenso) | Média | TTL por cena (90 dias); limpeza automática; documentar no wizard |
| Mudança da API Copernicus (ESA) | Baixa | Abstrair em connector dedicado; pin de versão da API |

## Posicionamento Revisado do Sistema (pós-v1.0)

```
NÍVEL DE MATURIDADE DA EXPLORAÇÃO:

Reconhecimento Regional
(1:500.000 – 1:250.000)
  │
  ▼
Prospecção Regional ◄──── miner-harness v1.0 opera aqui plenamente
(1:100.000 – 1:50.000)     (geofísica processada + geoquímica normalizada
  │                         + RS orbital + prospectividade ML)
  ▼
Prospecção Local
(1:25.000 – 1:10.000)      ◄── miner-harness suporta com dados do usuário (F7)
  │
  ▼
Sondagem de Reconhecimento  ◄── fora do escopo (requer furos de qualidade analítica)
```

## Correlação

- PRD-001 (baseline): [`PRD-001-miner-harness.md`](PRD-001-miner-harness.md)
- ADR-002 GeoSGB (furos, endpoints): [`../adr/ADR-002-geosgb-data-access.md`](../adr/ADR-002-geosgb-data-access.md)
- ADR-005 Sensoriamento Remoto (v2 planejado): [`../adr/ADR-005-remote-sensing-strategy.md`](../adr/ADR-005-remote-sensing-strategy.md)
- Briefing de crítica especializada: `../architecture/critica-especializada-2026-05-21.md`
- Persona: [`../personas/dr-augusto-valen.md`](../personas/dr-augusto-valen.md)
- Arquitetura: [`../architecture/system-overview.md`](../architecture/system-overview.md)
