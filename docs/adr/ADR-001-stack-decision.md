# ADR-001: Decisão de Stack — miner-harness

**Status**: ACCEPTED
**Data**: 2026-05-11
**valid_from**: 2026-05-11
**valid_until**: 2026-08-11
**review_trigger**: Conclusão da Fase 3 (Technical Design) ou mudança de requisitos de hardware

---

## Contexto

O miner-harness é um sistema de prospecção mineral que precisa rodar localmente, sem dependência de nuvem, com LLMs embarcados e wizard de instalação. O público-alvo são prospectores e geólogos que precisam de análise integrada de dados GeoSGB.

## Decisão

### Linguagem principal: Python 3.11+
- Ecossistema geocientífico maduro (geopandas, rasterio, shapely, fiona, pyproj)
- Bibliotecas de ML/IA consolidadas (scikit-learn, xgboost, pytorch)
- Integração nativa com LLMs locais (ollama, llama-cpp-python, transformers)
- Ferramentas de visualização geoespacial (folium, matplotlib, plotly)

### LLM Local: Ollama + modelos quantizados
- Instalação simples e multiplataforma
- Suporte a modelos quantizados (GGUF) para rodar em hardware modesto
- API REST local compatível com OpenAI
- Permite trocar modelos sem alterar código

### Interface: Python + Textual (CLI interativa) — RESOLVIDO
- **Decisão**: Textual para v1 (CLI interativa, sem dependência de browser)
- Wizard de instalação em Textual (TUI)
- Visualização de mapas via export para QGIS (GeoPackage) ou Folium (HTML)
- Ver ADR-004 para detalhes: [`ADR-004-user-interface.md`](ADR-004-user-interface.md)

### CI/CD: GitHub Actions
- Lint, testes, build do instalador
- Security scan automatizado

## Trade-offs

| Critério | Python + Ollama | Node.js + Ollama | Java + Spring |
|---|---|---|---|
| Ecossistema geocientífico | Excelente | Fraco | Médio |
| Integração com LLM local | Excelente | Bom | Médio |
| Velocidade de entrega | Alta | Alta | Média |
| Performance computacional | Médio (com numpy/C ext) | Médio | Alto |
| Complexidade operacional | Baixa | Baixa | Alta |
| Wizard/instalação local | Bom (PyInstaller/cx_Freeze) | Bom (pkg) | Complexo (JRE) |
| Maturidade para ML | Excelente | Limitada | Boa |

## Alternativas descartadas

- **Java + Spring**: ecossistema geocientífico limitado, JRE como dependência pesada para instalação local, overhead desnecessário para aplicação desktop
- **Node.js**: ecossistema de geociência praticamente inexistente, sem bibliotecas maduras para análise geoespacial e ML

## Riscos residuais

- Performance de Python para processamento pesado de dados geofísicos (mitigação: usar extensões C/numpy/dask)
- Tamanho do instalador com dependências geocientíficas (mitigação: instalação modular)
- Compatibilidade cross-platform do wizard (mitigação: testar Windows/macOS/Linux)

## Correlação

- PRD: [`../prd/PRD-001-miner-harness.md`](../prd/PRD-001-miner-harness.md)
- Persona: [`../personas/dr-augusto-valen.md`](../personas/dr-augusto-valen.md)
