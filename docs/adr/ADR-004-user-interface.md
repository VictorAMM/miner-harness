# ADR-004: Interface de Usuário — Textual (CLI Interativa)

**Status**: ACCEPTED
**Data**: 2026-05-11
**valid_from**: 2026-05-11
**valid_until**: 2027-02-11
**review_trigger**: Feedback de usuários beta indicando necessidade de interface gráfica ou Fase 5 (Implementação)

---

## Contexto

O ADR-001 deixou em aberto a decisão entre Textual (CLI interativa) e Streamlit (web local) para a interface do miner-harness. Essa decisão precisa ser resolvida antes de avançar para o design técnico (Fase 3).

O miner-harness é uma aplicação local, sem servidor, destinada a prospectores e geólogos. A interface precisa:
1. Funcionar sem navegador web como dependência
2. Ser leve (não consumir VRAM que o LLM precisa)
3. Permitir interação com agentes (entrada de região, visualização de resultados)
4. Suportar output de mapas e tabelas

## Decisão: Textual (CLI interativa) para v1

### Justificativa

| Critério | Textual | Streamlit |
|---|---|---|
| Dependência de navegador | Não precisa | Precisa (Chrome/Firefox) |
| Consumo de memória | ~50MB | ~200-400MB (navegador + servidor) |
| Complexidade de instalação | pip install | pip install + processo web |
| Visualização de mapas | Limitada (ASCII/Unicode) | Boa (Folium/Plotly no browser) |
| Tabelas de dados | Excelente (DataTable nativo) | Boa |
| Interatividade | Boa (widgets, forms) | Excelente |
| Experiência para geólogos | Profissional/técnica | Mais amigável |
| Wizard de instalação | Nativo (TUI) | Precisa de browser |

### Decisão para cada componente

| Componente | Interface | Razão |
|---|---|---|
| Wizard de instalação | Textual (TUI) | Deve funcionar antes de qualquer dependência estar instalada |
| Consulta interativa | Textual (TUI) | Input de região, substância, escala |
| Relatórios de prospecção | Markdown → terminal + arquivo .md | Exportável |
| Mapas de alvos | Exportar GeoPackage/KML para QGIS | Geólogos já usam QGIS |
| Visualização rápida | Folium → HTML local (abre no browser) | Só quando explicitamente pedido |

### Arquitetura da interface

```
miner-harness CLI
├── miner-harness install          # Wizard TUI (Textual)
├── miner-harness analyze          # Análise interativa (Textual)
│   ├── Input: região (bbox/nome)
│   ├── Input: substância alvo
│   ├── Input: escala de análise
│   └── Output: progresso dos agentes em tempo real
├── miner-harness report           # Gerar relatório
│   └── Output: Markdown + GeoPackage
├── miner-harness map              # Visualizar mapa
│   └── Output: Folium HTML (abre browser)
└── miner-harness config           # Configuração
```

## Trade-offs aceitos

- **Mapas**: sem visualização inline no terminal. Geólogos abrem GeoPackage no QGIS (que já é seu workflow natural). Para visualização rápida, exportar HTML com Folium.
- **Curva de aprendizado**: CLI pode intimidar usuários não-técnicos. Mitigação: wizard guiado, help interativo, documentação clara.
- **Limitação futura**: se houver demanda por GUI completa, Streamlit pode ser adicionado como frontend alternativo na v2 sem mudar o backend.

## Alternativas descartadas

- **Streamlit**: boa experiência visual, mas adiciona complexidade (processo web, navegador como dependência, consumo de memória). Para v1 de uma ferramenta local para geólogos técnicos, Textual é suficiente.
- **PyQt/Tkinter**: desktop GUI completa, mas complexidade de packaging cross-platform e manutenção alta.
- **Electron**: overkill para o escopo, dependência de Node.js.

## Correlação

- ADR-001: [`ADR-001-stack-decision.md`](ADR-001-stack-decision.md)
- PRD-001: [`../prd/PRD-001-miner-harness.md`](../prd/PRD-001-miner-harness.md)
- ADR-003: [`ADR-003-engineering-security-standards.md`](ADR-003-engineering-security-standards.md)
