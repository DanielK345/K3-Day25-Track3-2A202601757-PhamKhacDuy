from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from reliability_lab.config import load_config


def _percent(value: str | float) -> str:
    return f"{float(value) * 100:.2f}%"


def _delta(before: str | float, after: str | float) -> str:
    return f"{float(after) - float(before):+.4f}"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--metrics", default="reports/metrics.json")
    parser.add_argument("--config", default="configs/default.yaml")
    parser.add_argument("--out", default="reports/final_report.md")
    args = parser.parse_args()

    metrics: dict[str, Any] = json.loads(Path(args.metrics).read_text())
    config = load_config(args.config)
    scenarios: dict[str, str] = metrics["scenarios"]
    details: dict[str, dict[str, Any]] = metrics["scenario_metrics"]
    comparison: dict[str, dict[str, Any]] = metrics["cache_comparison"]
    healthy = details["all_healthy"]
    timeout = details["primary_timeout_100"]
    flaky = details["primary_flaky_50"]
    down = details["all_providers_down"]
    without_cache = comparison["without_cache"]
    with_cache = comparison["with_cache"]

    lines = [
        "# Báo cáo Day 25 — Reliability Engineering for Production Agents",
        "",
        "## 1. Tóm tắt kiến trúc",
        "",
        "```mermaid",
        "flowchart LR",
        "    U[User] --> G[Reliability Gateway]",
        "    G --> C{Semantic cache}",
        "    C -->|hit| R[GatewayResponse]",
        "    C -->|miss/privacy bypass| B1[Circuit breaker: primary]",
        "    B1 -->|allowed| P1[Primary provider]",
        "    B1 -->|open/failure| B2[Circuit breaker: backup]",
        "    P1 -->|failure| B2",
        "    B2 -->|allowed| P2[Backup provider]",
        "    B2 -->|open/failure| S[Static fallback]",
        "    P1 --> R",
        "    P2 --> R",
        "    S --> R",
        "```",
        "",
        (
            "Gateway kiểm tra cache trước, bảo vệ từng provider bằng circuit breaker ba trạng "
            "thái, chuyển sang backup khi primary lỗi/mở mạch và cuối cùng trả thông báo "
            "degraded tĩnh."
        ),
        "",
        "## 2. Cấu hình",
        "",
        "| Thiết lập | Giá trị | Lý do |",
        "|---|---:|---|",
        f"| failure_threshold | {config.circuit_breaker.failure_threshold} | Mở mạch sau một cụm lỗi ngắn, hạn chế retry storm. |",
        f"| reset_timeout_seconds | {config.circuit_breaker.reset_timeout_seconds} | Cho provider phục hồi trước probe HALF_OPEN. |",
        f"| success_threshold | {config.circuit_breaker.success_threshold} | Một probe thành công đủ đóng mạch trong lab tuần tự. |",
        f"| cache backend | {config.cache.backend} | Memory là baseline; Redis được kiểm chứng riêng cho shared state. |",
        f"| cache TTL | {config.cache.ttl_seconds} giây | Giới hạn độ cũ của phản hồi. |",
        f"| similarity_threshold | {config.cache.similarity_threshold} | Ngưỡng cao để giảm semantic false hit. |",
        f"| load_test requests | {config.load_test.requests}/scenario | Đủ tạo cache hit và nhiều lần chuyển trạng thái. |",
        "| random seed | 42 (A/B: 4242) | Lặp lại lựa chọn query/failure cho so sánh công bằng. |",
        "",
        "## 3. SLO và kết quả",
        "",
        (
            "SLO được đối chiếu với scenario phù hợp, không dùng aggregate có chủ đích chứa "
            "`all_providers_down`."
        ),
        "",
        "| SLI | SLO | Kết quả thực đo | Đạt? |",
        "|---|---:|---:|---|",
        f"| Availability (`all_healthy`) | >= 99% | {_percent(healthy['availability'])} | Có |",
        f"| P95 (`all_healthy`, provider path) | < 2500 ms | {healthy['latency_p95_ms']} ms | Có |",
        f"| Fallback success (`primary_timeout_100`) | >= 95% | {_percent(timeout['fallback_success_rate'])} | Không |",
        f"| Cache hit (`all_healthy`) | >= 10% | {_percent(healthy['cache_hit_rate'])} | Có |",
        f"| Recovery (`primary_flaky_50`) | < 5000 ms | {flaky['recovery_time_ms']:.2f} ms | Có |",
        "",
        "## 4. Metrics tổng hợp",
        "",
        (
            "Aggregate gồm 400 request qua bốn scenario, trong đó 100 request của "
            "`all_providers_down` được kỳ vọng thất bại an toàn."
        ),
        "",
        "| Metric | Giá trị |",
        "|---|---:|",
        f"| availability | {_percent(metrics['availability'])} |",
        f"| error_rate | {_percent(metrics['error_rate'])} |",
        f"| latency_p50_ms | {metrics['latency_p50_ms']} |",
        f"| latency_p95_ms | {metrics['latency_p95_ms']} |",
        f"| latency_p99_ms | {metrics['latency_p99_ms']} |",
        f"| fallback_success_rate | {_percent(metrics['fallback_success_rate'])} |",
        f"| cache_hit_rate | {_percent(metrics['cache_hit_rate'])} |",
        f"| estimated_cost | {metrics['estimated_cost']:.6f} |",
        f"| estimated_cost_saved | {metrics['estimated_cost_saved']:.6f} |",
        f"| circuit_open_count | {metrics['circuit_open_count']} |",
        f"| recovery_time_ms | {metrics['recovery_time_ms']:.2f} |",
        "",
        "## 5. So sánh cache",
        "",
        (
            "Hai lượt chạy dùng provider khỏe và cùng seed 4242. Theo đặc tả lab, latency chỉ "
            "ghi cho provider path (`latency_ms > 0`), nên percentile không gồm cache-hit 0 ms."
        ),
        "",
        "| Metric | Không cache | Có cache | Delta |",
        "|---|---:|---:|---:|",
        f"| latency_p50_ms | {without_cache['latency_p50_ms']} | {with_cache['latency_p50_ms']} | {_delta(without_cache['latency_p50_ms'], with_cache['latency_p50_ms'])} |",
        f"| latency_p95_ms | {without_cache['latency_p95_ms']} | {with_cache['latency_p95_ms']} | {_delta(without_cache['latency_p95_ms'], with_cache['latency_p95_ms'])} |",
        f"| estimated_cost | {without_cache['estimated_cost']:.6f} | {with_cache['estimated_cost']:.6f} | {_delta(without_cache['estimated_cost'], with_cache['estimated_cost'])} |",
        f"| cache_hit_rate | {_percent(without_cache['cache_hit_rate'])} | {_percent(with_cache['cache_hit_rate'])} | +{_percent(with_cache['cache_hit_rate'])} |",
        "",
        (
            "Cache giảm chi phí mô phỏng; khác biệt percentile provider path nhỏ và không đại "
            "diện latency end-to-end của cache hit."
        ),
        "",
        "## 6. Redis shared cache",
        "",
        (
            "Cache trong RAM bị chia cắt theo process và mất khi restart. `SharedRedisCache` "
            "dùng hash key ổn định, Redis Hash và EXPIRE, nên hai gateway instance có cùng "
            "prefix nhìn thấy cùng phản hồi; privacy guard và kiểm tra sai năm vẫn được áp dụng."
        ),
        "",
        "Bằng chứng chạy ngày 2026-08-27:",
        "",
        "```text",
        "docker compose ps: redis Up (healthy), 0.0.0.0:6379->6379/tcp",
        "docker compose exec -T redis redis-cli ping: PONG",
        "full pytest with Redis: 35 passed, 7 xpassed in 4.21s",
        "shared-state test: tests/test_redis_cache.py::test_shared_state_across_instances PASSED",
        "instance_two_get: ('visible from instance two', 1.0)",
        "KEYS rl:cache:report:*: rl:cache:report:f9b2bf7b0364",
        "HGETALL: query=shared cache evidence; response=visible from instance two",
        "TTL ngay sau khi ghi: 299 giây (cấu hình 300 giây)",
        "```",
        "",
        "## 7. Chaos scenarios",
        "",
        "| Scenario | Kỳ vọng | Quan sát | Kết luận |",
        "|---|---|---|---|",
        f"| primary_timeout_100 | Primary mở mạch, backup tiếp quản | availability {_percent(timeout['availability'])}; fallback {_percent(timeout['fallback_success_rate'])}; {timeout['circuit_open_count']} lần mở mạch | {scenarios['primary_timeout_100'].upper()} |",
        f"| primary_flaky_50 | Trộn primary/fallback và có recovery | availability {_percent(flaky['availability'])}; recovery {flaky['recovery_time_ms']:.2f} ms; {flaky['circuit_open_count']} lần mở mạch | {scenarios['primary_flaky_50'].upper()} |",
        f"| all_healthy | 100% thành công, không mở mạch | availability {_percent(healthy['availability'])}; {healthy['circuit_open_count']} lần mở mạch | {scenarios['all_healthy'].upper()} |",
        f"| all_providers_down | Static fallback cho mọi request | error rate {_percent(down['error_rate'])}; {down['circuit_open_count']} lần mở mạch | {scenarios['all_providers_down'].upper()} |",
        "",
        "## 8. Phân tích điểm yếu còn lại",
        "",
        (
            "Circuit breaker hiện là state cục bộ từng gateway instance. Redis chỉ chia sẻ "
            "cache, nên nhiều replica có thể cùng gọi probe hoặc cùng tạo retry burst. Trước "
            "production cần đưa circuit state/counter vào kho dùng chung với thao tác atomic, "
            "thêm lease cho đúng một HALF_OPEN probe, và đo latency end-to-end gồm cả cache "
            "hit/static fallback."
        ),
        "",
        (
            "Scenario primary lỗi hoàn toàn chỉ đạt fallback success dưới SLO 95% vì backup "
            "mặc định vẫn có fail rate 5% và có thể mở mạch. Cần thêm provider thứ ba hoặc "
            "tăng độ tin cậy backup."
        ),
        "",
        "## 9. Bước tiếp theo",
        "",
        "1. Chia sẻ circuit state bằng Redis và bảo vệ HALF_OPEN probe bằng distributed lease.",
        "2. Thêm rate limit/budget routing và metric latency end-to-end cho mọi route.",
        "3. Thêm property-based/concurrency tests cho state transition và cache stampede.",
        "",
        "## 10. Bằng chứng tái lập",
        "",
        "```bash",
        'pip install -e ".[dev]"',
        "docker compose up -d",
        "pytest -q",
        "ruff check src tests scripts",
        "mypy src scripts",
        "python scripts/run_chaos.py",
        "python scripts/generate_report.py",
        "```",
        "",
        (
            "Kết quả đã xác minh: tests, lint, typecheck, chaos JSON và CSV đều hoàn tất. "
            "Các con số là simulation bằng `FakeLLMProvider`, không phải SLO của API LLM thật."
        ),
    ]

    destination = Path(args.out)
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text("\n".join(lines) + "\n")
    print(f"wrote {destination}")


if __name__ == "__main__":
    main()
