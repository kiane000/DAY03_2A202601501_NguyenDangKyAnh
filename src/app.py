"""
🚀 CORE AGENT APP (Dành cho Role 4: Core Agent Developer)
File chính ghép nối tất cả các thành phần: Tools + Prompts + Test Cases + Multi-Provider.
"""

import json
import mimetypes
import os
import sys
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse
try:
    from dotenv import load_dotenv
except ImportError:
    def load_dotenv():
        return False

# Đảm bảo import các module cùng thư mục src/ hoạt động mượt mà
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

# Đảm bảo in ra Tiếng Việt và Emojis không bị lỗi trên Windows Console
if sys.stdout.encoding != 'utf-8':
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except Exception:
        pass

# Import các thành phần từ file của Role 2, Role 3 & Multi-Provider Adapter
from tools import AVAILABLE_TOOLS, tool_result_to_json
from prompts import CHATBOT_BASELINE_PROMPT, MAX_ITERATIONS
from providers import get_llm_provider

load_dotenv()

# Hồ sơ đầu vào cố định để chạy demo nhanh, không đại diện cho người thật.
DEMO_USER_PROFILE = {
    "user_id": "linh_demo",
    "age": 25,
    "location": "TP.HCM",
    "relationship_intent": "long_term",
    "interests": ["du lịch", "nấu ăn", "chạy bộ"],
    "values": ["gia đình", "trung thực", "phát triển bản thân"],
}

CUPID_REPORT_PROMPT = """Bạn là Cupid Agent.
Hãy trình bày top 3 ứng viên từ dữ liệu tool bằng tiếng Việt, ngắn gọn và thân thiện.
Giữ nguyên điểm số và thứ tự do tool trả về, không tự bịa thêm dữ liệu cá nhân.
Với mỗi ứng viên, nêu lý do phù hợp và một điểm cần tìm hiểu thêm.
Kết thúc bằng lưu ý rằng kết quả chỉ dựa trên dữ liệu giả lập phục vụ demo."""


def load_test_cases():
    """Đọc bộ test cases từ config/test_cases.json của Role 1"""
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    config_path = os.path.join(base_dir, "config", "test_cases.json")
    
    # Fallback kiểm tra nếu file ở thư mục hiện tại
    if not os.path.exists(config_path):
        config_path = "test_cases.json"
        
    with open(config_path, "r", encoding="utf-8") as f:
        return json.load(f)


def run_baseline_chatbot(user_query: str, provider):
    """
    Dựng Chatbot gốc (Baseline) không có công cụ.
    """
    print(f"\n💬 [CHATBOT BASELINE] Câu hỏi: {user_query}")
    print(f"⚙️ System Prompt: {CHATBOT_BASELINE_PROMPT.strip()}")
    
    # Gọi LLM Provider thực hiện sinh câu trả lời
    response = provider.generate(user_query, system_prompt=CHATBOT_BASELINE_PROMPT)
    print(f"🤖 Chatbot trả lời:\n{response}")


def _fallback_match_report(reports):
    """Tạo báo cáo deterministic khi provider đang ở mock mode hoặc gọi API lỗi."""
    lines = ["Cupid đã tìm thấy các ứng viên phù hợp nhất:"]
    for rank, report in enumerate(reports, start=1):
        strengths = " ".join(report["strengths"]) or "Cần thêm dữ liệu để đánh giá."
        difference = (
            report["differences"][0]
            if report["differences"]
            else "Chưa có khác biệt đáng chú ý trong dữ liệu hiện tại."
        )
        lines.append(
            f"{rank}. {report['candidate_name']}: {report['score']}/100 "
            f"({report['score_label']}). {strengths} "
            f"Điểm cần tìm hiểu: {difference}"
        )
    lines.append("Lưu ý: hồ sơ và điểm số chỉ phục vụ demo.")
    return "\n".join(lines)


