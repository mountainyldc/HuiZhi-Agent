"""轻量演示服务：静态页 + 认领/标记无效持久化。

用法:
  python serve.py [--port 8000]
  浏览器打开 http://127.0.0.1:8000
"""
import argparse
import json
import os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from common import project_path
import store
from build_queue import build_queue
from render_web import render


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
        elif self.path == "/queue.json":
            snap_dir = project_path("data/queue_snapshots")
            files = sorted(f for f in os.listdir(snap_dir) if f.endswith(".json"))
            with open(os.path.join(snap_dir, files[-1]), encoding="utf-8") as f:
                self._send(200, f.read())
        else:
            self._send(404, {"error": "not found"})

    def do_POST(self):
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
    print(f"[info] 商机雷达演示服务: http://127.0.0.1:{args.port}")
    ThreadingHTTPServer(("127.0.0.1", args.port), Handler).serve_forever()


if __name__ == "__main__":
    main()