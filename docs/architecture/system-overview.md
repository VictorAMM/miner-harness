# Arquitetura do Sistema — miner-harness

## Visão Geral

```
┌─────────────────────────────────────────────────────┐
│                   MINER-HARNESS                      │
│                 (Aplicação Local)                     │
│                                                      │
│  ┌───────────────────────────────────────────────┐   │
│  │              WIZARD DE INSTALAÇÃO              │   │
│  │  • Download e setup guiado                     │   │
│  │  • Instalação de dependências                  │   │
│  │  • Download de modelos LLM                     │   │
│  │  • Configuração inicial                        │   │
│  └───────────────────────────────────────────────┘   │
│                                                      │
│  ┌───────────────────────────────────────────────┐   │
│  │           ORQUESTRADOR DE AGENTES              │   │
│  │  (Persona: Dr. Augusto Valen)                  │   │
│  │                                                │   │
│  │  Coordena análise seguindo framework:          │   │
│  │  1. História tectônica                         │   │
│  │  2. Arquitetura estrutural                     │   │
│  │  3. Fertilidade magmática                      │   │
│  │  4. Evidências indiretas                       │   │
│  │  5. Integração total                           │   │
│  └──────────┬────────────────────────────────────┘   │
│             │                                        │
│  ┌──────────▼────────────────────────────────────┐   │
│  │            AGENTES ESPECIALISTAS               │   │
│  │                                                │   │
│  │  ┌──────────┐ ┌──────────┐ ┌──────────────┐   │   │
│  │  │ Geólogo  │ │Geofísico │ │ Geoquímico   │   │   │
│  │  │Estrutural│ │          │ │              │   │   │
│  │  └──────────┘ └──────────┘ └──────────────┘   │   │
│  │  ┌──────────────┐ ┌──────────────────────┐    │   │
│  │  │Sensoriamento │ │ Integrador/Avaliador │    │   │
│  │  │   Remoto     │ │   (Eval-Optimizer)   │    │   │
│  │  └──────────────┘ └──────────────────────┘    │   │
│  └──────────┬────────────────────────────────────┘   │
│             │                                        │
│  ┌──────────▼────────────────────────────────────┐   │
│  │             CAMADA DE DADOS                    │   │
│  │                                                │   │
│  │  ┌──────────┐ ┌──────────┐ ┌──────────────┐   │   │
│  │  │ GeoSGB   │ │ Cache    │ │   Índice     │   │   │
│  │  │ Connector│ │  Local   │ │  Vetorial    │   │   │
│  │  └──────────┘ └──────────┘ └──────────────┘   │   │
│  └───────────────────────────────────────────────┘   │
│                                                      │
│  ┌───────────────────────────────────────────────┐   │
│  │              LLM ENGINE (LOCAL)                │   │
│  │  Ollama + Modelos Quantizados (GGUF)           │   │
│  │  API REST local (compatível OpenAI)            │   │
│  └───────────────────────────────────────────────┘   │
│                                                      │
│  ┌───────────────────────────────────────────────┐   │
│  │              INTERFACE / OUTPUT                 │   │
│  │  • Consulta interativa                         │   │
│  │  • Mapas de alvos minerais                     │   │
│  │  • Relatórios de prospecção                    │   │
│  │  • Visualização geoespacial                    │   │
│  └───────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────┘
```

## Componentes

### 1. Wizard de Instalação
Responsável pelo setup completo: verifica requisitos, instala dependências Python, baixa Ollama + modelo LLM, configura caminhos e faz download inicial de dados GeoSGB.

### 2. Orquestrador de Agentes
Coordena os agentes especialistas seguindo o framework analítico do Dr. Augusto Valen. Garante que toda análise passe pelas 5 etapas de integração e que nenhuma técnica seja usada isoladamente.

### 3. Agentes Especialistas
- **Geólogo Estrutural**: análise de falhas, zonas de cisalhamento, reconstrução tectônica
- **Geofísico**: magnetometria, IP/Resistividade, gravimetria, interpretação de anomalias
- **Geoquímico**: análise de assinaturas geoquímicas, isotopia, alteração hidrotermal
- **Sensoriamento Remoto**: processamento de imagens ASTER/Sentinel/Landsat, lineamentos
- **Integrador/Avaliador**: agente Evaluator-Optimizer que valida conclusões e integra resultados

### 4. Camada de Dados
- **GeoSGB Connector**: interface com a base de dados do Serviço Geológico do Brasil
- **Cache Local**: dados baixados armazenados localmente para acesso offline
- **Índice Vetorial**: embeddings dos dados para busca semântica e RAG

### 5. LLM Engine
Ollama rodando localmente com modelos quantizados. Toda inferência acontece na máquina do usuário sem dados saindo para a internet.

## Correlação
- PRD: [`../prd/PRD-001-miner-harness.md`](../prd/PRD-001-miner-harness.md)
- RFC-001 GeoSGB Connector: [`../rfc/RFC-001-geosgb-connector.md`](../rfc/RFC-001-geosgb-connector.md)
- RFC-002 Agent Orchestration: [`../rfc/RFC-002-agent-orchestration.md`](../rfc/RFC-002-agent-orchestration.md)
- RFC-003 Storage & Index: [`../rfc/RFC-003-storage-and-index.md`](../rfc/RFC-003-storage-and-index.md)
- ADR Stack: [`../adr/ADR-001-stack-decision.md`](../adr/ADR-001-stack-decision.md)
- Persona: [`../personas/dr-augusto-valen.md`](../personas/dr-augusto-valen.md)
