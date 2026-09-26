#!/usr/bin/env python3
"""
claude-code-compact-restore installer

  team     : プロジェクトにコミットしてチーム全員で使う（仕組みは共有、ノートは各自）
  personal : このプロジェクトで自分だけ使う（git には一切載せない）
  global   : 自分の全プロジェクトで使う（~/.claude に入れる）

  --uninstall : 指定モードで入れたものを取り除く（作業ノート・スナップショットは残す）
何度実行しても重複しません。v1（CLAUDE.md の @import 方式）からの移行も兼ねます。
"""
import argparse
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

KIT = Path(__file__).resolve().parent
SCRIPTS = ["pre_compact_snapshot.py", "post_compact_restore.py"]
SECTION = "## コンテキスト復元（圧縮対策）"
MARK = "# compact-restore-kit"


def ok(msg):
    print(f"✓ {msg}")


# ---------- settings.json ----------
def hook_config(prefix):
    def cmd(script):
        return f'python3 "{prefix}/{script}"'
    return {
        "PreCompact": [{"matcher": "*", "hooks": [
            {"type": "command", "command": cmd("pre_compact_snapshot.py"), "timeout": 30}]}],
        "SessionStart": [{"hooks": [
            {"type": "command", "command": cmd("post_compact_restore.py"), "timeout": 30}]}],
    }


def strip_our_hooks(settings):
    """このキット由来のフック（v1含む）を取り除く"""
    hooks = settings.get("hooks", {})
    for event in list(hooks):
        groups = []
        for g in hooks[event]:
            g["hooks"] = [h for h in g.get("hooks", [])
                          if not any(s in h.get("command", "") for s in SCRIPTS)]
            if g["hooks"]:
                groups.append(g)
        if groups:
            hooks[event] = groups
        else:
            del hooks[event]
    if not hooks:
        settings.pop("hooks", None)


def update_settings(path, prefix, install):
    data = json.loads(path.read_text()) if path.exists() else {}
    strip_our_hooks(data)
    if install:
        hooks = data.setdefault("hooks", {})
        for event, groups in hook_config(prefix).items():
            hooks.setdefault(event, []).extend(groups)
    if not install and not data and path.exists():
        path.unlink()  # 中身が空になったら削除
    elif data or path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n")
    ok(f"{path} のフックを{'登録' if install else '削除'}")


# ---------- CLAUDE.md 系 ----------
def strip_section(text):
    pattern = re.compile(rf"\n*{re.escape(SECTION)}\n.*?(?=\n## |\Z)", re.S)
    return pattern.sub("", text).rstrip() + "\n"


def update_guidance(path, install):
    text = path.read_text(encoding="utf-8") if path.exists() else ""
    cleaned = strip_section(text) if SECTION in text else text
    if install:
        cleaned = cleaned.rstrip() + "\n" + (KIT / "templates" / "CLAUDE.md.snippet").read_text(encoding="utf-8")
    if not install and not cleaned.strip() and path.exists():
        path.unlink()
    elif cleaned.strip() or path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(cleaned.lstrip("\n"), encoding="utf-8")
    ok(f"{path} の運用ルールを{'追記' if install else '削除'}")


# ---------- ignore ----------
def update_ignore(path, entries, install, header):
    lines = path.read_text().splitlines() if path.exists() else []
    # 既存の自分のブロックを除去
    out, skip = [], False
    for ln in lines:
        if ln.strip() == f"{MARK} ({header})":
            skip = True
            continue
        if skip and (ln.strip() == "" or ln.startswith("#")):
            skip = False
        if skip:
            continue
        out.append(ln)
    # v1 が .gitignore に書いた行も除去
    out = [ln for ln in out if ln.strip() not in (
        "# Claude Code compaction snapshots",
        ".claude/context/snapshots/", ".claude/context/latest-snapshot.md")]
    while out and not out[-1].strip():
        out.pop()
    if install:
        out += ["", f"{MARK} ({header})", *entries]
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(out).strip("\n") + "\n")
    ok(f"{path} の除外設定を{'追加' if install else '削除'}")


