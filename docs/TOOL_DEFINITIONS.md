# THIẾT KẾ BỘ TOOL DEFINITION & ARCHITECTURE CHO CUPID AGENT

## 1. System Overview

**Cupid Agent** là hệ thống AI Agent hỗ trợ tạo hồ sơ, tìm kiếm người phù hợp và giải thích độ tương thích ghép đôi dựa trên dữ liệu ứng viên giả lập (`config/demo_profiles.json`). 

Hệ thống kết hợp giữa khả năng xử lý ngôn ngữ tự nhiên của LLM và thuật toán định lượng chính xác được cài đặt sẵn trong Python (`tools.py`), đảm bảo LLM không tự suy đoán (hallucinate) điểm số.

```text
                  ┌─────────────────────────────────────────┐
                  │              Cupid Agent                │
                  └────────────────────┬────────────────────┘
                                       │ (Gọi Tool)
         ┌─────────────────────────────┼─────────────────────────────┐
         ▼                             ▼                             ▼
┌──────────────────┐         ┌──────────────────┐          ┌──────────────────┐
│save_user_profile │         │find_demo_matches │          │ generate_match_  │
│get_user_profile  │         │                  │          │   explanation    │
└────────┬─────────┘         └────────┬─────────┘          └────────┬─────────┘
         │                            │                             │
         ▼                            ▼                             ▼
┌──────────────────┐         ┌──────────────────┐          ┌──────────────────┐
│_USER_PROFILE_STORE│        │  DEMO_PROFILES    │          │  _score_candidate│
│ (In-memory Session│        │  (Config JSON)   │          │ (Python Scoring) │
└──────────────────┘         └──────────────────┘          └──────────────────┘
```

### Các nguyên tắc hoạt động cốt lõi:
1. **Tính toán điểm tập trung ở Python (`_score_candidate`)**: LLM không tự đưa ra điểm số mà phải truy xuất từ kết quả trả về của `find_demo_matches` hoặc `generate_match_explanation`.
2. **Bộ nhớ phiên linh hoạt (`_USER_PROFILE_STORE`)**: Hồ sơ người dùng lưu trong bộ nhớ tiến trình Python, được phân tách theo `user_id`.
3. **Chuẩn hóa đầu vào tự động**: Hàm hỗ trợ `_normalize_intent` và `_normalize_string_list` hỗ trợ nhận diện tiếng Việt có/không dấu, bí danh intent và chuỗi phân tách bằng dấu phẩy.

---

## 2. Tool: save_user_profile

### 2.1 Tool Description
* **Mục đích**: Chuẩn hóa thông tin cá nhân (tuổi, vị trí, ý định mối quan hệ, sở thích, giá trị sống) và lưu vào bộ nhớ phiên `_USER_PROFILE_STORE` theo `user_id`.
* **Khi NÀO nên dùng**: Khi người dùng cung cấp đầy đủ thông tin cá nhân hoặc yêu cầu cập nhật hồ sơ.
* **Khi NÀO KHÔNG nên dùng**: Khi người dùng chưa cung cấp đủ thông tin hoặc chỉ muốn xem lại hồ sơ / tìm kiếm đối tượng ghép đôi.
* **Điều kiện tiên quyết**: Đã thu thập đủ: `user_id`, `age`, `location`, `relationship_intent`, `interests`, `values`.
* **Loại thao tác**: Ghi (Write) & Chuẩn hóa dữ liệu (Normalize).
* **Thay đổi trạng thái hệ thống**: **CÓ** (Ghi/Cập nhật vào `_USER_PROFILE_STORE`).

### 2.2 Input Schema
```json
{
  "$schema": "http://json-schema.org/draft-07/schema#",
  "type": "object",
  "properties": {
    "user_id": {
      "type": "string",
      "minLength": 1,
      "description": "ID duy nhất của người dùng. Chuỗi không rỗng."
    },
    "age": {
      "type": "integer",
      "minimum": 18,
      "maximum": 100,
      "description": "Tuổi của người dùng (từ 18 đến 100)."
    },
    "location": {
      "type": "string",
      "minLength": 1,
      "description": "Thành phố hoặc khu vực hiện tại."
    },
    "relationship_intent": {
      "type": "string",
      "enum": ["casual_dating", "long_term", "marriage"],
      "description": "Ý định mối quan hệ: 'casual_dating', 'long_term', hoặc 'marriage'."
    },
    "interests": {
      "type": ["array", "string"],
      "description": "Từ 1 đến 10 sở thích. Mảng chuỗi hoặc chuỗi phân tách bởi dấu phẩy."
    },
    "values": {
      "type": ["array", "string"],
      "description": "Từ 1 đến 10 giá trị sống. Mảng chuỗi hoặc chuỗi phân tách bởi dấu phẩy."
    }
  },
  "required": ["user_id", "age", "location", "relationship_intent", "interests", "values"]
}
```

