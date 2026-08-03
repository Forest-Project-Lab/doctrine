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
    4. 設定の見張り(常時。ADR-096): 統治の設定 doctrine_docs/_system/
       .context-config.json が在るなら、それを対象にする EXT アンカーが在り、
       検査が hash で、指紋の行を持つこと。設定が無い木では何も言わない。
       ここに置く理由: 指紋が動けば監査が warn を出すが、アンカーそのものが
       消されても監査は何も言わない(見張りが無くなった状態は見張りでは分から
       ない)。同梱の試験には置けない(配布物の外を素で読む形になる。ADR-075)。

marketplace.json との一致は検めない(TEST-020 が強制済み。二重定義しない)。
終了コード: 0 一致 / 1 違反 / 2 前提が読めない。決定的。標準ライブラリのみ。
"""
# doctrine:end SPEC-027
import json
import os
import re
import subprocess
import sys

# plugin/scripts の共有コアを引くとき、配布される作業木に __pycache__ を
# 残さない(ADR-075)。ディレクトリ配布では利用者へそのまま複製される。
sys.dont_write_bytecode = True

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


GOVERNED_CONFIG = "doctrine_docs/_system/.context-config.json"

# EXT の「検査」の行の読み方。監査(docs-audit.py の _EXT_CHECK_RE)と同じ形で読む。
# 本文全体で "hash" を探すと、散文の「hash にする」で通ってしまう(実測)。
_EXT_CHECK_LINE_RE = re.compile(r"検査[:：]\s*(\S+)")


def check_config_anchor(repo):
    """統治の設定が指紋で見張られているかを検める(ADR-096)。空なら整合。

    設定の一枚は、常時投入の上限(確定事実6)・追跡の悉皆の様式・走査の適用除外を
    握っている。指紋が動けば監査が warn を出すが、**アンカーそのものが消されても
    監査は何も言わない**(見張りが無くなった状態は、見張りでは分からない)。
    ここが、アンカーの存在を保つ唯一の歯止めである。

    設定が無い木では見張るものが無いので、何も言わない。
    """
    violations = []
    config = os.path.join(repo, GOVERNED_CONFIG.replace("/", os.sep))
    if not os.path.isfile(config):
        return violations
    docs_root = os.path.join(repo, "doctrine_docs")
    if not os.path.isdir(docs_root):
        return violations
    found = []
    for base, _dirs, files in os.walk(docs_root):
        for fn in sorted(files):
            if not fn.endswith(".md"):
                continue
            path = os.path.join(base, fn)
            try:
                with open(path, encoding="utf-8") as fh:
                    text = fh.read()
            except (OSError, UnicodeError):
                continue
            if "\ntype: EXT\n" not in text:
                continue
            if GOVERNED_CONFIG not in text:
                continue
            found.append((os.path.relpath(path, repo), text))
    if not found:
        violations.append(
            "統治の設定 %s を対象にする EXT アンカーが無い(ADR-096)。"
            "上限・悉皆の様式・適用除外が黙って変わる状態に戻っている"
            % GOVERNED_CONFIG)
        return violations
    for rel, text in found:
        m = _EXT_CHECK_LINE_RE.search(text)
        check = m.group(1) if m else "exists"
        if "hash" not in check:
            violations.append(
                "%s の『検査』が hash でない(いまは %s)。存在は変わらず、"
                "変わるのは中身である(ADR-096)" % (rel, check))
        if "- 指紋: sha256:" not in text:
            violations.append(
                "%s に指紋の行が無い。hash 検査は指紋が無いと素通りする(ADR-039)"
                % rel)
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


def check_distribution_hygiene(repo):
    """配布物に開発機の実行時生成物が残っていないか(ADR-075)。違反の列を返す。

    marketplace の `source` がディレクトリのとき、配布は git archive ではなく
    作業木の複製である。`plugin/.gitignore` は複製を止めないので、実行時に
    plugin/ の下へ書いた物はそのまま利用者の導入先へ配られる。実際に、別の
    ワークスペース時代の監査要約と開発機のセッション印、および __pycache__ が
    導入実体へ複製されていた。リリースの直前に一度だけ、ここで断つ。
    """
    plugin = os.path.join(repo, "plugin")
    forbidden = (".cache", ".claude", "__pycache__")
    found = []
    for base, dirs, _files in os.walk(plugin):
        for name in list(dirs):
            if name in forbidden:
                found.append(os.path.relpath(os.path.join(base, name), repo))
    if not found:
        return []
    return ["配布物に実行時生成物が残っている: %s。ディレクトリ配布では"
            "そのまま利用者へ複製される。消してからリリースすること"
            % ", ".join(sorted(found))]


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
        violations += check_distribution_hygiene(REPO)
        violations += check_config_anchor(REPO)
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
    print("release-check: 整合(版の整合・公開ビューの刻印・配布物の衛生・設定の見張り%sを確認)"
          % ("・記録の義務" if base is not None else ""))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
