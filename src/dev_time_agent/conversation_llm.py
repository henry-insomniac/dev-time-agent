import json
import os
from collections.abc import Mapping
from typing import Any
from urllib.request import Request, urlopen

from dev_time_agent.client import HTTPServerClient
from dev_time_agent.llm import nested_value
from dev_time_agent.schemas import (
    AgentDraftResponse,
    AgentPlan,
    LLMProviderConfig,
    ResponseVerification,
)


class OpenAICompatibleConversationLLM:
    def __init__(self, config: LLMProviderConfig) -> None:
        self.config = config
        self.base_url = config.base_url.rstrip("/")

    def plan_turn(self, context: dict[str, Any]) -> AgentPlan:
        content = self._chat_json(
            {
                "stage": "plan_turn",
                "required_output_schema": {
                    "intent": "普通对话 | 能力说明 | 风险解释 | 项目状态 | 行动计划 | 工具请求",
                    "confidence": "0 到 1",
                    "needs_evidence": "是否需要读取风险证据",
                    "needs_tools": "是否需要调用工具",
                    "tool_names": ["仅允许上下文 available_tools 中的工具名"],
                    "program": {
                        "version": "agent_program.v1",
                        "goal": "多步骤工具目标；不需要多步骤时为 null",
                        "steps": [
                            {
                                "id": "小写下划线步骤 id",
                                "kind": "tool | select",
                                "tool": "tool 步骤使用，必须来自 available_tools",
                                "arguments": {
                                    "参数名": "字面量，或 {'$var': 'selector_output_key'}"
                                },
                                "from_step": "select 步骤读取的前置步骤 id",
                                "selector": "$.path[0].field",
                                "output_key": "select 输出变量名",
                            }
                        ],
                        "answer_contract": {
                            "format": "text",
                            "required_sections": ["summary", "evidence"],
                            "must_cite_evidence": True,
                        },
                    },
                    "answer_strategy": "一句话说明回答策略",
                    "reasoning_summary": "只输出简短判断摘要，不输出推理链",
                    "safety_notes": ["证据、权限、答非所问等风险"],
                },
                "agent_context": context,
            }
        )
        return AgentPlan.model_validate_json(content)

    def generate_response(
        self,
        context: dict[str, Any],
        plan: AgentPlan,
    ) -> AgentDraftResponse:
        content = self._chat_json(
            {
                "stage": "generate_response",
                "required_output_schema": {
                    "answer": "直接给用户看的中文回答",
                    "evidence_refs": ["必须来自上下文 evidence_summary.evidence_refs"],
                    "suggested_actions": [
                        {
                            "action_type": "动作类型",
                            "target_ref": "目标引用",
                            "draft_body": "草稿内容",
                            "reason": "建议原因",
                            "evidence_refs": ["相关证据 id"],
                            "required_permission": "需要的权限",
                        }
                    ],
                    "reasoning_summary": "简短说明回答依据，不输出推理链",
                    "confidence": "0 到 1",
                },
                "agent_context": context,
                "plan": plan.model_dump(),
            }
        )
        return AgentDraftResponse.model_validate_json(content)

    def verify_response(
        self,
        context: dict[str, Any],
        plan: AgentPlan,
        draft: AgentDraftResponse,
    ) -> ResponseVerification:
        content = self._chat_json(
            {
                "stage": "verify_response",
                "required_output_schema": {
                    "passed": "回答是否贴合用户问题并遵守边界",
                    "issues": ["off_topic | fabricated_evidence | unsafe_action 等"],
                    "rewrite_instruction": "如果不通过，给出可直接展示给用户的中文改写",
                },
                "agent_context": context,
                "plan": plan.model_dump(),
                "draft_response": draft.model_dump(),
            }
        )
        return ResponseVerification.model_validate_json(content)

    def _chat_json(self, payload: dict[str, Any]) -> str:
        request = Request(
            f"{self.base_url}/chat/completions",
            data=json.dumps(
                {
                    "model": self.config.model,
                    "messages": [
                        {
                            "role": "system",
                            "content": (
                                "你是 Dev Time 的项目风险 Agent 编排器。"
                                "必须围绕用户问题、Agent 定位、可用证据和可用工具回答。"
                                "普通对话不要强行解释当前风险；风险结论必须引用证据；"
                                "GitHub 项目、仓库、PR、CI 可见性必须先规划 GitHub 工具调用；"
                                "不要把 project_id 当作用户可见项目名称；"
                                "写操作只能提出待确认动作。只输出 JSON。"
                            ),
                        },
                        {
                            "role": "user",
                            "content": json.dumps(payload, ensure_ascii=False),
                        },
                    ],
                    "response_format": {"type": "json_object"},
                    "temperature": 0.2,
                },
                ensure_ascii=False,
            ).encode(),
            headers={
                "Accept": "application/json",
                "Authorization": f"Bearer {self.config.api_key}",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        with urlopen(request, timeout=30) as response:
            body = json.loads(response.read())

        content = nested_value(body, "choices", 0, "message", "content")
        if not isinstance(content, str) or content == "":
            raise ValueError("conversation llm response did not include content")
        return content


def build_conversation_llm_from_env(
    environment: Mapping[str, str] | None = None,
    *,
    workspace_id: str | None = None,
) -> OpenAICompatibleConversationLLM | None:
    loaded_environment = environment or os.environ
    server_internal_base_url = loaded_environment.get("DEV_TIME_SERVER_INTERNAL_BASE_URL")
    if not server_internal_base_url:
        return None

    server_client = HTTPServerClient(server_internal_base_url)
    return OpenAICompatibleConversationLLM(
        server_client.get_llm_provider_config(workspace_id)
    )