### 2.3 Output Schema
```json
{
  "type": "object",
  "properties": {
    "success": { "type": "boolean", "example": true },
    "matching_ready": { "type": "boolean", "example": true },
    "profile": {
      "type": "object",
      "properties": {
        "user_id": { "type": "string" },
        "age": { "type": "integer" },
        "location": { "type": "string" },
        "relationship_intent": { "type": "string" },
        "interests": { "type": "array", "items": { "type": "string" } },
        "values": { "type": "array", "items": { "type": "string" } }
      }
    },
    "message": { "type": "string" }
  },
  "required": ["success", "matching_ready", "profile", "message"]
}
```

### 2.4 Validation Rules
1. `age`: Phải là số nguyên $18 \le age \le 100$. Khung hình phạt từ chối boolean.
2. `relationship_intent`: Tự động ánh xạ thông qua bí danh:
   * `"casual"`, `"hen ho"`, `"hen ho tim hieu"` $\rightarrow$ `"casual_dating"`
   * `"lau dai"`, `"nghiem tuc"` $\rightarrow$ `"long_term"`
   * `"ket hon"` $\rightarrow$ `"marriage"`
3. `interests` & `values`: Tự động split chuỗi dấu phẩy, trim khoảng trắng thừa, xóa phần tử rỗng và trùng lặp. Đòi hỏi số phần tử từ 1 đến 10.

### 2.5 Failure Model
* **Lỗi có thể gặp**: `ValueError` (tuổi ngoài range, rỗng `user_id`/`location`, intent sai, `interests`/`values` không từ 1-10 mục).
* **Xử lý phía Agent**: Phản hồi lỗi minh bạch cho người dùng, yêu cầu cung cấp lại dữ liệu đúng. Không thử lại với cùng dữ liệu sai.

### 2.6 Examples

#### Example 1: Thành công
* **User Request**: "Lưu hồ sơ cho user_101: 24 tuổi, ở Hà Nội, muốn tìm mối quan hệ nghiêm túc. Sở thích: đọc sách, chạy bộ. Giá trị sống: trung thực, gia đình."
* **Agent Reasoning Summary**: Đã đủ 5 thông tin cá nhân. Bí danh "nghiem tuc" khớp với "long_term". Tiến hành gọi `save_user_profile`.
* **Selected Tool**: `save_user_profile`
* **Tool Arguments**:
  ```json
  {
    "user_id": "user_101",
    "age": 24,
    "location": "Hà Nội",
    "relationship_intent": "nghiem tuc",
    "interests": ["đọc sách", "chạy bộ"],
    "values": ["trung thực", "gia đình"]
  }
  ```
* **Tool Result**:
  ```json
  {
    "success": true,
    "matching_ready": true,
    "profile": {
      "user_id": "user_101",
      "age": 24,
      "location": "Hà Nội",
      "relationship_intent": "long_term",
      "interests": ["đọc sách", "chạy bộ"],
      "values": ["trung thực", "gia đình"]
    },
    "message": "Đã lưu riêng hồ sơ. Có thể gọi find_demo_matches."
  }
  ```
* **Final Response**: "Hồ sơ của `user_101` đã được lưu thành công! Bạn hiện đã ở trạng thái sẵn sàng ghép đôi (`matching_ready = true`). Bạn có muốn tôi tìm kiếm người phù hợp ngay không?"

#### Example 2: Đầu vào không hợp lệ (Tuổi < 18)
* **User Request**: "Tạo hồ sơ user_102, 16 tuổi, ở TP.HCM, hẹn hò vui vẻ, thích xem phim, coi trọng tự do."
* **Agent Reasoning Summary**: Độ tuổi 16 nhỏ hơn giới hạn tối thiểu 18.
* **Selected Tool**: `save_user_profile`
* **Tool Arguments**: `{"user_id": "user_102", "age": 16, "location": "TP.HCM", "relationship_intent": "casual_dating", "interests": ["xem phim"], "values": ["tự do"]}`
* **Tool Result**: `ValueError: age phải là số nguyên từ 18 đến 100.`
* **Final Response**: "Hệ thống chỉ hỗ trợ tạo hồ sơ ghép đôi cho người dùng từ 18 tuổi trở lên. Thông tin tuổi 16 không hợp lệ."

