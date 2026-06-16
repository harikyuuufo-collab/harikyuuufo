#!/usr/bin/env python3
"""
renamer.py — ファイルリネームツール（連番対応）

使い方:
  python renamer.py [ディレクトリ] [オプション]

例:
  python renamer.py ./photos --prefix "photo_" --seq --start 1 --pad 3
  python renamer.py ./files --pattern "{stem}_{n:03d}{ext}" --ext .txt
  python renamer.py ./docs --replace "old" "new"
"""

import os
import re
import sys
import argparse
from pathlib import Path


RESET  = "\033[0m"
BOLD   = "\033[1m"
GREEN  = "\033[32m"
YELLOW = "\033[33m"
CYAN   = "\033[36m"
RED    = "\033[31m"
DIM    = "\033[2m"


def color(text, *codes):
    return "".join(codes) + text + RESET


def build_rename_plan(files, args):
    """ファイルリストからリネーム計画を生成する"""
    plan = []
    counter = args.start

    for i, path in enumerate(files):
        stem = path.stem
        ext = path.suffix
        n = counter + i if args.seq else i + args.start

        if args.pattern:
            try:
                new_name = args.pattern.format(
                    stem=stem,
                    ext=ext,
                    n=n,
                    i=i,
                    name=path.name,
                )
            except KeyError as e:
                print(color(f"パターンエラー: {e} は無効なキーです", RED))
                sys.exit(1)
        else:
            new_stem = stem
            if args.replace:
                old, new = args.replace
                new_stem = new_stem.replace(old, new)
            if args.regex_replace:
                pattern_re, repl = args.regex_replace
                new_stem = re.sub(pattern_re, repl, new_stem)
            if args.prefix:
                new_stem = args.prefix + new_stem
            if args.suffix:
                new_stem = new_stem + args.suffix
            if args.seq:
                pad = args.pad
                seq_str = str(n).zfill(pad)
                if args.seq_pos == "prefix":
                    new_stem = seq_str + (args.sep or "_") + new_stem
                else:
                    new_stem = new_stem + (args.sep or "_") + seq_str
            new_ext = args.new_ext if args.new_ext else ext
            new_name = new_stem + new_ext

        new_path = path.parent / new_name
        plan.append((path, new_path))

    return plan


def print_preview(plan, cwd):
    """リネーム計画をプレビュー表示する"""
    print()
    print(color("  リネームプレビュー", BOLD, CYAN))
    print(color("  " + "─" * 60, DIM))
    changed = 0
    for src, dst in plan:
        src_rel = src.relative_to(cwd) if src.is_relative_to(cwd) else src
        dst_rel = dst.relative_to(cwd) if dst.is_relative_to(cwd) else dst
        if src == dst:
            print(color(f"  = {src_rel}", DIM))
        else:
            print(f"  {color(str(src_rel), YELLOW)}  →  {color(str(dst_rel), GREEN)}")
            changed += 1
    print(color("  " + "─" * 60, DIM))
    print(f"  {color(str(changed), BOLD)} 件が変更されます（合計 {len(plan)} 件）")
    print()
    return changed


def check_conflicts(plan):
    """重複・上書き衝突を検出する"""
    errors = []
    dst_set = {}
    for src, dst in plan:
        if dst in dst_set:
            errors.append(f"衝突: {dst.name} が複数回使用されています")
        dst_set[dst] = src
        if dst.exists() and dst != src:
            errors.append(f"上書き警告: {dst} は既に存在します")
    return errors


def execute_plan(plan, dry_run=False):
    """リネームを実行する"""
    done = 0
    errors = []
    for src, dst in plan:
        if src == dst:
            continue
        if dry_run:
            print(color(f"  [DRY] {src.name} → {dst.name}", DIM))
            done += 1
            continue
        try:
            src.rename(dst)
            print(color(f"  ✓ {src.name} → {dst.name}", GREEN))
            done += 1
        except OSError as e:
            msg = f"  ✗ {src.name}: {e}"
            print(color(msg, RED))
            errors.append(msg)
    return done, errors


def collect_files(directory, ext_filter, recursive, sort_key):
    """対象ファイルを収集する"""
    p = Path(directory)
    if not p.exists():
        print(color(f"エラー: ディレクトリが見つかりません: {directory}", RED))
        sys.exit(1)

    glob = "**/*" if recursive else "*"
    files = [f for f in p.glob(glob) if f.is_file()]

    if ext_filter:
        exts = [e if e.startswith(".") else "." + e for e in ext_filter]
        files = [f for f in files if f.suffix.lower() in exts]

    key_fn = {
        "name": lambda f: f.name.lower(),
        "mtime": lambda f: f.stat().st_mtime,
        "ctime": lambda f: f.stat().st_ctime,
        "size": lambda f: f.stat().st_size,
    }.get(sort_key, lambda f: f.name.lower())

    files.sort(key=key_fn)
    return files


