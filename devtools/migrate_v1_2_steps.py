"""MentalMapping v1.2 マイグレーション Phase 2 ステップディスパッチ（facade）

実装は schema / populate / validate に分離されている:
- migrate_v1_2_steps_schema.py : step 1, 2, 3
- migrate_v1_2_steps_populate.py: step 4_5_8, 6_7, 9, 10
- migrate_v1_2_steps_validate.py: step 11, 12, 13

本ファイルは 3 ファイルの STEP 辞書を統合して `STEP_DISPATCHER` として公開する。
`devtools/migrate_v1_2.py._run_phase2()` が本モジュールを遅延 import し
`STEP_DISPATCHER[args.step]` を解決する。
"""
from __future__ import annotations

from typing import Callable

from devtools.migrate_v1_2 import STEP_CHOICES
from devtools.migrate_v1_2_steps_populate import POPULATE_STEPS
from devtools.migrate_v1_2_steps_schema import SCHEMA_STEPS
from devtools.migrate_v1_2_steps_validate import VALIDATE_STEPS

STEP_DISPATCHER: dict[str, Callable[..., None]] = {
    **SCHEMA_STEPS,
    **POPULATE_STEPS,
    **VALIDATE_STEPS,
}

# ガード: CLI choices と dispatcher キーの不整合を import 時に検出
assert set(STEP_DISPATCHER.keys()) == set(STEP_CHOICES), (
    "STEP_DISPATCHER keys must match STEP_CHOICES in migrate_v1_2.py"
)