def run_react_agent(user_query: str, provider):
    """
    Chạy luồng Cupid Agent: lưu hồ sơ -> tìm match -> giải thích kết quả.
    """
    print(f"\n🤖 [REACT AGENT] Câu hỏi: {user_query}")
    if MAX_ITERATIONS < 3:
        print("🛡️ GUARDRAIL: Cupid Agent cần tối thiểu 3 bước xử lý.")
        return None

    step = 0
    completed = False
    saved_profile = None
    matches = None
    reports = []

    while step < MAX_ITERATIONS:
        step += 1
        print(f"\n--- 🔄 Vòng lặp ReAct (Step {step}/{MAX_ITERATIONS}) ---")

        if step == 1:
            print("🧠 Thought: Cần lưu và chuẩn hóa hồ sơ trước khi ghép đôi.")
            print("🛠️ Action: save_user_profile")
            saved_profile = AVAILABLE_TOOLS["save_user_profile"](
                **DEMO_USER_PROFILE
            )
            print(f"👁️ Observation:\n{tool_result_to_json(saved_profile)}")

        elif step == 2:
            print("🧠 Thought: Hồ sơ đã sẵn sàng, cần tìm và xếp hạng ứng viên.")
            print("🛠️ Action: find_demo_matches")
            matches = AVAILABLE_TOOLS["find_demo_matches"](
                user_id=DEMO_USER_PROFILE["user_id"],
                limit=3,
            )
            print(f"👁️ Observation:\n{tool_result_to_json(matches)}")

        elif step == 3:
            if not matches or not matches["matches"]:
                print("🏁 Final Answer: Không tìm thấy hồ sơ phù hợp trong dữ liệu demo.")
                completed = True
                break

            print("🧠 Thought: Cần giải thích minh bạch vì sao từng ứng viên phù hợp.")
            print("🛠️ Action: generate_match_explanation (cho top 3)")
            reports = [
                AVAILABLE_TOOLS["generate_match_explanation"](
                    user_id=DEMO_USER_PROFILE["user_id"],
                    candidate_user_id=match["user_id"],
                )
                for match in matches["matches"]
            ]
            print(
                "👁️ Observation:\n"
                + tool_result_to_json({"reports": reports})
            )

            llm_input = json.dumps(
                {
                    "user_query": user_query,
                    "user_profile": saved_profile["profile"],
                    "matches": matches["matches"],
                    "reports": reports,
                },
                ensure_ascii=False,
                indent=2,
            )
            final_answer = provider.generate(
                llm_input,
                system_prompt=CUPID_REPORT_PROMPT,
            )
            provider_failed = final_answer.startswith(
                (
                    "[OpenAI",
                    "[Gemini",
                    "[Anthropic",
                    "[OpenRouter",
                )
            )
            if provider.__class__.__name__ == "MockProvider" or provider_failed:
                final_answer = _fallback_match_report(reports)

            print(f"🏁 Final Answer:\n{final_answer}")
            completed = True
            break

    if not completed:
        print(f"🛡️ GUARDRAIL TRIGGERED: Đã đạt giới hạn tối đa {MAX_ITERATIONS} bước. Ngắt lặp an toàn!")

    return {
        "saved_profile": saved_profile,
        "matches": matches,
        "reports": reports,
        "completed": completed,
    }


def build_web_match_response(payload):
    """Run Cupid tools for the browser UI and return JSON-serializable data."""
    user_id = (payload.get("user_id") or "web_demo").strip()
    age = int(payload["age"])
    limit = int(payload.get("limit") or 3)
    min_age = payload.get("min_age")
    max_age = payload.get("max_age")
    saved_profile = AVAILABLE_TOOLS["save_user_profile"](
        user_id=user_id,
        age=age,
        location=payload["location"],
        relationship_intent=payload["relationship_intent"],
        interests=payload["interests"],
        values=payload["values"],
    )
    matches = AVAILABLE_TOOLS["find_demo_matches"](
        user_id=user_id,
        limit=limit,
        min_age=int(min_age) if min_age not in (None, "") else None,
        max_age=int(max_age) if max_age not in (None, "") else None,
    )
    reports = [
        AVAILABLE_TOOLS["generate_match_explanation"](
            user_id=user_id,
            candidate_user_id=match["user_id"],
        )
        for match in matches["matches"]
    ]
    return {
        "profile": saved_profile["profile"],
        "matches": matches["matches"],
        "reports": reports,
        "trace": [
            {
                "thought": "Cần lưu và chuẩn hóa hồ sơ trước khi ghép đôi.",
                "action": "save_user_profile",
                "observation": saved_profile,
            },
            {
                "thought": "Hồ sơ đã sẵn sàng, cần tìm và xếp hạng ứng viên.",
                "action": "find_demo_matches",
                "observation": matches,
            },
            {
                "thought": "Cần giải thích minh bạch vì sao từng ứng viên phù hợp.",
                "action": "generate_match_explanation",
                "observation": {"reports": reports},
            },
        ],
        "disclaimer": "Hồ sơ và điểm số chỉ phục vụ demo lab.",
    }


