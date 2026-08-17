---
id: CTXMAP-001
title: 全体図
type: CTXMAP
domain: _system
status: current
owner: render-projection
updated: 2026-06-30
llm_context: task
sources: []
---

描画される。手で編集しない。

# Context Map

結合の要点はこの印の外側に書く。印の内側は描画される。

<!-- BEGIN PROJECTION:context-map-skeleton -->
## ドメインとICD

- _system: (ICD 未公開)
- audit: ICD-005
- authoring: ICD-007
- context: ICD-006
- graph: ICD-002
- guard: ICD-003
- lint: ICD-004
- model: ICD-001
- packaging: ICD-008

## ドメイン越えの依存(ICD境界)

- ADR-021 --depends_on--> ICD-004
- ADR-021 --depends_on--> ICD-006
- ADR-022 --depends_on--> ICD-001
- ADR-072 --depends_on--> ICD-005
- ADR-074 --depends_on--> ICD-005
- ADR-075 --depends_on--> ICD-004
- ADR-150 --depends_on--> ICD-005
- ADR-156 --depends_on--> ICD-002
- ADR-161 --depends_on--> ICD-006
- ADR-161 --depends_on--> ICD-007
- ADR-169 --depends_on--> ICD-001
- CHANGE-003 --depends_on--> ICD-005
- CHANGE-005 --depends_on--> ICD-005
- CHANGE-010 --depends_on--> ICD-002
- CHANGE-010 --depends_on--> ICD-005
- CHANGE-010 --depends_on--> ICD-007
- ICD-004 --depends_on--> ICD-001
- ICD-004 --depends_on--> ICD-002
- IMPACT-010 --depends_on--> ICD-002
- IMPACT-010 --depends_on--> ICD-005
- IMPACT-010 --depends_on--> ICD-007
- SPEC-003 --depends_on--> ICD-001
- SPEC-003 --depends_on--> ICD-002
- SPEC-006 --depends_on--> ICD-001
- SPEC-007 --depends_on--> ICD-001
- SPEC-007 --depends_on--> ICD-002
- SPEC-007 --depends_on--> ICD-005
- SPEC-011 --depends_on--> ICD-001
- SPEC-011 --depends_on--> ICD-002
- SPEC-011 --depends_on--> ICD-008
- SPEC-012 --depends_on--> ICD-001
- SPEC-012 --depends_on--> ICD-005
- SPEC-013 --depends_on--> ICD-001
- SPEC-014 --depends_on--> ICD-001
- SPEC-016 --depends_on--> ICD-001
- SPEC-016 --depends_on--> ICD-004
- SPEC-016 --depends_on--> ICD-006
- SPEC-017 --depends_on--> ICD-001
- SPEC-019 --depends_on--> ICD-001
- SPEC-019 --depends_on--> ICD-002
- SPEC-019 --depends_on--> ICD-003
- SPEC-019 --depends_on--> ICD-004
- SPEC-019 --depends_on--> ICD-005
- SPEC-019 --depends_on--> ICD-006
- SPEC-019 --depends_on--> ICD-007
- SPEC-021 --depends_on--> ICD-005
- SPEC-021 --depends_on--> ICD-006
- SPEC-022 --depends_on--> ICD-004
- SPEC-022 --depends_on--> ICD-006
- SPEC-023 --depends_on--> ICD-005
- SPEC-027 --depends_on--> ICD-005
- SPEC-030 --depends_on--> ICD-005
<!-- END PROJECTION:context-map-skeleton -->
