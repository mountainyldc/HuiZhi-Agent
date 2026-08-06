# -*- coding: utf-8 -*-
"""按需实时 Web 搜索：返回带来源链接的实时结果，供 Pi 回答时效性问题（政策/竞品/行业动态）。

后端链（按可用性自动选择）：
  1. mcporter -> exa.web_search_exa（agent-reach 配置存在时）
  2. so.com 零配置网页搜索（中文友好，requests+bs4/regex 解析）
  3. 全部失败 -> 明确降级提示（附手工搜索链接）

硬约束：每条结果带来源 URL；输出标注「网络信息，需人工核验」；后端失败明确提示。

用法:
  python web_search.py --query "最近外汇管理局有什么新政策"
  python web_search.py --query "..." --n 8 --json
  python web_search.py --query "..." --dry-run     # 只打印将使用的后端与提示
"""
import argparse
import json
import re
import shutil
import subprocess
import sys

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

import requests

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/126.0 Safari/537.36")
NOTE = "网络信息，需人工核验"


def _clean(s):
    if not s:
        return ""
    s = re.sub(r"<[^>]+>", "", s)
    s = re.sub(r"\s+", " ", s)
    return s.strip()


def _try_exa(query, n):
    if not shutil.which("mcporter"):
        return None
    try:
        call = ("exa.web_search_exa(query: %r, numResults: %d)" % (query, n))
        r = subprocess.run(
            ["mcporter", "call", call], capture_output=True, text=True, timeout=60,
            encoding="utf-8", errors="replace",
        )
        if r.returncode != 0:
            return None
        out = r.stdout.strip()
        m = re.search(r"\[[\s\S]*\]", out)
        if not m:
            return None
        data = json.loads(m.group(0))
        results = []
        for it in data:
            url = it.get("url") or it.get("link") or ""
            title = it.get("title") or ""
            sn = it.get("snippet") or it.get("text") or it.get("description") or ""
            if url and title:
                results.append({"title": _clean(title), "url": url, "snippet": _clean(sn)})
        return {"backend": "exa(mcporter)", "results": results} if results else None
    except Exception:
        return None


def _try_so360(query, n):
    try:
        r = requests.get(
            "https://www.so.com/s", params={"q": query},
            headers={"User-Agent": UA}, timeout=20,
        )
        if r.status_code != 200:
            return None
        items = re.findall(r'<li class="res-list".*?</li>', r.text, re.S)
        results = []
        for li in items[:n]:
            href_m = re.search(r'<a[^>]+href="([^"]+)"', li)
            title_m = re.search(r"<h3[^>]*>(.*?)</h3>", li, re.S)
            sn_m = re.search(r'<p class="res-desc"[^>]*>(.*?)</p>', li, re.S)
            title = _clean(title_m.group(1)) if title_m else ""
            url = href_m.group(1) if href_m else ""
            sn = _clean(sn_m.group(1)) if sn_m else ""
            if not title or not url:
                continue
            results.append({"title": title, "url": _resolve(url), "snippet": sn})
        return {"backend": "so360", "results": results} if results else None
    except Exception:
        return None


def _resolve(url):
    """so.com/link 跳转链接解析为最终 URL；失败保留原链接。"""
    if "so.com/link" not in url:
        return url
    try:
        r = requests.get(url, headers={"User-Agent": UA}, timeout=10,
                         allow_redirects=True)
        if r.url and r.url.startswith("http"):
            return r.url
    except Exception:
        pass
    return url


def search(query, n=5):
    for fn in (_try_exa, _try_so360):
        res = fn(query, n)
        if res:
            res["query"] = query
            res["note"] = NOTE
            return res
    # 全部失败：明确降级提示 + 手工搜索链接
    import urllib.parse
    bing = "https://www.bing.com/search?q=" + urllib.parse.quote(query)
    so = "https://www.so.com/s?q=" + urllib.parse.quote(query)
    return {
        "query": query,
        "backend": "fallback",
        "results": [],
        "note": NOTE,
        "degraded": True,
        "message": f"实时搜索后端暂不可用（可能断网或搜索服务被限流）。可手工打开：{bing} 或 {so}",
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--query", required=True)
    ap.add_argument("--n", type=int, default=5)
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()
    res = search(args.query, n=args.n)
    if args.json:
        print(json.dumps(res, ensure_ascii=False, indent=2))
        return
    print(f"后端：{res['backend']} | 说明：{res.get('note','')}")
    if res.get("degraded"):
        print(res["message"])
        return
    for i, it in enumerate(res["results"], start=1):
        print(f"[{i}] {it['title']}")
        print(f"    {it['url']}")
        if it["snippet"]:
            print(f"    {it['snippet'][:120]}")


if __name__ == "__main__":
    main()