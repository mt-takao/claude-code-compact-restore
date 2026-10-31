"""
compact-restore の共通部: 保存先、git、スナップショットの書式、注入量の制御。

フックの入口（pre_compact_snapshot.py / post_compact_restore.py）から import して使う。
記録（transcript）の読み取りはツールごとのモジュール（compact_restore_claude.py など）が担い、
ここでは次の形の dict を受け取る:
  prompts, files, memories, todos, last_assistant, progress, warning
"""
import json
import os
import re
import subprocess
import sys
from datetime import datetime
from pathlib import Path

# ツールごとの設定。budget は注入する文章の上限（文字数）
AGENTS = {
    "claude": {
        "name": "Claude Code",
        "latest": "latest-snapshot.md",
        "history": "snapshots",
        "budget": 9000,  # Claude Code のフック出力の上限 10,000 文字に余裕を持たせる
    },
}
KEEP = 20                    # 保持するスナップショット数
PROMPT_MAX_CHARS = 600       # 1指示あたりの最大文字数
LAST_ASSISTANT_MAX = 1500    # 直前の発言の最大文字数
PROGRESS_MAX = 1500          # スレッドの進捗表示の最大文字数
NOTES_NAME = "working-notes.md"

# スナップショットの見出し（注入量の制御でも使うので、ここでまとめて持つ）
H_TASKS = "## 進行中のタスクリスト"
H_PROGRESS = "## スレッドの進捗表示"
H_PROMPTS = "## 直近のユーザー指示"
H_LAST = "## 圧縮直前の"
H_GIT = "## Git 状態"
H_FILES = "## このセッションで編集したファイル"
H_MEMORIES = "## このセッションで更新したメモリ"


def read_hook_input():
    try:
        return json.load(sys.stdin)
    except Exception:
        return {}


def git(args, cwd):
    try:
        r = subprocess.run(["git", *args], cwd=cwd, capture_output=True,
                           text=True, timeout=5)
        return r.stdout.strip() if r.returncode == 0 else ""
    except Exception:
        return ""


def project_root(hook):
    return Path(os.environ.get("CLAUDE_PROJECT_DIR") or hook.get("cwd") or os.getcwd()).resolve()


def context_dir(root):
    return root / ".claude" / "context"


def clip(s, n):
    s = s.strip()
    return s if len(s) <= n else s[:n] + " …(省略)"


# ---------- スナップショット ----------
def render_snapshot(hook, data, project_dir, agent="claude"):
    """退避する内容を Markdown にする。見出しは要点（タスク・指示・直前の発言）を先に並べる"""
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    trigger = hook.get("trigger", "unknown")
    L = [f"# 圧縮前スナップショット（{now} / trigger: {trigger} / {AGENTS[agent]['name']}）", ""]
    if data.get("warning"):
        L += [f"⚠ {data['warning']}", ""]
    focus = (hook.get("custom_instructions") or "").strip()
    if focus:
        L += [f"/compact の focus 指定: {focus}", ""]
    sid = os.environ.get("CLAUDE_CODE_REMOTE_SESSION_ID", "")
    if sid:  # クラウドセッション（Projects のスレッドを含む）: 元のトランスクリプトへのリンク
        L += [f"元のセッション: https://claude.ai/code/{sid.replace('cse_', 'session_', 1)}", ""]

    todos, progress = data.get("todos"), data.get("progress")
    if todos:
        L.append(H_TASKS)
        mark = {"completed": "[x]", "in_progress": "[→]", "pending": "[ ]"}
        for t in todos:
            L.append(f"- {mark.get(t.get('status'), '[ ]')} {t.get('content', '')}")
        L.append("")
    elif not progress:  # Projects のスレッドは進捗表示で足りるので、空の欄は出さない
        L += [H_TASKS, "- （タスクリストの記録なし）", ""]
    if progress:
        L.append(H_PROGRESS + "（最新。✓ 完了 / ✱ 作業中 / ○ 未着手）")
        L.append(clip(progress, PROGRESS_MAX))
        L.append("")

    L.append(H_PROMPTS + "（古い→新しい）")
    prompts = data.get("prompts") or []
    if prompts:
        for i, p in enumerate(prompts, 1):
            L.append(f"{i}. " + clip(p, PROMPT_MAX_CHARS).replace("\n", "\n   "))
    else:
        L.append("- （なし）")
    L.append("")

    last = data.get("last_assistant") or ""
    L.append(H_LAST + f" {'Claude' if agent == 'claude' else AGENTS[agent]['name']} の発言（どこまで進んでいたか）")
    L.append(clip(last, LAST_ASSISTANT_MAX) if last else "（なし）")
    L.append("")

    branch = git(["branch", "--show-current"], project_dir)
    status = git(["status", "--short"], project_dir)
    if branch or status:
        L.append(H_GIT)
        if branch:
            L.append(f"- ブランチ: `{branch}`")
        if status:
            lines = status.splitlines()
            L.append("- 未コミットの変更:")
            L.append("```")
            L += lines[:40]
            if len(lines) > 40:
                L.append(f"...ほか {len(lines) - 40} 件")
            L.append("```")
        L.append("")

    files = data.get("files") or []
    L.append(H_FILES + "（最後に触った順で末尾）")
    L += [f"- {f}" for f in files[-30:]] or ["- （なし）"]
    L.append("")
    memories = data.get("memories") or []
    if memories:
        L.append(H_MEMORIES + "（プロジェクト外。記憶済みの決定事項の手がかり）")
        L += [f"- {m}" for m in memories[-10:]]
        L.append("")
    return "\n".join(L)


