"""四大名著语料取数器（公版文本）。

源：GitHub `xp44mm/hanchuancaolu`（源自漢川草廬），四部全本、逐回分章、UTF-8 纯文本。
本脚本只做一件事：把分章 txt 拉到本地 corpus/ 目录，供 B1 抽取层与 Creator 引擎消费。

零依赖（仅标准库 urllib）。可重复执行：目标文件已存在且字节数一致则跳过。

用法：
    python corpus_fetch.py            # 全量拉取四部
    python corpus_fetch.py --verify   # 只核验本地已下载的完整性，不联网取新文件
"""

from __future__ import annotations

import json
import os
import sys
import time
import urllib.parse
import urllib.request

REPO = "xp44mm/hanchuancaolu"
UA = "nohn-corpus-fetch/1.0"

# 仓库中的繁体目录名 -> 本地简体目录名（本地用简体，便于跨工具检索）
BOOKS = {
    "三國演義": "三国演义",
    "水滸傳": "水浒传",
    "西遊記": "西游记",
    "紅樓夢": "红楼梦",
}

ROOT = os.path.dirname(os.path.abspath(__file__))
DEST = os.path.join(ROOT, "corpus")


def _encode_url(url: str) -> str:
    """远端返回的 download_url 路径含中文与空格，urllib 会拒绝，须逐段百分号编码。

    注意 safe 必须含 `%`：调用方可能已经编码过路径，若再编码一次会把 `%E4` 变成
    `%25E4` 造成双重编码（实测会 404）。
    """
    parts = urllib.parse.urlsplit(url)
    path = urllib.parse.quote(parts.path, safe="/%")
    query = urllib.parse.quote(parts.query, safe="=&%+")
    return urllib.parse.urlunsplit((parts.scheme, parts.netloc, path, query, parts.fragment))


def _get(url: str, timeout: int = 90) -> bytes:
    req = urllib.request.Request(_encode_url(url), headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read()


def list_dir(path: str) -> list:
    """列出仓库中某个目录的文件条目。"""
    url = "https://api.github.com/repos/%s/contents/%s" % (
        REPO,
        urllib.parse.quote(path),
    )
    return json.loads(_get(url).decode("utf-8"))


def fetch_book(remote_dir: str, local_dir: str, verify_only: bool = False) -> dict:
    """拉取一本书的全部分章；返回统计。

    断点续传：本地文件字节数 == 远端声明字节数则跳过（半截文件会被重下）。
    重试：每个文件最多 3 次，单次 socket 超时 25s —— 实测 raw.githubusercontent
    偶发「连上不吐数据」，urlopen 的 timeout 只作用于单次 socket 操作，
    若不设短超时+重试会整批挂死（本脚本初版即如此，停在 206/461）。
    """
    entries = [e for e in list_dir(remote_dir) if e.get("type") == "file"]
    out_dir = os.path.join(DEST, local_dir)
    os.makedirs(out_dir, exist_ok=True)

    ok, skipped, failed = 0, 0, []
    for e in entries:
        name = e["name"]
        size = e["size"]
        dest = os.path.join(out_dir, name)
        if os.path.exists(dest) and os.path.getsize(dest) == size:
            skipped += 1
            continue
        if verify_only:
            failed.append((name, "本地缺失或字节数不符"))
            continue
        last_err = ""
        blob = None
        for attempt in range(1, 4):
            try:
                blob = _get(e["download_url"], timeout=25)
                break
            except Exception as exc:  # 网络失败：退避重试，用尽后记录
                last_err = str(exc)[:60]
                blob = None
                time.sleep(attempt * 1.5)
        if blob is None:
            failed.append((name, "重试3次仍失败: " + last_err))
            continue
        if len(blob) == size:
            with open(dest, "wb") as fh:
                fh.write(blob)
            ok += 1
        else:
            failed.append((name, "字节数不符 %d != %d" % (len(blob), size)))

    local_total = 0
    for name in os.listdir(out_dir):
        local_total += os.path.getsize(os.path.join(out_dir, name))

    return {
        "book": local_dir,
        "remote_files": len(entries),
        "downloaded": ok,
        "skipped": skipped,
        "failed": failed,
        "local_bytes": local_total,
    }


def main() -> int:
    verify_only = "--verify" in sys.argv

    print("语料取数：%s -> %s" % (REPO, DEST))
    print("%-10s %8s %8s %8s %14s" % ("书", "远端文件", "新下载", "跳过", "本地字节"))
    print("-" * 54)

    grand_files = grand_bytes = 0
    all_failed = []
    for remote, local in BOOKS.items():
        stat = fetch_book(remote, local, verify_only=verify_only)
        grand_files += stat["remote_files"]
        grand_bytes += stat["local_bytes"]
        print(
            "%-10s %8d %8d %8d %14s"
            % (
                stat["book"],
                stat["remote_files"],
                stat["downloaded"],
                stat["skipped"],
                format(stat["local_bytes"], ","),
            )
        )
        for name, why in stat["failed"]:
            all_failed.append("%s/%s: %s" % (stat["book"], name, why))

    print("-" * 54)
    print(
        "%-10s %8d %8s %8s %14s"
        % ("合计", grand_files, "", "", format(grand_bytes, ","))
    )
    if all_failed:
        print("\n失败 %d 项：" % len(all_failed))
        for line in all_failed[:20]:
            print("  " + line)
        return 1
    print("\n全部一致。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
