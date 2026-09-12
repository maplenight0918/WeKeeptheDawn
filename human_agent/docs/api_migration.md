# Human API schema 1.0 → 2.0

路徑仍為 `POST /human-agent/analyze`。本版拒絕 schema 1.0，回 HTTP 422 與遷移提示，不猜测舊單位。

| 舊資料 | 2.0 必須提供 |
| --- | --- |
| crew.count／只有公共存量 | 四筆唯一 `crew[]`，每人 alive、food_energy、water，加上公共 resources |
| oxygen_kg／百分比／每日流量 | 公共 oxygen（OU）、power（EU）、water（L）、food（遊戲 kcal）實際存量 |
| remaining_days／每日存活模型 | tick、state_id、between_ticks 快照；plan 指向 tick+1 |
| recycling_efficiency／scientific profile | world 0.12 的固定製水公式與 world_v0_12 profile |
| 自動補給／未指定的人自動工作 | 完整四人互斥任務、refill_order、Core 灌溉配額與執行順序 |

未知存量用 null，但必填存量欄位不可省略。plots=null 表示未知；提供時必須是 20 筆唯一地塊。空陣列不是二十塊空地。irrigation_allocations=[] 明確表示無分配；null 表示未知。NaN、Infinity、負數、超容量、錯 tick、額外欄位均拒絕。

讀取 `next_tick_audit.status`：`feasible_in_scope`、`unsafe_in_scope`、`fatal_in_scope`、`incomplete`、`not_applicable`。`unsafe_in_scope` 是已知植物死亡等不安全結果，不能當作可行，但不代表全員死亡。stage status：`evaluated`、`unknown`、`not_reached`。沒有完整計畫時 audit=null，個人不補給餘裕仍可計算。

2026-09-12 相容更新：原 Human 2.0 請求仍要求 alive；Core `/discuss` 轉接另外接受 alive 未提供，以 null 表示未知。回應 CrewAssessment.alive 支援 null；power.energy_equivalent 提供使用者確認的 3.9745 kWh/EU 換算。所有後端仍以 EU 計算。

正常分析的 coverage_end 固定為 `after_irrigation_before_crop_operations`。沒有 `world_safe` 或世界 step。公共水／food 歸零不直接判 crew 死亡；個人歸零與公共缺氧依規則判定。致命階段停止後段核算，不將後段產氧／食物拿來救人。

正式 JSON Schema：`human_api_2.0_request.schema.json`、`human_api_2.0_response.schema.json`；Swagger 與 `openapi.json` 由同一份 Pydantic 定義產生。Core-side 範例 `examples/brain_client.py` 不 import app。