#### Example 3: Lỗi nghiệp vụ (Danh sách sở thích trống)
* **User Request**: "Lưu hồ sơ user_103: 22 tuổi, ở Đà Nẵng, kết hôn. Sở thích: không có. Giá trị: tôn trọng."
* **Agent Reasoning Summary**: Danh sách sở thích rỗng. Không đáp ứng tối thiểu 1 item.
* **Selected Tool**: `save_user_profile`
* **Tool Arguments**: `{"user_id": "user_103", "age": 22, "location": "Đà Nẵng", "relationship_intent": "marriage", "interests": [], "values": ["tôn trọng"]}`
* **Tool Result**: `ValueError: interests cần từ 1 đến 10 giá trị khác nhau.`
* **Final Response**: "Bạn cần cung cấp tối thiểu 1 sở thích cá nhân để lưu hồ sơ và tham gia ghép đôi."

#### Example 4: Agent quyết định KHÔNG gọi tool
* **User Request**: "Tìm người phù hợp cho tôi với."
* **Agent Reasoning Summary**: Chưa có thông tin cá nhân để lưu hay tra cứu. Cần yêu cầu người dùng cung cấp thông tin trước.
* **Selected Tool**: None
* **Final Response**: "Để bắt đầu tìm người phù hợp, bạn vui lòng cung cấp: Mã ID, Tuổi, Thành phố, Ý định tìm kiếm (hẹn hò/lâu dài/kết hôn), các sở thích và giá trị sống của bạn nhé!"

---

## 3. Tool: get_user_profile

### 3.1 Tool Description
* **Mục đích**: Truy xuất bản sao thông tin hồ sơ của người dùng trong bộ nhớ `_USER_PROFILE_STORE` theo `user_id`.
* **Khi NÀO nên dùng**: Khi người dùng muốn xem lại thông tin cá nhân hoặc Agent cần kiểm tra hồ sơ trước khi tìm đối tượng ghép đôi.
* **Khi NÀO KHÔNG nên dùng**: Khi người dùng muốn cập nhật hồ sơ hoặc khi chưa biết `user_id`.
* **Điều kiện tiên quyết**: Đã có `user_id`.
* **Loại thao tác**: Đọc (Read).
* **Thay đổi trạng thái hệ thống**: **KHÔNG**.

### 3.2 Input Schema
```json
{
  "$schema": "http://json-schema.org/draft-07/schema#",
  "type": "object",
  "properties": {
    "user_id": {
      "type": "string",
      "minLength": 1,
      "description": "ID duy nhất của hồ sơ cần lấy."
    }
  },
  "required": ["user_id"]
}
```

### 3.3 Output Schema
```json
{
  "type": "object",
  "properties": {
    "found": { "type": "boolean", "example": true },
    "matching_ready": { "type": "boolean", "example": true },
    "profile": {
      "type": "object",
      "properties": {
        "user_id": { "type": "string" },
        "age": { "type": "integer" },
        "location": { "type": "string" },
        "relationship_intent": { "type": "string" },
        "interests": { "type": "array", "items": { "type": "string" } },
        "values": { "type": "array", "items": { "type": "string" } }
      }
    }
  },
  "required": ["found", "matching_ready", "profile"]
}
```

### 3.4 Validation Rules
1. `user_id` không rỗng sau khi trim khoảng trắng.

### 3.5 Failure Model
* **Lỗi có thể gặp**: `ValueError` ("Chưa có hồ sơ cho user_id='...'. Hãy gọi save_user_profile trước.").
* **Xử lý phía Agent**: Thông báo cho người dùng biết hồ sơ chưa tồn tại và mời nhập thông tin để tạo hồ sơ mới.

### 3.6 Examples

#### Example 1: Thành công
* **User Request**: "Kiểm tra hồ sơ của user_101 giúp tôi."
* **Agent Reasoning Summary**: Truy vấn hồ sơ `user_101`. Gọi `get_user_profile`.
* **Selected Tool**: `get_user_profile`
* **Tool Arguments**: `{"user_id": "user_101"}`
* **Tool Result**:
  ```json
  {
    "found": true,
    "matching_ready": true,
    "profile": {
      "user_id": "user_101",
      "age": 24,
      "location": "Hà Nội",
      "relationship_intent": "long_term",
      "interests": ["đọc sách", "chạy bộ"],
      "values": ["trung thực", "gia đình"]
    }
  }
  ```
* **Final Response**: "Hồ sơ của bạn (`user_101`):\n- Tuổi: 24\n- Vị trí: Hà Nội\n- Mục tiêu: Mối quan hệ lâu dài\n- Sở thích: Đọc sách, chạy bộ\n- Giá trị sống: Trung thực, gia đình\n\nHồ sơ đã hoàn tất và sẵn sàng ghép đôi!"

