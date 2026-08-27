# REFLECT — Reliability Engineering for Production Agents

## 1. Yêu cầu của bài lab

Bài lab yêu cầu xây dựng một lớp reliability cho LLM Agent Gateway, gồm:

- Circuit breaker ba trạng thái: `CLOSED`, `OPEN`, `HALF_OPEN`.
- Pipeline định tuyến: cache → primary provider → backup provider → static fallback.
- Semantic cache sử dụng cosine similarity trên word token và character 3-gram.
- Guardrail không cache dữ liệu nhạy cảm và phát hiện false hit giữa các mốc năm/ID.
- Redis cache dùng chung cho nhiều gateway instance, có TTL.
- Chaos testing và thu thập availability, error rate, P50/P95/P99, cache hit rate,
  fallback success rate, recovery time và chi phí ước tính.
- Xuất kết quả JSON/CSV và viết report dựa trên số liệu chạy thật.

## 2. Cách thức thực hiện

Quá trình triển khai được thực hiện theo thứ tự phụ thuộc giữa các thành phần:

1. Đọc `README.md`, source code, test và các vị trí TODO để xác định contract.
2. Hoàn thiện circuit breaker, bao gồm bộ đếm lỗi/thành công, timeout và transition log.
3. Hoàn thiện cache trong bộ nhớ và Redis với TTL, semantic similarity và privacy guard.
4. Hoàn thiện gateway để thử provider theo thứ tự và trả static fallback khi tất cả đều lỗi.
5. Hoàn thiện chaos runner, recovery-time calculation và CSV export.
6. Thêm seed cố định để các lần chaos test có thể tái lập tương đối.
7. Chạy focused tests trước, sau đó chạy toàn bộ tests, Ruff và mypy strict.
8. Khởi động Redis thật, kiểm tra shared state giữa hai cache instance và chạy lại full tests.
9. Chạy bốn chaos scenario, thực hiện A/B cache bật/tắt và sinh report từ metrics.

Kết quả kiểm chứng cuối cùng:

- Pytest với Redis: `35 passed, 7 xpassed`.
- Ruff: pass.
- mypy strict: pass.
- Bốn chaos scenario đều đạt tiêu chí hành vi đã định nghĩa.
- Scenario primary lỗi hoàn toàn chỉ đạt fallback success `92.86%`, thấp hơn SLO `95%`;
  kết quả này được giữ nguyên trong report thay vì báo cáo sai là đạt SLO.

## 3. Lỗi gặp phải và cách khắc phục

### Không tìm thấy `pytest`

Python hệ thống không có các dependency dev. Môi trường `.venv` đã có dependency runtime
nhưng thiếu `pytest`, `ruff` và `mypy`.

Cách khắc phục:

```bash
.venv/bin/python -m ensurepip --upgrade
.venv/bin/python -m pip install pytest ruff mypy types-PyYAML
```

### `uv run` không hoạt động

Bản `uv` cài qua Snap báo thiếu capability của sandbox. Vì vậy lab được chạy trực tiếp bằng
`.venv/bin/python`, không coi lỗi Snap là lỗi source code.

### Không tải được dependency từ PyPI

Sandbox ban đầu không phân giải được `pypi.org`. Sau khi cấp quyền network phù hợp, dependency
dev và build dependency được cài thành công.

### CLI không import được package `reliability_lab`

Pytest tự thêm `src/` vào Python path nhưng `scripts/run_chaos.py` chạy độc lập thì không. Package
được cài editable theo đúng Quickstart:

```bash
.venv/bin/python -m pip install -e .
```

### Redis tests bị skipped dù container đã chạy

Redis container ở trạng thái healthy nhưng process trong network sandbox không được kết nối
`localhost:6379` và báo `Operation not permitted`. Full tests được chạy trong môi trường được phép
truy cập localhost; kết quả là cả sáu Redis integration tests đều pass.

### Lỗi Ruff và mypy

Ruff phát hiện import chưa sắp xếp, exception quá rộng và cách nối chuỗi trong report generator.
mypy thiếu type stub của PyYAML và phát hiện helper nhận kiểu `object` quá rộng. Các import/type
annotation được sửa rõ ràng và cài thêm `types-PyYAML`, sau đó cả hai công cụ đều pass.

