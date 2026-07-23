#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Helpers: check whether orders are TR-complete (selectable / generatable)."""

from __future__ import annotations

from typing import Iterable, List, Dict, Any


def _row_val(row, *keys, default=None):
    if row is None:
        return default
    if isinstance(row, dict):
        for k in keys:
            if k in row and row[k] is not None:
                return row[k]
        return default
    return row[0] if row else default


def get_orders_tr_status(conn, order_nos: Iterable[int]) -> Dict[int, Dict[str, Any]]:
    """
    Return {order_no: {tr_status, missing_diameters, selectable}}.
    Prefer bbs_tr_status; fall back to dedup/bbs_dd columns; default complete.
    """
    nos = []
    for n in order_nos:
        try:
            nos.append(int(n))
        except (TypeError, ValueError):
            continue
    result = {
        n: {"tr_status": "complete", "missing_diameters": None, "selectable": True}
        for n in nos
    }
    if not nos:
        return result

    cur = conn.cursor()
    placeholders = ",".join(["%s"] * len(nos))

    # bbs_tr_status
    try:
        cur.execute(
            f"""
            SELECT bbs_no, tr_status, missing_diameters
            FROM bbs_tr_status
            WHERE bbs_no IN ({placeholders})
            """,
            nos,
        )
        for row in cur.fetchall():
            bbs = int(_row_val(row, "bbs_no", 0))
            status = (_row_val(row, "tr_status", 1) or "complete").strip().lower()
            missing = _row_val(row, "missing_diameters", 2)
            result[bbs] = {
                "tr_status": status,
                "missing_diameters": missing,
                "selectable": status != "incomplete",
            }
        return result
    except Exception:
        try:
            conn.rollback()
        except Exception:
            pass

    # Fallback: dedup column
    try:
        cur.execute(
            f"""
            SELECT "Order_No", tr_status, missing_diameters
            FROM "TR_Report_Deduplication"
            WHERE "Order_No" IN ({placeholders})
            """,
            nos,
        )
        for row in cur.fetchall():
            bbs = int(_row_val(row, "Order_No", 0))
            status = (_row_val(row, "tr_status", 1) or "complete").strip().lower()
            missing = _row_val(row, "missing_diameters", 2)
            result[bbs] = {
                "tr_status": status,
                "missing_diameters": missing,
                "selectable": status != "incomplete",
            }
    except Exception:
        try:
            conn.rollback()
        except Exception:
            pass

    return result


def find_incomplete_orders(conn, order_nos: Iterable[int]) -> List[Dict[str, Any]]:
    status_map = get_orders_tr_status(conn, order_nos)
    blocked = []
    for n, info in status_map.items():
        if not info.get("selectable", True):
            blocked.append(
                {
                    "order_no": n,
                    "tr_status": info.get("tr_status"),
                    "missing_diameters": info.get("missing_diameters"),
                }
            )
    return blocked


def assert_orders_tr_complete(conn, order_nos: Iterable[int]) -> None:
    """Raise ValueError if any order is incomplete."""
    blocked = find_incomplete_orders(conn, order_nos)
    if not blocked:
        return
    parts = []
    for b in blocked[:10]:
        miss = b.get("missing_diameters") or "?"
        parts.append(f"{b['order_no']}(缺TR:{miss})")
    extra = f" 等共{len(blocked)}单" if len(blocked) > 10 else ""
    raise ValueError(
        "以下订单因缺少 TR 数据不可生成/下载："
        + ", ".join(parts)
        + extra
        + "。请先在源系统补全 TR 并同步。"
    )
