# logs/

Thư mục này lưu **bản sao log** của từng lần chạy backtest, đặt tên theo `run_id`.

## Tại sao có 2 nơi lưu log?

Mỗi lần chạy, `run.py` ghi log vào **2 nơi đồng thời** (dual-logging):

| Nơi lưu | Tên file | Mục đích |
|---|---|---|
| `logs/<run_id>.log` | theo run | **Xem nhanh, so sánh** nhiều run cùng chỗ |
| `result/<run_id>/run.log` | cố định `run.log` | **Self-contained** — log đi kèm với output của run |

Nội dung 2 file là **giống hệt nhau**, chỉ khác nơi lưu.

## Cơ chế (run.py)

```python
logging.FileHandler(log_dir / f"{result_dir.name}.log")  # → logs/<run_id>.log
logging.FileHandler(result_dir / "run.log")               # → result/<run_id>/run.log
```
