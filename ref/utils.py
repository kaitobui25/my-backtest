# utils.py
# ============================================================
# Helper functions: ghi CSV, validate candle, logging setup,
# resample 1min → 3min.
# KHÔNG import pandas ở đây — thuần stdlib + csv module.
# ============================================================

import csv
import os
import logging
import tempfile
import shutil
from datetime import datetime, timezone
from pathlib import Path

from config import DATA_DIR, LOG_DIR, TIMEZONE


# ─────────────────────────────────────────────
# 1. LOGGING SETUP
# ─────────────────────────────────────────────

def setup_logger(name: str = "collector") -> logging.Logger:
    """
    Tạo logger ghi ra cả console lẫn file logs/collector.log.
    Gọi một lần duy nhất ở đầu collector.py.
    """
    Path(LOG_DIR).mkdir(parents=True, exist_ok=True)
    log_path = os.path.join(LOG_DIR, f"{name}.log")

    fmt = "%(asctime)s [%(levelname)s] %(message)s"
    datefmt = "%Y-%m-%d %H:%M:%S"

    logger = logging.getLogger(name)
    logger.setLevel(logging.DEBUG)

    # Console handler
    ch = logging.StreamHandler()
    ch.setLevel(logging.INFO)
    ch.setFormatter(logging.Formatter(fmt, datefmt))

    # File handler
    fh = logging.FileHandler(log_path, encoding="utf-8")
    fh.setLevel(logging.DEBUG)
    fh.setFormatter(logging.Formatter(fmt, datefmt))

    logger.addHandler(ch)
    logger.addHandler(fh)
    return logger


# ─────────────────────────────────────────────
# 2. PATH HELPERS
# ─────────────────────────────────────────────

def get_csv_path(dt: datetime) -> str:
    """
    Trả về đường dẫn file CSV theo tháng.
    Ví dụ: data/raw/XAUUSD_3min_2025-04.csv
    """
    month_str = dt.strftime("%Y-%m")
    Path(DATA_DIR).mkdir(parents=True, exist_ok=True)
    return os.path.join(DATA_DIR, f"XAUUSD_3min_{month_str}.csv")


CSV_HEADER = ["datetime", "open", "high", "low", "close", "volume"]


