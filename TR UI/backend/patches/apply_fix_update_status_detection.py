#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
修复「更新数据」完成后前端仍显示「更新中」的问题。

根因：auto_update_all 日志结尾为
  "... file index auto update ended"
而检测逻辑只认 "... process ended"，导致阶段 B 永远无法判为 completed。

用法（以管理员身份运行 PowerShell）：
  cd C:\\TR-master\\TR UI\\backend
  python patches\\apply_fix_update_status_detection.py

可选：同时重置卡住的作业状态
  python patches\apply_fix_update_status_detection.py --reset-stuck-job
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent
TARGET = BACKEND_DIR / "tr_full_update_pipeline.py"
STATE_FILE = Path(r"C:\TR-master\TR database\logs\full_update_job_state.json")

OLD_MARKER = '''def _batch_log_has_end_marker(s: str) -> bool:
    """批处理/Python 脚本写 auto_update_all 或 batch_run 日志时的「流程已收尾」标记（中英）。"""
    if "自动更新流程结束" in s or "更新流程结束" in s:
        return True
    low = s.lower()
    if "script execution completed" in low:
        return True
    if "update completed successfully" in low:
        return True
    if "file index auto update process ended" in low:
        return True
    if "automatic update process ended" in low:
        return True
    return False'''

NEW_MARKER = '''def _batch_log_has_end_marker(s: str) -> bool:
    """批处理/Python 脚本写 auto_update_all 或 batch_run 日志时的「流程已收尾」标记（中英）。"""
    if "自动更新流程结束" in s or "更新流程结束" in s:
        return True
    low = s.lower()
    if "script execution completed" in low:
        return True
    if "update completed successfully" in low:
        return True
    if "all data update successful" in low:
        return True
    if "tr database tables update completed" in low:
        return True
    if "file index auto update process ended" in low:
        return True
    if "file index auto update ended" in low:
        return True
    if "auto update ended" in low:
        return True
    if "automatic update process ended" in low:
        return True
    return False'''

OLD_PHASE_B_TAIL = '''        content = _read_auto_update_log_text(latest_path)
        if _batch_log_has_end_marker(content):
            if _batch_log_indicates_success(content):
                return "completed", "阶段B：批处理已完成"
            return "failed", "阶段B：批处理可能失败"
        return "unknown", "阶段B：无法从日志判定状态"'''

NEW_PHASE_B_TAIL = '''        content = _read_auto_update_log_text(latest_path)
        if _batch_log_has_end_marker(content):
            if _batch_log_indicates_success(content):
                return "completed", "阶段B：批处理已完成"
            return "failed", "阶段B：批处理可能失败"
        # 日志已停止更新较久且含成功标记时，仍视为完成（兼容结束文案变更）
        if time_diff >= recent_secs and _batch_log_indicates_success(content):
            return "completed", "阶段B：批处理已完成（日志含成功标记）"
        return "unknown", "阶段B：无法从日志判定状态"'''

OLD_UNKNOWN_1 = '''            elif status == "unknown":
                if time.time() - lm < 300:
                    last_msg = "阶段B：批处理可能进行中"
        elif log_files:'''

NEW_UNKNOWN_1 = '''            elif status == "unknown":
                idle_sec = time.time() - lm
                if idle_sec < 300:
                    last_msg = "阶段B：批处理可能进行中"
                else:
                    content = _read_auto_update_log_text(latest_log)
                    if _batch_log_indicates_success(content):
                        return (
                            "completed",
                            "阶段B：批处理已完成（日志已停止更新且含成功标记）",
                            latest_log,
                        )
        elif log_files:'''

OLD_UNKNOWN_2 = '''            elif status == "unknown":
                if time.time() - lm < 300:
                    last_msg = "阶段B：批处理可能进行中"
        time.sleep(poll_interval)'''

