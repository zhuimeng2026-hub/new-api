#!/usr/bin/env python3
"""直接查询 new-api PostgreSQL 数据库日志表

用法:
  python3 query_db.py                                 # 运行全部 4 个查询
  python3 query_db.py --token 72                      # 指定令牌 ID
  python3 query_db.py --ip 175.178.33.107             # 指定 IP
  python3 query_db.py --model deepseek-v4-flash       # 指定模型名
  python3 query_db.py -n 30                           # 条数 (默认 20)
"""

import argparse
import subprocess
import sys


DOCKER_EXEC = [
    "docker", "exec", "-i", "postgres",
    "psql", "-U", "root", "-d", "new-api",
    "--no-align", "--tuples-only",
    "--field-separator=|",
]


def run_sql(sql):
    """执行 SQL，返回行列表"""
    r = subprocess.run(
        DOCKER_EXEC + ["-c", sql],
        capture_output=True, text=True, timeout=15,
    )
    if r.returncode != 0:
        print(f"  错误: {r.stderr.strip()}")
        return []
    lines = [l.strip() for l in r.stdout.strip().split("\n") if l.strip()]
    return lines


def query1(token, n):
    """token 最近 N 条日志"""
    return run_sql(f"""
        SELECT id, to_char(to_timestamp(created_at) AT TIME ZONE 'Asia/Shanghai', 'MM-DD HH24:MI:SS'), type,
               model_name, channel_id, quota, ip,
               left(coalesce(content,''), 80)
        FROM logs
        WHERE token_id = {token}
        ORDER BY id DESC LIMIT {n}
    """)


def query2(token, model, n):
    """指定模型的消耗日志"""
    return run_sql(f"""
        SELECT id, to_char(to_timestamp(created_at) AT TIME ZONE 'Asia/Shanghai', 'MM-DD HH24:MI:SS'),
               model_name, channel_id, quota, ip, content
        FROM logs
        WHERE token_id = {token} AND model_name = '{model}' AND type = 2
        ORDER BY id DESC LIMIT {n}
    """)


def query3(ip, n):
    """IP 的错误日志"""
    return run_sql(f"""
        SELECT id, to_char(to_timestamp(created_at) AT TIME ZONE 'Asia/Shanghai', 'MM-DD HH24:MI:SS'),
               model_name, channel_id, content
        FROM logs
        WHERE ip = '{ip}' AND type = 5
        ORDER BY id DESC LIMIT {n}
    """)


def query4(ip):
    """IP 调了哪些模型"""
    return run_sql(f"""
        SELECT model_name, count(*),
               to_char(min(to_timestamp(created_at) AT TIME ZONE 'Asia/Shanghai'), 'MM-DD HH24:MI'),
               to_char(max(to_timestamp(created_at) AT TIME ZONE 'Asia/Shanghai'), 'MM-DD HH24:MI')
        FROM logs
        WHERE ip = '{ip}'
        GROUP BY model_name
        ORDER BY count(*) DESC
    """)


def parse_args():
    p = argparse.ArgumentParser(description="直查 new-api PostgreSQL 日志")
    p.add_argument("--token", type=int, default=72, help="令牌 ID (默认 72)")
    p.add_argument("--ip", default="175.178.33.107", help="IP 地址")
    p.add_argument("--model", default="deepseek-v4-flash", help="模型名")
    p.add_argument("-n", type=int, default=20, help="每条查询条数 (默认 20)")
    return p.parse_args()


def header(title):
    w = 60
    print()
    print(f"  {'=' * w}")
    print(f"  {title}")
    print(f"  {'=' * w}")


def show(rows, cols):
    if not rows:
        print("  (无结果)")
        return
    # 固定宽度
    widths = [20, 18, 12, 12, 10] + [40] * (len(cols) - 5)
    # 打印表头
    hdr = "  " + " │ ".join(c.ljust(w) for c, w in zip(cols, widths))
    sep = "  " + "─┼─".join("─" * w for w in widths)
    print(hdr)
    print(sep)
    for row in rows:
        fields = row.split("|")
        line = "  " + " │ ".join(f.ljust(w)[:w] for f, w in zip(fields, widths))
        print(line)


def main():
    args = parse_args()

    header("Q1: token 最近日志")
    show(query1(args.token, args.n),
         ["ID", "时间", "Type", "Model", "Ch", "Quota", "IP", "Content"])

    header(f"Q2: {args.model} 错误日志 (type=5)")
    show(run_sql(f"""
        SELECT id, to_char(to_timestamp(created_at) AT TIME ZONE 'Asia/Shanghai', 'MM-DD HH24:MI:SS'),
               model_name, channel_id, ip,
               left(coalesce(content,''), 80)
        FROM logs
        WHERE model_name = '{args.model}' AND type = 5
        ORDER BY id DESC LIMIT {args.n}
    """), ["ID", "时间", "Model", "Ch", "IP", "Content"])

    header(f"Q3: {args.model} 消耗日志 (type=2)")
    show(run_sql(f"""
        SELECT id, to_char(to_timestamp(created_at) AT TIME ZONE 'Asia/Shanghai', 'MM-DD HH24:MI:SS'),
               channel_id, quota, ip,
               left(coalesce(content,''), 80)
        FROM logs
        WHERE model_name = '{args.model}' AND type = 2
        ORDER BY id DESC LIMIT {args.n}
    """), ["ID", "时间", "Ch", "Quota", "IP", "Content"])

    header(f"Q4: {args.model} 按 IP 分布")
    show(run_sql(f"""
        SELECT ip, count(*),
               to_char(min(to_timestamp(created_at) AT TIME ZONE 'Asia/Shanghai'), 'MM-DD HH24:MI'),
               to_char(max(to_timestamp(created_at) AT TIME ZONE 'Asia/Shanghai'), 'MM-DD HH24:MI')
        FROM logs
        WHERE model_name = '{args.model}'
        GROUP BY ip
        ORDER BY count(*) DESC LIMIT 20
    """), ["IP", "Count", "最早", "最晚"])


if __name__ == "__main__":
    main()
