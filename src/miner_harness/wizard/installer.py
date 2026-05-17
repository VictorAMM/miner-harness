"""Wizard installer — creates MINER_HOME structure and writes initial config.

Performs the actual file-system operations after all checks pass.
Pure logic with no TUI dependencies — fully testable.

Ref: ADR-004, RFC-003 §5
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import structlog

from miner_harness.core.config import MinerHarnessConfig, OrchestratorConfig, StorageConfig

logger = structlog.get_logger(__name__)

_CONFIG_FILENAME = "config.json"


@dataclass
class InstallStep:
    """Result of a single installation step."""

    name: str
    success: bool
    message: str
    detail: str = ""


@dataclass
class InstallResult:
    """Aggregated result of the full installation."""

    miner_home: Path
    steps: list[InstallStep] = field(default_factory=list)

    @property
    def success(self) -> bool:
        return all(s.success for s in self.steps)

    @property
    def failed_steps(self) -> list[InstallStep]:
        return [s for s in self.steps if not s.success]

    def to_dict(self) -> dict[str, Any]:
        return {
            "miner_home": str(self.miner_home),
            "success": self.success,
            "steps": [
                {
                    "name": s.name,
                    "success": s.success,
                    "message": s.message,
                    "detail": s.detail,
                }
                for s in self.steps
            ],
        }


def create_miner_home(miner_home: Path) -> InstallStep:
    """Create MINER_HOME directory structure."""
    try:
        config = MinerHarnessConfig(
            storage=StorageConfig(miner_home=miner_home),
        )
        config.storage.ensure_dirs()
        return InstallStep(
            name="create_dirs",
            success=True,
            message=f"Diretorios criados em {miner_home}",
            detail=str(miner_home),
        )
    except OSError as e:
        return InstallStep(
            name="create_dirs",
            success=False,
            message=f"Falha ao criar diretorios: {e}",
        )


def write_initial_config(
    miner_home: Path,
    model: str = "qwen3:8b-q4_K_M",
    ollama_url: str = "http://localhost:11434",
) -> InstallStep:
    """Write initial configuration file to MINER_HOME."""
    config_path = miner_home / _CONFIG_FILENAME
    try:
        config = MinerHarnessConfig(
            storage=StorageConfig(miner_home=miner_home),
            orchestrator=OrchestratorConfig(
                model=model,
                ollama_base_url=ollama_url,
            ),
        )
        config_path.write_text(
            json.dumps(config.model_dump(mode="json"), indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        return InstallStep(
            name="write_config",
            success=True,
            message=f"Configuracao salva em {config_path}",
            detail=f"modelo={model}, ollama={ollama_url}",
        )
    except OSError as e:
        return InstallStep(
            name="write_config",
            success=False,
            message=f"Falha ao salvar configuracao: {e}",
        )


def write_env_hint(miner_home: Path) -> InstallStep:
    """Write a shell environment hint file."""
    hint_path = miner_home / "env_hint.sh"
    try:
        content = f"# Adicione ao seu ~/.bashrc ou ~/.zshrc:\nexport MINER_HOME={miner_home}\n"
        hint_path.write_text(content, encoding="utf-8")
        return InstallStep(
            name="write_env_hint",
            success=True,
            message="Dica de variavel de ambiente salva",
            detail=str(hint_path),
        )
    except OSError as e:
        return InstallStep(
            name="write_env_hint",
            success=False,
            message=f"Nao foi possivel salvar dica de env: {e}",
        )


def run_installation(
    miner_home: Path | None = None,
    model: str = "qwen3:8b-q4_K_M",
    ollama_url: str = "http://localhost:11434",
) -> InstallResult:
    """Run full installation sequence.

    Steps:
      1. Create MINER_HOME directory structure.
      2. Write initial config.json.
      3. Write env_hint.sh.

    Args:
        miner_home: Target directory. Defaults to ~/.miner-harness.
        model: Default LLM model to configure.
        ollama_url: Ollama base URL to configure.

    Returns:
        InstallResult with per-step outcomes.
    """
    home = miner_home or (Path.home() / ".miner-harness")
    result = InstallResult(miner_home=home)

    step1 = create_miner_home(home)
    result.steps.append(step1)
    logger.info("install_step", name=step1.name, success=step1.success)

    if not step1.success:
        logger.error("install_aborted", reason=step1.message)
        return result

    step2 = write_initial_config(home, model=model, ollama_url=ollama_url)
    result.steps.append(step2)
    logger.info("install_step", name=step2.name, success=step2.success)

    step3 = write_env_hint(home)
    result.steps.append(step3)
    logger.info("install_step", name=step3.name, success=step3.success)

    logger.info(
        "installation_complete",
        miner_home=str(home),
        success=result.success,
        failed=len(result.failed_steps),
    )
    return result
