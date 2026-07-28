"""
Tools cho MVP "Cupid Agent: Trợ lý ghép đôi & phân tích độ tương thích".

Thiết kế ưu tiên demo nhanh:
- Dữ liệu ứng viên giả lập được đọc từ config/demo_profiles.json.
- Mỗi hồ sơ người dùng được lưu riêng theo user_id trong bộ nhớ của tiến trình.
- Điểm tương thích do Python tính theo quy tắc cố định, không để LLM tự bịa điểm.

Lưu ý: DEMO_PROFILES là dữ liệu giả lập, không đại diện cho người thật.
"""

from __future__ import annotations

import json
import unicodedata
from functools import wraps
from pathlib import Path
from typing import Any, Callable


ToolResult = dict[str, Any] | str


# ---------------------------------------------------------------------------
# Dữ liệu demo và bộ nhớ phiên
# ---------------------------------------------------------------------------

DEMO_PROFILE_PATH = (
    Path(__file__).resolve().parent.parent / "config" / "demo_profiles.json"
)
_REQUIRED_DEMO_FIELDS = {
    "user_id",
    "name",
    "age",
    "location",
    "relationship_intent",
    "interests",
    "values",
}
_SUPPORTED_INTENTS = {"casual_dating", "long_term", "marriage"}


def _return_error_message(
    tool_function: Callable[..., dict[str, Any]],
) -> Callable[..., ToolResult]:
    """
    Biến lỗi input dự kiến thành Observation dạng chuỗi để Agent không bị crash.

    Lỗi lập trình ngoài các nhóm TypeError/ValueError vẫn được raise để không che
    giấu bug trong quá trình phát triển.
    """
    @wraps(tool_function)
    def safe_tool(*args: Any, **kwargs: Any) -> ToolResult:
        try:
            return tool_function(*args, **kwargs)
        except (TypeError, ValueError) as exc:
            return f"LỖI [{tool_function.__name__}]: {exc}"

    return safe_tool


def _load_demo_profiles(path: Path = DEMO_PROFILE_PATH) -> tuple[dict[str, Any], ...]:
    """Đọc và kiểm tra dữ liệu ứng viên giả lập ngay khi module được import."""
    try:
        with path.open("r", encoding="utf-8") as file:
            raw_profiles = json.load(file)
    except FileNotFoundError as exc:
        raise RuntimeError(f"Không tìm thấy dữ liệu demo tại: {path}") from exc
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"File dữ liệu demo không phải JSON hợp lệ: {path}") from exc

    if not isinstance(raw_profiles, list) or not raw_profiles:
        raise RuntimeError("Dữ liệu demo phải là một JSON array không rỗng.")

    profiles: list[dict[str, Any]] = []
    seen_ids: set[str] = set()
    for index, raw_profile in enumerate(raw_profiles, start=1):
        if not isinstance(raw_profile, dict):
            raise RuntimeError(f"Hồ sơ demo #{index} phải là JSON object.")

        missing_fields = _REQUIRED_DEMO_FIELDS - raw_profile.keys()
        if missing_fields:
            missing = ", ".join(sorted(missing_fields))
            raise RuntimeError(f"Hồ sơ demo #{index} thiếu trường: {missing}.")

        user_id = raw_profile["user_id"]
        if not isinstance(user_id, str) or not user_id.strip():
            raise RuntimeError(f"user_id của hồ sơ demo #{index} không hợp lệ.")
        if user_id in seen_ids:
            raise RuntimeError(f"user_id demo bị trùng: {user_id}.")
        seen_ids.add(user_id)

        age = raw_profile["age"]
        if isinstance(age, bool) or not isinstance(age, int) or not 18 <= age <= 100:
            raise RuntimeError(f"age của hồ sơ '{user_id}' không hợp lệ.")
        if raw_profile["relationship_intent"] not in _SUPPORTED_INTENTS:
            raise RuntimeError(
                f"relationship_intent của hồ sơ '{user_id}' không hợp lệ."
            )
        for field_name in ("interests", "values"):
            items = raw_profile[field_name]
            if (
                not isinstance(items, list)
                or not items
                or not all(isinstance(item, str) and item.strip() for item in items)
            ):
                raise RuntimeError(
                    f"{field_name} của hồ sơ '{user_id}' phải là array chuỗi không rỗng."
                )

        profiles.append(
            {
                **raw_profile,
                "interests": list(raw_profile["interests"]),
                "values": list(raw_profile["values"]),
            }
        )
    return tuple(profiles)


