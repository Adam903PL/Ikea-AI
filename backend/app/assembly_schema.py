from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator


class AssemblyStep(BaseModel):
    model_config = ConfigDict(extra="forbid")

    stepNumber: int = Field(ge=1)
    title: str = Field(min_length=1, max_length=140)
    description: str = Field(min_length=1, max_length=500)
    partIndices: list[int] = Field(min_length=1, max_length=2)
    contextPartIndices: list[int] = Field(default_factory=list)
    partRoles: dict[str, str] = Field(default_factory=dict)

    @field_validator("partIndices", "contextPartIndices")
    @classmethod
    def ensure_unique_indices(cls, value: list[int]) -> list[int]:
        seen: set[int] = set()
        normalized: list[int] = []

        for item in value:
            if item not in seen:
                normalized.append(item)
                seen.add(item)

        return normalized

    @field_validator("partRoles")
    @classmethod
    def ensure_string_keys(cls, value: dict[str, str]) -> dict[str, str]:
        normalized: dict[str, str] = {}

        for key, role in value.items():
            normalized[str(key)] = role

        return normalized


class AssemblyPlan(BaseModel):
    model_config = ConfigDict(extra="forbid")

    steps: list[AssemblyStep] = Field(min_length=1)


def get_assembly_plan_schema() -> dict[str, Any]:
    schema = AssemblyPlan.model_json_schema()
    schema["additionalProperties"] = False
    return schema


def build_openrouter_response_format() -> dict[str, Any]:
    return {
        "type": "json_schema",
        "json_schema": {
            "name": "assembly_plan",
            "strict": True,
            "schema": get_assembly_plan_schema(),
        },
    }


def parse_assembly_plan(payload: Any) -> AssemblyPlan:
    return AssemblyPlan.model_validate(payload)