NEW_UNKNOWN_2 = '''            elif status == "unknown":
                idle_sec = time.time() - lm
                if idle_sec < 300:
                    last_msg = "阶段B：批处理可能进行中"
                else:
                    content = _read_auto_update_log_text(latest_log)
                    if _batch_log_indicates_success(content):
                        return (
                            "completed",
                            "阶段B：批处理已完成（日志已停止更新且含成功标记）",
                            latest_log,
                        )
        time.sleep(poll_interval)'''


def _already_patched(text: str) -> bool:
    return "file index auto update ended" in text and "日志已停止更新且含成功标记" in text


def apply_pipeline_patch() -> None:
    if not TARGET.is_file():
        raise SystemExit(f"目标文件不存在: {TARGET}")

    text = TARGET.read_text(encoding="utf-8")
    if _already_patched(text):
        print(f"[跳过] 已打过补丁: {TARGET}")
        return

    replacements = [
        (OLD_MARKER, NEW_MARKER, "_batch_log_has_end_marker"),
        (OLD_PHASE_B_TAIL, NEW_PHASE_B_TAIL, "auto_update_log_phase_b_status 收尾"),
        (OLD_UNKNOWN_1, NEW_UNKNOWN_1, "wait_for_auto_update_logs unknown#1"),
        (OLD_UNKNOWN_2, NEW_UNKNOWN_2, "wait_for_auto_update_logs unknown#2"),
    ]
    for old, new, label in replacements:
        if old not in text:
            raise SystemExit(f"补丁失败：未找到片段 [{label}]，请确认 tr_full_update_pipeline.py 版本")
        text = text.replace(old, new, 1)

    TARGET.write_text(text, encoding="utf-8")
    print(f"[OK] 已更新: {TARGET}")


def reset_stuck_job() -> None:
    if not STATE_FILE.is_file():
        print(f"[跳过] 状态文件不存在: {STATE_FILE}")
        return

    data = json.loads(STATE_FILE.read_text(encoding="utf-8"))
    if data.get("phase") not in ("sync", "batch"):
        print(f"[跳过] 当前 phase={data.get('phase')!r}，无需重置")
        return

    log_dir = STATE_FILE.parent
    logs = sorted(
        list(log_dir.glob("auto_update_all_*.log")) + list(log_dir.glob("auto_update_all_*.txt")),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    latest_log = str(logs[0]) if logs else data.get("phase_b_log")

    data.update(
        {
            "phase": "completed",
            "message": "数据更新已完成（手动重置卡住的作业状态）",
            "phase_b_log": latest_log,
            "finished_at": datetime.now().isoformat(),
        }
    )
    STATE_FILE.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[OK] 已重置作业状态: {STATE_FILE}")


def verify() -> None:
    sys.path.insert(0, str(BACKEND_DIR))
    from tr_full_update_pipeline import auto_update_log_phase_b_status

    log_dir = Path(r"C:\TR-master\TR database\logs")
    logs = sorted(
        list(log_dir.glob("auto_update_all_*.log")) + list(log_dir.glob("auto_update_all_*.txt")),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    if not logs:
        print("[WARN] 未找到 auto_update 日志，跳过验证")
        return
    latest = str(logs[0])
    st, msg = auto_update_log_phase_b_status(latest, recent_secs=0.0)
    print(f"[验证] {logs[0].name} -> status={st!r}")
    if st != "completed":
        raise SystemExit(f"验证失败: 期望 completed，实际 {st!r} ({msg})")
    print("[OK] 日志完成检测验证通过")


def main() -> int:
    parser = argparse.ArgumentParser(description="应用「更新数据」状态检测修复补丁")
    parser.add_argument(
        "--reset-stuck-job",
        action="store_true",
        help="将 full_update_job_state.json 中卡住的 batch 作业标记为 completed",
    )
    parser.add_argument("--no-verify", action="store_true", help="打补丁后不跑日志验证")
    args = parser.parse_args()

    apply_pipeline_patch()
    if args.reset_stuck_job:
        reset_stuck_job()
    if not args.no_verify:
        verify()

    print()
    print("请重启 TR-Backend 服务使补丁生效：")
    print("  Restart-Service TR-Backend")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
