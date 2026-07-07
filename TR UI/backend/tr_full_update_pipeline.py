# -*- coding: utf-8 -*-
"""
全量更新流水线：阶段 A（EXEC sync_tr_data）+ 阶段 B（计划任务 / bat）。
日志按阶段分文件写入 TR database 目录。
"""
from __future__ import annotations

import glob
import os
import subprocess
import sys
import time
from datetime import datetime
from typing import Any, Callable

DEFAULT_LOG_DIR = r"C:\TR-master\TR database\logs"
DEFAULT_BATCH_FILE = r"C:\TR-master\TR database\auto_update_all_tables.bat"


def _win_subprocess_creationflags() -> int:
    """无控制台/以服务运行时 CREATE_NO_WINDOW + 管道易导致 WinError 6，默认不加该标志。"""
    if sys.platform != "win32":
        return 0
    raw = os.getenv("SUBPROCESS_CREATE_NO_WINDOW", "").strip().lower()
    if raw in ("1", "true", "yes"):
        return subprocess.CREATE_NO_WINDOW  # type: ignore[attr-defined]
    return 0


def resolve_tr_update_log_dir() -> str:
    return os.getenv("TR_UPDATE_LOG_DIR", DEFAULT_LOG_DIR)


def resolve_batch_file() -> str:
    return os.getenv("AUTO_UPDATE_ALL_TABLES_BAT", DEFAULT_BATCH_FILE)


def glob_auto_update_all_outputs(log_dir: str) -> list[str]:
    """
    列出目录下批处理产生的 auto_update_all 输出文件。
    同时匹配 *.log 与 *.txt（部分 bat 重定向为 .txt）。
    """
    paths: list[str] = []
    for pat in ("auto_update_all_*.log", "auto_update_all_*.txt"):
        paths.extend(glob.glob(os.path.join(log_dir, pat)))
    return list(dict.fromkeys(paths))


def snapshot_auto_update_log_mtimes(log_dir: str) -> dict[str, float]:
    """阶段 B 开始前对 auto_update_all 输出文件（.log/.txt）各路径 mtime 拍快照。"""
    files = glob_auto_update_all_outputs(log_dir)
    return {f: os.path.getmtime(f) for f in files}


def _fresh_auto_update_logs(log_dir: str, before: dict[str, float]) -> list[str]:
    files = glob_auto_update_all_outputs(log_dir)
    fresh: list[str] = []
    for f in files:
        try:
            lm = os.path.getmtime(f)
        except OSError:
            continue
        prev = before.get(f)
        if prev is None:
            fresh.append(f)
        elif lm > prev + 0.01:
            fresh.append(f)
    return fresh


def log_scheduled_task_query_summary(
    task_name: str,
    log_fn: Callable[[str], None] | None = None,
) -> None:
    """触发计划任务后打一条 /Query 摘要，便于对照「是否真的在跑、上次结果码」。"""
    if sys.platform != "win32":
        return
    try:
        proc = subprocess.run(
            ["schtasks", "/Query", "/TN", task_name, "/FO", "LIST", "/V"],
            stdin=subprocess.DEVNULL,
            capture_output=True,
            text=True,
            shell=False,
            creationflags=_win_subprocess_creationflags(),
        )
        blob = ((proc.stdout or "") + "\n" + (proc.stderr or "")).strip()
        keys = (
            "Status",
            "Last Run Time",
            "Last Result",
            "Task To Run",
            "Start In",
            "状态",
            "上次运行时间",
            "上次结果",
        )
        hits = [
            ln.strip()
            for ln in blob.splitlines()
            if any(k in ln for k in keys) and ":" in ln
        ]
        if log_fn:
            log_fn(
                "schtasks /Query 摘要: "
                + ("; ".join(hits[:20]) if hits else blob[:400])
            )
    except Exception as exc:
        if log_fn:
            log_fn(f"schtasks /Query 异常: {exc}")


