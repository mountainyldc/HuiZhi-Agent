"""杞婚噺婕旂ず鏈嶅姟锛氶潤鎬侀〉 + 璁ら/鏍囪鏃犳晥鎸佷箙鍖?+ 璧勮涓績 + 骞存姤鏁版嵁銆?
鐢ㄦ硶:
  python serve.py [--port 8000]
  娴忚鍣ㄦ墦寮€ http://127.0.0.1:8000

鍚姩鏃惰嫢鏁版嵁搴撲负绌猴紝浼氳嚜鍔ㄧ敤 data/crawled 涓嬬殑鏁版嵁閲嶅缓鍟嗘満闃熷垪锛宑lone 鍗崇敤銆?"""
import argparse
import json
import os
import subprocess
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from common import project_path
import store
from build_queue import build_queue
from render_web import render
import fetch_financials


def _ensure_seeded():
    """鏁版嵁搴撲负绌烘椂锛岀敤宸叉湁 crawled 鏁版嵁閲嶅缓鍏憡/鍟嗘満骞舵覆鏌撻〉闈€?""
    n = len(store.list_announcements())
    if n > 0:
        return False
    print("[info] 鏁版嵁搴撲负绌猴紝鑷姩閲嶅缓锛坮ule_screen -> build_queue -> render锛?..")
    from rule_screen import rule_screen
    opps = rule_screen()
    print(f"[info] 閲嶅缓鍟嗘満 {len(opps)} 鏉?)
    build_queue()
    render()
    return True


def _run_pipeline():
    """鏇存柊鏁版嵁锛氫緷娆¤窇鐖櫕(鍚牱渚嬪洖閫€) -> 瑙勫垯绛涢€?-> 闃熷垪 -> 娓叉煋銆傝繑鍥?{script: ok/fail}銆?""
    results = {}
    for script in ("crawl_cninfo.py", "sina_news.py", "eastmoney_news.py", "crawl_em_feed.py", "crawl_ths.py", "crawl_hkex.py", "crawl_mofcom.py", "crawl_gov_gd.py"):
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
            data = fetch_financials.fetch_financials(company) if company else {"status": "no_report", "message": "缂哄皯 company 鍙傛暟"}
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
        elif self.path == "/queue.json":
            snap_dir = project_path("data/queue_snapshots")
            files = sorted(f for f in os.listdir(snap_dir) if f.endswith(".json"))
            with open(os.path.join(snap_dir, files[-1]), encoding="utf-8") as f:
                self._send(200, f.read())
        else:
            self._send(404, {"error": "not found"})

    def do_POST(self):
        if self.path == "/financials/update":
            n = int(self.headers.get("Content-Length", 0))
            body = json.loads(self.rfile.read(n).decode("utf-8"))
            company = body.get("company", "")
            try:
                data = fetch_financials.fetch_financials(company, force=True)
                data["message"] = data.get("message") or "宸叉洿鏂?
                self._send(200, data)
            except Exception as exc:
                self._send(500, {"status": "error", "message": f"鎶撳彇澶辫触锛歿exc}"})
            return
        if self.path == "/news/update":
            try:
                results = _run_pipeline()
                ok = all(v == "ok" for v in results.values())
                self._send(200, {
                    "ok": ok,
                    "message": "鏁版嵁宸叉洿鏂帮紙鐖櫕+绛涢€?闃熷垪+椤甸潰宸查噸寤猴級" if ok
                              else f"閮ㄥ垎鏇存柊锛坽results}锛?,
                    "results": results,
                })
            except Exception as exc:
                self._send(500, {"error": f"鏇存柊澶辫触锛歿exc}"})
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
                self._send(400, {"error": f"鏈煡鍔ㄤ綔 {act}"})
                return
            build_queue()
            render()
            self._send(200, {"ok": True, "opportunity_id": oid, "lifecycle": store.get_opportunity(oid)["lifecycle"],
                             "message": "宸叉洿鏂板苟閲嶆柊鐢熸垚闃熷垪涓庨〉闈?})
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
    print(f"[info] 鍟嗘満闆疯揪婕旂ず鏈嶅姟: http://127.0.0.1:{args.port}")
    ThreadingHTTPServer(("127.0.0.1", args.port), Handler).serve_forever()


if __name__ == "__main__":
    main()

