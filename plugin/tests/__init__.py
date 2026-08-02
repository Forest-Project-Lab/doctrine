# doctrine:exempt 受入の対応は TEST 文書の sources が持つ。コード側と二重に結ばない(ADR-067)
"""試験パッケージ。作業木にバイトコードを残さない(ADR-075)。

`python3 -m unittest tests.test_x` を直に叩く経路は run_tests.py を通らない。
ここは その経路でも最初に読まれるので、旗を立てる場所として一番早い。
"""
import os
import sys

sys.dont_write_bytecode = True
os.environ["PYTHONDONTWRITEBYTECODE"] = "1"
