"""
Ứng dụng Cupid Agent với bộ định tuyến Chatbot/Agent và vòng lặp ReAct động.

Ví dụ:
    python src/app.py --test-id 1
    python src/app.py --test-id 4
    python src/app.py --all-tests
    python src/app.py --query "Tìm người phù hợp cho tôi"
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from typing import Any

from dotenv import load_dotenv

# Cho phép chạy trực tiếp bằng: python src/app.py
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from prompts import CHATBOT_BASELINE_PROMPT, MAX_ITERATIONS, REACT_SYSTEM_PROMPT
from providers import get_llm_provider
from tools import AVAILABLE_TOOLS, tool_result_to_json


load_dotenv()

if sys.stdout.encoding != "utf-8":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass


ROUTER_SYSTEM_PROMPT = """
Bạn là bộ định tuyến cho Cupid Agent. Hãy phân loại yêu cầu vào đúng một route:

- "chatbot": có thể trả lời chỉ bằng kiến thức chung hoặc viết nội dung; không cần
  đọc/ghi hồ sơ, tìm ứng viên, tính điểm hay lấy dữ liệu từ tool. Yêu cầu cần từ
  chối vì quyền riêng tư/an toàn cũng đi route này và không được gọi tool.
- "agent": cần đọc hoặc lưu hồ sơ, tìm/xếp hạng ứng viên, tính hay giải thích điểm
  tương thích dựa trên dữ liệu hệ thống.

Chỉ trả về một JSON object hợp lệ, không dùng Markdown:
{"route":"chatbot","reason":"lý do ngắn"}
hoặc
{"route":"agent","reason":"lý do ngắn"}
""".strip()


AGENT_JSON_PROTOCOL = """
Trong mỗi lượt, chỉ trả về đúng một JSON object, không dùng Markdown.

Nếu cần gọi tool:
{
  "thought": "lý do ngắn gọn cho bước kế tiếp",
  "action": {
    "name": "tên tool có trong danh sách",
    "arguments": {"tham_số": "giá trị"}
  },
  "final_answer": null
}

Nếu đã đủ dữ liệu hoặc cần hỏi thêm người dùng:
{
  "thought": "lý do ngắn gọn",
  "action": null,
  "final_answer": "câu trả lời hoàn chỉnh cho người dùng"
}

Quy tắc:
- Không tự bịa điểm hoặc dữ liệu hồ sơ; phải dùng Observation từ tool.
- Không lặp lại cùng một action với cùng arguments.
- Nếu Observation báo LỖI, sửa tham số nếu có đủ dữ liệu; nếu không, giải thích
  lỗi hoặc hỏi người dùng bổ sung.
- Không tiết lộ hay suy đoán số điện thoại, địa chỉ nhà hoặc dữ liệu riêng tư.
- Khi đưa kết quả matching, luôn nói điểm chỉ dựa trên dữ liệu demo và mang tính
  tham khảo.