def schtasks_query_task_details(task_name: str) -> dict[str, Any]:
    """
    解析 schtasks /Query /FO LIST /V，提取 Last Result / Status / Last Run Time。
    last_result 为带符号整数（负值即 HRESULT 失败，如无法启动 bat）。
    """
    out: dict[str, Any] = {
        "last_result": None,
        "status": None,
        "last_run_time": None,
        "raw_head": "",
    }
    if sys.platform != "win32":
        return out
    try:
        proc = subprocess.run(
            ["schtasks", "/Query", "/TN", task_name, "/FO", "LIST", "/V"],
            stdin=subprocess.DEVNULL,
            capture_output=True,
            text=True,
            shell=False,
            creationflags=_win_subprocess_creationflags(),
        )
        blob = ((proc.stdout or "") + "\n" + (proc.stderr or "")).strip()
        out["raw_head"] = blob[:2500]
        for line in blob.splitlines():
            if ":" not in line:
                continue
            key, _, rest = line.partition(":")
            key = key.strip()
            val = rest.strip()
            if key in ("Last Result", "上次结果"):
                try:
                    tok = val.split()[0] if val else ""
                    out["last_result"] = int(tok, 10)
                except (ValueError, IndexError):
                    pass
            elif key in ("Status", "状态"):
                out["status"] = val
            elif key in ("Last Run Time", "上次运行时间"):
                out["last_run_time"] = val
    except OSError:
        pass
    return out


def scheduled_task_status_looks_running(status: str | None) -> bool:
    if not status:
        return False
    s = status.lower()
    if "running" in s:
        return True
    return "正在运行" in status


def scheduled_task_launch_failure_suspect(
    last_result: int | None, status: str | None
) -> bool:
    """
    Last Result 为负的 HRESULT 时，任务往往未真正执行 bat（路径、工作目录、权限等）。
    若状态明确为 Running，则可能是上一轮结果尚未刷新，不据此立即判死。
    """
    if last_result is None:
        return False
    if last_result >= 0:
        return False
    if scheduled_task_status_looks_running(status):
        return False
    return True


def phase_b_wait_message_is_stale_no_log(msg: str | None) -> bool:
    """wait_for_auto_update_logs 因「无新日志」或总超时失败时的文案特征。"""
    if not msg:
        return False
    return ("未观察到" in msg) or ("等待日志超时" in msg)


def append_log(log_path: str, line: str) -> None:
    os.makedirs(os.path.dirname(log_path), exist_ok=True)
    stamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with open(log_path, "a", encoding="utf-8", errors="replace") as f:
        f.write(f"[{stamp}] {line}\n")


def _batch_log_has_end_marker(s: str) -> bool:
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
    return False


def _batch_log_indicates_success(s: str) -> bool:
    if "成功" in s or "🎉" in s:
        return True
    low = s.lower()
    if "update completed successfully" in low:
        return True
    if "script execution completed" in low:
        return True
    if "[success]" in low:
        return True
    u = s.upper()
    if "SUCCESS" in u and any(x in u for x in ("COMPLETE", "COMPLETED", "FINISH", "DONE", "END")):
        return True
    if "数据" in s and "更新" in s and "完成" in s:
        return True
    if "更新已完成" in s or "数据已更新" in s:
        return True
    return False


def _read_auto_update_log_text(log_path: str) -> str:
    """先按 UTF-8 读；若看不出流程结束标记则再试 GBK（控制台批处理常见）。"""
    try:
        with open(log_path, "rb") as f:
            raw = f.read()
    except OSError:
        return ""
    u = raw.decode("utf-8", errors="replace")
    if _batch_log_has_end_marker(u):
        return u
    g = raw.decode("gbk", errors="replace")
    return g if _batch_log_has_end_marker(g) else u


def auto_update_log_phase_b_status(latest_path: str, *, recent_secs: float = 300.0) -> tuple[str, str]:
    """
    从 auto_update_all 输出文件路径（.log 或 .txt）推断阶段 B 状态，返回 (status, message)。
    status: running | completed | failed | unknown
    """
    try:
        mtime = os.path.getmtime(latest_path)
        time_diff = time.time() - mtime
        if time_diff < recent_secs:
            content = _read_auto_update_log_text(latest_path)
            lines = content.splitlines()
            tail = "\n".join(lines[-30:]) if len(lines) > 30 else content
            if _batch_log_has_end_marker(tail):
                if _batch_log_indicates_success(tail):
                    return "completed", "阶段B：批处理已完成"
                return "failed", "阶段B：批处理可能失败，请查看日志"
            return "running", "阶段B：批处理进行中"
        content = _read_auto_update_log_text(latest_path)
        if _batch_log_has_end_marker(content):
            if _batch_log_indicates_success(content):
                return "completed", "阶段B：批处理已完成"
            return "failed", "阶段B：批处理可能失败"
        # 日志已停止更新较久且含成功标记时，仍视为完成（兼容结束文案变更）
        if time_diff >= recent_secs and _batch_log_indicates_success(content):
            return "completed", "阶段B：批处理已完成（日志含成功标记）"
        return "unknown", "阶段B：无法从日志判定状态"
    except OSError:
        return "unknown", "阶段B：无法读取日志文件"