DEMO_PROFILES = _load_demo_profiles()

# Kho hồ sơ tách biệt với dữ liệu ứng viên và kết quả matching.
# Mỗi user_id sở hữu một dict riêng; dữ liệu tồn tại trong lúc chương trình chạy.
_USER_PROFILE_STORE: dict[str, dict[str, Any]] = {}

_INTENT_ALIASES = {
    "casual": "casual_dating",
    "casual_dating": "casual_dating",
    "hen ho": "casual_dating",
    "hen ho tim hieu": "casual_dating",
    "long_term": "long_term",
    "lau dai": "long_term",
    "nghiem tuc": "long_term",
    "marriage": "marriage",
    "ket hon": "marriage",
}


# ---------------------------------------------------------------------------
# Hàm hỗ trợ nội bộ
# ---------------------------------------------------------------------------

def _search_key(value: str) -> str:
    """Chuẩn hóa chữ hoa, dấu tiếng Việt và khoảng trắng để so khớp."""
    value = value.strip().lower().replace("đ", "d")
    value = unicodedata.normalize("NFD", value)
    value = "".join(char for char in value if unicodedata.category(char) != "Mn")
    return " ".join(value.split())


def _normalize_intent(value: str) -> str:
    normalized = _INTENT_ALIASES.get(_search_key(value))
    if normalized is None:
        allowed = ", ".join(sorted(set(_INTENT_ALIASES.values())))
        raise ValueError(
            f"relationship_intent không hợp lệ. Giá trị hỗ trợ: {allowed}."
        )
    return normalized


def _normalize_string_list(
    value: list[str] | tuple[str, ...] | str,
    field_name: str,
    *,
    min_items: int = 1,
    max_items: int = 10,
) -> list[str]:
    """Chấp nhận cả JSON array lẫn chuỗi phân tách bằng dấu phẩy."""
    if isinstance(value, str):
        items = value.split(",")
    elif isinstance(value, (list, tuple)):
        items = list(value)
    else:
        raise TypeError(f"{field_name} phải là danh sách chuỗi.")

    cleaned: list[str] = []
    seen: set[str] = set()
    for item in items:
        if not isinstance(item, str):
            raise TypeError(f"Mỗi phần tử của {field_name} phải là chuỗi.")
        display_value = " ".join(item.strip().split())
        key = _search_key(display_value)
        if key and key not in seen:
            cleaned.append(display_value)
            seen.add(key)

    if not min_items <= len(cleaned) <= max_items:
        raise ValueError(
            f"{field_name} cần từ {min_items} đến {max_items} giá trị khác nhau."
        )
    return cleaned


def _shared_items(left: list[str], right: list[str]) -> list[str]:
    right_keys = {_search_key(item) for item in right}
    return [item for item in left if _search_key(item) in right_keys]


def _get_session_profile(user_id: str) -> dict[str, Any]:
    try:
        return _USER_PROFILE_STORE[user_id]
    except KeyError as exc:
        raise ValueError(
            f"Chưa có hồ sơ cho user_id='{user_id}'. "
            "Hãy gọi save_user_profile trước."
        ) from exc


def _get_candidate(candidate_user_id: str) -> dict[str, Any]:
    for profile in DEMO_PROFILES:
        if profile["user_id"] == candidate_user_id:
            return profile
    raise ValueError(f"Không tìm thấy ứng viên '{candidate_user_id}'.")


def _score_candidate(
    user_profile: dict[str, Any], candidate: dict[str, Any]
) -> dict[str, Any]:
    """
    Công thức 100 điểm:
    - Cùng định hướng mối quan hệ: 40
    - Cùng thành phố: 20
    - Mỗi sở thích chung: 10, tối đa 20
    - Mỗi giá trị chung: 10, tối đa 20
    """
    same_intent = (
        user_profile["relationship_intent"] == candidate["relationship_intent"]
    )
    same_location = (
        _search_key(user_profile["location"]) == _search_key(candidate["location"])
    )
    shared_interests = _shared_items(
        user_profile["interests"], candidate["interests"]
    )
    shared_values = _shared_items(user_profile["values"], candidate["values"])

    breakdown = {
        "relationship_intent": 40 if same_intent else 0,
        "location": 20 if same_location else 0,
        "interests": min(len(shared_interests), 2) * 10,
        "values": min(len(shared_values), 2) * 10,
    }
    return {
        "user_id": candidate["user_id"],
        "name": candidate["name"],
        "age": candidate["age"],
        "location": candidate["location"],
        "relationship_intent": candidate["relationship_intent"],
        "score": sum(breakdown.values()),
        "score_breakdown": breakdown,
        "shared_interests": shared_interests,
        "shared_values": shared_values,
        "age_difference": abs(user_profile["age"] - candidate["age"]),
    }


