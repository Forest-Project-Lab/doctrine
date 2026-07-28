#!/usr/bin/env python3
# doctrine:begin SPEC-027
"""リリース整合の門 — 変更履歴の書き忘れを CI で止める (SPEC-027, ADR-071)。

検めること:
    1. 版の整合(常時): CHANGELOG.md の先頭の版付き節『## [X.Y.Z] — 日付』が、
       版番号の正本(plugin/.claude-plugin/plugin.json の version)と一致し、
       日付を持つこと。「未リリース」節は飛ばして判じる。
    2. 記録の義務(--diff-base <ref> のときだけ): git diff --name-only <ref> HEAD
       が plugin/ 配下を含むなら、同じ差分が CHANGELOG.md も含むこと。
       環境変数 RELEASE_CHECK_PR_TITLE に [no-changelog] が含まれれば
       この検査だけを免除し、免除した旨を告げる(版の整合は免除しない)。
    3. 公開ビューの刻印(常時。ADR-073): README.md・plugin/README.md・
       CONTRIBUTING.md が刻印(書式の正本は ICD-005 の view-stamp-format。
       解析は共有コア _intake)を持ち、その as-of が版番号の正本と一致する
       こと。[no-changelog] では免除しない。

marketplace.json との一致は検めない(TEST-020 が強制済み。二重定義しない)。
終了コード: 0 一致 / 1 違反 / 2 前提が読めない。決定的。標準ライブラリのみ。
"""
# doctrine:end SPEC-027
import json
import os
import re
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)

# 刻印の解析は共有コア _intake に一本化する(ICD-005。二重定義しない)。
sys.path.insert(0, os.path.join(REPO, "plugin", "scripts"))
import _intake  # noqa: E402

SKIP_MARKER = "[no-changelog]"
PR_TITLE_ENV = "RELEASE_CHECK_PR_TITLE"

# 公開ビュー(ADR-073)。リリースごとに内容を検めてから刻印を打ち直す。
PUBLIC_VIEWS = ("README.md", "plugin/README.md", "CONTRIBUTING.md")

# 版付き節の見出し。日付の区切りは — (em dash) と - (hyphen) を受ける。
_SECTION_RE = re.compile(r"^## \[(\d+\.\d+\.\d+)\](?:\s*[—-]\s*(\S.*))?$")
_UNRELEASED_RE = re.compile(r"^## \[未リリース\]\s*$")
_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


class ReleaseCheckError(Exception):
    """前提が読めない(終了コード 2 に対応)。"""


def canonical_version(repo):
    """版番号の正本 plugin/.claude-plugin/plugin.json の version を返す。"""
    path = os.path.join(repo, "plugin", ".claude-plugin", "plugin.json")
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, ValueError) as exc:
        raise ReleaseCheckError("版番号の正本が読めない: %s (%s)" % (path, exc))
    version = data.get("version")
    if not isinstance(version, str) or not version:
        raise ReleaseCheckError("plugin.json に version が無い: %s" % path)
    return version


def changelog_head(repo):
    """CHANGELOG.md の先頭の版付き節から (版, 日付文字列 or None) を返す。

    「未リリース」節は飛ばす。版付き節が一つも無ければ ReleaseCheckError。
    """
    path = os.path.join(repo, "CHANGELOG.md")
    try:
        with open(path, encoding="utf-8") as f:
            text = f.read()
    except OSError as exc:
        raise ReleaseCheckError("CHANGELOG.md が読めない: %s (%s)" % (path, exc))
    for line in text.splitlines():
        if _UNRELEASED_RE.match(line):
            continue
        m = _SECTION_RE.match(line)
        if m:
            return m.group(1), m.group(2)
    raise ReleaseCheckError("CHANGELOG.md に版付き節(## [X.Y.Z])が一つも無い")


def check_version_integrity(repo):
    """版の整合の違反を列挙して返す(空なら整合)。"""
    violations = []
    version = canonical_version(repo)
    head_version, head_date = changelog_head(repo)
    if head_version != version:
        violations.append(
            "版の不整合: CHANGELOG 先頭の版付き節は %s、正本(plugin.json)は %s"
            % (head_version, version))
    if head_date is None or not _DATE_RE.match(head_date.strip()):
        violations.append(
            "日付の欠落: CHANGELOG の節 [%s] に YYYY-MM-DD の日付が無い"
            % head_version)
    return violations


def check_view_stamps(repo):
    """公開ビューの刻印の違反を列挙して返す(空なら整合)。ADR-073。"""
    violations = []
    version = canonical_version(repo)
    for rel in PUBLIC_VIEWS:
        path = os.path.join(repo, rel)
        try:
            with open(path, encoding="utf-8") as f:
                text = f.read()
        except OSError:
            violations.append("公開ビューが読めない: %s" % rel)
            continue
        stamp, err = _intake.parse_view_stamp(text)
        if stamp is None:
            violations.append(
                "刻印の欠落: %s に doctrine:view の刻印が無い(ICD-005)" % rel)
            continue
        if err is not None:
            violations.append("刻印が読めない: %s (%s)" % (rel, err))
            continue
        if stamp["as_of"] != version:
            violations.append(
                "刻印の版の遅れ: %s の as-of は %s、正本(plugin.json)は %s。"
                "内容を検めてから刻印を打ち直す"
                % (rel, stamp["as_of"] or "(無し)", version))
    return violations


def changed_files(repo, base):
    """git diff --name-only base HEAD の一覧を返す。失敗は ReleaseCheckError。"""
    try:
        r = subprocess.run(
            ["git", "-C", repo, "diff", "--name-only", base, "HEAD"],
            capture_output=True, text=True, timeout=60)
    except Exception as exc:
        raise ReleaseCheckError("git diff の呼び出しに失敗: %r" % exc)
    if r.returncode != 0:
        raise ReleaseCheckError(
            "git diff が失敗(終了コード %d): %s" % (r.returncode, r.stderr.strip()))
    return [ln.strip() for ln in r.stdout.splitlines() if ln.strip()]


def check_record_duty(repo, base, pr_title):
    """記録の義務の違反を列挙して返す。免除なら告げて空を返す。"""
    if SKIP_MARKER in (pr_title or ""):
        print("記録の義務: 題名の %s により免除(版の整合は免除しない)" % SKIP_MARKER)
        return []
    files = changed_files(repo, base)
    touches_plugin = any(f == "plugin" or f.startswith("plugin/") for f in files)
    touches_changelog = "CHANGELOG.md" in files
    if touches_plugin and not touches_changelog:
        return [
            "記録の欠落: 差分が plugin/ に触れるのに CHANGELOG.md に触れていない。"
            "「未リリース」節へ一行を積む(記録に値しない変更は題名に %s)"
            % SKIP_MARKER]
    return []


def main(argv):
    base = None
    args = list(argv[1:])
    while args:
        a = args.pop(0)
        if a == "--diff-base" and args:
            base = args.pop(0)
        else:
            print("usage: release-check.py [--diff-base <ref>]", file=sys.stderr)
            return 2
    try:
        violations = check_version_integrity(REPO)
        violations += check_view_stamps(REPO)
        if base is not None:
            violations += check_record_duty(
                REPO, base, os.environ.get(PR_TITLE_ENV, ""))
    except ReleaseCheckError as exc:
        print("release-check: 前提が読めない: %s" % exc, file=sys.stderr)
        return 2
    if violations:
        for v in violations:
            print("[ERROR] %s" % v)
        return 1
    print("release-check: 整合(版の整合と公開ビューの刻印%sを確認)"
          % ("と記録の義務" if base is not None else ""))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