""".strip()


def load_test_cases() -> list[dict[str, Any]]:
    """Đọc các test case từ config/test_cases.json."""
    project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    config_path = os.path.join(project_root, "config", "test_cases.json")
    with open(config_path, "r", encoding="utf-8") as file:
        tests = json.load(file)
    if not isinstance(tests, list):
        raise ValueError("config/test_cases.json phải chứa một JSON array.")
    return tests


def _provider_failed(response: str) -> bool:
    """Nhận diện chuỗi lỗi thống nhất từ các provider adapter."""
    return not response or response.startswith(
        (
            "[OpenAI",
            "[Gemini",
            "[Anthropic",
            "[OpenRouter",
        )
    )


def _parse_json_object(response: str, source: str) -> dict[str, Any]:
    """Đọc JSON object kể cả khi model vô tình bọc bằng code fence."""
    if not isinstance(response, str) or not response.strip():
        raise ValueError(f"{source} trả về nội dung rỗng.")

    cleaned = response.strip()
    if cleaned.startswith("```"):
        lines = cleaned.splitlines()
        if lines:
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        cleaned = "\n".join(lines).strip()

    try:
        parsed = json.loads(cleaned)
    except json.JSONDecodeError:
        start = cleaned.find("{")
        if start < 0:
            raise ValueError(f"{source} không trả về JSON object hợp lệ.")
        try:
            parsed, _ = json.JSONDecoder().raw_decode(cleaned[start:])
        except json.JSONDecodeError as exc:
            raise ValueError(
                f"{source} không trả về JSON object hợp lệ."
            ) from exc

    if not isinstance(parsed, dict):
        raise ValueError(f"{source} phải trả về JSON object.")
    return parsed


def classify_request(user_query: str, provider: Any) -> dict[str, str]:
    """Dùng chính LLM để quyết định đi Chatbot path hay Agent path."""
    if provider.__class__.__name__ == "MockProvider":
        raise RuntimeError(
            "MockProvider cũ chỉ trả phản hồi mẫu và không thể suy luận route/tool. "
            "Hãy dùng --provider openai để chạy Dynamic Router."
        )

    response = provider.generate(user_query, system_prompt=ROUTER_SYSTEM_PROMPT)
    if _provider_failed(response):
        raise RuntimeError(f"Không thể phân loại yêu cầu: {response}")

    decision = _parse_json_object(response, "Router")
    route = decision.get("route")
    reason = decision.get("reason")
    if route not in {"chatbot", "agent"}:
        raise ValueError("Router phải chọn route 'chatbot' hoặc 'agent'.")
    if not isinstance(reason, str) or not reason.strip():
        raise ValueError("Router phải cung cấp reason dạng chuỗi.")
    return {"route": route, "reason": reason.strip()}


def run_baseline_chatbot(user_query: str, provider: Any) -> dict[str, Any]:
    """Trả lời trực tiếp, không cho phép gọi tool."""
    print(f"\n💬 [CHATBOT PATH] {user_query}")
    response = provider.generate(
        user_query,
        system_prompt=CHATBOT_BASELINE_PROMPT,
    )
    if _provider_failed(response):
        raise RuntimeError(f"Chatbot provider lỗi: {response}")
    print(f"🏁 Final Answer:\n{response}")
    return {
        "route": "chatbot",
        "completed": True,
        "steps": [],
        "final_answer": response,
    }


def _build_agent_input(
    user_query: str,
    history: list[dict[str, Any]],
) -> str:
    """Đưa yêu cầu và toàn bộ Observation trước đó trở lại model."""
    return (
        f"{AGENT_JSON_PROTOCOL}\n\n"
        "YÊU CẦU NGƯỜI DÙNG:\n"
        f"{user_query}\n\n"
        "LỊCH SỬ ACTION/OBSERVATION:\n"
        f"{json.dumps(history, ensure_ascii=False, indent=2)}"
    )


def _validate_agent_decision(decision: dict[str, Any]) -> dict[str, Any]:
    """Kiểm tra giao thức quyết định trước khi thực thi action."""
    thought = decision.get("thought", "")
    action = decision.get("action")
    final_answer = decision.get("final_answer")

    if not isinstance(thought, str):
        raise ValueError("thought phải là chuỗi.")
    if action is None:
        if not isinstance(final_answer, str) or not final_answer.strip():
            raise ValueError("Khi action=null, final_answer phải là chuỗi không rỗng.")
        return {
            "thought": thought.strip(),
            "action": None,
            "final_answer": final_answer.strip(),
        }

    if final_answer not in (None, ""):
        raise ValueError("Một lượt không được vừa gọi action vừa trả final_answer.")
    if not isinstance(action, dict):
        raise ValueError("action phải là object hoặc null.")

    tool_name = action.get("name")
    arguments = action.get("arguments")
    if not isinstance(tool_name, str) or not tool_name:
        raise ValueError("action.name phải là chuỗi không rỗng.")
    if not isinstance(arguments, dict):
        raise ValueError("action.arguments phải là JSON object.")

    return {
        "thought": thought.strip(),
        "action": {"name": tool_name, "arguments": arguments},
        "final_answer": None,
    }


def _execute_action(action: dict[str, Any]) -> dict[str, Any] | str:
    """Thực thi đúng tool mà model đã chọn từ registry."""
    tool_name = action["name"]
    arguments = action["arguments"]
    tool = AVAILABLE_TOOLS.get(tool_name)
    if tool is None:
        return (
            f"LỖI [tool_registry]: Tool '{tool_name}' không tồn tại. "
            f"Tools hợp lệ: {', '.join(AVAILABLE_TOOLS)}."
        )
    return tool(**arguments)


def run_react_agent(user_query: str, provider: Any) -> dict[str, Any]:
    """Cho LLM tự chọn tool theo từng Observation cho đến khi có câu trả lời."""
    print(f"\n🤖 [AGENT PATH] {user_query}")
    history: list[dict[str, Any]] = []
    action_signatures: set[str] = set()

    for step in range(1, MAX_ITERATIONS + 1):
        print(f"\n--- 🔄 ReAct Step {step}/{MAX_ITERATIONS} ---")
        response = provider.generate(
            _build_agent_input(user_query, history),
            system_prompt=REACT_SYSTEM_PROMPT,
        )
        if _provider_failed(response):
            final_answer = f"Không thể tiếp tục vì provider gặp lỗi: {response}"
            print(f"🛡️ {final_answer}")
            return {
                "route": "agent",
                "completed": False,
                "steps": history,
                "final_answer": final_answer,
            }

        try:
            decision = _validate_agent_decision(
                _parse_json_object(response, "Agent")
            )
        except ValueError as exc:
            observation = f"LỖI [agent_protocol]: {exc}"
            history.append({"step": step, "observation": observation})
            print(f"👁️ Observation: {observation}")
            continue

        print(f"🧠 Thought: {decision['thought']}")
        if decision["action"] is None:
            print(f"🏁 Final Answer:\n{decision['final_answer']}")
            return {
                "route": "agent",
                "completed": True,
                "steps": history,
                "final_answer": decision["final_answer"],
            }

        action = decision["action"]
        signature = json.dumps(action, ensure_ascii=False, sort_keys=True)
        if signature in action_signatures:
            observation = (
                "LỖI [loop_guard]: Action và arguments này đã được gọi trước đó."
            )
        else:
            action_signatures.add(signature)
            observation = _execute_action(action)

        history.append(
            {
                "step": step,
                "thought": decision["thought"],
                "action": action,
                "observation": observation,
            }
        )
        print(
            f"🛠️ Action: {action['name']}"
            f"({json.dumps(action['arguments'], ensure_ascii=False)})"
        )
        print(f"👁️ Observation:\n{tool_result_to_json(observation)}")

    final_answer = (
        f"Đã dừng sau {MAX_ITERATIONS} bước để tránh vòng lặp. "
        "Vui lòng bổ sung thông tin hoặc thử lại."
    )
    print(f"🛡️ Guardrail: {final_answer}")
    return {
        "route": "agent",
        "completed": False,
        "steps": history,
        "final_answer": final_answer,
    }


def process_query(user_query: str, provider: Any) -> dict[str, Any]:
    """Phân loại trước, sau đó chạy đúng execution path."""
    classification = classify_request(user_query, provider)
    print(
        f"\n🧭 Route: {classification['route']} "
        f"| Reason: {classification['reason']}"
    )

    if classification["route"] == "chatbot":
        result = run_baseline_chatbot(user_query, provider)
    else:
        result = run_react_agent(user_query, provider)
    result["classification"] = classification
    return result


def _find_test_case(
    tests: list[dict[str, Any]],
    test_id: int,
) -> dict[str, Any]:
    for test in tests:
        if test.get("id") == test_id:
            return test
    valid_ids = ", ".join(str(test.get("id")) for test in tests)
    raise ValueError(f"Không có test ID {test_id}. ID hợp lệ: {valid_ids}.")


def _run_test_case(test: dict[str, Any], provider: Any) -> dict[str, Any]:
    print("\n" + "=" * 60)
    print(f"🧪 TEST {test['id']}: {test['category']}")
    print(f"❓ Query: {test['question']}")
    print(f"🎯 Expected: {test['expected_behavior']}")
    return process_query(test["question"], provider)


def build_argument_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Cupid Agent MVP")
    selection = parser.add_mutually_exclusive_group()
    selection.add_argument("--test-id", type=int, help="Chạy một test theo ID.")
    selection.add_argument(
        "--all-tests",
        action="store_true",
        help="Chạy tuần tự tất cả test case.",
    )
    selection.add_argument("--query", help="Chạy một câu hỏi tự do.")
    parser.add_argument(
        "--provider",
        choices=["openai", "gemini", "anthropic", "openrouter", "mock"],
        help="Ghi đè LLM_PROVIDER cho lần chạy này.",
    )
    return parser


def main() -> int:
    args = build_argument_parser().parse_args()
    provider = get_llm_provider(args.provider)
    model_name = getattr(provider, "model_name", "Offline Mock Mode")
    tests = load_test_cases()

    print("==================================================")
    print("💘 CUPID AGENT - DYNAMIC ROUTER & REACT LOOP")
    print("==================================================")
    print(
        f"🔌 Provider: {provider.__class__.__name__} | "
        f"Model: {model_name}"
    )

    try:
        if args.query:
            process_query(args.query, provider)
        elif args.all_tests:
            for test in tests:
                _run_test_case(test, provider)
        else:
            test_id = args.test_id
            if test_id is None:
                print("\nTest cases:")
                for test in tests:
                    print(f"  {test['id']}: {test['category']}")
                try:
                    selected = input(
                        "\nNhập test ID hoặc Enter để chọn test 4: "
                    ).strip()
                except EOFError:
                    selected = ""
                test_id = int(selected) if selected else 4
            _run_test_case(_find_test_case(tests, test_id), provider)
    except (RuntimeError, TypeError, ValueError) as exc:
        print(f"\n❌ {exc}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