# ---------------------------------------------------------------------------
# Tools chính cho Cupid Agent
# ---------------------------------------------------------------------------

@_return_error_message
def save_user_profile(
    age: int,
    location: str,
    relationship_intent: str,
    interests: list[str] | str,
    values: list[str] | str,
    user_id: str,
) -> ToolResult:
    """
    Lưu hồ sơ tối thiểu của người đang sử dụng Cupid Agent vào bộ nhớ phiên.

    Args:
        age: Tuổi người dùng, từ 18 đến 100.
        location: Thành phố hoặc khu vực hiện tại.
        relationship_intent: Một trong casual_dating, long_term hoặc marriage.
        interests: Từ 1 đến 10 sở thích, dạng danh sách hoặc chuỗi phân tách dấu phẩy.
        values: Từ 1 đến 10 giá trị sống, dạng danh sách hoặc chuỗi phân tách dấu phẩy.
        user_id: ID duy nhất dùng để lưu và truy xuất riêng hồ sơ.

    Returns:
        Thành công: dict chứa hồ sơ đã chuẩn hóa và trạng thái matching.
        Thất bại: chuỗi "LỖI [save_user_profile]: ..." để Agent quan sát.

    Agent Call Trigger:
        Gọi sau khi người dùng đã cung cấp đủ 5 nhóm thông tin bắt buộc.
    """
    if isinstance(age, bool) or not isinstance(age, int) or not 18 <= age <= 100:
        raise ValueError("age phải là số nguyên từ 18 đến 100.")
    if not isinstance(user_id, str) or not user_id.strip():
        raise ValueError("user_id không được để trống.")
    if not isinstance(location, str) or not location.strip():
        raise ValueError("location không được để trống.")
    if not isinstance(relationship_intent, str):
        raise TypeError("relationship_intent phải là chuỗi.")

    profile = {
        "user_id": user_id.strip(),
        "age": age,
        "location": " ".join(location.strip().split()),
        "relationship_intent": _normalize_intent(relationship_intent),
        "interests": _normalize_string_list(interests, "interests"),
        "values": _normalize_string_list(values, "values"),
    }
    # Sao chép cả hai list để các hồ sơ không dùng chung object mutable.
    stored_profile = {
        **profile,
        "interests": list(profile["interests"]),
        "values": list(profile["values"]),
    }
    _USER_PROFILE_STORE[profile["user_id"]] = stored_profile
    return {
        "success": True,
        "matching_ready": True,
        "profile": {
            **stored_profile,
            "interests": list(stored_profile["interests"]),
            "values": list(stored_profile["values"]),
        },
        "message": "Đã lưu riêng hồ sơ. Có thể gọi find_demo_matches.",
    }


@_return_error_message
def get_user_profile(user_id: str) -> ToolResult:
    """
    Lấy một hồ sơ đã lưu theo user_id.

    Args:
        user_id: ID duy nhất của hồ sơ cần lấy.

    Returns:
        Thành công: dict chứa bản sao hồ sơ.
        Thất bại: chuỗi "LỖI [get_user_profile]: ..." để Agent quan sát.

    Agent Call Trigger:
        Gọi trước khi matching hoặc khi cần kiểm tra thông tin đã thu thập.
    """
    if not isinstance(user_id, str) or not user_id.strip():
        raise ValueError("user_id không được để trống.")
    profile = _get_session_profile(user_id.strip())
    return {
        "found": True,
        "matching_ready": True,
        "profile": {
            **profile,
            "interests": list(profile["interests"]),
            "values": list(profile["values"]),
        },
    }


