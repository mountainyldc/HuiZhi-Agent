"""Web 渲染引擎：由队列快照生成自包含的静态 HTML（零依赖，可直接双击打开）。

用法:
  python render_web.py                     # 用最新快照渲染 web/index.html
  python render_web.py --input <snapshot>  # 指定快照
  python render_web.py --out <path>        # 指定输出
"""
import argparse
import json
import os

from common import load_config, project_path


def load_template():
    """读取引擎目录下的 web_template.html（标准模板，避免内嵌失同步）。"""
    path = project_path("engines", "web_template.html")
    with open(path, encoding="utf-8") as f:
        return f.read()


def render(input_path=None, out=None):
    cfg = load_config()
    if input_path is None:
        snap_dir = project_path("data/queue_snapshots")
        files = sorted(f for f in os.listdir(snap_dir) if f.endswith(".json"))
        if not files:
            raise FileNotFoundError("没有队列快照，请先运行 build_queue.py")
        input_path = os.path.join(snap_dir, files[-1])
    with open(input_path, encoding="utf-8") as f:
        snapshot = json.load(f)
    template = load_template()
    html = template.replace("__SNAPSHOT_JSON__", json.dumps(snapshot, ensure_ascii=False))
    import store
    profiles = {p["company"]: p for p in store.list_profiles(limit=500)}
    html = html.replace("__PROFILES_JSON__", json.dumps(profiles, ensure_ascii=False))
    out = out or project_path(cfg["web"]["output"])
    os.makedirs(os.path.dirname(out), exist_ok=True)
    with open(out, "w", encoding="utf-8") as f:
        f.write(html)
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--input", default=None)
    ap.add_argument("--out", default=None)
    args = ap.parse_args()
    out = render(args.input, args.out)
    print(f"[result] 已渲染: {out}")


if __name__ == "__main__":
    main()
