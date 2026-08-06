"""轻量演示服务：静态页 + 认领/标记无效持久化 + 资讯中心 + 年报数据。

用法:
  python serve.py [--port 8000]
  浏览器打开 http://127.0.0.1:8000

启动时若数据库为空，会自动用 data/crawled 下的数据重建商机队列，clone 即用。
"""
import argparse
import json
import os
import subprocess
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from common import load_config, project_path
import store
from build_queue import build_queue
from render_web import render
import fetch_financials
import settings as radar_settings


def _ensure_seeded():
    """数据库为空时，用已有 crawled 数据重建公告/商机并渲染页面。"""
    n = len(store.list_announcements())
    if n > 0:
        return False
    print("[info] 数据库为空，自动重建（rule_screen -> build_queue -> render）...")
    from rule_screen import rule_screen
    opps = rule_screen()
    print(f"[info] 重建商机 {len(opps)} 条")
    build_queue()
    render()
    return True


def _run_pipeline():
    """更新数据：依次跑爬虫(含样例回退) -> 规则筛选 -> 队列 -> 渲染。返回 {script: ok/fail}。"""
    results = {}
    for script in ("crawl_cninfo.py", "sina_news.py", "eastmoney_news.py"):
        try:
            r = subprocess.run(
                [sys.executable, project_path("engines", script)],
                cwd=project_path(), timeout=240,
            )
            results[script] = "ok" if r.returncode == 0 else "fail"
        except Exception:
            results[script] = "fail"
    try:
        r = subprocess.run(
            [sys.executable, project_path("engines", "rule_screen.py"), "--reset"],
            cwd=project_path(), timeout=120,
        )
        results["rule_screen"] = "ok" if r.returncode == 0 else "fail"
    except Exception:
        results["rule_screen"] = "fail"
    build_queue()
    render()
    return results


