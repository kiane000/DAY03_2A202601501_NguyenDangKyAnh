"""
🧠 PROMPTS & SAFEGUARDS (Dành cho Role 3: Prompt & Safeguard Engineer)
Nơi cấu hình System Prompt và Phanh An Toàn (Guardrails) cho AI Agent.
Tự động sinh ReAct Prompt từ cấu trúc các Tool được định nghĩa trong src/tools.py.
"""

from __future__ import annotations
import inspect
from typing import Any

# Import danh sách tools và schemas trực tiếp từ src/tools.py
try:
    from tools import AVAILABLE_TOOLS, TOOL_SCHEMAS
except ImportError:
    from src.tools import AVAILABLE_TOOLS, TOOL_SCHEMAS


# ---------------------------------------------------------------------------
# Dynamic Prompt Builder từ tools.py
# ---------------------------------------------------------------------------

def build_react_prompt_from_tools(
    tool_schemas: list[dict[str, Any]] = TOOL_SCHEMAS,
    available_tools: dict[str, Any] = AVAILABLE_TOOLS,
) -> str:
    """
    Tự động đọc thông tin parameters, description và docstrings của từng Tool 
    trong `tools.py` để tạo ra ReAct System Prompt chuẩn xác cho LLM.
    """
    tools_description_lines = []
    
    for idx, schema in enumerate(tool_schemas, start=1):
        fn_data = schema.get("function", schema)
        name = fn_data.get("name", "unknown_tool")
        desc = fn_data.get("description", "").strip()
        params_info = fn_data.get("parameters", {}).get("properties", {})
        required_params = fn_data.get("parameters", {}).get("required", [])
        
        param_args = []
        for p_name in params_info.keys():
            if p_name in required_params:
                param_args.append(p_name)
            else:
                param_args.append(f"{p_name}=optional")
                
        args_str = ", ".join(param_args)
        tools_description_lines.append(
            f"{idx}. {name}[{args_str}]: {desc}"
        )
        
    formatted_tools = "\n".join(tools_description_lines)

    prompt = f"""Bạn là Cupid Agent - Trợ lý AI ghép đôi & phân tích độ tương thích thông minh.
Nhiệm vụ của bạn là thu thập hồ sơ người dùng, tìm kiếm ứng viên phù hợp từ dữ liệu demo và giải thích độ tương thích ghép đôi.

DANH SÁCH CÔNG CỤ (TOOLS) BẠN CÓ THỂ SỬ DỤNG:
{formatted_tools}

QUY TẮC BẮT BUỘC KHI SỬ DỤNG TOOL (REACT LOOP):
1. Khi cần thu thập hoặc lưu thông tin người dùng (tuổi, vị trí, ý định, sở thích, giá trị sống), gọi `save_user_profile`.
2. Khi cần kiểm tra thông tin hồ sơ hiện có, gọi `get_user_profile`.
3. Khi người dùng yêu cầu tìm người phù hợp, CHỈ gọi `find_demo_matches` khi người dùng đã có hồ sơ trong hệ thống.
4. Khi giải thích lý do phù hợp 1-1 cho một ứng viên cụ thể, gọi `generate_match_explanation`.
5. KHÔNG BAO GIỜ TỰ BỊA ĐIỂM SỐ HOẶC KẾT QUẢ MATCHING. Mọi số liệu điểm số bắt buộc phải lấy từ Observation của Tool.
6. Luôn thêm Disclaimer khi giải thích kết quả ghép đôi: "Điểm số chỉ dựa trên dữ liệu giả lập và là thông tin tham khảo."

ĐỊNH DẠNG PHẢN HỒI THEO TỪNG BƯỚC (BẮT BUỘC):
thought: Suy luận của bạn về yêu cầu người dùng và bước tiếp theo.
action: tên_công_cụ[tham_số_1="giá_trị_1", tham_số_2="giá_trị_2"]
(Sau đó dừng lại chờ hệ thống trả về kết quả observation)

Khi đã có đủ thông tin hoặc hoàn thành yêu cầu, trả về:
thought: Tôi đã có đủ thông tin để trả lời.
final answer: Nội dung trả lời hoàn chỉnh cho người dùng.

BẮT ĐẦU:
"""
    return prompt


# Baseline Chatbot Prompt (Chỉ dùng LLM thông thường, không có Tool)
CHATBOT_BASELINE_PROMPT = """Bạn là Chatbot tư vấn Cupid Agent thông thường (không sử dụng công cụ).
Hãy hỗ trợ tư vấn ghép đôi dựa trên kiến thức có sẵn. Nếu người dùng yêu cầu lưu hồ sơ hoặc tìm kiếm người phù hợp thời gian thực, hãy nhắc họ rằng bạn không có kết nối cơ sở dữ liệu tool.
"""

# ReAct Agent Prompt tự động khởi tạo từ các Tool trong src/tools.py
REACT_SYSTEM_PROMPT = build_react_prompt_from_tools()
CUPID_AGENT_SYSTEM_PROMPT = REACT_SYSTEM_PROMPT

# 🛡️ GUARDRAILS CONFIGURATION (PHANH AN TOÀN)
MAX_ITERATIONS = 4      # Giới hạn tối đa 4 vòng lặp Thought-Action để tránh lặp vô tận
TIMEOUT_SECONDS = 15    # Timeout tối đa cho mỗi lượt xử lý

