# 隊友 Agent 串接邊界

本專案負責前後端整合、世界運行與展示。隊友負責 Core／Plant／Human 的決策、LLM 呼叫、提示詞及記憶；本專案沒有這些實作。

## 資料來源

- 已確定資料契約：WorldState 是權威 snapshot；API 階段將提供 `GET /world` 與 WebSocket `state_update`。本階段只提供下述 Python 對接邊界，不表示 HTTP／WebSocket 已啟動。
- `shared/tick_plan.schema.json` 是提交計畫的 schema；來源是 Pydantic model 與共用作物 JSON，可用 `.venv/bin/python -m checks.generate_schema` 重生。
- 數值只從 `shared/world_constants.json` 與 `shared/crops.json` 載入。每個數值的 `source` 對應 guide 章節。
- `tick` 是即將執行的輸入 snapshot tick，執行後世界 tick 加一。`state_version` 應等於觀察到的版本，玩家控制或資源干預會使旧版本失效。
- `pending_oxygen`／`pending_food` 已占用容量，下一 tick 引擎才併入可用庫存。不要再次把 pending 計成產出。

## 計畫與訊息

外部來源提交完整 `TickPlan`，後端回傳驗證錯誤，不替隊友修補工作分配。`refills` 的順序與 `plot_ops.order` 均由 Core 提供；沒有補充安排就提交空陣列。

Agent 訊息使用 `AgentThought`：`agent` 為 core／plant／human，`kind` 為 observe／risk／advice／plan／validation_error／reflection。`text` 是供畫面展示的摘要，不依賴模型內部逐步思考。真正的 reflection 應在取得執行摘要後提交。

後端排程的可注入邊界為 `await plan_source.plan(state, events)`。等待計畫期間不結算；控制／編輯後返回的舊計畫不會被執行。三輪無效計畫依本次規格執行一次空計畫並發出 `plan_failed`。

展示模式使用預錄計畫與訊息 fixture；前端獨立模式只播放預錄 snapshots。兩者都不是遊戲 Agent 的決策功能。任意資源編輯及正確世界結算應以實際後端模式測試。

## 待定

- `TODO(guide-pending)`：正式 refill 工具未定，目前以 `TickPlan.refills` 和 `amount` 表達。
- `TODO(guide-pending)`：飲水點無場景位置，不自行指定房間。
- `TODO(guide-pending)`：clear UI 入口與設備故障规则不在目前實作範圍。

HTTP 提交端點與可執行範例會在 API 階段完成後補入，本文不代表尚未建立的端點已可使用。

## Python 對接 API

`backend.integration.sources.ExternalPlanSource(bus)` 是隊友提交計畫與展示訊息的 adapter；它不持有 StateRepository，不計算或修改資源。

| 方法 | 契約 |
|---|---|
| `submit(plan: TickPlan | dict) -> TickPlan` | 同步解析 schema 後排入佇列；成功排隊不代表通過世界狀態、版本及工作占用驗證。 |
| `await plan(state: WorldState, events: list[WorldEvent]) -> TickPlan` | 由 WorldLoop 呼叫，等待外部計畫；等待本身不結算、無補跑 tick。 |
| `await relay_thought(thought: AgentThought | dict) -> AgentThought` | 驗證展示訊息後轉送 `agent_thought` envelope；禁止藉訊息覆寫 WorldState。 |

WorldLoop 注入邊界是 `PlanSource` protocol 的 `plan` 方法，因此隊友亦可實作相同 protocol。版本錯誤由 loop／PlanValidator 拒絕；三輪無效計畫的空計畫退路屬排程規格，不是 adapter 自行選擇策略。等待途中若玩家改資源，原觀察版本失效，不得將舊計畫套入新狀態。

## Wire schema 注意事項

- 欄位維持 `snake_case`，完整輸出由 Pydantic `model_dump(mode="json")` 產生。
- `TickPlan` 包含 `tick`、`state_version`、`refills`、`generation`、`water_production_l`、`irrigation`、`plot_ops`、`rationale`；無一次性工作時 refills／plot_ops 為空。
- refill 每項有 `crew_id`、`kind`、`amount`，陣列順序代表 Core 執行順序。`generation` 為 crew_id 到工作量的 mapping。
- plot operation 有 `order`、`crew_id`、`plot_id`、`op`、`crop`；plant 的作物 key 以即時共用 JSON 為合法集合，其餘操作可將 crop 設 null。
- `state_version` 雖允許 null 以支援模型最小表達，正式對接應提交觀察到的版本，避免同 tick 控制操作後的舊決策生效。
- AgentThought 的額外頂層欄位會拒絕；payload 是展示附加資料，即使包含看似資源的鍵，也沒有狀態寫入權限。
- `pending_oxygen`／`pending_food` 與可用庫存合計才是已占容量；玩家編輯對應公共資源會清除該項 pending。

## Mock 邊界

本 repo 不實作 Core／Plant／Human、LLM provider、策略 prompt 或記憶系統。展示 adapter 只能回傳明確標示的 fixture 計畫／訊息；資源依真實 WorldEngine 結算，不能將 fixture 視為自主決策證据。

前端獨立 mock server 只重播預錄 state／事件，不從輸入推算新資源；預錄情境以外的任意干預應連線真後端。新增作物的合法 key 與參數只來自共用 JSON，不在 adapter 維護第二份五作物清單。

## Agent 對話與協商呈現契約

使用者指定決策互動呈現為聊天式討論協商。场景氣泡仍錨定 Core 主控台、Plant 溫室及 Human 人員區；右下抽屜展開為完整對話窗，以同回合對話串組織訊息，不呈現為彼此無關的 log 流水帳。這是展示協定，不新增本 repo 的 Agent 決策實作。

既有 `AgentThought` 頂層欄位不變，可在 `payload` 中提供以下可選 metadata：

| payload 欄位 | 建議型別 | 用途 |
|---|---|---|
| `conversation_id` | `string` | 一次討論／重規劃回合的識別；同回合訊息沿用同一值。 |
| `to` | `'core' \| 'plant' \| 'human'` | 回覆或建議的主要對象；省略時表示對整個回合發言。 |
| `reply_to` | `string` | 被回覆的 AgentThought `id`，供回覆摘要與對話關係呈現。 |

UI 顯示發言角色名稱、角色頭像與回覆對象。`conversation_id` 存在時據此串連；相容舊訊息時可按 tick 分組，但必須將此視為 UI 分組，不能擅自推論隊友間已發生的協商。未知或尚未收到的 `reply_to` 保留引用，不阻擋訊息顯示；重送同一訊息 id 不新增另一則聊天。

每回合以 Core 的 `kind="plan"` 訊息及已通過驗證的 TickPlan 呈現計畫卡；訊息中的建議與计划文字不能當成已執行動作。取得權威 `state_update.last_summary` 後呈現結算結果卡，再接隊友提交的 reflection。結果卡對照实际輸入 TickPlan 的 tick／版本，而非以動畫或訊息到達時間推測執行結果。若多回合同一 tick 重新規劃，使用 conversation_id 區分，避免過期計畫與新結果混接。

所有聊天 metadata 與 payload 都只供呈現。未提供角色互答內容時，不由前端虛構對話；展示 mock 可重播明確標示的預錄協商訊息，並沿用同一對話串格式。
