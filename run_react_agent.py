"""
Script chạy ReAct Agent THỰC TẾ cho TC#3, TC#4, TC#5 (test cases mới nhất).
Dùng OpenAI Function Calling — Thought -> Action -> Observation thật.
"""
import json, os, sys
sys.path.insert(0, 'src')
if sys.stdout.encoding != 'utf-8':
    try: sys.stdout.reconfigure(encoding='utf-8')
    except: pass

from dotenv import load_dotenv
load_dotenv()

import openai
from tools import AVAILABLE_TOOLS, TOOL_SCHEMAS, tool_result_to_json
from prompts import REACT_SYSTEM_PROMPT, MAX_ITERATIONS

client = openai.OpenAI(api_key=os.getenv("OPENAI_API_KEY"))


def run_react_agent_real(query: str, label: str = "") -> list:
    """Chạy ReAct Agent thật với OpenAI Function Calling, trả về trace log."""
    sep = "=" * 65
    print(f"\n{sep}")
    print(f"REACT AGENT — {label}")
    print(f"QUERY: {query[:120]}{'...' if len(query) > 120 else ''}")
    print(sep)

    messages = [
        {"role": "system", "content": REACT_SYSTEM_PROMPT},
        {"role": "user",   "content": query}
    ]
    trace = []

    for step in range(1, MAX_ITERATIONS + 1):
        print(f"\n--- BUOC {step}/{MAX_ITERATIONS} ---")

        resp = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=messages,
            tools=TOOL_SCHEMAS,
            tool_choice="auto"
        )
        msg = resp.choices[0].message
        finish = resp.choices[0].finish_reason

        thought = (msg.content or "").strip()
        if thought:
            print(f"Thought: {thought[:300]}{'...' if len(thought) > 300 else ''}")
        else:
            print(f"Thought: [Agent gọi Tool trực tiếp]")
        trace.append({"step": step, "thought": thought or "[Agent gọi Tool trực tiếp]"})

        # Final answer — không có tool call
        if finish == "stop" and not msg.tool_calls:
            print(f"\n*** FINAL ANSWER ***\n{thought}")
            trace.append({"final_answer": thought})
            break

        if msg.tool_calls:
            messages.append(msg)
            for tc in msg.tool_calls:
                name = tc.function.name
                try:
                    args = json.loads(tc.function.arguments)
                except Exception:
                    args = {}

                print(f"\nAction: {name}({json.dumps(args, ensure_ascii=False)})")
                trace.append({"action": f"{name}({json.dumps(args, ensure_ascii=False)})"})

                # Thực thi Tool Python thật
                if name in AVAILABLE_TOOLS:
                    result = AVAILABLE_TOOLS[name](**args)
                else:
                    result = f"LỖI: Tool '{name}' không tồn tại."

                obs = tool_result_to_json(result)
                print(f"Observation: {obs[:600]}{'...' if len(obs) > 600 else ''}")
                trace.append({"observation": obs})

                messages.append({
                    "role": "tool",
                    "tool_call_id": tc.id,
                    "content": obs
                })
        else:
            break

    return trace


def main():
    with open('config/test_cases.json', encoding='utf-8') as f:
        tests = json.load(f)

    all_traces = {}

    # ── TC #3: save_user_profile + get_user_profile ──────────────────────
    tc3 = tests[2]
    print(f"\n{'#'*65}")
    print(f"TEST CASE #3 | {tc3['category']}")
    print(f"Expected: {tc3['expected_behavior']}")
    trace3 = run_react_agent_real(tc3["question"], f"TC#3 | {tc3['category']}")
    all_traces["tc3"] = trace3

    # ── TC #4: save + find_demo_matches + generate_match_explanation ──────
    tc4 = tests[3]
    print(f"\n{'#'*65}")
    print(f"TEST CASE #4 | {tc4['category']}")
    print(f"Expected: {tc4['expected_behavior']}")
    trace4 = run_react_agent_real(tc4["question"], f"TC#4 | {tc4['category']}")
    all_traces["tc4"] = trace4

    # ── TC #5: Edge Case — input không hợp lệ, Guardrail test ────────────
    tc5 = tests[4]
    print(f"\n{'#'*65}")
    print(f"TEST CASE #5 | {tc5['category']}")
    print(f"Expected: {tc5['expected_behavior']}")
    trace5 = run_react_agent_real(tc5["question"], f"TC#5 | {tc5['category']}")
    all_traces["tc5"] = trace5

    print("\n\n" + "="*65)
    print("=== FULL TRACE LOG (JSON) ===")
    print(json.dumps(all_traces, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