#### Example 2: Không tìm thấy hồ sơ
* **User Request**: "Xem hồ sơ user_999."
* **Agent Reasoning Summary**: `user_999` chưa được lưu trong bộ nhớ phiên.
* **Selected Tool**: `get_user_profile`
* **Tool Arguments**: `{"user_id": "user_999"}`
* **Tool Result**: `ValueError: Chưa có hồ sơ cho user_id='user_999'. Hãy gọi save_user_profile trước.`
* **Final Response**: "Không tìm thấy hồ sơ cho ID `user_999`. Bạn vui lòng cung cấp thông tin để tạo hồ sơ mới nhé!"

#### Example 3: Đầu vào không hợp lệ
* **User Request**: "Xem giúp hồ sơ của tôi." (Không đưa ID)
* **Agent Reasoning Summary**: Thiếu `user_id`.
* **Selected Tool**: None
* **Final Response**: "Bạn vui lòng cho tôi biết mã `user_id` của bạn để tôi tra cứu hồ sơ giúp bạn nhé!"

#### Example 4: Agent quyết định KHÔNG gọi tool
* **User Request**: "Cập nhật tuổi của user_101 thành 25."
* **Agent Reasoning Summary**: Yêu cầu chỉnh sửa hồ sơ. Cần thu thập thông tin đầy đủ để gọi `save_user_profile`.
* **Selected Tool**: None

---

## 4. Tool: find_demo_matches

### 4.1 Tool Description
* **Mục đích**: Phân tích, chấm điểm tương thích (thang 100 điểm) và lọc ra top các ứng viên giả lập từ `DEMO_PROFILES` phù hợp nhất với người dùng.
* **Khi NÀO nên dùng**: Khi người dùng yêu cầu tìm ứng viên phù hợp và đã có hồ sơ trong bộ nhớ phiên.
* **Khi NÀO KHÔNG nên dùng**: Khi người dùng chưa tạo hồ sơ hoặc khi muốn giải thích sâu 1 ứng viên cụ thể.
* **Điều kiện tiên quyết**: Hồ sơ `user_id` đã được lưu bằng `save_user_profile`.
* **Loại thao tác**: Lọc & Chấm điểm (Filter & Score).
* **Thay đổi trạng thái hệ thống**: **KHÔNG**.

### 4.2 Input Schema
```json
{
  "$schema": "http://json-schema.org/draft-07/schema#",
  "type": "object",
  "properties": {
    "user_id": {
      "type": "string",
      "minLength": 1,
      "description": "ID hồ sơ người dùng đã lưu."
    },
    "limit": {
      "type": "integer",
      "minimum": 1,
      "maximum": 5,
      "default": 3,
      "description": "Số lượng ứng viên tối đa trả về (từ 1 đến 5)."
    },
    "min_age": {
      "type": ["integer", "null"],
      "minimum": 18,
      "description": "Độ tuổi tối thiểu của ứng viên (tùy chọn)."
    },
    "max_age": {
      "type": ["integer", "null"],
      "maximum": 100,
      "description": "Độ tuổi tối đa của ứng viên (tùy chọn)."
    }
  },
  "required": ["user_id"]
}
```

### 4.3 Output Schema
```json
{
  "type": "object",
  "properties": {
    "user_id": { "type": "string" },
    "is_demo_data": { "type": "boolean", "example": true },
    "scoring_method": {
      "type": "object",
      "properties": {
        "same_relationship_intent": { "type": "integer", "example": 40 },
        "same_location": { "type": "integer", "example": 20 },
        "each_shared_interest": { "type": "integer", "example": 10 },
        "each_shared_value": { "type": "integer", "example": 10 },
        "maximum_score": { "type": "integer", "example": 100 }
      }
    },
    "total_candidates": { "type": "integer" },
    "matches": {
      "type": "array",
      "items": {
        "type": "object",
        "properties": {
          "user_id": { "type": "string" },
          "name": { "type": "string" },
          "age": { "type": "integer" },
          "location": { "type": "string" },
          "relationship_intent": { "type": "string" },
          "score": { "type": "integer" },
          "score_breakdown": {
            "type": "object",
            "properties": {
              "relationship_intent": { "type": "integer" },
              "location": { "type": "integer" },
              "interests": { "type": "integer" },
              "values": { "type": "integer" }
            }
          },
          "shared_interests": { "type": "array", "items": { "type": "string" } },
          "shared_values": { "type": "array", "items": { "type": "string" } },
          "age_difference": { "type": "integer" }
        }
      }
    },
    "message": { "type": "string" }
  },
  "required": ["user_id", "is_demo_data", "scoring_method", "total_candidates", "matches", "message"]
}
```

### 4.4 Matching and Scoring Logic (Công thức Python `_score_candidate`)

Tổng điểm ghép đôi tối đa **100 điểm** được tính theo 4 tiêu chí định lượng:

$$Score_{total} = Score_{intent} + Score_{location} + Score_{interests} + Score_{values}$$

#### Chi tiết bảng điểm:
1. **Ý định mối quan hệ (`relationship_intent`)**:
   * Trùng khớp = **40 điểm**. Khác nhau = **0 điểm**.
2. **Thành phố / Địa điểm (`location`)**:
   * Cùng địa điểm (chuẩn hóa tiếng Việt) = **20 điểm**. Khác = **0 điểm**.
3. **Sở thích chung (`interests`)**:
   * Mỗi sở thích chung = **10 điểm** (Tối đa 2 sở thích $\rightarrow$ Max **20 điểm**).
4. **Giá trị sống chung (`values`)**:
   * Mỗi giá trị chung = **10 điểm** (Tối đa 2 giá trị $\rightarrow$ Max **20 điểm**).

#### Sắp xếp xếp hạng:
1. Điểm `score` **giảm dần** (`-item["score"]`).
2. Chênh lệch tuổi `age_difference` **tăng dần** (`item["age_difference"]`).
3. Tên ứng viên `name` **tăng dần theo alphabet** (`item["name"]`).

### 4.5 Validation Rules
1. `limit`: Số nguyên $1 \le limit \le 5$.
2. `min_age` & `max_age`: Nếu truyền, bắt buộc $18 \le min\_age \le max\_age \le 100$.

### 4.6 Failure Model
* **Lỗi có thể gặp**: `ValueError` (Chưa tạo hồ sơ `user_id`, `limit` sai range, `min_age > max_age`).
* **Xử lý phía Agent**: Báo lỗi cụ thể, hướng dẫn mở rộng tuổi nếu không tìm thấy ứng viên.

### 4.7 Examples

#### Example 1: Thành công
* **User Request**: "Tìm 2 ứng viên phù hợp nhất với user_101 từ 20 đến 25 tuổi."
* **Agent Reasoning Summary**: Gọi `find_demo_matches` cho `user_101` với `limit = 2`, `min_age = 20`, `max_age = 25`.
* **Selected Tool**: `find_demo_matches`
* **Tool Arguments**: `{"user_id": "user_101", "limit": 2, "min_age": 20, "max_age": 25}`
* **Tool Result**:
  ```json
  {
    "user_id": "user_101",
    "is_demo_data": true,
    "scoring_method": {
      "same_relationship_intent": 40,
      "same_location": 20,
      "each_shared_interest": 10,
      "each_shared_value": 10,
      "maximum_score": 100
    },
    "total_candidates": 3,
    "matches": [
      {
        "user_id": "demo_01",
        "name": "Linh",
        "age": 23,
        "location": "Hà Nội",
        "relationship_intent": "long_term",
        "score": 90,
        "score_breakdown": {
          "relationship_intent": 40,
          "location": 20,
          "interests": 10,
          "values": 20
        },
        "shared_interests": ["đọc sách"],
        "shared_values": ["trung thực", "gia đình"],
        "age_difference": 1
      }
    ],
    "message": "Đây là kết quả từ hồ sơ giả lập phục vụ demo."
  }
  ```
* **Final Response**: "Kết quả ghép đôi hàng đầu cho bạn:\n- **Linh (23 tuổi, Hà Nội)** - Điểm tương thích: **90/100**\n  + Cùng tìm kiếm mối quan hệ lâu dài (40đ)\n  + Cùng sinh sống tại Hà Nội (20đ)\n  + Sở thích chung: Đọc sách (10đ)\n  + Giá trị sống chung: Trung thực, Gia đình (20đ)\n\n*(Lưu ý: Dữ liệu giả lập demo)*"

#### Example 2: Lỗi bộ lọc tuổi (`min_age > max_age`)
* **User Request**: "Tìm ứng viên cho user_101 trong độ tuổi 30 đến 20."
* **Agent Reasoning Summary**: `min_age = 30` lớn hơn `max_age = 20`.
* **Selected Tool**: `find_demo_matches`
* **Tool Arguments**: `{"user_id": "user_101", "min_age": 30, "max_age": 20}`
* **Tool Result**: `ValueError: min_age không được lớn hơn max_age.`
* **Final Response**: "Khoảng tuổi tìm kiếm không hợp lệ (`min_age` lớn hơn `max_age`). Bạn vui lòng điều chỉnh lại bộ lọc tuổi."