def write_snapshot(ctx, md, agent="claude"):
    conf = AGENTS[agent]
    snap_dir = ctx / conf["history"]
    snap_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    (snap_dir / f"{stamp}.md").write_text(md, encoding="utf-8")
    (ctx / conf["latest"]).write_text(md, encoding="utf-8")
    for old in sorted(snap_dir.glob("*.md"))[:-KEEP]:
        old.unlink()


# ---------- 注入量の制御 ----------
def budget(agent="claude"):
    try:
        n = int(os.environ.get("COMPACT_RESTORE_MAX_CHARS", ""))
        if n > 0:
            return n
    except ValueError:
        pass
    return AGENTS[agent]["budget"]


def split_sections(md):
    """Markdown を (前置き, [[見出し行, 本文行...], ...]) に分ける。コードブロック内の ## は見出しとみなさない"""
    head, sections, fence = [], [], False
    for ln in md.splitlines():
        if ln.startswith("```"):
            fence = not fence
        if not fence and ln.startswith("## "):
            sections.append([ln])
        elif sections:
            sections[-1].append(ln)
        else:
            head.append(ln)
    return head, sections


def join_sections(head, sections):
    return "\n".join(head + [ln for s in sections for ln in s]).strip()


def age(ts):
    minutes = int((datetime.now().timestamp() - ts) // 60)
    if minutes < 1:
        return "1 分以内"
    if minutes < 60:
        return f"{minutes} 分前"
    if minutes < 60 * 48:
        return f"{minutes // 60} 時間前"
    return f"{minutes // (60 * 24)} 日前"


def notes_stamp(path):
    try:
        ts = path.stat().st_mtime
    except OSError:
        return ""
    return f"最終更新: {datetime.fromtimestamp(ts).strftime('%Y-%m-%d %H:%M')}（{age(ts)}）"


class Injection:
    """注入する文章を、予算に収まるよう優先度の低いものから削りながら組み立てる。

    並び: 復元の指示 → スナップショット（タスク・指示・直前の発言・git・編集ファイル・メモリ）
          → 作業ノート → 環境の案内
    削る順: 更新したメモリ → 編集ファイル → git の未コミット一覧 → 古いユーザー指示
          → 作業ノートの末尾 → 直前の発言 → 最後に全体の末尾
    """

    def __init__(self, limit):
        self.limit = limit
        self.intro, self.snap_head, self.snap = "", [], []
        self.snap_path = None
        self.notes_title, self.notes, self.notes_path = "", "", None
        self._notes_full = ""
        self.tail = ""
        self.notice = ""
        self._notes_kept = None  # 作業ノート・直前の発言を、元の本文の先頭から何文字残しているか
        self._last_full, self._last_kept = "", None

    def set_snapshot(self, intro, md, path):
        self.intro, self.snap_path = intro, path
        self.snap_head, self.snap = split_sections(md)

    def set_notes(self, title, body, path):
        self.notes_title, self.notes, self.notes_path = title, body, path
        self._notes_full = body

    def render(self):
        parts = []
        if self.snap_head or self.snap:
            parts.append(self.intro + "\n\n" + join_sections(self.snap_head, self.snap) + self.notice)
        if self.notes:
            parts.append(self.notes_title + "\n\n" + self.notes)
        if self.tail:
            parts.append(self.tail)
        return "\n\n---\n\n".join(parts)

    def _section(self, prefix):
        for s in self.snap:
            if s[0].startswith(prefix):
                return s
        return None

    def _drop_first_item(self, prefix, keep=0):
        """リスト型の節から一番古い項目（先頭）を1つ外す。外せなければ False"""
        s = self._section(prefix)
        if not s:
            return False
        items = [i for i, ln in enumerate(s) if re.match(r"^(- |\d+\. )", ln)]
        if len(items) <= keep:
            if keep == 0:
                self.snap.remove(s)
                return True
            return False
        start = items[0]
        end = items[1] if len(items) > 1 else len(s)
        while end > start + 1 and s[end - 1] == "":
            end -= 1  # 節末の空行は残す
        del s[start:end]
        if not any(re.match(r"^(- |\d+\. )", ln) for ln in s) and keep == 0:
            self.snap.remove(s)
        return True

    def _shrink_git(self):
        s = self._section(H_GIT)
        if not s or "```" not in s:
            return False
        start = s.index("```")
        count = sum(1 for ln in s[start + 1:] if ln and not ln.startswith("```"))
        s[start - 1:] = [f"- 未コミットの変更: {count} 件（一覧は省略。git status で確認）", ""]
        return True

    def _shrink_notes(self, over):
        """作業ノートの末尾を削り、全文の場所を添える。毎回元の本文から切り直すので注記が積み重ならない"""
        full = self._notes_full
        kept = len(full) if self._notes_kept is None else self._notes_kept
        pointer = f"\n…(以下省略。全文は {self.notes_path})"
        keep = max(200, kept - over - len(pointer))
        if not full or keep >= kept:
            return False
        self._notes_kept = keep
        self.notes = full[:keep].rstrip() + pointer
        return True

    def _shrink_last(self, over):
        s = self._section(H_LAST)
        if not s or len(s) < 2:
            return False
        if self._last_kept is None:
            self._last_full = "\n".join(s[1:]).strip()
        full = self._last_full
        kept = len(full) if self._last_kept is None else self._last_kept
        keep = max(200, kept - over - 10)
        if keep >= kept:
            return False
        self._last_kept = keep
        s[1:] = [full[:keep].rstrip() + " …(省略)", ""]
        return True

    def text(self):
        out = self.render()
        limit = self.limit - 150  # 省略の注記を足す分を空けておく
        steps = [
            lambda o: self._drop_first_item(H_MEMORIES),
            lambda o: self._drop_first_item(H_FILES),
            lambda o: self._shrink_git(),
            lambda o: self._drop_first_item(H_PROMPTS, keep=1),
            self._shrink_notes,
            self._shrink_last,
        ]
        trimmed = False
        for step in steps:
            while len(out) > limit and step(len(out) - limit):
                trimmed = True
                shorter = self.render()
                if len(shorter) >= len(out):  # 縮まなければ次の手段へ（無限ループを防ぐ）
                    out = shorter
                    break
                out = shorter
        if trimmed and self.snap_path:
            self.notice = f"\n\n（注入量の上限のため一部を省略しました。全文は {self.snap_path}）"
            out = self.render()
        if len(out) > self.limit:  # それでも収まらなければ末尾を切る
            out = out[:self.limit - 40].rstrip() + "\n…(上限のため以下省略)"
        return out
