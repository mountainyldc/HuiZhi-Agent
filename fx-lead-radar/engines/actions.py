"""商机动作 CLI：认领 / 推进 / 标记无效（供 Pi 工具调用）。

用法:
  python actions.py --id opp_x --claim --owner 叶霖德
  python actions.py --id opp_x --contact --owner 叶霖德
  python actions.py --id opp_x --invalid --owner 叶霖德
"""
import argparse

import store


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--id", required=True)
    ap.add_argument("--claim", action="store_true", help="认领 -> 待核实")
    ap.add_argument("--contact", action="store_true", help="推进 -> 已联系")
    ap.add_argument("--invalid", action="store_true", help="标记无效")
    ap.add_argument("--owner", default=None)
    args = ap.parse_args()

    store.init_db()
    o = store.get_opportunity(args.id)
    if not o:
        print(f"[error] 商机不存在: {args.id}")
        raise SystemExit(1)

    if args.claim:
        store.set_lifecycle(args.id, "verifying", owner=args.owner)
        print(f"[result] 已认领 {o['company_name']} -> 待核实, owner={args.owner}")
    elif args.contact:
        store.set_lifecycle(args.id, "contacted", owner=args.owner)
        print(f"[result] 已推进 {o['company_name']} -> 已联系, owner={args.owner}")
    elif args.invalid:
        store.set_lifecycle(args.id, "invalid", owner=args.owner)
        print(f"[result] 已标记无效 {o['company_name']}")
    else:
        print("[error] 请指定 --claim / --contact / --invalid")
        raise SystemExit(1)


if __name__ == "__main__":
    main()