#### Example 3: Lỗi người dùng chưa tạo hồ sơ
* **User Request**: "Tìm đối tượng cho user_newbie."
* **Agent Reasoning Summary**: `user_newbie` chưa từng lưu hồ sơ.
* **Selected Tool**: `find_demo_matches`
* **Tool Arguments**: `{"user_id": "user_newbie"}`
* **Tool Result**: `ValueError: Chưa có hồ sơ cho user_id='user_newbie'. Hãy gọi save_user_profile trước.`
* **Final Response**: "Bạn chưa tạo hồ sơ cá nhân. Vui lòng cập nhật hồ sơ trước khi thực hiện ghép đôi nhé!"

#### Example 4: Agent quyết định KHÔNG gọi tool
* **User Request**: "Tại sao Linh lại đạt 90 điểm với tôi?"
* **Agent Reasoning Summary**: Yêu cầu giải thích chi tiết 1 đối tượng. Chuyển sang gọi `generate_match_explanation`.
* **Selected Tool**: None

---

## 5. Tool: generate_match_explanation

### 5.1 Tool Description
* **Mục đích**: So sánh chi tiết dữ liệu giữa `user_id` và `candidate_user_id`. Trả về điểm số, nhãn mức độ phù hợp (`score_label`), danh sách điểm mạnh (`strengths`), điểm khác biệt (`differences`), câu gợi mở trò chuyện (`suggested_question`) và tuyên bố miễn trừ trách nhiệm (`disclaimer`).
* **Khi NÀO nên dùng**: Khi người dùng chọn 1 ứng viên cụ thể và muốn biết lý do chi tiết vì sao phù hợp.
* **Khi NÀO KHÔNG nên dùng**: Khi người dùng chưa có `candidate_user_id` hoặc muốn xem danh sách tổng quát.
* **Điều kiện tiên quyết**: Có `user_id` đã lưu và `candidate_user_id` tồn tại trong `DEMO_PROFILES`.
* **Loại thao tác**: Phân tích & Giải thích (Analyze & Explain).
* **Thay đổi trạng thái hệ thống**: **KHÔNG**.

### 5.2 Input Schema
```json
{
  "$schema": "http://json-schema.org/draft-07/schema#",
  "type": "object",
  "properties": {
    "candidate_user_id": {
      "type": "string",
      "description": "ID ứng viên giả lập."
    },
    "user_id": {
      "type": "string",
      "minLength": 1,
      "description": "ID người dùng chính."
    }
  },
  "required": ["candidate_user_id", "user_id"]
}
```

### 5.3 Output Schema
```json
{
  "type": "object",
  "properties": {
    "user_id": { "type": "string" },
    "candidate_user_id": { "type": "string" },
    "candidate_name": { "type": "string" },
    "score": { "type": "integer" },
    "score_label": { 
      "type": "string", 
      "enum": ["phù hợp cao", "khá phù hợp", "cần tìm hiểu thêm"] 
    },
    "strengths": { "type": "array", "items": { "type": "string" } },
    "differences": { "type": "array", "items": { "type": "string" } },
    "suggested_question": { "type": "string" },
    "disclaimer": { "type": "string" }
  },
  "required": [
    "user_id", "candidate_user_id", "candidate_name", 
    "score", "score_label", "strengths", "differences", 
    "suggested_question", "disclaimer"
  ]
}
```

### 5.4 Validation Rules & Gán Nhãn (`score_label`)
Quy tắc gán nhãn dựa trên tổng điểm `score`:
* $score \ge 70$: `"phù hợp cao"`
* $score \ge 50$: `"khá phù hợp"`
* $score < 50$: `"cần tìm hiểu thêm"`

### 5.5 Failure Model
* **Lỗi có thể gặp**: `ValueError` (Không tìm thấy `user_id` hoặc không tìm thấy `candidate_user_id`).
* **Xử lý phía Agent**: Thông báo cho người dùng mã ứng viên không tồn tại, tuyệt đối không tự bịa thông tin giải thích.

### 5.6 Examples

#### Example 1: Thành công
* **User Request**: "Phân tích vì sao demo_01 phù hợp với user_101."
* **Agent Reasoning Summary**: Đã có `user_id = user_101` và `candidate_user_id = demo_01`. Tiến hành gọi `generate_match_explanation`.
* **Selected Tool**: `generate_match_explanation`
* **Tool Arguments**: `{"user_id": "user_101", "candidate_user_id": "demo_01"}`
* **Tool Result**:
  ```json
  {
    "user_id": "user_101",
    "candidate_user_id": "demo_01",
    "candidate_name": "Linh",
    "score": 90,
    "score_label": "phù hợp cao",
    "strengths": [
      "Hai bạn có cùng định hướng mối quan hệ.",
      "Hai bạn đang ở cùng khu vực.",
      "Sở thích chung: đọc sách.",
      "Giá trị sống chung: trung thực, gia đình."
    ],
    "differences": [],
    "suggested_question": "Bạn thích điều gì nhất ở hoạt động đọc sách?",
    "disclaimer": "Điểm số chỉ dựa trên dữ liệu giả lập và là thông tin tham khảo."
  }
  ```
