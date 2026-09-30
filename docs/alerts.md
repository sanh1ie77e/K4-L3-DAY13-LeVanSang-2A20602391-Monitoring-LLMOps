# Template Alert và Runbook

Mỗi alert phải dựa trên triệu chứng người dùng hoặc SLO, không dựa trực tiếp vào tên implementation nội bộ.

## Alert mẫu để tham khảo

Ví dụ dưới đây minh họa mức độ cụ thể cần có. Học viên không cần copy nguyên, nhưng ba alert trong bài nộp nên rõ ràng tương tự: điều kiện là gì, kéo dài bao lâu, ảnh hưởng tới user ra sao và người trực cần kiểm tra gì trước.

- Tên: `HighLatencyP95`
- Severity: `warning`
- Duration: `5m`
- Kênh thông báo: Slack `#k4-l3b-alerts`
- SLI/SLO liên quan: latency P95 của `response_sent.latency_ms`
- Điều kiện và thời gian duy trì: `p95(latency_ms) > 3000ms` trong 5 phút
- Ảnh hưởng tới người dùng: người dùng phải chờ lâu hơn trước khi nhận câu trả lời
- Ba bước kiểm tra đầu tiên:
  1. Mở dashboard latency để xác nhận P95/P99 và khoảng thời gian tăng.
  2. Lọc `data/logs.jsonl` trong khoảng đó, lấy một `correlation_id` có `latency_ms` cao.
  3. Mở trace cùng `correlation_id` trên Langfuse, so sánh các span chính để xác định bước nào bất thường.
- Mitigation tạm thời: dựa trên evidence thực tế để rollback prompt, khôi phục cấu hình liên quan, tắt practice scenario hoặc giảm tải khi demo.
- Owner: `student-<MSSV>`

## Alert 1

- Tên: `HighLatencyP95`
- Severity: `warning`
- Duration: `5m`
- Kênh thông báo: Slack `#k4-l3b-alerts`
- SLI/SLO liên quan: latency P95 của event `response_sent`, SLO latency không quá 3000 ms.
- Điều kiện và thời gian duy trì: `p95(response_sent.latency_ms) > 3000` liên tục trong 5 phút.
- Ảnh hưởng tới người dùng: người dùng phải chờ lâu hơn trước khi nhận được câu trả lời.
- Ba bước kiểm tra đầu tiên:
  1. Mở panel Latency, xác nhận P95/P99, TTFT và khoảng thời gian tăng.
  2. Lọc `data/logs.jsonl` trong khoảng đó và chọn một `correlation_id` có `latency_ms` cao.
  3. Mở trace cùng `correlation_id`, so sánh thời gian của `retrieval` và `generation` để xác định bước chậm.
- Mitigation tạm thời: rollback prompt nếu sự cố bắt đầu sau khi promote; nếu retrieval chậm thì khôi phục cấu hình hoặc tắt scenario gây chậm; giảm tải khi cần.
- Owner: `student-2A202602391`

## Alert 2

- Tên: `HighErrorRate`
- Severity: `critical`
- Duration: `5m`
- Kênh thông báo: Slack `#k4-l3b-alerts`
- SLI/SLO liên quan: tỉ lệ request thành công trong SLO `fast_successful_requests`.
- Điều kiện và thời gian duy trì: `error_rate_pct > 2` liên tục trong 5 phút.
- Ảnh hưởng tới người dùng: nhiều request không nhận được câu trả lời hợp lệ.
- Ba bước kiểm tra đầu tiên:
  1. Mở panel Errors, xác nhận error rate và breakdown theo `error_type`.
  2. Lọc event `request_failed` trong log và lấy một `correlation_id` đại diện.
  3. Mở trace cùng `correlation_id`, tìm observation có trạng thái lỗi và đọc status message.
- Mitigation tạm thời: rollback thay đổi gần nhất, tắt incident scenario nếu đang thực hành, hoặc chuyển sang fallback an toàn trong khi điều tra dependency lỗi.
- Owner: `student-2A202602391`

## Alert 3

- Tên: `LowRetrievalSuccess`
- Severity: `warning`
- Duration: `5m`
- Kênh thông báo: Slack `#k4-l3b-alerts`
- SLI/SLO liên quan: guardrail retrieval success tối thiểu 90%.
- Điều kiện và thời gian duy trì: `retrieval_success_rate_pct < 90` liên tục trong 5 phút.
- Ảnh hưởng tới người dùng: câu trả lời thiếu context hoặc request thất bại khi truy xuất tài liệu.
- Ba bước kiểm tra đầu tiên:
  1. Mở panel Errors và xác nhận retrieval success giảm trong khoảng thời gian nào.
  2. Lọc log theo `tool_name=retrieval` và `tool_success=false`, lấy một `correlation_id`.
  3. Mở trace cùng `correlation_id`, kiểm tra observation `retrieval` và so sánh với `generation`.
- Mitigation tạm thời: kiểm tra/khôi phục nguồn dữ liệu retrieval, tắt scenario gây lỗi và dùng fallback document nếu được phép.
- Owner: `student-2A202602391`
