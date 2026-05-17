# miner-harness

Sistema de prospecção mineral inteligente que utiliza agentes de IA especializados em geologia e geofísica para analisar dados da base GeoSGB.

## Sobre

O miner-harness combina LLMs rodando localmente com agentes especialistas (geologia estrutural, geofísica, geoquímica, sensoriamento remoto) para fornecer análise integrada de prospecção mineral — seguindo o framework analítico do Dr. Augusto Valen.

### Características

- **100% local**: LLMs embarcados via Ollama, sem dependência de nuvem
- **Agentes especialistas**: cada disciplina geocientífica tem seu agente dedicado
- **Integração GeoSGB**: acesso e análise de dados públicos do Serviço Geológico do Brasil
- **Wizard de instalação**: setup guiado para download e configuração
- **Análise integrada**: nunca usa uma técnica isolada — integra geologia, geofísica, geoquímica e imagens orbitais

## Requisitos

- Python 3.11+
- Ollama (instalado automaticamente pelo wizard)
- 16GB RAM (mínimo recomendado)
- GPU com 8GB+ VRAM (recomendado: NVIDIA RTX 2060 ou superior)
- ~10GB de espaço em disco (modelos LLM + cache de dados)

## Instalação

```bash
# Wizard de instalação (em desenvolvimento)
python scripts/install.py
```

## Estrutura

```
miner-harness/
├── docs/           # PRD, RFC, ADR, RCA, arquitetura, personas
├── src/            # Código-fonte
├── tests/          # Testes
├── scripts/        # Scripts de automação e instalação
├── infra/          # Configuração de infraestrutura
└── .github/        # GitHub Actions
```

## Desenvolvimento

Este projeto segue o **Agentic SDLC Operating System v3** (ASO v3). Consulte `CLAUDE.md` para diretrizes de desenvolvimento e o diretório `docs/` para artefatos do projeto.

## Status

**Fase atual**: 11 — Self-Improvement

Fases concluídas:
- Fase 0 — Fundação e Governança ✅
- Fase 1 — Discovery e Pesquisa Autônoma ✅
- Fase 2 — PRD Executável ✅
- Fase 3 — Technical Design e RFC Swarm ✅
- Fase 4 — Incepção de Ambientes e Infra ✅
- Fase 5 — Implementação ✅
- Fase 6 — Validation Harness ✅
- Fase 7 — Testing Swarm ✅
- Fase 8 — Governed CI/CD ✅
- Fase 9 — Observabilidade ✅
- Fase 10 — RCA Autônomo ✅

## Licença

MIT