class Handler(BaseHTTPRequestHandler):
    def _send(self, code, body, ctype="application/json; charset=utf-8"):
        data = body if isinstance(body, bytes) else json.dumps(body, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        if self.path in ("/", "/index.html"):
            html_path = project_path("web/index.html")
            if not os.path.exists(html_path):
                render()
            with open(html_path, "rb") as f:
                self._send(200, f.read(), "text/html; charset=utf-8")
        elif self.path.startswith("/financials"):
            from urllib.parse import parse_qs, urlparse
            qs = parse_qs(urlparse(self.path).query)
            company = (qs.get("company") or [""])[0]
            data = fetch_financials.fetch_financials(company) if company else {"status": "no_report", "message": "缺少 company 参数"}
            self._send(200, data)
        elif self.path.startswith("/news"):
            from urllib.parse import parse_qs, urlparse
            qs = parse_qs(urlparse(self.path).query)
            q = (qs.get("q") or [""])[0]
            source = (qs.get("source") or [""])[0]
            try:
                days = int((qs.get("days") or ["45"])[0])
            except ValueError:
                days = 45
            try:
                page = max(1, int((qs.get("page") or ["1"])[0]))
            except ValueError:
                page = 1
            try:
                page_size = min(100, max(5, int((qs.get("page_size") or ["50"])[0])))
            except ValueError:
                page_size = 50
            data = store.search_announcements(q=q, source=source, days=days, page=page, page_size=page_size)
            self._send(200, data)
        elif self.path == "/settings":
            s = radar_settings.get_settings()
            cfg = load_config()
            self._send(200, {
                "settings": s,
                "defaults": radar_settings.DEFAULTS,
                "effective": {
                    "keywords": radar_settings.effective_keywords(
                        (cfg or {}).get("crawl", {}).get("keywords", []) if cfg else []),
                    "days_window": radar_settings.effective_days_window(
                        (cfg or {}).get("crawl", {}).get("days_window", 180) if cfg else 180),
                    "exclude_words": radar_settings.exclude_words(),
                },
                "message": "关键词为空时回退 config.yaml 默认值；配置在下次运行流程时生效。",
            })
        elif self.path == "/queue.json":
            snap_dir = project_path("data/queue_snapshots")
            files = sorted(f for f in os.listdir(snap_dir) if f.endswith(".json"))
            with open(os.path.join(snap_dir, files[-1]), encoding="utf-8") as f:
                self._send(200, f.read())
        else:
            self._send(404, {"error": "not found"})

    def do_POST(self):
        if self.path == "/pitch":
            try:
                n = int(self.headers.get("Content-Length", 0))
                body = json.loads(self.rfile.read(n).decode("utf-8")) if n else {}
                company = (body.get("company") or "").strip()
                if not company:
                    self._send(400, {"error": "缺少 company 参数"})
                    return
                r = subprocess.run(
                    [sys.executable, project_path("engines", "visit_pitch.py"),
                     "--company", company, "--json"],
                    cwd=project_path(), timeout=180, capture_output=True, text=True,
                )
                if r.returncode != 0:
                    self._send(500, {"error": (r.stderr or r.stdout or "生成失败").strip()[:500]})
                    return
                import json as _json
                data = _json.loads(r.stdout)
                data["company"] = company
                self._send(200, data)
            except Exception as exc:
                self._send(500, {"error": f"话术生成失败：{exc}"})
            return
        if self.path == "/settings":
            try:
                n = int(self.headers.get("Content-Length", 0))
                body = json.loads(self.rfile.read(n).decode("utf-8")) if n else {}
                if body.get("action") == "reset":
                    cur = radar_settings.reset_settings()
                    self._send(200, {"ok": True, "settings": cur, "message": "已恢复默认配置（下次运行生效）"})
                else:
                    patch = {k: body.get(k) for k in ("keywords", "exclude_words", "days_window") if k in body}
                    cur = radar_settings.save_settings(patch)
                    self._send(200, {"ok": True, "settings": cur, "message": "已保存（下次运行流程时生效）"})
            except Exception as exc:
                self._send(500, {"error": f"保存失败：{exc}"})
            return
        if self.path == "/financials/update":
            n = int(self.headers.get("Content-Length", 0))
            body = json.loads(self.rfile.read(n).decode("utf-8"))
            company = body.get("company", "")
            try:
                data = fetch_financials.fetch_financials(company, force=True)
                data["message"] = data.get("message") or "已更新"
                self._send(200, data)
            except Exception as exc:
                self._send(500, {"status": "error", "message": f"抓取失败：{exc}"})
            return
        if self.path == "/news/update":
            try:
                results = _run_pipeline()
                ok = all(v == "ok" for v in results.values())
                self._send(200, {
                    "ok": ok,
                    "message": "数据已更新（爬虫+筛选+队列+页面已重建）" if ok
                              else f"部分更新（{results}）",
                    "results": results,
                })
            except Exception as exc:
                self._send(500, {"error": f"更新失败：{exc}"})
            return
        if self.path != "/action":
            self._send(404, {"error": "not found"})
            return
        try:
            n = int(self.headers.get("Content-Length", 0))
            body = json.loads(self.rfile.read(n).decode("utf-8"))
            oid, act, owner = body.get("opportunity_id"), body.get("action"), body.get("owner")
            if act == "claim":
                store.set_lifecycle(oid, "verifying", owner=owner)
            elif act == "contact":
                store.set_lifecycle(oid, "contacted", owner=owner)
            elif act == "invalid":
                store.set_lifecycle(oid, "invalid", owner=owner)
            else:
                self._send(400, {"error": f"未知动作 {act}"})
                return
            build_queue()
            render()
            self._send(200, {"ok": True, "opportunity_id": oid, "lifecycle": store.get_opportunity(oid)["lifecycle"],
                             "message": "已更新并重新生成队列与页面"})
        except Exception as exc:
            self._send(500, {"error": str(exc)})

    def log_message(self, *args):
        pass


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=8000)
    args = ap.parse_args()
    store.init_db()
    _ensure_seeded()
    print(f"[info] 商机雷达演示服务: http://127.0.0.1:{args.port}")
    ThreadingHTTPServer(("127.0.0.1", args.port), Handler).serve_forever()


if __name__ == "__main__":
    main()