def parse_args():
    parser = argparse.ArgumentParser(
        description="ファイルリネームツール（連番対応）",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
パターン変数:
  {stem}   拡張子なしのファイル名
  {ext}    拡張子（.txt など）
  {name}   ファイル名全体
  {n}      連番（--start で開始番号を指定）
  {i}      0始まりのインデックス

例:
  # 連番をサフィックスに付ける
  python renamer.py ./photos --seq

  # 連番をプレフィックスに付ける（3桁ゼロパディング）
  python renamer.py ./photos --seq --seq-pos prefix --pad 3

  # カスタムパターンで連番
  python renamer.py ./files --pattern "report_{n:04d}{ext}"

  # 文字列置換
  python renamer.py ./docs --replace " " "_"

  # 正規表現置換
  python renamer.py ./files --regex-replace "\\d+" "NUM"

  # 特定の拡張子のみ対象
  python renamer.py ./files --ext jpg png --seq

  # プレビューのみ（実際には変更しない）
  python renamer.py ./files --seq --dry-run
        """,
    )
    parser.add_argument("directory", nargs="?", default=".", help="対象ディレクトリ（省略時はカレント）")
    parser.add_argument("--ext", nargs="+", metavar="EXT", help="対象拡張子（例: jpg png）")
    parser.add_argument("--recursive", "-r", action="store_true", help="サブディレクトリも対象")
    parser.add_argument("--sort", choices=["name", "mtime", "ctime", "size"], default="name", help="ソート順（デフォルト: name）")
    parser.add_argument("--dry-run", "-n", action="store_true", help="プレビューのみ（実際には変更しない）")
    parser.add_argument("--yes", "-y", action="store_true", help="確認をスキップして実行")

    # リネームオプション
    grp = parser.add_argument_group("リネームオプション")
    grp.add_argument("--pattern", metavar="PATTERN", help="カスタムパターン（例: '{stem}_{n:03d}{ext}'）")
    grp.add_argument("--prefix", metavar="STR", help="ファイル名の先頭に追加")
    grp.add_argument("--suffix", metavar="STR", help="ファイル名の末尾（拡張子の前）に追加")
    grp.add_argument("--replace", nargs=2, metavar=("OLD", "NEW"), help="文字列置換")
    grp.add_argument("--regex-replace", nargs=2, metavar=("PATTERN", "REPL"), help="正規表現置換")
    grp.add_argument("--new-ext", metavar="EXT", help="拡張子を変更（例: .jpg）")

    # 連番オプション
    seq = parser.add_argument_group("連番オプション")
    seq.add_argument("--seq", "-s", action="store_true", help="連番を付ける")
    seq.add_argument("--start", type=int, default=1, help="開始番号（デフォルト: 1）")
    seq.add_argument("--pad", type=int, default=3, help="ゼロパディング桁数（デフォルト: 3）")
    seq.add_argument("--sep", default="_", metavar="SEP", help="連番と名前の区切り文字（デフォルト: _）")
    seq.add_argument("--seq-pos", choices=["suffix", "prefix"], default="suffix", help="連番の位置（デフォルト: suffix）")

    return parser.parse_args()


def main():
    args = parse_args()
    cwd = Path.cwd()

    files = collect_files(args.directory, args.ext, args.recursive, args.sort)

    if not files:
        print(color("  対象ファイルが見つかりませんでした。", YELLOW))
        return

    print(color(f"\n  対象: {args.directory}  ({len(files)} ファイル)", BOLD))

    plan = build_rename_plan(files, args)
    changed = print_preview(plan, cwd)

    if changed == 0:
        print(color("  変更するファイルはありません。", DIM))
        return

    conflicts = check_conflicts(plan)
    if conflicts:
        print(color("  警告:", YELLOW, BOLD))
        for c in conflicts:
            print(color(f"    {c}", YELLOW))
        print()

    if args.dry_run:
        print(color("  --dry-run モード: 実際の変更は行われません。", DIM))
        execute_plan(plan, dry_run=True)
        return

    if not args.yes:
        try:
            ans = input(color("  実行しますか? [y/N]: ", BOLD))
        except (KeyboardInterrupt, EOFError):
            print()
            print(color("  キャンセルしました。", DIM))
            return
        if ans.strip().lower() not in ("y", "yes"):
            print(color("  キャンセルしました。", DIM))
            return

    done, errors = execute_plan(plan)
    print()
    print(color(f"  完了: {done} 件リネームしました。", BOLD, GREEN))
    if errors:
        print(color(f"  エラー: {len(errors)} 件", RED))


if __name__ == "__main__":
    main()
