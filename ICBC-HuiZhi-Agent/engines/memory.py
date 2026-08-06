# -*- coding: utf-8 -*-
"""跨轮次会话记忆：记住最近分析的公司 / 关注区域，支撑「追问指代」。
存储：SQLite conversation_memory 单行 JSON。隐私：只存公司/区域名，不存个人信息。"""
import re

from store import memory_get, memory_set


def get_memory():
    return memory_get()


def remember_company(company):
    if not company:
        return get_memory()
    m = memory_get()
    recents = m.get("recent_companies") or []
    if company in recents:
        recents.remove(company)
    recents.insert(0, company)
    m["recent_companies"] = recents[:10]
    m["last_company"] = company
    memory_set(m)
    return m


def remember_region(region):
    if not region:
        return get_memory()
    m = memory_get()
    regions = m.get("regions") or []
    if region not in regions:
        regions.insert(0, region)
    m["regions"] = regions[:5]
    memory_set(m)
    return m


def clear_memory():
    memory_set({"recent_companies": [], "last_company": None, "regions": []})
    return memory_get()


def fallback_company(query):
    """追问时（含 它/该/这/那/其 等指代词，或极短问题）回退到最近分析的公司。"""
    if not query or not isinstance(query, str):
        return None
    m = memory_get()
    last = m.get("last_company")
    if not last:
        return None
    q = query.strip()
    if not q:
        return None
    if re.search(r"它|该|这|那|其", q) or len(q) <= 6:
        return last
    return None


def format_memory():
    m = memory_get()
    lines = []
    if m.get("last_company"):
        lines.append(f"最近分析：{m['last_company']}")
    rec = m.get("recent_companies") or []
    if rec:
        lines.append("历史：" + " → ".join(rec))
    if m.get("regions"):
        lines.append("关注区域：" + "、".join(m["regions"]))
    if not lines:
        lines.append("暂无记忆")
    return "\n".join(lines)


if __name__ == "__main__":
    import sys
    if "--clear" in sys.argv:
        print(clear_memory())
    elif "--company" in sys.argv:
        c = sys.argv[sys.argv.index("--company") + 1]
        print(remember_company(c))
    else:
        print(format_memory())