* **Final Response**: "Phân tích độ tương thích với **Linh (demo_01)**:\n- **Điểm tương thích**: 90/100 (**phù hợp cao**)\n- **Điểm mạnh**: Cùng định hướng lâu dài, sinh sống tại Hà Nội, cùng sở thích đọc sách và các giá trị trung thực, gia đình.\n- **Gợi ý mở lời**: *'Bạn thích điều gì nhất ở hoạt động đọc sách?'*\n\n📌 *Disclaimer: Điểm số chỉ dựa trên dữ liệu giả lập và là thông tin tham khảo.*"

#### Example 2: Không tìm thấy ứng viên
* **User Request**: "Giải thích ghép đôi giữa user_101 và demo_99."
* **Agent Reasoning Summary**: Ứng viên `demo_99` không tồn tại trong `DEMO_PROFILES`.
* **Selected Tool**: `generate_match_explanation`
* **Tool Arguments**: `{"user_id": "user_101", "candidate_user_id": "demo_99"}`
* **Tool Result**: `ValueError: Không tìm thấy ứng viên 'demo_99'.`
* **Final Response**: "Không tìm thấy mã ứng viên `demo_99` trong tập dữ liệu demo. Vui lòng kiểm tra lại ID ứng viên!"

#### Example 3: Lỗi người dùng chưa có hồ sơ
* **User Request**: "Giải thích ghép đôi cho user_ghost và demo_01."
* **Agent Reasoning Summary**: `user_ghost` chưa lưu hồ sơ trong bộ nhớ phiên.
* **Selected Tool**: `generate_match_explanation`
* **Tool Arguments**: `{"user_id": "user_ghost", "candidate_user_id": "demo_01"}`
* **Tool Result**: `ValueError: Chưa có hồ sơ cho user_id='user_ghost'. Hãy gọi save_user_profile trước.`
* **Final Response**: "Người dùng `user_ghost` chưa tạo hồ sơ nên hệ thống chưa thể thực hiện so sánh."

#### Example 4: Agent quyết định KHÔNG gọi tool
* **User Request**: "Tìm đối tượng khác giúp tôi."
* **Agent Reasoning Summary**: Yêu cầu tìm kiếm danh sách ứng viên mới. Chuyển sang gọi `find_demo_matches`.
* **Selected Tool**: None

---

## 6. Tool Selection Matrix

| Ý định của Người dùng | Tool lựa chọn | Tool KHÔNG chọn | Ghi chú & Điều kiện |
| :--- | :--- | :--- | :--- |
| Nhập / Cập nhật thông tin cá nhân | `save_user_profile` | `get_user_profile` | Cần đủ 5 nhóm thông tin cá nhân. |
| Xem lại thông tin cá nhân | `get_user_profile` | `save_user_profile` | Đã có `user_id`. |
| Tìm danh sách đối tượng phù hợp | `find_demo_matches` | `generate_match_explanation` | Cần có hồ sơ đã lưu trước đó. |
| Phân tích chi tiết 1 đối tượng cụ thể | `generate_match_explanation` | `find_demo_matches` | Cần cả `user_id` và `candidate_user_id`. |

---

## 7. Tool Execution Workflows

```text
Luồng 1: Người dùng mới
[Cung cấp thông tin] ──> save_user_profile ──> find_demo_matches ──> Trả danh sách gợi ý

Luồng 2: Tìm kiếm ghép đôi
get_user_profile ──> (Đã có hồ sơ) ──> find_demo_matches ──> Trình bày danh sách ứng viên

Luồng 3: Giải thích kết quả ghép đôi 1-1
get_user_profile ──> (Đã có hồ sơ) ──> generate_match_explanation ──> Trình bày phân tích & Disclaimer
```

---

## 8. Privacy and Safety Rules

1. **Bảo mật dữ liệu demo**: Chỉ sử dụng dữ liệu giả lập từ `config/demo_profiles.json`. Không cố gắng thu thập hoặc suy đoán dữ liệu người thật ngoài đời.
2. **Tương thích định lượng (Anti-Hallucination)**: Tuyệt đối không tự suy đoán điểm số hoặc câu hỏi mở đầu. Mọi số liệu bắt buộc phải lấy từ kết quả trả về của hàm Python `_score_candidate`.
3. **Disclaimer bắt buộc**: Trong các câu phản hồi giải thích hoặc gợi ý ghép đôi, luôn hiển thị thông điệp disclaimer: *"Dữ liệu giả lập phục vụ mục đích demo."*

---

## 9. Complete Agent System Prompt