@_return_error_message
def find_demo_matches(
    user_id: str,
    limit: int = 3,
    min_age: int | None = None,
    max_age: int | None = None,
) -> ToolResult:
    """
    Lọc, chấm điểm và trả về các hồ sơ giả lập phù hợp nhất.

    Args:
        user_id: ID hồ sơ đã lưu bằng save_user_profile.
        limit: Số kết quả cần trả về, từ 1 đến 5.
        min_age: Tuổi ứng viên tối thiểu, optional.
        max_age: Tuổi ứng viên tối đa, optional.

    Returns:
        Thành công: dict chứa danh sách ứng viên đã xếp hạng.
        Thất bại: chuỗi "LỖI [find_demo_matches]: ..." để Agent quan sát.

    Agent Call Trigger:
        Gọi khi người dùng yêu cầu tìm người phù hợp và hồ sơ đã được lưu.
    """
    if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= 5:
        raise ValueError("limit phải là số nguyên từ 1 đến 5.")
    if min_age is not None and (
        isinstance(min_age, bool) or not isinstance(min_age, int) or min_age < 18
    ):
        raise ValueError("min_age phải là số nguyên từ 18 trở lên.")
    if max_age is not None and (
        isinstance(max_age, bool) or not isinstance(max_age, int) or max_age > 100
    ):
        raise ValueError("max_age phải là số nguyên không lớn hơn 100.")
    if min_age is not None and max_age is not None and min_age > max_age:
        raise ValueError("min_age không được lớn hơn max_age.")

    user_profile = _get_session_profile(user_id)
    candidates = [
        profile
        for profile in DEMO_PROFILES
        if (min_age is None or profile["age"] >= min_age)
        and (max_age is None or profile["age"] <= max_age)
    ]
    scored = [_score_candidate(user_profile, candidate) for candidate in candidates]
    scored.sort(key=lambda item: (-item["score"], item["age_difference"], item["name"]))
    matches = scored[:limit]

    return {
        "user_id": user_id,
        "is_demo_data": True,
        "scoring_method": {
            "same_relationship_intent": 40,
            "same_location": 20,
            "each_shared_interest": 10,
            "each_shared_value": 10,
            "maximum_score": 100,
        },
        "total_candidates": len(candidates),
        "matches": matches,
        "message": (
            "Đây là kết quả từ hồ sơ giả lập phục vụ demo."
            if matches
            else "Không có hồ sơ demo thỏa bộ lọc tuổi."
        ),
    }


@_return_error_message
def generate_match_explanation(
    candidate_user_id: str,
    user_id: str,
) -> ToolResult:
    """
    Tạo phần giải thích có cấu trúc cho một cặp ghép đôi.

    Args:
        candidate_user_id: ID ứng viên lấy từ find_demo_matches.
        user_id: ID hồ sơ người dùng hiện tại.

    Returns:
        Thành công: dict chứa điểm, điểm mạnh, khác biệt và câu hỏi gợi ý.
        Thất bại: chuỗi "LỖI [generate_match_explanation]: ..." để Agent quan sát.

    Agent Call Trigger:
        Gọi khi người dùng chọn một ứng viên hoặc hỏi vì sao hai người phù hợp.
    """
    user_profile = _get_session_profile(user_id)
    candidate = _get_candidate(candidate_user_id)
    result = _score_candidate(user_profile, candidate)

    strengths: list[str] = []
    differences: list[str] = []
    if result["score_breakdown"]["relationship_intent"]:
        strengths.append("Hai bạn có cùng định hướng mối quan hệ.")
    else:
        differences.append("Hai bạn đang có định hướng mối quan hệ khác nhau.")
    if result["score_breakdown"]["location"]:
        strengths.append("Hai bạn đang ở cùng khu vực.")
    else:
        differences.append("Hai bạn hiện ở khác khu vực.")
    if result["shared_interests"]:
        strengths.append(
            "Sở thích chung: " + ", ".join(result["shared_interests"]) + "."
        )
    else:
        differences.append("Chưa tìm thấy sở thích chung trong dữ liệu demo.")
    if result["shared_values"]:
        strengths.append(
            "Giá trị sống chung: " + ", ".join(result["shared_values"]) + "."
        )
    else:
        differences.append("Chưa tìm thấy giá trị sống chung trong dữ liệu demo.")

    conversation_seed = (
        result["shared_interests"][0]
        if result["shared_interests"]
        else candidate["interests"][0]
    )
    return {
        "user_id": user_id,
        "candidate_user_id": candidate_user_id,
        "candidate_name": candidate["name"],
        "score": result["score"],
        "score_label": (
            "phù hợp cao"
            if result["score"] >= 70
            else "khá phù hợp"
            if result["score"] >= 50
            else "cần tìm hiểu thêm"
        ),
        "strengths": strengths,
        "differences": differences,
        "suggested_question": (
            f"Bạn thích điều gì nhất ở hoạt động {conversation_seed}?"
        ),
        "disclaimer": (
            "Điểm số chỉ dựa trên dữ liệu giả lập và là thông tin tham khảo."
        ),
    }