def global_excludes_file():
    try:
        r = subprocess.run(["git", "config", "--global", "core.excludesFile"],
                           capture_output=True, text=True)
        if r.stdout.strip():
            return Path(os.path.expanduser(r.stdout.strip()))
    except FileNotFoundError:
        pass
    base = os.environ.get("XDG_CONFIG_HOME") or os.path.expanduser("~/.config")
    return Path(base) / "git" / "ignore"


def untrack_context(proj):
    """v1 でコミットされた作業ノート等を git の追跡から外す（ファイル自体は残す）"""
    try:
        r = subprocess.run(["git", "ls-files", ".claude/context"], cwd=proj,
                           capture_output=True, text=True)
    except FileNotFoundError:
        return
    if r.returncode == 0 and r.stdout.strip():
        subprocess.run(["git", "rm", "-r", "--cached", "-q", ".claude/context"], cwd=proj)
        ok(".claude/context/ を git の追跡から外しました（ファイルは手元に残ります。次のコミットで反映）")


# ---------- files ----------
def copy_files(hooks_dir, cmds_dir, install):
    if install:
        hooks_dir.mkdir(parents=True, exist_ok=True)
        cmds_dir.mkdir(parents=True, exist_ok=True)
        for s in SCRIPTS:
            dst = hooks_dir / s
            shutil.copy2(KIT / "hooks" / s, dst)
            dst.chmod(0o755)
        shutil.copy2(KIT / "commands" / "checkpoint.md", cmds_dir / "checkpoint.md")
        ok(f"スクリプトを {hooks_dir}、/checkpoint を {cmds_dir} に配置")
    else:
        for p in [*(hooks_dir / s for s in SCRIPTS), cmds_dir / "checkpoint.md"]:
            if p.exists():
                p.unlink()
        ok("スクリプトと /checkpoint を削除")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("mode", choices=["team", "personal", "global"])
    ap.add_argument("project", nargs="?", default=".", help="team/personal の導入先（既定: カレント）")
    ap.add_argument("--uninstall", action="store_true")
    a = ap.parse_args()
    install = not a.uninstall

    if a.mode == "global":
        home = Path.home() / ".claude"
        print(f"→ モード: global（{home}）")
        copy_files(home / "hooks", home / "commands", install)
        update_settings(home / "settings.json", "$HOME/.claude/hooks", install)
        update_guidance(home / "CLAUDE.md", install)
        update_ignore(global_excludes_file(), [".claude/context/"], install, "global")
    else:
        proj = Path(a.project).resolve()
        if not proj.is_dir():
            sys.exit(f"導入先が見つかりません: {proj}")
        print(f"→ モード: {a.mode}（{proj}）")
        claude = proj / ".claude"
        copy_files(claude / "hooks", claude / "commands", install)
        prefix = "$CLAUDE_PROJECT_DIR/.claude/hooks"
        if a.mode == "team":
            update_settings(claude / "settings.json", prefix, install)
            update_guidance(proj / "CLAUDE.md", install)
            update_ignore(proj / ".gitignore", [".claude/context/"], install, "team")
            if install:
                untrack_context(proj)
        else:
            update_settings(claude / "settings.local.json", prefix, install)
            update_guidance(proj / "CLAUDE.local.md", install)
            git_dir = proj / ".git"
            if git_dir.is_dir():
                update_ignore(git_dir / "info" / "exclude", [
                    ".claude/context/", ".claude/settings.local.json", "CLAUDE.local.md",
                    ".claude/hooks/pre_compact_snapshot.py", ".claude/hooks/post_compact_restore.py",
                    ".claude/commands/checkpoint.md"], install, "personal")
            else:
                print("  （.git が見つからないため git 除外設定はスキップ）")

    if install:
        print("完了。Claude Code を再起動（Desktop は新しいセッションを開始）してください。")
        print("作業ノートは初回の /checkpoint で .claude/context/working-notes.md に作られます。")
    else:
        print("アンインストール完了。.claude/context/（作業ノート・スナップショット）は残しています。")


if __name__ == "__main__":
    main()