```markdown
You are Cupid Agent, an expert AI Matchmaking Assistant. You assist users in finding compatible dating profiles based on simulated candidate data (`DEMO_PROFILES`).

### OPERATIONAL MANDATES:

1. DATA COLLECTION & SAVING:
   - When a user provides their personal details, call `save_user_profile`.
   - Ensure all parameters are present: `user_id`, `age` (18-100), `location`, `relationship_intent` ('casual_dating' | 'long_term' | 'marriage'), `interests` (1-10 items), and `values` (1-10 items).
   - NEVER invent or guess any user attribute. If missing, explicitly prompt the user.

2. MATCHMAKING & EXPLANATION EXECUTION:
   - Use `find_demo_matches` to search and rank compatible candidates once a profile is saved.
   - Use `generate_match_explanation` to provide deep analysis for a specific `candidate_user_id`.
   - NEVER invent compatibility scores. Strictly use the exact numeric values returned by tool outputs.

3. ERROR HANDLING & RETRY POLICY:
   - If `save_user_profile` or `get_user_profile` raises a ValueError indicating missing profile data, instruct the user to complete their profile first.
   - Do NOT retry tools with identical invalid arguments when receiving validation errors.

4. SAFETY & DISCLAIMERS:
   - Always clarify that candidate data is simulated for demo purposes.
   - Include the mandatory disclaimer on explanation responses: "Điểm số chỉ dựa trên dữ liệu giả lập và là thông tin tham khảo."
   - Maintain a respectful, friendly, encouraging, and non-judgmental tone.
```

---

## 10. Complete JSON Tool Definitions

```json
[
  {
    "type": "function",
    "function": {
      "name": "save_user_profile",
      "description": "Lưu riêng hồ sơ tối thiểu của một người dùng theo user_id.",
      "parameters": {
        "type": "object",
        "properties": {
          "user_id": { "type": "string", "minLength": 1, "description": "ID duy nhất dùng để lưu hồ sơ." },
          "age": { "type": "integer", "minimum": 18, "maximum": 100, "description": "Tuổi người dùng (18-100)." },
          "location": { "type": "string", "minLength": 1, "description": "Thành phố hoặc khu vực sinh sống." },
          "relationship_intent": {
            "type": "string",
            "enum": ["casual_dating", "long_term", "marriage"],
            "description": "Ý định mối quan hệ (hẹn hò / lâu dài / kết hôn)."
          },
          "interests": {
            "type": ["array", "string"],
            "description": "Từ 1 đến 10 sở thích (dạng mảng hoặc chuỗi cách dấu phẩy)."
          },
          "values": {
            "type": ["array", "string"],
            "description": "Từ 1 đến 10 giá trị sống (dạng mảng hoặc chuỗi cách dấu phẩy)."
          }
        },
        "required": ["user_id", "age", "location", "relationship_intent", "interests", "values"],
        "additionalProperties": false
      }
    }
  },
  {
    "type": "function",
    "function": {
      "name": "get_user_profile",
      "description": "Lấy hồ sơ đã lưu riêng của một người dùng theo user_id.",
      "parameters": {
        "type": "object",
        "properties": {
          "user_id": { "type": "string", "minLength": 1, "description": "ID hồ sơ cần xem." }
        },
        "required": ["user_id"],
        "additionalProperties": false
      }
    }
  },
  {
    "type": "function",
    "function": {
      "name": "find_demo_matches",
      "description": "Tìm và chấm điểm các hồ sơ giả lập phù hợp nhất.",
      "parameters": {
        "type": "object",
        "properties": {
          "user_id": { "type": "string", "minLength": 1, "description": "ID hồ sơ đã lưu." },
          "limit": { "type": "integer", "minimum": 1, "maximum": 5, "default": 3, "description": "Số ứng viên cần lấy (1-5)." },
          "min_age": { "type": ["integer", "null"], "minimum": 18, "description": "Tuổi ứng viên tối thiểu." },
          "max_age": { "type": ["integer", "null"], "maximum": 100, "description": "Tuổi ứng viên tối đa." }
        },
        "required": ["user_id"],
        "additionalProperties": false
      }
    }
  },
  {
    "type": "function",
    "function": {
      "name": "generate_match_explanation",
      "description": "Giải thích điểm mạnh và khác biệt của một cặp ghép đôi.",
      "parameters": {
        "type": "object",
        "properties": {
          "user_id": { "type": "string", "minLength": 1, "description": "ID người dùng hiện tại." },
          "candidate_user_id": { "type": "string", "description": "ID ứng viên từ kết quả find_demo_matches." }
        },
        "required": ["user_id", "candidate_user_id"],
        "additionalProperties": false
      }
    }
  }
]
```
