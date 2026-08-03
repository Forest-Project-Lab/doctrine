#!/usr/bin/env python3
"""統治の設定(`_system/.context-config.json`)の読み取りの正本(ADR-104)。

保証限界:
- 予防: 何も予防しない。読み取りと解析だけを持つ。
- 検出: 値の妥当性は検めない。呼び手が判ずる(監査は型を検め、注入は上限を解く)。
- 委ねる: 調整値の意味と既定は呼び手に残す(受け持ちが違うものを一つにしない)。

**この一枚は常時投入の上限(確定事実6)・パックの上限・追跡の悉皆の様式・走査の適用除外を
握る**(ADR-096 で指紋の見張りを付けた、あの一枚である)。以前は読む実装が四箇所に在り、
**そのうち一つだけが `utf-8` で開いていた** —— BOM を一つ付けるだけで監査が設定を丸ごと
見失い、`trace_mode: "exhaustive"` が無視されて印なしの残高の警告が黙って消えた。
鼓動はまだ悉皆を見ているので、二つの読み手が木の様式について食い違った(実測)。

読み取りは共有の読み手(`_frontmatter.read_text`)を通す。通常ファイルでなければ開かない
(ADR-075。名前付きパイプ・デバイスを開いて戻らない類型を、設定にも掛ける)。

標準ライブラリのみ。pip も通信も使わない。決して例外を投げない。
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import _frontmatter          # noqa: E402  通常ファイルの門を通す共有の読み手(ADR-075)


# doctrine:begin SPEC-012
CONFIG_NAME = ".context-config.json"
# doctrine:end SPEC-012


def path_for(docs_root):
    """統治木から設定の道を組む。docs_root が空なら None。

    道の組み立てもここに一度だけ置く —— 呼び手が自前で組むと、`_system` の位置を
    取り違えたときに読み手ごとに違う場所を見る。
    """
    if not docs_root:
        return None
    return os.path.join(docs_root, "_system", CONFIG_NAME)


def load(docs_root=None, config_path=None):
    """設定を写像で返す。読めなければ空の写像。決して例外を投げない(ADR-104)。

    `config_path` が明示されていればそちらを優先する(監査の `--config`・注入の
    明示指定)。無ければ `docs_root` から組む。

    BOM は落とす(`utf-8-sig`)。**多く読める側へ揃える** —— 編集器が BOM を付けるのは
    普通にあり、以前は監査だけがそれで既定へ落ちていた。
    """
    path = config_path or path_for(docs_root)
    if not path or not os.path.isfile(path):
        return {}
    try:
        text = _frontmatter.read_text(path)
    except (OSError, UnicodeError, ValueError):
        return {}
    try:
        data = json.loads(text)
    except (ValueError, TypeError):
        return {}
    return data if isinstance(data, dict) else {}