## 4. Setup môi trường và chạy lab

Yêu cầu: Python từ 3.10 trở lên và Docker có Docker Compose.

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -e ".[dev]"
```

Khởi động Redis và chạy toàn bộ validation:

```bash
docker compose up -d
pytest -q
ruff check src tests scripts
mypy src scripts
```

Chạy chaos simulation và sinh report:

```bash
python scripts/run_chaos.py \
  --config configs/default.yaml \
  --out reports/metrics.json \
  --csv-out reports/metrics.csv

python scripts/generate_report.py \
  --metrics reports/metrics.json \
  --config configs/default.yaml \
  --out reports/final_report.md
```

Các artifact chính:

- `reports/metrics.json`: metrics tổng hợp và chi tiết từng scenario.
- `reports/metrics.csv`: một dòng metrics để phân tích bằng spreadsheet/dashboard.
- `reports/final_report.md`: kiến trúc, SLO, chaos results, Redis evidence và failure analysis.

Sau khi hoàn tất có thể dừng Redis:

```bash
docker compose down
```

## 5. Áp dụng vào Agent + RAG trên production

Trong một hệ thống Agent + RAG thực tế, các kiến thức của lab có thể áp dụng như sau:

1. **Bảo vệ từng dependency bằng circuit breaker**: tạo breaker riêng cho LLM, embedding API,
   vector database, reranker và các external tools. Một dịch vụ lỗi không làm toàn bộ agent bị
   treo hoặc retry vô hạn.
2. **Thiết kế fallback theo chất lượng**: LLM chính có thể fallback sang model rẻ hơn; vector DB
   có thể fallback sang lexical search/BM25; nếu retrieval lỗi, agent trả câu trả lời degraded có
   thông báo rõ ràng thay vì tạo nội dung không có căn cứ.
3. **Cache đúng tầng**: cache embedding, retrieval result và final answer bằng Redis để dùng chung
   giữa nhiều replica. Cache key cần bao gồm tenant, phiên bản index, model, prompt template và
   quyền truy cập để tránh trả nhầm dữ liệu.
4. **Áp dụng privacy guard trước khi cache**: không lưu prompt chứa thông tin định danh, bí mật,
   token hoặc dữ liệu nội bộ. Với RAG nhiều tenant, phải kiểm tra ACL trước cả cache lookup và
   cache write.
5. **Chống semantic false hit**: ngoài similarity threshold, cần so khớp entity, thời gian, tenant,
   document version và citation. Khi nguồn dữ liệu thay đổi, cache phải được invalidation theo
   index/document version.
6. **Đo SLI theo từng route**: theo dõi end-to-end latency, retrieval latency, generation latency,
   groundedness, cache hit, fallback rate, circuit state, token cost và tỷ lệ static fallback.
7. **Chaos test trước production**: mô phỏng LLM timeout, vector DB mất kết nối, Redis unavailable,
   tài liệu rỗng và tool trả lỗi để xác minh agent vẫn degrade an toàn.
8. **Chia sẻ reliability state**: khi deploy nhiều replica, cache đã dùng Redis nhưng circuit
   breaker cũng cần distributed state hoặc lease để chỉ một instance thực hiện HALF_OPEN probe,
   tránh retry storm và cache stampede.

Một pipeline production phù hợp có thể là:

```text
Request
  → Authentication / tenant ACL / rate limit
  → Semantic cache
  → Agent orchestrator
      → Retrieval breaker → vector search → BM25 fallback
      → Tool breaker      → tool API       → degraded response
      → LLM breaker       → primary LLM    → cheaper backup LLM
  → Citation/quality guard
  → Response + metrics + trace
```

Bài học quan trọng nhất là production reliability không chỉ có retry. Hệ thống cần giới hạn lỗi,
fallback có kiểm soát, cache an toàn, quan sát được trạng thái và báo cáo trung thực khi chỉ đang
degrade thay vì hoạt động đầy đủ.
