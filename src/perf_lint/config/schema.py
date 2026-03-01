"""Pydantic schema for perf-lint configuration."""

from __future__ import annotations

from pydantic import BaseModel, Field, field_validator


class RuleConfig(BaseModel):
    """Configuration for a single rule."""

    enabled: bool = True
    severity: str | None = None

    @field_validator("severity")
    @classmethod
    def validate_severity(cls, v: str | None) -> str | None:
        if v is not None and v not in ("error", "warning", "info"):
            raise ValueError(f"severity must be 'error', 'warning', or 'info', got: {v!r}")
        return v


class CustomRuleConfig(BaseModel):
    """Configuration for a custom rule plugin."""

    path: str


class PerfLintConfig(BaseModel):
    """Root configuration schema for .perf-lint.yml / .perf-lint.toml."""

    version: int = Field(default=1, ge=1)

    @field_validator("version")
    @classmethod
    def validate_version(cls, v: int) -> int:
        if v > 1:
            raise ValueError(
                f"Unsupported config version {v}. "
                "This version of perf-lint supports config version 1 only. "
                "Upgrade perf-lint to use a newer config format."
            )
        return v
    severity_threshold: str = Field(default="warning")
    rules: dict[str, RuleConfig] = Field(default_factory=dict)
    custom_rules: list[CustomRuleConfig] = Field(default_factory=list)
    ignore_paths: list[str] = Field(default_factory=list)
    api_key: str | None = None
    api_url: str = "https://perflint.martkos-it.co.uk"

    @field_validator("severity_threshold")
    @classmethod
    def validate_threshold(cls, v: str) -> str:
        if v not in ("error", "warning", "info"):
            raise ValueError(
                f"severity_threshold must be 'error', 'warning', or 'info', got: {v!r}"
            )
        return v

    @classmethod
    def default(cls) -> PerfLintConfig:
        """Return default config with no overrides."""
        return cls()