def wait_for_auto_update_logs(
    log_dir: str,
    *,
    max_wait_sec: int = 7200,
    poll_interval: float = 5.0,
    log_fn: Callable[[str], None] | None = None,
    min_log_mtime: float | None = None,
    log_mtime_snapshot: dict[str, float] | None = None,
    stale_abort_sec: float | None = None,
) -> tuple[str, str, str | None]:
    """
    轮询 auto_update_all 输出（*.log / *.txt），直到 completed / failed 或超时。
    返回 (status, message, latest_log_path)

    log_mtime_snapshot: 若提供，则仅当「出现新日志文件」或「已有文件 mtime 大于快照」时才采信，
    避免误把未更新的旧日志当成当前轮次（推荐，默认由调用方传入）。

    min_log_mtime: 未提供 snapshot 时使用；仅当某日志 mtime >= 该值时才采信（旧逻辑）。

    stale_abort_sec: 长时间无任何「新鲜」日志时判失败前的等待秒数。
    """
    deadline = time.time() + max_wait_sec
    latest_log: str | None = None
    last_msg = "阶段B：等待批处理日志..."
    if stale_abort_sec is None:
        stale_abort_sec = float(os.getenv("PHASE_B_STALE_LOG_ABORT_SEC", "900"))
    stale_only_since: float | None = None
    while time.time() < deadline:
        log_files = glob_auto_update_all_outputs(log_dir)
        if log_mtime_snapshot is not None:
            fresh = _fresh_auto_update_logs(log_dir, log_mtime_snapshot)
            if not fresh:
                last_msg = "阶段B：等待新日志文件或已有日志被更新..."
                if log_fn and log_files:
                    probe = max(log_files, key=os.path.getmtime)
                    log_fn(
                        f"skip no fresh auto_update log yet (latest unchanged file={probe})"
                    )
                now = time.time()
                if stale_only_since is None:
                    stale_only_since = now
                elif now - stale_only_since >= stale_abort_sec:
                    return (
                        "failed",
                        "阶段B：在 "
                        f"{int(stale_abort_sec)}s 内未观察到日志目录内 auto_update_all（.log/.txt）有新文件或 mtime 增长；"
                        "schtasks 可能仅排队成功、任务未真正执行 bat，或 bat 将日志写到其他路径。"
                        "请在任务计划程序中核对「操作/起始于」与 Last Result，并可调大 "
                        "PHASE_B_STALE_LOG_ABORT_SCHEDULED_SEC / PHASE_B_STALE_LOG_ABORT_BAT_SEC。",
                        max(log_files, key=os.path.getmtime) if log_files else None,
                    )
                time.sleep(poll_interval)
                continue
            stale_only_since = None
            latest_log = max(fresh, key=os.path.getmtime)
            lm = os.path.getmtime(latest_log)
            status, msg = auto_update_log_phase_b_status(latest_log)
            last_msg = msg
            if log_fn:
                log_fn(f"poll status={status} file={latest_log}")
            if status == "completed":
                return "completed", msg, latest_log
            if status == "failed":
                return "failed", msg, latest_log
            if status == "running":
                pass
            elif status == "unknown":
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
        elif log_files:
            latest_log = max(log_files, key=os.path.getmtime)
            lm = os.path.getmtime(latest_log)
            if min_log_mtime is not None and lm < min_log_mtime:
                last_msg = "阶段B：等待新的批处理日志..."
                if log_fn:
                    log_fn(f"skip stale log mtime={lm} < min={min_log_mtime} file={latest_log}")
                now = time.time()
                if stale_only_since is None:
                    stale_only_since = now
                elif now - stale_only_since >= stale_abort_sec:
                    return (
                        "failed",
                        "阶段B：在 "
                        f"{int(stale_abort_sec)}s 内未观察到本轮产生的新日志文件（mtime≥起点）；"
                        "常见原因：计划任务排队延迟、bat 前几步较慢未写日志、或日志写在别的目录。"
                        "可适当增大环境变量 PHASE_B_STALE_LOG_ABORT_SCHEDULED_SEC / PHASE_B_STALE_LOG_ABORT_BAT_SEC。"
                        "若曾出现 WinError 6，还需检查服务账户能否启动计划任务/子进程。",
                        latest_log,
                    )
                time.sleep(poll_interval)
                continue
            stale_only_since = None
            status, msg = auto_update_log_phase_b_status(latest_log)
            last_msg = msg
            if log_fn:
                log_fn(f"poll status={status} file={latest_log}")
            if status == "completed":
                return "completed", msg, latest_log
            if status == "failed":
                return "failed", msg, latest_log
            if status == "running":
                pass
            elif status == "unknown":
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
        time.sleep(poll_interval)
    return "failed", f"阶段B：等待日志超时（{max_wait_sec}s），最后状态：{last_msg}", latest_log


