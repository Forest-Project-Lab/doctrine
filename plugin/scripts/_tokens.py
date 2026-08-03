#!/usr/bin/env python3
"""トークンの見積りと較正の解釈の正本(ADR-105)。

保証限界:
- 予防: 何も予防しない。見積りと較正の解釈だけを持つ。
- 検出: 較正の値が妥当かは見ない(2.0 が正しいかは測らない)。壊れた値を既定へ退避させる。
- 委ねる: 上限そのもの(注入の上限・パックの上限)は呼び手が持つ。確定事実6 のとおり
  二つの別々のキーであり、ここでは統合しない。**分けるのは上限であって較正ではない。**

以前は見積りが二箇所に在り、**較正の設定が片方にしか効いていなかった** —— パックの
説明文は「較正が要る導入先は設定の model_chars_per_token を下げる」と書いていたのに
読んでおらず、較正 2.0 の木で同じ 1000 文字を注入は 500、パックは 250 と見ていた
(実測)。**同じ内容の重さが二通りある**状態で、パックの上限は未較正の見積りで判じられ、
較正した木では意図の二倍が入っていた。

壊れた値への頑健さも違った。零で例外、`-1` で **-1000(負のトークン数)** を返し、
**負は上限との比較を必ず通すので上限が黙って無効になる。** ここが芯である。

見積りは文字数の近似であり、実トークンではない。4 文字/トークンは英語の近似で、
日本語では実トークンを下回りうる(ADR-075 が記録した限界。ここでは変えない)。

標準ライブラリのみ。pip も通信も使わない。決定的。決して例外を投げない。
"""
import math

# doctrine:begin SPEC-012
DEFAULT_CHARS_PER_TOKEN = 4.0
CONFIG_KEY = "model_chars_per_token"
# doctrine:end SPEC-012


def chars_per_token(config=None):
    """設定から較正を解く。壊れた値・不在は既定へ退避する(ADR-105)。

    真偽値は数として受けない(True が 1.0 になるのを防ぐ)。零以下も既定へ退避する
    —— 零は零除算、負は**負のトークン数**を生み、負は上限との比較を必ず通すので
    上限が黙って無効になる。
    """
    if not isinstance(config, dict):
        return DEFAULT_CHARS_PER_TOKEN
    raw = config.get(CONFIG_KEY)
    if raw is None or isinstance(raw, bool):
        return DEFAULT_CHARS_PER_TOKEN
    try:
        value = float(raw)
    except (TypeError, ValueError):
        return DEFAULT_CHARS_PER_TOKEN
    if not (value > 0) or math.isinf(value) or math.isnan(value):
        return DEFAULT_CHARS_PER_TOKEN
    return value


def estimate(text, cpt=None):
    """文字数ベースの見積り(天井)。純粋関数、決定的。決して例外を投げない。

    `cpt` は較正済みの値(`chars_per_token` が返したもの)を渡す。壊れた値が直に
    来ても既定へ退避する —— 呼び手が解き忘れても負や例外を出さないためである。
    """
    if not text:
        return 0
    if cpt is None or isinstance(cpt, bool):
        cpt = DEFAULT_CHARS_PER_TOKEN
    else:
        try:
            cpt = float(cpt)
        except (TypeError, ValueError):
            cpt = DEFAULT_CHARS_PER_TOKEN
        if not (cpt > 0) or math.isinf(cpt) or math.isnan(cpt):
            cpt = DEFAULT_CHARS_PER_TOKEN
    try:
        return int(math.ceil(len(text) / cpt))
    except (TypeError, ValueError, OverflowError):
        return 0