# Registry được Agent dùng để ánh xạ tên action sang Python function.
AVAILABLE_TOOLS = {
    "save_user_profile": save_user_profile,
    "get_user_profile": get_user_profile,
    "find_demo_matches": find_demo_matches,
    "generate_match_explanation": generate_match_explanation,
}


# JSON Schema tối giản, tương thích với khai báo function calling phổ biến.
TOOL_SCHEMAS = [
    {
        "type": "function",
        "function": {
            "name": "save_user_profile",
            "description": "Lưu riêng hồ sơ tối thiểu của một người dùng theo user_id.",
            "parameters": {
                "type": "object",
                "properties": {
                    "age": {"type": "integer", "minimum": 18, "maximum": 100},
                    "location": {"type": "string", "minLength": 1},
                    "relationship_intent": {
                        "type": "string",
                        "enum": ["casual_dating", "long_term", "marriage"],
                    },
                    "interests": {
                        "type": "array",
                        "items": {"type": "string"},
                        "minItems": 1,
                        "maxItems": 10,
                    },
                    "values": {
                        "type": "array",
                        "items": {"type": "string"},
                        "minItems": 1,
                        "maxItems": 10,
                    },
                    "user_id": {"type": "string", "minLength": 1},
                },
                "required": [
                    "user_id",
                    "age",
                    "location",
                    "relationship_intent",
                    "interests",
                    "values",
                ],
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_user_profile",
            "description": "Lấy hồ sơ đã lưu riêng của một người dùng theo user_id.",
            "parameters": {
                "type": "object",
                "properties": {
                    "user_id": {"type": "string", "minLength": 1},
                },
                "required": ["user_id"],
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "find_demo_matches",
            "description": "Tìm và chấm điểm các hồ sơ giả lập phù hợp nhất.",
            "parameters": {
                "type": "object",
                "properties": {
                    "user_id": {"type": "string", "minLength": 1},
                    "limit": {
                        "type": "integer",
                        "minimum": 1,
                        "maximum": 5,
                        "default": 3,
                    },
                    "min_age": {
                        "type": ["integer", "null"],
                        "minimum": 18,
                    },
                    "max_age": {
                        "type": ["integer", "null"],
                        "maximum": 100,
                    },
                },
                "required": ["user_id"],
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "generate_match_explanation",
            "description": "Giải thích điểm mạnh và khác biệt của một cặp ghép đôi.",
            "parameters": {
                "type": "object",
                "properties": {
                    "candidate_user_id": {"type": "string"},
                    "user_id": {"type": "string", "minLength": 1},
                },
                "required": ["candidate_user_id", "user_id"],
                "additionalProperties": False,
            },
        },
    },
]


# ---------------------------------------------------------------------------
# Tương thích tạm thời với app.py hiện tại
# ---------------------------------------------------------------------------

def get_weather(location: str) -> str:
    """
    Tool cũ được giữ lại vì app.py hiện vẫn import hàm này.

    Hàm không nằm trong AVAILABLE_TOOLS của Cupid Agent.
    """
    locations = {
        "ha noi": "Thời tiết Hà Nội: 28°C, nắng nhẹ, độ ẩm 65%.",
        "tp.hcm": "Thời tiết TP.HCM: 33°C, nắng nóng, có mây.",
        "hcm": "Thời tiết TP.HCM: 33°C, nắng nóng, có mây.",
        "ho chi minh": "Thời tiết TP.HCM: 33°C, nắng nóng, có mây.",
        "da nang": "Thời tiết Đà Nẵng: 30°C, gió nhẹ, mát mẻ.",
    }
    key = _search_key(location)
    for location_key, weather in locations.items():
        if location_key in key:
            return weather
    return f"LỖI: Không tìm thấy dữ liệu thời tiết cho '{location}'."


def search_flights(origin: str, destination: str) -> str:
    """
    Tool cũ được giữ lại vì app.py hiện vẫn import hàm này.

    Hàm không nằm trong AVAILABLE_TOOLS của Cupid Agent.
    """
    return (
        f"Chuyến bay từ {origin} -> {destination} ngày mai:\n"
        "1. VN123 (08:00) - Giá: 1,500,000 VNĐ (Còn vé)\n"
        "2. VJ456 (14:30) - Giá: 1,200,000 VNĐ (Còn vé)"
    )


def tool_result_to_json(result: ToolResult) -> str:
    """Chuyển kết quả tool sang JSON Unicode để in trong ReAct Observation."""
    return json.dumps(result, ensure_ascii=False, indent=2)