def try_run_scheduled_task(task_name: str, log_fn: Callable[[str], None] | None = None) -> bool:
    if sys.platform != "win32":
        if log_fn:
            log_fn("schtasks 仅在 Windows 上可用，跳过计划任务")
        return False
    task_cmd = ["schtasks", "/Run", "/TN", task_name]
    flags = _win_subprocess_creationflags()

    def _run(cf: int) -> subprocess.CompletedProcess:
        return subprocess.run(
            task_cmd,
            stdin=subprocess.DEVNULL,
            capture_output=True,
            text=True,
            shell=False,
            creationflags=cf,
        )

    proc: subprocess.CompletedProcess | None = None
    try:
        proc = _run(flags)
    except OSError as exc:
        winerr = getattr(exc, "winerror", None)
        if winerr == 6 and flags != 0:
            if log_fn:
                log_fn("schtasks WinError 6，重试不使用 CREATE_NO_WINDOW")
            try:
                proc = _run(0)
            except OSError as exc2:
                if log_fn:
                    log_fn(f"schtasks 仍失败: {exc2}，尝试 stdout/stderr=DEVNULL")
                try:
                    proc = subprocess.run(
                        task_cmd,
                        stdin=subprocess.DEVNULL,
                        stdout=subprocess.DEVNULL,
                        stderr=subprocess.DEVNULL,
                        shell=False,
                        creationflags=0,
                    )
                except OSError as exc3:
                    if log_fn:
                        log_fn(f"schtasks 异常: {exc3}")
                    return False
        elif winerr == 6:
            if log_fn:
                log_fn("schtasks WinError 6，尝试 stdout/stderr=DEVNULL")
            try:
                proc = subprocess.run(
                    task_cmd,
                    stdin=subprocess.DEVNULL,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    shell=False,
                    creationflags=0,
                )
            except OSError as exc2:
                if log_fn:
                    log_fn(f"schtasks 异常: {exc2}")
                return False
        else:
            if log_fn:
                log_fn(f"schtasks 异常: {exc}")
            return False
    except Exception as exc:
        if log_fn:
            log_fn(f"schtasks 异常: {exc}")
        return False

    if proc is None:
        return False
    ok = proc.returncode == 0
    if log_fn:
        err_hint = ""
        if getattr(proc, "stderr", None) is not None:
            err_hint = (proc.stderr or "").strip()
        log_fn(
            f"schtasks /Run /TN {task_name} returncode={proc.returncode}"
            + (f" stderr={err_hint}" if err_hint else "")
        )
    return ok


