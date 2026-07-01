import re
from dataclasses import dataclass, field
from typing import Any

from dev_time_agent.capability_registry import CapabilityRegistry
from dev_time_agent.schemas import (
    AgentProgram,
    AgentProgramStep,
    ReasoningTraceStep,
    validate_agent_program_arguments,
)
from dev_time_agent.tools import ToolRegistry


@dataclass
class AgentProgramExecutionResult:
    status: str
    tool_calls: list[dict[str, Any]] = field(default_factory=list)
    reasoning_trace: list[ReasoningTraceStep] = field(default_factory=list)
    tool_results: dict[str, Any] = field(default_factory=dict)
    step_outputs: dict[str, Any] = field(default_factory=dict)
    variables: dict[str, Any] = field(default_factory=dict)
    evidence_refs: list[str] = field(default_factory=list)
    error: str = ""


def execute_agent_program(
    program: AgentProgram,
    tool_registry: ToolRegistry,
    capability_registry: CapabilityRegistry,
    *,
    max_steps: int = 12,
    max_output_items: int = 50,
) -> AgentProgramExecutionResult:
    if len(program.steps) > max_steps:
        return AgentProgramExecutionResult(
            status="failed",
            error="max_steps_exceeded",
        )

    program.validate_against_tool_specs(capability_registry)
    result = AgentProgramExecutionResult(status="succeeded")

    for step in program.steps:
        if step.kind == "tool":
            execute_tool_step(
                step,
                tool_registry,
                capability_registry,
                result,
                max_output_items=max_output_items,
            )
            if result.status != "succeeded":
                break
            continue
        execute_select_step(step, result)
        if result.status != "succeeded":
            break

    return result


def execute_tool_step(
    step: AgentProgramStep,
    tool_registry: ToolRegistry,
    capability_registry: CapabilityRegistry,
    result: AgentProgramExecutionResult,
    *,
    max_output_items: int,
) -> None:
    try:
        arguments = resolve_agent_program_variables(step.arguments, result.variables)
    except KeyError:
        fail_tool_step(step, step.arguments, result, "missing_variable")
        return
    capability = capability_registry.get(step.tool)
    try:
        validate_agent_program_arguments(
            step.model_copy(update={"arguments": arguments}),
            capability.input_schema,
        )
    except ValueError:
        fail_tool_step(step, arguments, result, "invalid_arguments")
        return
    if capability.requires_approval:
        tool_call = {
            "step_id": step.id,
            "name": step.tool,
            "status": "blocked",
            "input": arguments,
            "error": "approval_required",
            "evidence_refs": [],
        }
        result.status = "partial"
        result.error = "approval_required"
        result.tool_calls.append(tool_call)
        result.reasoning_trace.append(
            ReasoningTraceStep(
                stage="tool_call",
                title=f"阻断需审批 Program 工具 {step.tool}",
                summary="该工具需要用户审批，不能由 AgentProgram 直接执行。",
                tool_call=tool_call,
            )
        )
        return
    tool_result = tool_registry.run(step.tool, arguments)
    output = bound_agent_program_output(tool_result.data, max_output_items)
    result.step_outputs[step.id] = output
    result.tool_results[step.tool] = output
    result.evidence_refs = unique_values(
        [*result.evidence_refs, *tool_result.evidence_refs]
    )
    tool_call = {
        "step_id": step.id,
        "name": step.tool,
        "status": "succeeded",
        "input": arguments,
        "evidence_refs": tool_result.evidence_refs,
    }
    result.tool_calls.append(tool_call)
    result.reasoning_trace.append(
        ReasoningTraceStep(
            stage="tool_call",
            title=f"执行 Program 工具 {step.tool}",
            summary=f"AgentProgram step {step.id} 调用 {step.tool}。",
            evidence_refs=tool_result.evidence_refs,
            tool_call=tool_call,
        )
    )


def fail_tool_step(
    step: AgentProgramStep,
    arguments: dict[str, Any],
    result: AgentProgramExecutionResult,
    error: str,
) -> None:
    tool_call = {
        "step_id": step.id,
        "name": step.tool,
        "status": "failed",
        "input": arguments,
        "error": error,
        "evidence_refs": [],
    }
    result.status = "partial"
    result.error = error
    result.tool_calls.append(tool_call)
    result.reasoning_trace.append(
        ReasoningTraceStep(
            stage="tool_call",
            title=f"Program 工具 {step.tool} 执行前失败",
            summary=f"AgentProgram step {step.id} 在执行前因 {error} 停止。",
            tool_call=tool_call,
        )
    )


def execute_select_step(
    step: AgentProgramStep,
    result: AgentProgramExecutionResult,
) -> None:
    source = result.step_outputs[step.from_step]
    try:
        selected_value = select_agent_program_value(source, step.selector)
    except (KeyError, IndexError, TypeError, ValueError):
        tool_call = {
            "step_id": step.id,
            "name": "program.select",
            "status": "failed",
            "input": {
                "from_step": step.from_step,
                "selector": step.selector,
                "output_key": step.output_key,
            },
            "error": "selector_value_missing",
            "evidence_refs": [],
        }
        result.status = "partial"
        result.error = "selector_value_missing"
        result.tool_calls.append(tool_call)
        result.reasoning_trace.append(
            ReasoningTraceStep(
                stage="tool_call",
                title=f"Program selector {step.id} 缺少数据",
                summary=f"无法从 {step.from_step} 选择 {step.output_key}，已停止后续步骤。",
                tool_call=tool_call,
            )
        )
        return
    result.variables[step.output_key] = selected_value
    result.step_outputs[step.id] = selected_value
    tool_call = {
        "step_id": step.id,
        "name": "program.select",
        "status": "succeeded",
        "input": {
            "from_step": step.from_step,
            "selector": step.selector,
            "output_key": step.output_key,
        },
        "evidence_refs": [],
    }
    result.tool_calls.append(tool_call)
    result.reasoning_trace.append(
        ReasoningTraceStep(
            stage="tool_call",
            title=f"执行 Program selector {step.id}",
            summary=f"从 {step.from_step} 选择 {step.output_key}。",
            tool_call=tool_call,
        )
    )


def resolve_agent_program_variables(value: Any, variables: dict[str, Any]) -> Any:
    if isinstance(value, dict):
        if set(value.keys()) == {"$var"}:
            return variables[value["$var"]]
        return {
            key: resolve_agent_program_variables(nested, variables)
            for key, nested in value.items()
        }
    if isinstance(value, list):
        return [resolve_agent_program_variables(nested, variables) for nested in value]
    return value


def select_agent_program_value(value: Any, selector: str) -> Any:
    selected = value
    for segment in selector.removeprefix("$.").split("."):
        match = re.fullmatch(r"([A-Za-z0-9_]+)(?:\[(\d+)])?", segment)
        if match is None:
            raise ValueError(f"invalid selector segment: {segment}")
        key = match.group(1)
        selected = selected[key]
        index = match.group(2)
        if index is not None:
            selected = selected[int(index)]
    return selected


def bound_agent_program_output(value: Any, max_output_items: int) -> Any:
    if isinstance(value, list):
        return [
            bound_agent_program_output(item, max_output_items)
            for item in value[:max_output_items]
        ]
    if isinstance(value, dict):
        return {
            key: bound_agent_program_output(nested, max_output_items)
            for key, nested in value.items()
        }
    return value


def unique_values(values: list[str]) -> list[str]:
    seen: set[str] = set()
    unique: list[str] = []
    for value in values:
        if value in seen:
            continue
        seen.add(value)
        unique.append(value)
    return unique
