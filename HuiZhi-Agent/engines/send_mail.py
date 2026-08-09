# -*- coding: utf-8 -*-
"""工银汇智 · 邮件发送引擎：商机日报 / 公司报告发送到指定邮箱。

用法:
  python send_mail.py --daily [--top 10] [--to xxx@qq.com]   # 发今日商机日报
  python send_mail.py --report 东鹏饮料 [--to xxx@qq.com]     # 发某公司商机摘要
  python send_mail.py --test                                  # 发测试邮件验证 SMTP 配置

配置来源（优先级：环境变量 > data/mail_config.json，授权码不进 Git）:
  SMTP_HOST / SMTP_PORT / SMTP_USERNAME / SMTP_PASSWORD / MAIL_TO
"""
import argparse
import datetime
import json
import os
import smtplib
import sys
from email.header import Header
from email.mime.text import MIMEText
from email.utils import formataddr

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from common import project_path


def load_config():
    cfg = {}
    path = project_path("data", "mail_config.json")
    if os.path.exists(path):
        try:
            with open(path, encoding="utf-8") as f:
                cfg = json.load(f)
        except Exception:
            cfg = {}

    def pick(env, key, default=None):
        v = os.environ.get(env)
        return v if v else cfg.get(key, default)

    return {
        "host": pick("SMTP_HOST", "host", "smtp.qq.com"),
        "port": int(pick("SMTP_PORT", "port", 587)),
        "username": pick("SMTP_USERNAME", "username"),
        "password": pick("SMTP_PASSWORD", "password"),
        "to": pick("MAIL_TO", "to"),
    }


def latest_snapshot():
    snap_dir = project_path("data", "queue_snapshots")
    if not os.path.isdir(snap_dir):
        return None
    files = sorted(
        (f for f in os.listdir(snap_dir) if f.endswith(".json")),
        reverse=True,
    )
    for fn in files:
        try:
            with open(os.path.join(snap_dir, fn), encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, dict) and data.get("items"):
                return data
        except Exception:
            continue
    return None