def run_batch_subprocess(
    batch_file: str, log_fn: Callable[[str], None] | None = None
) -> tuple[bool, str, str]:
    """
    阻塞执行 bat，返回 (success, stdout, stderr)。
    默认将子进程 stdin/stdout/stderr 重定向到 DEVNULL，避免 Windows 服务下
    “无有效控制台句柄”导致 WinError 6；输出请依赖 auto_update 日志。

    自动设置 TR_SKIP_BACKEND_SERVICE_CONTROL=1：auto_update_all_tables.bat 否则会 net stop TR-Backend，
    在「API 子进程直接跑 bat」场景下会终止自身服务进程，导致无日志、全量更新永远 batch。
    """
    batch_dir = os.path.dirname(batch_file)
    flags = _win_subprocess_creationflags()
    env = os.environ.copy()
    allow_stop = os.getenv("PHASE_B_ALLOW_BAT_STOP_SERVICE", "").strip().lower() in (
        "1",
        "true",
        "yes",
    )
    if not allow_stop:
        env["TR_SKIP_BACKEND_SERVICE_CONTROL"] = "1"
        if log_fn:
            log_fn(
                "bat 子进程已设置 TR_SKIP_BACKEND_SERVICE_CONTROL=1（避免 bat 内 net stop 终止当前后端）"
            )

    # /NO_PAUSE：非交互运行时不 pause；路径加引号以支持含空格目录
    cmd = f'"{batch_file}" /NO_PAUSE'

    def _popen(cf: int) -> subprocess.Popen:
        return subprocess.Popen(
            cmd,
            cwd=batch_dir,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            shell=True,
            creationflags=cf,
            env=env,
        )

    try:
        try:
            proc = _popen(flags)
        except OSError as exc:
            if getattr(exc, "winerror", None) == 6 and flags != 0:
                if log_fn:
                    log_fn("bat Popen WinError 6，重试不使用 CREATE_NO_WINDOW")
                proc = _popen(0)
            else:
                raise
        proc.wait()
        ok = proc.returncode == 0
        if log_fn:
            log_fn(f"bat 结束 exit={proc.returncode}")
        return ok, "", ""
    except Exception as exc:
        if log_fn:
            log_fn(f"bat 执行异常: {exc}")
        return False, "", str(exc)


def execute_sync_tr_data(
    log_path: str,
    *,
    procedure: str | None = None,
) -> None:
    """
    阶段 A：EXEC 存储过程。日志写入 log_path。
    使用 pyodbc；密码中的特殊字符由 ODBC 处理。
    """
    proc_name = procedure or os.getenv("SYNC_TR_DATA_PROCEDURE", "dbo.sync_tr_data")
    server = os.getenv("SQL_SERVER", "192.168.80.242")
    database = os.getenv("SQL_DATABASE", "TVSC")
    username = os.getenv("SQL_USERNAME", "reportuser")
    password = os.getenv("SQL_PASSWORD", "HKSHA123")
    driver = os.getenv(
        "SQL_ODBC_DRIVER",
        os.getenv("SQL_DRIVER", "ODBC Driver 17 for SQL Server"),
    )

    encrypt_explicit = os.getenv("SQL_ENCRYPT", "").strip().lower()
    if encrypt_explicit in ("yes", "true", "1"):
        encrypt = True
    elif encrypt_explicit in ("no", "false", "0"):
        encrypt = False
    else:
        # 旧版「SQL Server」+ Encrypt=yes 常见：SSL Security error (DBNETLIB)
        encrypt = driver.strip().lower() != "sql server"

    trust_cert = os.getenv("SQL_TRUST_SERVER_CERTIFICATE", "yes").strip().lower() in (
        "yes",
        "true",
        "1",
        "",
    )

    append_log(
        log_path,
        f"开始执行 {proc_name} server={server} database={database} "
        f"driver={driver} encrypt={'yes' if encrypt else 'no'}",
    )

    try:
        import pyodbc  # type: ignore
    except ImportError as exc:
        append_log(log_path, f"错误：未安装 pyodbc，无法执行阶段A ({exc})")
        raise RuntimeError("未安装 pyodbc，请在后端环境执行 pip install pyodbc") from exc

    conn_str = (
        f"DRIVER={{{driver}}};SERVER={server};DATABASE={database};"
        f"UID={username};PWD={password};"
        f"Encrypt={'yes' if encrypt else 'no'};"
    )
    if trust_cert:
        conn_str += "TrustServerCertificate=yes;"
    try:
        cn = pyodbc.connect(conn_str, timeout=60)
        try:
            cn.autocommit = True
            if hasattr(cn, "timeout"):
                try:
                    cn.timeout = 0
                except Exception:
                    pass
            cur = cn.cursor()
            append_log(log_path, f"已连接，执行 EXEC {proc_name} ...")
            cur.execute(f"EXEC {proc_name}")
            cur.close()
        finally:
            cn.close()
        append_log(log_path, f"{proc_name} 执行完成")
    except Exception as exc:
        append_log(log_path, f"{proc_name} 执行失败: {exc}")
        raise
