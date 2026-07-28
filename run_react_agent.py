"""
Script chạy ReAct Agent THỰC TẾ với GPT-4o-mini qua OpenAI Function Calling.
Trích xuất chuỗi Thought -> Action -> Observation cho docs/trace_eval.md
"""
import json, os, sys, re
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

def parse_action_from_text(text):
    """Parse action từ text dạng: action: ten_tool[param='val']"""
    match = re.search(r'action:\s*(\w+)\[([^\]]*)\]', text, re.IGNORECASE)
    if match:
        return match.group(1), match.group(2)
    return None, None

def run_react_agent_real(query, user_id="tc4_linh"):
    """ReAct Agent dùng OpenAI với function calling thật"""
    print(f"\n{'='*60}")
    print(f"REACT AGENT — CÂU HỎI: {query}")
    print(f"{'='*60}")

    messages = [
        {"role": "system", "content": REACT_SYSTEM_PROMPT},
        {"role": "user",   "content": query}
    ]

    trace_log = []

    for step in range(1, MAX_ITERATIONS + 1):
        print(f"\n--- BUOC {step}/{MAX_ITERATIONS} ---")

        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=messages,
            tools=TOOL_SCHEMAS,
            tool_choice="auto"
        )

        msg = response.choices[0].message
        finish_reason = response.choices[0].finish_reason

        # ---- Thought từ text content ----
        thought_text = (msg.content or "").strip()
        if thought_text:
            print(f"Thought: {thought_text}")
            trace_log.append({"step": step, "thought": thought_text})
        else:
            print(f"Thought: [Agent chọn gọi Tool trực tiếp]")
            trace_log.append({"step": step, "thought": "[Agent chọn gọi Tool trực tiếp]"})

        # ---- Kiểm tra Final Answer ----
        if finish_reason == "stop" and not msg.tool_calls:
            print(f"\nFinal Answer: {thought_text}")
            trace_log.append({"final_answer": thought_text})
            break

        # ---- Xử lý Tool Calls ----
        if msg.tool_calls:
            messages.append(msg)  # thêm assistant message với tool_calls

            for tc in msg.tool_calls:
                tool_name = tc.function.name
                try:
                    args = json.loads(tc.function.arguments)
                except json.JSONDecodeError:
                    args = {}

                print(f"Action: {tool_name}({json.dumps(args, ensure_ascii=False)})")

                # Thực thi Tool thực tế
                if tool_name in AVAILABLE_TOOLS:
                    result = AVAILABLE_TOOLS[tool_name](**args)
                else:
                    result = f"LỖI: Tool '{tool_name}' không tồn tại."

                obs_str = tool_result_to_json(result)
                print(f"Observation: {obs_str[:500]}{'...' if len(obs_str) > 500 else ''}")

                trace_log.append({
                    "action": f"{tool_name}({json.dumps(args, ensure_ascii=False)})",
                    "observation": obs_str
                })

                # Thêm tool result vào messages
                messages.append({
                    "role": "tool",
                    "tool_call_id": tc.id,
                    "content": obs_str
                })
        else:
            # No tool call và không phải stop -> break
            break

    return trace_log


def main():
    with open('config/test_cases.json', encoding='utf-8') as f:
        tests = json.load(f)

    # === TC #3: Multi-step, cần save_user_profile + find_demo_matches ===
    tc3 = tests[2]  # id=3
    print("\n" + "="*60)
    print(f"[TC #3] {tc3['category']}")

    # Kịch bản: Người dùng tên "An", 26 tuổi, TP.HCM, long_term
    query_tc3 = (
        "Tôi tên An, 26 tuổi, sống ở TP.HCM, thích du lịch, chạy bộ, nấu ăn, "
        "coi trọng gia đình và trung thực. Tôi muốn tìm mối quan hệ lâu dài (long_term). "
        "Hãy lưu hồ sơ của tôi và phân tích ai phù hợp nhất với tôi, cho điểm và nêu 3 lý do chính."
    )
    trace3 = run_react_agent_real(query_tc3, user_id="An_26")

    print("\n" + "="*60)
    # === TC #4: Multi-step, cần nhiều tools, tìm 3 ứng viên cho Linh ===
    tc4 = tests[3]  # id=4
    print(f"\n[TC #4] {tc4['category']}")

    query_tc4 = (
        "Tôi tên Khánh Linh, 24 tuổi, sống ở TP.HCM, thích âm nhạc, phim ảnh, trò chơi, "
        "coi trọng tự do và sáng tạo. Tôi muốn hẹn hò nhẹ nhàng (casual_dating). "
        "Hãy lưu hồ sơ và tìm 3 ứng viên phù hợp nhất, xếp hạng theo điểm, rồi giải thích lý do cho ứng viên số 1."
    )
    trace4 = run_react_agent_real(query_tc4, user_id="Linh_24")

    print("\n\n=== TRACE LOGS HOÀN CHỈNH (JSON) ===")
    print(json.dumps({"tc3": trace3, "tc4": trace4}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