def _esc(s):
    return str(s or "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def build_daily_html(top=10):
    snap = latest_snapshot()
    if not snap:
        return None, "未找到商机队列快照，请先运行 /radar 或 build_queue.py"
    items = snap["items"][:top]
    rows = []
    for it in items:
        tags = "、".join(it.get("tags") or [])
        rows.append(
            "<tr><td align=center>{rank}</td><td><b>{name}</b></td><td align=center>{city}</td>"
            "<td align=center><b>{score}</b></td><td>{tags}</td><td>{title}</td></tr>".format(
                rank=it.get("rank", ""),
                name=_esc(it.get("company_name", "")),
                city=_esc(it.get("city", "")),
                score=it.get("score", ""),
                tags=_esc(tags),
                title=_esc(it.get("title", "")),
            )
        )
    date_str = snap.get("date") or snap.get("generated_at", "")[:10]
    html = (
        "<html><body style='font-family:Microsoft YaHei,sans-serif;color:#212121;'>"
        "<h3 style='color:#C7000B;'>📡 工银汇智 · 今日商机日报（{date}）</h3>"
        "<p>共 <b>{total}</b> 条商机，以下为 Top {top}：</p>"
        "<table border='1' cellspacing='0' cellpadding='6' style='border-collapse:collapse;'>"
        "<tr style='background:#FAF8F5;'><th>#</th><th>公司</th><th>城市</th><th>分数</th><th>标签</th><th>触发事件</th></tr>"
        "{rows}</table>"
        "<p style='color:#6E6E6E;'>—— 工银汇智 · 企业外汇智能体自动生成</p>"
        "</body></html>"
    ).format(date=date_str, total=len(snap["items"]), top=top, rows="".join(rows))
    return html, None


def build_company_html(company, top=10):
    snap = latest_snapshot()
    if not snap:
        return None, "未找到商机队列快照，请先运行 /radar 或 build_queue.py"
    hits = [it for it in snap["items"] if company in (it.get("company_name") or "")]
    if not hits:
        return None, "商机队列中未找到公司：%s" % company
    rows = []
    for it in hits[:top]:
        tags = "、".join(it.get("tags") or [])
        rows.append(
            "<tr><td align=center>{rank}</td><td><b>{name}</b></td><td align=center>{city}</td>"
            "<td align=center><b>{score}</b></td><td>{tags}</td><td>{title}</td></tr>".format(
                rank=it.get("rank", ""),
                name=_esc(it.get("company_name", "")),
                city=_esc(it.get("city", "")),
                score=it.get("score", ""),
                tags=_esc(tags),
                title=_esc(it.get("title", "")),
            )
        )
    date_str = snap.get("date") or snap.get("generated_at", "")[:10]
    html = (
        "<html><body style='font-family:Microsoft YaHei,sans-serif;color:#212121;'>"
        "<h3 style='color:#C7000B;'>🏢 工银汇智 · 商机摘要：{company}</h3>"
        "<p>数据日期：{date}，命中 {n} 条商机：</p>"
        "<table border='1' cellspacing='0' cellpadding='6' style='border-collapse:collapse;'>"
        "<tr style='background:#FAF8F5;'><th>#</th><th>公司</th><th>城市</th><th>分数</th><th>标签</th><th>触发事件</th></tr>"
        "{rows}</table>"
        "<p style='color:#6E6E6E;'>—— 工银汇智 · 企业外汇智能体自动生成</p>"
        "</body></html>"
    ).format(company=_esc(company), date=date_str, n=len(hits), rows="".join(rows))
    return html, None


def send(subject, html, to, cfg):
    if not cfg.get("username") or not cfg.get("password"):
        return "缺少 SMTP 配置（环境变量或 data/mail_config.json）"
    msg = MIMEText(html, "html", "utf-8")
    msg["Subject"] = Header(subject, "utf-8")
    msg["From"] = formataddr((str(Header("工银汇智", "utf-8")), cfg["username"]))
    msg["To"] = to
    server = smtplib.SMTP(cfg["host"], cfg["port"], timeout=30)
    try:
        server.starttls()
        server.login(cfg["username"], cfg["password"])
        server.sendmail(cfg["username"], [to], msg.as_string())
    finally:
        try:
            server.quit()
        except Exception:
            pass
    return "已发送至 %s" % to


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--daily", action="store_true", help="发送今日商机日报")
    ap.add_argument("--report", default=None, help="发送指定公司商机摘要")
    ap.add_argument("--top", type=int, default=10)
    ap.add_argument("--to", default=None, help="收件人邮箱，默认取配置")
    ap.add_argument("--test", action="store_true", help="发送测试邮件")
    args = ap.parse_args()

    cfg = load_config()
    to = args.to or cfg.get("to")
    if not to:
        print("[error] 未配置收件人（--to 或 MAIL_TO / mail_config.json 的 to 字段）")
        sys.exit(1)

    if args.test:
        html = "<html><body style='font-family:Microsoft YaHei,sans-serif;'><h3 style='color:#C7000B;'>✅ 工银汇智邮件功能测试</h3><p>SMTP 配置可用。</p></body></html>"
        subject = "[工银汇智] 邮件功能测试"
        msg = send(subject, html, to, cfg)
        print("[result]", msg)
        return

    if args.daily:
        html, err = build_daily_html(top=args.top)
        if err:
            print("[error]", err)
            sys.exit(1)
        today = datetime.date.today().isoformat()
        subject = "[工银汇智] 今日商机日报 %s" % today
        print("[result]", send(subject, html, to, cfg))
        return

    if args.report:
        html, err = build_company_html(args.report, top=args.top)
        if err:
            print("[error]", err)
            sys.exit(1)
        subject = "[工银汇智] 商机摘要：%s" % args.report
        print("[result]", send(subject, html, to, cfg))
        return

    ap.print_help()


if __name__ == "__main__":
    main()