def ensure_csv_header(path: str) -> None:
    """
    Nếu file chưa tồn tại hoặc rỗng → ghi header.
    Không ghi lại nếu đã có nội dung.
    """
    if not os.path.exists(path) or os.path.getsize(path) == 0:
        with open(path, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow(CSV_HEADER)


# ─────────────────────────────────────────────
# 3. VALIDATE CANDLE
# ─────────────────────────────────────────────

def is_valid_candle(candle: dict) -> bool:
    """
    Kiểm tra nến hợp lệ trước khi ghi:
    - Đủ 6 field
    - open/high/low/close là số dương
    - high >= low, high >= open/close, low <= open/close
    - volume >= 0
    """
    required = {"datetime", "open", "high", "low", "close", "volume"}
    if not required.issubset(candle.keys()):
        return False

    try:
        o = float(candle["open"])
        h = float(candle["high"])
        l = float(candle["low"])
        c = float(candle["close"])
        v = float(candle["volume"])
    except (ValueError, TypeError):
        return False

    if any(x <= 0 for x in [o, h, l, c]):
        return False
    if h < l:
        return False
    if h < o or h < c:
        return False
    if l > o or l > c:
        return False
    if v < 0:
        return False

    return True


# ─────────────────────────────────────────────
# 4. ĐỌC TIMESTAMP CUỐI CÙNG
# ─────────────────────────────────────────────

def get_last_timestamp(path: str) -> datetime | None:
    """
    Đọc dòng cuối cùng của CSV (hiệu quả, không load cả file vào RAM).
    Trả về datetime object (UTC) hoặc None nếu file trống / chưa có data.
    """
    if not os.path.exists(path) or os.path.getsize(path) == 0:
        return None

    last_line = None
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            stripped = line.strip()
            if stripped and stripped != ",".join(CSV_HEADER):
                last_line = stripped

    if last_line is None:
        return None

    try:
        dt_str = last_line.split(",")[0]
        dt = datetime.strptime(dt_str, "%Y-%m-%d %H:%M:%S")
        return dt.replace(tzinfo=timezone.utc)
    except (ValueError, IndexError):
        return None


# ─────────────────────────────────────────────
# 5. KIỂM TRA TRÙNG LẶP
# ─────────────────────────────────────────────

def is_duplicate(path: str, dt_str: str) -> bool:
    """
    Kiểm tra xem datetime đã tồn tại trong CSV chưa.
    CHỈ đọc 200 dòng cuối để tiết kiệm RAM (nến 3min = ~1.5h cuối).
    """
    if not os.path.exists(path):
        return False

    # Đọc N dòng cuối không load cả file
    tail_lines = _tail(path, n=200)
    for line in tail_lines:
        if line.startswith(dt_str):
            return True
    return False


def _tail(path: str, n: int = 200) -> list[str]:
    """Đọc n dòng cuối của file (không dùng pandas/deque không giới hạn)."""
    with open(path, "rb") as f:
        # Binary seek từ cuối
        try:
            f.seek(0, 2)
            size = f.tell()
            block = min(size, n * 60)  # ước 60 bytes/dòng
            f.seek(-block, 2)
            raw = f.read().decode("utf-8", errors="replace")
        except OSError:
            f.seek(0)
            raw = f.read().decode("utf-8", errors="replace")

    lines = raw.splitlines()
    return lines[-n:]


# ─────────────────────────────────────────────
# 6. GHI CANDLE VÀO CSV (AN TOÀN)
# ─────────────────────────────────────────────

def append_candle(candle: dict, logger: logging.Logger) -> bool:
    """
    Ghi một nến vào CSV theo tháng.
    - Validate trước khi ghi
    - Kiểm tra duplicate
    - Ghi vào temp file rồi rename (tránh corrupt khi crash)
    - Trả về True nếu ghi thành công
    """
    if not is_valid_candle(candle):
        logger.warning(f"[SKIP] Nến không hợp lệ: {candle}")
        return False

    dt_str = str(candle["datetime"])  # "2025-04-09 08:00:00"
    try:
        dt = datetime.strptime(dt_str, "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc)
    except ValueError:
        logger.warning(f"[SKIP] Datetime không parse được: {dt_str}")
        return False

    csv_path = get_csv_path(dt)
    ensure_csv_header(csv_path)

    if is_duplicate(csv_path, dt_str):
        logger.debug(f"[DUP] Bỏ qua nến trùng: {dt_str}")
        return False

    row = [
        dt_str,
        candle["open"],
        candle["high"],
        candle["low"],
        candle["close"],
        candle["volume"],
    ]

    # Ghi an toàn: dùng temp file cùng thư mục, rename sau
    dir_name = os.path.dirname(csv_path)
    try:
        with tempfile.NamedTemporaryFile(
            mode="w", newline="", encoding="utf-8",
            dir=dir_name, delete=False, suffix=".tmp"
        ) as tmp:
            tmp_path = tmp.name
            # Copy nội dung cũ vào temp (nếu cần ghi giữa file — hiếm)
            # Ở đây ta chỉ APPEND → ghi thẳng vào file gốc là đủ an toàn
            # vì append là atomic trên hầu hết OS.
            # Dùng temp chỉ để tránh corruption khi ghi bulk (backfill).

        # Thực tế: với append đơn lẻ → ghi thẳng an toàn hơn
        os.unlink(tmp_path)  # xóa temp không dùng
        with open(csv_path, "a", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow(row)

    except OSError as e:
        logger.error(f"[ERROR] Không ghi được CSV: {e}")
        return False

    logger.info(f"[OK] Đã ghi nến: {dt_str} | C={candle['close']}")
    return True


# ─────────────────────────────────────────────
# 7. GHI NHIỀU CANDLE AN TOÀN (BACKFILL)
# ─────────────────────────────────────────────

def append_candles_bulk(candles: list[dict], logger: logging.Logger) -> int:
    """
    Ghi nhiều nến từ backfill REST API.
    Nhóm theo tháng, ghi từng file một lần (batch) bằng temp+rename.
    Trả về số nến đã ghi thành công.
    """
    # Nhóm candle theo tháng
    month_buckets: dict[str, list] = {}
    for c in candles:
        if not is_valid_candle(c):
            continue
        try:
            dt = datetime.strptime(str(c["datetime"]), "%Y-%m-%d %H:%M:%S")
        except ValueError:
            continue
        key = dt.strftime("%Y-%m")
        month_buckets.setdefault(key, []).append((dt, c))

    total_written = 0

    for month_key, items in month_buckets.items():
        # Sort theo thời gian tăng dần
        items.sort(key=lambda x: x[0])

        # Lấy path từ item đầu tiên
        sample_dt = items[0][0].replace(tzinfo=timezone.utc)
        csv_path = get_csv_path(sample_dt)
        ensure_csv_header(csv_path)

        # Lọc duplicate (cả trong file lẫn trong danh sách đang ghi)
        new_rows = []
        seen_in_bulk = set()
        for dt, c in items:
            dt_str = dt.strftime("%Y-%m-%d %H:%M:%S")
            if dt_str in seen_in_bulk:
                continue
            if not is_duplicate(csv_path, dt_str):
                seen_in_bulk.add(dt_str)
                new_rows.append([
                    dt_str,
                    c["open"], c["high"], c["low"], c["close"], c["volume"]
                ])

        if not new_rows:
            logger.info(f"[BULK] Tháng {month_key}: không có nến mới.")
            continue

        # Ghi bulk vào temp rồi merge với file cũ
        dir_name = os.path.dirname(csv_path)
        Path(dir_name).mkdir(parents=True, exist_ok=True)

        try:
            with tempfile.NamedTemporaryFile(
                mode="w", newline="", encoding="utf-8",
                dir=dir_name, delete=False, suffix=".tmp"
            ) as tmp:
                tmp_path = tmp.name
                writer = csv.writer(tmp)

                # Copy header + nội dung cũ
                if os.path.exists(csv_path) and os.path.getsize(csv_path) > 0:
                    with open(csv_path, "r", encoding="utf-8") as old_f:
                        shutil.copyfileobj(old_f, tmp)
                else:
                    writer.writerow(CSV_HEADER)

                # Append rows mới
                for row in new_rows:
                    writer.writerow(row)

            # Rename atomic
            shutil.move(tmp_path, csv_path)
            total_written += len(new_rows)
            logger.info(f"[BULK] Tháng {month_key}: đã ghi {len(new_rows)} nến.")

        except OSError as e:
            logger.error(f"[ERROR] Bulk write thất bại tháng {month_key}: {e}")
            if os.path.exists(tmp_path):
                os.unlink(tmp_path)

    return total_written


# ─────────────────────────────────────────────
# 8. RESAMPLE 1MIN → 3MIN
# ─────────────────────────────────────────────

def resample_1min_to_3min(candles_1min: list[dict]) -> list[dict]:
    """
    Gộp nến 1min thành nến 3min (không dùng pandas).
    Input: list candle 1min, đã sort theo datetime tăng dần.
    Output: list candle 3min đã đóng.

    YÊU CẦU CHẶT:
    - Chỉ tạo nến 3min khi có đúng 3 nến 1min LIÊN TIẾP.
    - Phút của nến đầu tiên phải chia hết cho 3 (00, 03, 06, ...).
    - Nếu dữ liệu 1min bị thiếu (gap phút) → KHÔNG sinh nến 3min "giả".

    Volume: cộng dồn (nếu có), nếu không có thì để 0.
    """
    if not candles_1min:
        return []

    result: list[dict] = []
    bucket: list[dict] = []

    def _flush_if_full_valid(b: list[dict]) -> dict | None:
        """Chỉ flush khi bucket có đúng 3 nến 1min liên tiếp, minute%3==0."""
        if len(b) != 3:
            return None
        try:
            dt0 = datetime.strptime(str(b[0]["datetime"]), "%Y-%m-%d %H:%M:%S")
            dt1 = datetime.strptime(str(b[1]["datetime"]), "%Y-%m-%d %H:%M:%S")
            dt2 = datetime.strptime(str(b[2]["datetime"]), "%Y-%m-%d %H:%M:%S")
        except ValueError:
            return None

        # Phải là 3 phút liên tiếp
        if (dt1 - dt0).total_seconds() != 60 or (dt2 - dt1).total_seconds() != 60:
            return None

        # Phút đầu tiên phải nằm trên lưới 3 phút
        if dt0.minute % 3 != 0:
            return None

        return _flush_bucket(b)

    for c in candles_1min:
        try:
            dt = datetime.strptime(str(c["datetime"]), "%Y-%m-%d %H:%M:%S")
        except ValueError:
            continue

        minute = dt.minute
        bucket_start_minute = (minute // 3) * 3

        if bucket:
            prev_dt = datetime.strptime(str(bucket[0]["datetime"]), "%Y-%m-%d %H:%M:%S")
            prev_bucket = (prev_dt.minute // 3) * 3

            same_bucket = (
                dt.date() == prev_dt.date()
                and dt.hour == prev_dt.hour
                and bucket_start_minute == prev_bucket
            )
            if not same_bucket:
                flushed = _flush_if_full_valid(bucket)
                if flushed:
                    result.append(flushed)
                bucket = []

        bucket.append(c)

    # Flush bucket cuối (chỉ khi là 3 nến liên tiếp trên lưới 3 phút)
    flushed = _flush_if_full_valid(bucket)
    if flushed:
        result.append(flushed)

    return result


def _flush_bucket(bucket: list[dict]) -> dict | None:
    """Gộp bucket 3 nến 1min thành 1 nến 3min chuẩn."""
    if not bucket:
        return None
    try:
        opens  = [float(c["open"])  for c in bucket]
        highs  = [float(c["high"])  for c in bucket]
        lows   = [float(c["low"])   for c in bucket]
        closes = [float(c["close"]) for c in bucket]
        vols   = [float(c.get("volume", 0) or 0) for c in bucket]
    except (ValueError, TypeError):
        return None

    return {
        "datetime": bucket[0]["datetime"],   # Mở tại nến đầu tiên
        "open":     round(opens[0], 5),
        "high":     round(max(highs), 5),
        "low":      round(min(lows), 5),
        "close":    round(closes[-1], 5),
        "volume":   int(sum(vols)),
    }