def build_web_compare_response(payload):
    p1 = payload.get("person1", {})
    p2 = payload.get("person2", {})

    saved_p1 = AVAILABLE_TOOLS["save_user_profile"](
        user_id="person1",
        name=p1.get("name", "Người 1"),
        age=int(p1.get("age", 20)),
        location=p1.get("location", "Unknown"),
        relationship_intent=p1.get("relationship_intent", "long_term"),
        interests=p1.get("interests", []),
        values=p1.get("values", []),
    )

    saved_p2 = AVAILABLE_TOOLS["save_user_profile"](
        user_id="person2",
        name=p2.get("name", "Người 2"),
        age=int(p2.get("age", 20)),
        location=p2.get("location", "Unknown"),
        relationship_intent=p2.get("relationship_intent", "long_term"),
        interests=p2.get("interests", []),
        values=p2.get("values", []),
    )

    report = AVAILABLE_TOOLS["generate_match_explanation"](
        user_id="person1",
        candidate_user_id="person2",
    )

    return {
        "report": report,
        "trace": [
            {
                "thought": "Đã nhận thông tin người 1. Cần lưu hồ sơ người 1.",
                "action": "save_user_profile(user_id='person1')",
                "observation": saved_p1,
            },
            {
                "thought": "Đã nhận thông tin người 2. Cần lưu hồ sơ người 2.",
                "action": "save_user_profile(user_id='person2')",
                "observation": saved_p2,
            },
            {
                "thought": "Đã lưu 2 hồ sơ. Cần phân tích và giải thích độ tương thích giữa 2 người.",
                "action": "generate_match_explanation(user_id='person1', candidate_user_id='person2')",
                "observation": report,
            },
        ],
        "disclaimer": "Đã tính toán độ tương thích qua Tool ở Backend.",
    }


def build_web_chat_response(payload):
    """Xử lý API chat, gọi OpenAI Provider."""
    user_query = payload.get("message", "").strip()
    if not user_query:
        raise ValueError("Tin nhắn không được để trống.")
    
    provider = get_llm_provider("openai")
    response = provider.generate(user_query, system_prompt=CHATBOT_BASELINE_PROMPT)
    return {"reply": response}

class CupidWebHandler(SimpleHTTPRequestHandler):
    """Serve the static UI and a tiny JSON API without adding a web framework."""

    def __init__(self, *args, **kwargs):
        root = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "web")
        super().__init__(*args, directory=root, **kwargs)

    def _send_json(self, status, data):
        body = json.dumps(data, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        path = urlparse(self.path).path
        if path == "/api/test-cases":
            self._send_json(200, {"test_cases": load_test_cases()})
            return
        if path == "/":
            self.path = "/index.html"
        return super().do_GET()

    def do_POST(self):
        path = urlparse(self.path).path
        if path == "/api/matches":
            try:
                length = int(self.headers.get("Content-Length", "0"))
                payload = json.loads(self.rfile.read(length).decode("utf-8"))
                self._send_json(200, build_web_match_response(payload))
            except Exception as exc:
                self._send_json(400, {"error": str(exc)})
        elif path == "/api/compare":
            try:
                length = int(self.headers.get("Content-Length", "0"))
                payload = json.loads(self.rfile.read(length).decode("utf-8"))
                self._send_json(200, build_web_compare_response(payload))
            except Exception as exc:
                self._send_json(400, {"error": str(exc)})
        elif path == "/api/chat":
            try:
                length = int(self.headers.get("Content-Length", "0"))
                payload = json.loads(self.rfile.read(length).decode("utf-8"))
                self._send_json(200, build_web_chat_response(payload))
            except Exception as exc:
                self._send_json(400, {"error": str(exc)})
        else:
            self._send_json(404, {"error": "Not found"})


def run_web_server(port=8000):
    mimetypes.add_type("text/css", ".css")
    mimetypes.add_type("application/javascript", ".js")
    server = ThreadingHTTPServer(("127.0.0.1", port), CupidWebHandler)
    print(f"🌐 Cupid Agent UI: http://127.0.0.1:{port}")
    server.serve_forever()


def run_cli_demo():
    print("==================================================")
    print("💘 CUPID AGENT - CHATBOT VS REACT AGENT")
    print("==================================================")
    
    # Khởi tạo Multi-Provider LLM Adapter (Đọc từ biến môi trường LLM_PROVIDER)
    provider = get_llm_provider()
    model_name = getattr(provider, "model_name", "Offline Mock Mode")
    print(f"🔌 LLM Provider đang hoạt động: {provider.__class__.__name__} (Model: {model_name})")
    
    tests = load_test_cases()
    print(f"✅ Đã tải thành công {len(tests)} Test Cases từ config/test_cases.json\n")
    
    # Test số 4 phù hợp với luồng tìm top 3 ứng viên của bộ tools hiện tại.
    sample_query = tests[3]["question"]
    
    print("--- DEMO 1: CHẠY TRÊN CHATBOT BASELINE ---")
    run_baseline_chatbot(sample_query, provider)
    
    print("\n--- DEMO 2: CHẠY TRÊN REACT AGENT ---")
    run_react_agent(sample_query, provider)


if __name__ == "__main__":
    if "--web" in sys.argv:
        arg_port = next((arg for arg in sys.argv if arg.startswith("--port=")), "")
        run_web_server(int(arg_port.split("=", 1)[1]) if arg_port else 8000)
    else:
        run_cli_demo()
