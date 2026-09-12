# Space Greenhouse v2：三 Agent 整合手冊

本手冊提供 Core、Plant、Human 三個 Agent 與現有遊戲前後端的整合者使用。目標是讓 Agent 進行對話式協商、由 Core 產生單一遊戲 tick 的 `TickPlan`，並由既有後端驗證與結算；不建立第二套世界規則或資源結算邏輯。

實作進度（2026-09-12）：已新增 [agent_runner](../agent_runner/README.md)，包含逐 tick Core 轉接、公開訊息、WS 結算確認與 `/decision`、`/ingest/decision-plan`、`/ingest/decision-failure`。新提交路徑提供 request 綁定及程序內去重，舊 `/ingest/plan` 仍無 idempotency key。Plant Release 索引已安裝、校驗並通過完整服務健康檢查；Plant 數值對齊與一項檢索排序測試、Human pending 支援及 Core 真實 reflection 仍待完成。完整啟動方式與驗證限制見上述 README。

## 1. 開工前必讀順序

在寫任何 adapter、API 呼叫或 prompt 前，必須依序閱讀以下檔案。第 4 至第 7 項是各 Agent 的 README，不能略過。

1. 根目錄 [AGENTS.md](../AGENTS.md)
2. [world-settings-guide.md](../world-settings-guide.md)
3. [space_greenhouse_spec_v2.md](../space_greenhouse_spec_v2.md)
4. [core_agent/README.md](../core_agent/README.md)
5. [core_agent/docs/README.md](../core_agent/docs/README.md)
6. [plant_agent/README.md](../plant_agent/README.md)
7. [human_agent/README.md](../human_agent/README.md)
8. [docs/integration_contract.md](integration_contract.md)
9. [docs/model_connection.md](model_connection.md)
10. [core_agent/docs/integration/core-agent-integration.md](../core_agent/docs/integration/core-agent-integration.md)
11. [core_agent/docs/integration/specialist-agent-api-handoff.md](../core_agent/docs/integration/specialist-agent-api-handoff.md)
12. [plant_agent/docs/DISCUSS_HANDOFF.md](../plant_agent/docs/DISCUSS_HANDOFF.md)
13. [human_agent/docs/core_handoff_alignment.md](../human_agent/docs/core_handoff_alignment.md)

閱讀完成後，先列出各 Agent 的啟動方式、必要環境變數、`/discuss` request/response 範例與任何數值假設，再開始串接。

## 2. 權威與不可違反的邊界

衝突時採用以下優先序：最新使用者指示 → 根目錄 `AGENTS.md` → `world-settings-guide.md` → `space_greenhouse_spec_v2.md` → 遊戲整合契約。各 Agent repo 內的世界數值、示例資料與舊版規則不得覆寫遊戲世界設定。

| 範圍 | 唯一負責者 | 整合規則 |
| --- | --- | --- |
| 作物、資源、消耗、容量、警戒線數值 | `shared/crops.json`、`shared/world_constants.json` | Agent 僅讀取，不另建常數表；UI 也不自行計算資源。 |
| 決策與協商 | Core Agent | Core 蒐集 Plant / Human 建議，選擇本 tick 行動。不得把決策規則硬寫在引擎或前端。 |
| 專業建議 | Plant / Human Agent | 只回傳建議與風險，不改 world state、不提交最終 `TickPlan`。 |
| `TickPlan` 驗證 | `backend/orchestration/plan_validator.py` | 所有外部計畫都要通過同一個 validator。 |
| 資源、作物、人物狀態結算 | `WorldEngine.settle()` | 這是唯一可造成庫存變動的入口。 |
| 對話呈現與遊戲畫面 | Frontend | 接收事件並呈現；不得由前端修改資源或推導世界狀態。 |

禁止：由 Agent HTTP endpoint、bridge、前端或 mock server 直接修改 `WorldState`；把 fallback 策略（例如平均灌溉、依固定順序分配）寫進程式；啟用 forecaster 或未來模擬。

## 3. 建議整合架構

現有遊戲後端已支援 `PLAN_SOURCE=external`。整合時以「Agent Bridge」作為唯一的外部決策接點，保留 `WorldLoop → PlanValidator → WorldEngine` 這條既有路徑。

```text
Frontend (Vite :5175)
  │  WebSocket：state_update / tick_plan / agent_thought
  ▼
Game Backend (:8001, PLAN_SOURCE=external)
  │  GET /world（已提交 snapshot）
  │  POST /ingest/thought
  │  POST /ingest/plan
  ▼
Agent Bridge / Runner
  ├── Core Agent
  │     ├── POST Plant Agent /discuss (:8101)
  │     └── POST Human Agent /discuss (:8102)
  └── 將當前決策轉成遊戲 TickPlan
       ▼
PlanValidator → WorldEngine.settle() → EventBus → Frontend
```

建議將 bridge 做成獨立 server 或獨立背景程序，例如 `backend/integration/agent_bridge.py` 或新建的 `agent_runner/`；它只能透過公開遊戲 API / WebSocket 傳入 thought 與 plan。不要讓 Core 的程式直接取得 repository、database session 或 `WorldEngine`。

### 為何不直接使用 Core 的 `WorldPort`

Core 目前的 `CoreController` 文件描述 `observe → pause_for_core → apply_and_resume` 與多階段計畫。遊戲後端目前則以 `ExternalPlanSource` 等待一份單 tick `TickPlan`，由 `WorldLoop` 統一驗證與結算，沒有對外的「planning pause」狀態轉換。

第一版整合應由遊戲 `WorldLoop` 擁有流程控制權：bridge 取得已提交 snapshot、完成協商、提交一份 plan。不要直接把 Core 的 `pause_for_core()` / `apply_and_resume()` 接到資料庫或引擎。

若日後必須使用 `CoreController`，先實作並測試一層 `WorldPort` adapter，保證其最終仍只呼叫既有 `/ingest/plan` 與由 `WorldLoop` 結算；不可增加第二條 apply-state 路徑。

## 4. 狀態與資料格式轉接

所有遊戲 API wire format 一律維持 `snake_case`。bridge 不應向前端暴露 Agent 專案內部 model。

### 4.1 快照轉接要求：遊戲 WorldState 至 Core snapshot

bridge 必須完整保留以下資料，並依 Core 實際 schema 轉接。數值原樣傳遞，不四捨五入；已提交的 `WorldState` 作為 `snapshot_phase: "between_ticks"` 的觀察快照。

| 遊戲欄位 | 轉接規則 |
| --- | --- |
| `tick`、`version` | 保留觀察時的值；Core 使用 `world_version` 時由 `version` 映射，提交時分別對應 `TickPlan.tick`、`state_version`，不可由 bridge 自增。 |
| `resources[key].value` | 公共可用庫存；`resources[key]` 本身是物件，不能直接當作數值。 |
| `resources[key].unit/capacity/warning` | 原樣保留單位、容量與警戒線。 |
| `pending_oxygen`、`pending_food` | 單獨傳遞，不預先加進可用庫存；入庫由引擎處理。 |
| `crew` | 保留人物 ID、個人存量、存活狀態及工作狀態。 |
| `plots` | 保留地塊 ID、作物、生長、成熟、死亡與灌溉中斷狀態。 |
| `settings` | 保留 `generation`、`water_production_l`、`irrigation`。 |
| `last_summary` | 傳入實際結算摘要；初始可為 `null`。 |
| `paused`、`paused_reason`、`failed`、`failure_reason`、`speed` | 保留控制與失敗狀態，不混同為一般暫停；若映射為 Core `world_status`，不得遺失原始資訊、虛構 `planning` 狀態或改變原狀態。 |

若 Core schema 無法表達 pending 或 settings，必須補齊契約，不能靜默捨棄欄位。完整 snapshot 範例從 `GET /world` 取得，避免手抄另一份世界數值。整合測試需涵蓋非零 pending、有效 settings，以及 `last_summary` 為 `null`／非 `null` 的情況。

snapshot 取得後，bridge 必須記住 `(tick, world_version)`。`pause`、`resume`、`speed`、資源修改與 `reset` 都可能改變 version；失敗或其他狀態更新也可能使觀察過期。版本改變時，舊請求與尚未提交的 plan 必須失效，重新觀察後才能決策；暫停或失敗時不得開始新的決策。已提交計畫的結果須依第 5.2 節確認，不能把結算造成的版本更新當成尚未提交的舊請求處理。

### 4.2 多階段計畫執行契約：Core 決策至遊戲 TickPlan

Core 負責保存多階段計畫及判斷階段轉換。bridge 負責轉接、提交與回傳實際結果，不從自然語言自行推斷下一步。每個決策 tick 都由 Core 明確提供當前 `TickPlan`；未來階段不得預先排入後端。

以下僅示範 Core 明確選擇本 tick 不執行任何行動的格式，不是輸出缺漏時的預設 plan：

```json
{
  "tick": 42,
  "state_version": 17,
  "refills": [],
  "generation": {},
  "water_production_l": 0,
  "irrigation": [],
  "plot_ops": [],
  "rationale": "Core 的公開決策摘要"
}
```

轉接規則：

1. `generation`、`water_production_l`、`refills`、`irrigation`、`plot_ops` 必須使用 `shared/tick_plan.schema.json` 和 `shared/types.ts` 的欄位名稱。
2. `generation`、`water_production_l`、`irrigation`：新決策 plan 必須明確提供設定；只有 loop 的非決策 tick 才會沿用 `state.settings`。
3. `refills`：一次性動作，`amount` 必填，陣列位置代表執行順序。
4. `plot_ops`：一次性動作，保留 Core 指定的 `order`，不自動重播或重種。
5. Core 明確選擇不執行時，才轉成零值、空物件或空陣列。輸出缺漏、解析失敗或沿用語意不明，應回報契約錯誤，不能自行補成空計畫；即使後端 schema 提供預設值，bridge 仍須遵守此完整性要求。
6. `tick` 與 `state_version` 必須與起始 snapshot 完全相同，只可藉由 `POST /ingest/plan` 提交。

目前 `/ingest/plan` 沒有 idempotency key。提交 timeout 不代表未入隊，不能盲目重送。已新增的 `/ingest/decision-plan` 使用 request_id／submission_id 去重；bridge 僅對此新路徑以完全相同 body 重試。去重範圍與重啟限制見 [bridge README](../agent_runner/README.md)。

## 5. Agent 協商協議與對話 UI

Core、Plant、Human 採用其交接文件的 v1.5 訊息 envelope：

```json
{
  "message_id": "uuid",
  "discussion_id": "uuid",
  "round": 1,
  "sender": "core",
  "recipient": "plant",
  "world_version": 17,
  "display_text": "給玩家看的繁中短摘要。",
  "explanation": {},
  "content": {}
}
```

Plant 與 Human `/discuss` 都回傳同一類 envelope；Core 以原始回覆作下一輪輸入。`display_text` 是公開 UI 文案，應為 2–4 句繁體中文，不輸出模型 chain-of-thought、API 金鑰、完整內部 prompt 或未驗證的資源修改指令。

### 5.1 agent_thought 完整格式

每一則公開訊息同時要 relay 至遊戲：

```text
POST /ingest/thought
```

建議映射為 `AgentThought`：

| Agent envelope | 遊戲 thought 欄位 |
| --- | --- |
| `message_id` | `id` |
| 訊息時間（Unix 秒數，例如 Python `time.time()`） | `ts`（必填） |
| 建議所依據的觀察 tick | `tick`；不能把舊建議標成提交時的新 tick。 |
| `sender` | `agent` |
| Core observe / risk / plan / reflection | 同名 `kind` |
| Plant、Human 回覆 | `kind: "advice"` |
| validator 或協商失敗 | `kind: "validation_error"` |
| `display_text` | `text` |
| `discussion_id` | `payload.conversation_id` |
| `recipient` | `payload.to` |
| 前一則 `message_id`（若有） | `payload.reply_to` |
| `round`、`world_version` | `payload.round`、`payload.world_version` |
| `explanation`、`content` | 僅轉送可公開欄位至 `payload`，不能整包當成前端訊息。 |

`POST /ingest/thought` 的完整格式示例：

```json
{
  "id": "plant-message-example",
  "ts": 1789171200.0,
  "tick": 42,
  "agent": "plant",
  "kind": "advice",
  "text": "已收到世界快照。請 Core 將作物需求納入本輪決策。",
  "payload": {
    "conversation_id": "discussion-example",
    "to": "core",
    "reply_to": "core-message-example",
    "round": 1,
    "world_version": 17
  }
}
```

以上識別碼、時間與版本僅為格式示例，送出時替換為實際值。前端群組欄位是 `payload.conversation_id`。

理想 UI 時序為：`observe → risk → Plant advice → Human advice → plan → 實際結算確認 → reflection`。驗證拒絕與恢復流程依第 5.3 節處理。

### 5.2 結算確認與 reflection

HTTP 202 只表示計畫已排隊，不代表通過驗證或執行成功。bridge 必須先訂閱 WebSocket `/ws`，再提交計畫。後端提交狀態後的事件順序是：

```text
mission_failed（若有）→ tick_plan（若有）→ world_event → state_update
```

使用 `tick_plan.tick`／`state_version` 配對提交計畫，再把同次 `state_update.last_summary` 交給 Core，之後才能發 reflection。資源修改或控制操作也會產生 `state_update`，不能只憑收到 `state_update` 就認定計畫執行完成；`tick_plan` 也不代表所有請求量都實際完成，仍須讀取結算摘要。

目前 `ExternalPlanSource` 沒有 mock 的 `post_settle` 回呼，上述結果回饋需要由 bridge 實作。斷線後無法確認結果時，應標示未確認，不編造成功反思。

### 5.3 失敗處理與恢復

| 失敗情況 | 處理方式 |
| --- | --- |
| REST schema 驗證回 422 | 未入隊，不增加 loop 驗證次數；交回 Core 修正。 |
| `PlanValidator` 拒絕 | 訂閱後端 `agent_thought` 中 `kind: "validation_error"` 的訊息，讀取 thought 的 `payload.errors`，請 Core 依仍有效的 snapshot 修正。 |
| loop 三次驗證失敗 | 後端自行空計畫結算並發 `plan_failed`（`world_event` 的事件類型）；bridge 不另送空計畫。 |
| 模型 timeout、specialist 斷線、bridge 離線 | 基礎 `ExternalPlanSource` 會持續等待；遊戲 external 模式使用 managed 子類別，由正式失敗通知或等待期限解除等待。僅發訊息仍無法解除等待。 |

正式失敗通知與等待期限已由 `ManagedExternalPlanSource` 實作：`GET /decision` 提供綁定 tick/version 的 request 識別；`POST /ingest/decision-failure` 接受仍有效的失敗通知，或由 `decision_timeout_seconds` 控制等待期限。loop 在鎖內處理錯誤、設 `paused_reason=error`，並推送 `plan_failed` 與 `state_update`。過期通知回 409，不得暫停新版本世界。原 `ExternalPlanSource` 本身仍可無期限等待；遊戲 external 模式現在使用 managed 子類別，不能以 `/ingest/thought` 或 `/ingest/event` 代替正式通知。

手動展示需要停止等待時，操作人員可使用：

```http
POST /control
Content-Type: application/json

{"cmd":"pause"}
```

此路徑的 `paused_reason` 是 `player`，不是正式錯誤暫停。恢復服務後，作廢舊請求，由操作人員 `resume`，再重新觀察。bridge 不得自動解除玩家暫停。

模型重試次數、協商輪次、loop 三次驗證是不同計數，不能混用。

## 6. Endpoint、port 與設定建議

不要讓 Plant、Human 與遊戲 API 佔用同一個 port。以下是建議本機配置，實際依各 README 的啟動指令調整。

| 服務 | 建議 port | 主要用途 |
| --- | ---: | --- |
| Game Backend | 8001 | `/healthz`、`/world`、`/ingest/plan`、`/ingest/thought`、WebSocket |
| Plant Agent | 8101 | `POST /discuss` |
| Human Agent | 8102 | `POST /discuss`；相容端點 `/human-agent/analyze` 僅供舊客戶端 |
| Agent Bridge | 8103（可選） | 協商流程、version guard、事件 relay |
| Frontend | 5175 | 視覺呈現與玩家操作 |

### 6.1 YAML 載入與服務設定

將 [config/runtime.example.yaml](../config/runtime.example.yaml) 複製為未追蹤的 `config/runtime.yaml`，確認其中 `plan_source: external`，再從 repo 根目錄啟動：

```bash
GREENHOUSE_CONFIG=config/runtime.yaml \
  .venv/bin/python -m uvicorn backend.main:app \
  --host 127.0.0.1 --port 8001
```

載入 YAML 時，YAML 的 `plan_source` 會覆蓋 `PLAN_SOURCE`；未指定 YAML 時才使用 `PLAN_SOURCE`。用 `GET /healthz` 確認 `mode` 是 `external`。

遊戲 YAML 不會自動設定或啟動三個 Agent。Core、Plant、Human 各依其 README 載入模型、provider、服務 URL 與金鑰，不能假設三者共用同一份設定。API key 僅可放在 server 的環境變數或未提交的 `.env`：

```bash
OPENAI_API_KEY=... 
OPENAI_MODEL=... 
PLANT_AGENT_URL=http://127.0.0.1:8101
HUMAN_AGENT_URL=http://127.0.0.1:8102
```

Core README 使用 `OPENAI_API_KEY`；Plant、Human README 另有其 provider / embedding 所需環境變數。不能假設一把 OpenAI key 自動滿足三者，應依各 README 明確配置。前端永遠不可拿到任何 key，也不可直接呼叫 LLM。

## 7. 數值衝突處理與待實作項目

以下項目要在 PR 或交接紀錄中明列；在 owner 確認前不得「修正」世界數字。

1. **Plant 耗電數值衝突。** [Plant 交接文件](../plant_agent/docs/DISCUSS_HANDOFF.md) 描述約 `0.208339 EU/hour/plot`；遊戲 guide 與 shared 設定的灌溉耗電為 `5 EU/plot/tick`，且一 tick 是一模擬小時。整合 runtime 依根目錄 guide、shared 設定及 [已核准偏差](tick_order.md) 執行，不修改世界數值來配合 Agent 文件。請 Plant owner 對齊其建議計算依據，並驗證建議能使用權威設定。這不阻擋其他接口、對話與 fixture 測試；在對齊完成前，不能宣稱真實數值整合已驗收通過。
2. **Core 的 multi-stage plan 與遊戲 single-tick plan 不同。** 必須完成第 4.2 節的 explicit adapter 與測試，不能把 Core plan 直接 POST 給遊戲。
3. **Core 的 pause/resume 介面與遊戲 loop 不同。** 第一版採 external `PlanSource` bridge，不可直接繞過 `WorldLoop`。
4. **各 Agent repo 可能保有快照 schema、示例世界或舊版限制。** 僅可作為轉接來源；遊戲 runtime 的數值與 validator 仍是唯一權威。
5. **`TODO(guide-pending)` 項目。** `TickPlan.refills` 是最小表達，仍須提供 `amount` 及陣列順序；未有 guide 數值或規則者不自行引入策略。Core 輸出缺漏屬契約錯誤，不能視為明確不執行。
6. **提交去重、正式失敗通知與等待期限。** 新 managed 請求路徑已實作，分別依第 4.2、5.3 節及 bridge README 記錄限制；舊 `/ingest/plan` 不具去重，結果跨重啟恢復仍未提供。

## 8. 實作順序與驗收

### A. 個別 Agent 健康檢查

1. 依每個 README 建立其環境並跑各自測試。
2. 以 mock / fixture 各呼叫一次 Plant 與 Human `POST /discuss`。
3. 驗證兩者回覆可解析 v1.5 envelope，且不包含資源變動 command。
4. Core offline 模式可讀 snapshot、產出內部決策結果。

### B. Bridge contract 測試

1. 以 backend `GET /world` fixture 建立 Core snapshot，涵蓋非零 pending、有效 settings、`last_summary` 為 `null`／非 `null`，確認轉接無欄位遺失或提前入庫。
2. 模擬 Core → Plant / Human 的一輪協商，將公開訊息轉成 `/ingest/thought`；確認必填 `ts`、觀察 tick、`payload.conversation_id` 與公開欄位篩選。
3. 驗證多階段計畫每個決策 tick 均明確提供設定，保留 `refills.amount`、陣列順序及 `plot_ops.order`，一次性動作不重播；缺漏或解析失敗回報契約錯誤。
4. 先訂閱 WebSocket，再以 `POST /ingest/plan` 排隊。配對 `tick_plan.tick`／`state_version` 與同次 `state_update.last_summary`，確認 Core 收到實際結果後才發 reflection；thought 本身不能造成資源變動。
5. 以資源修改、`pause`、`resume`、`speed`、`reset` 測試舊請求失效；控制產生的 `state_update` 不得被誤判為計畫完成，暫停或失敗時不得啟動決策。
6. 分別驗證 REST 422 不計入 loop 驗證次數、`validation_error` 的 `payload.errors` 可供 Core 修正，以及三次驗證失敗由後端空計畫結算，bridge 不另送空計畫。
7. 模擬提交 timeout 與 WebSocket 斷線，確認不盲目重送、不編造 reflection，無法確認的結果標示未確認。提交識別與去重機制完成後，另驗證可靠重試。
8. 模擬模型 timeout、specialist 斷線及 bridge 離線，確認目前等待限制與手動 `pause`／`resume` 流程；正式失敗通知與等待期限完成後，另驗證錯誤暫停及過期通知不影響新版本。

### C. 前後端展示測試

1. `curl http://127.0.0.1:8001/healthz` 回健康狀態，且 `mode` 為 `external`。
2. WebSocket 客戶端至少收到一次 `state_update`、`agent_thought` 與 `tick_plan`。
3. 前端 AgentDrawer 按 `payload.conversation_id` 分組、`payload.reply_to` 串接 Core、Plant、Human 對話；頭像、框與訊息保持對齊。
4. 在協商期間玩家編輯資源或 pause，確認舊對話產出的計畫不會套用到新 version。
5. 將 `oxygen` 改為零，下一個遊戲事件必為 `mission_failed`，不允許 Agent 或前端自行補回。
6. 快轉與暫停仍只由 world loop 時鐘控制：暫停時人物移動、作物動畫與資源狀態皆停止；快轉加速同一套 tick，不另算資源。

### D. 真實 LLM 展示前檢查

1. 確認 key 僅存在 server 環境，`git status --short` 沒有 `.env`、`runtime.yaml` 或 token。
2. 分開設定模型 timeout／retry 與協商輪次，不生成規則型 fallback plan；依第 5.3 節處理外部服務失敗。正式失敗通知與等待期限尚未實作時，明列展示限制及操作人員的手動暫停／恢復流程，不得宣稱 relay 訊息可解除等待。
3. 人工檢查一輪 public `display_text`，確定是繁中簡短協商摘要而非隱藏推理。
4. 記錄使用的 model、mode 與時間，但不記錄金鑰或完整敏感 prompt。

## 9. 整合完成定義

整合完成必須同時滿足：

- [ ] 三個 Agent 的 README 都已閱讀，並在 PR / handoff 中列出版本與啟動方式。
- [ ] Core 能讀取當前遊戲 snapshot，並向 Plant、Human 發送協商請求。
- [ ] snapshot 保留 pending、settings、控制與失敗狀態及實際摘要，已涵蓋第 4.1 節的轉接案例。
- [ ] 三方公開訊息以含 `ts` 的 `agent_thought` 顯示在前端，按 `payload.conversation_id` 分組，保留觀察 tick。
- [ ] 只有 Core 的當前決策能轉成單一 `TickPlan`，設定明確、一次性動作不重播、缺漏回報契約錯誤。
- [ ] bridge 能配對計畫與實際摘要後才回傳結果並發 reflection；斷線未確認時不編造成功。
- [ ] 所有 plan 都經過既有 `PlanValidator` 與 `WorldEngine.settle()`；無第二條 state mutation 路徑。
- [ ] stale version、API timeout、無效 plan、玩家 pause / 資源修改都有可重現測試。
- [ ] 沒有 API key、額外世界數值、預設資源分配策略或 forecaster 被提交。
- [ ] 提交去重、正式失敗通知與等待期限的實作／驗證狀態有明確記錄；未完成時僅能依已列限制驗收手動展示，不宣稱可靠重試或自動錯誤恢復完成。
- [ ] Plant owner 已對齊權威設定並驗證建議計算；未完成時僅回報接口、對話與 fixture 驗證結果，不宣稱真實數值整合通過。

## 10. 可直接交給整合者的任務說明

> 請整合 `core_agent`、`plant_agent`、`human_agent` 到 Space Greenhouse v2。開始前必須完整閱讀根目錄 `AGENTS.md`、`world-settings-guide.md`、`space_greenhouse_spec_v2.md`，以及 `core_agent/README.md`、`core_agent/docs/README.md`、`plant_agent/README.md`、`human_agent/README.md` 與本手冊列出的交接文件。依第 6.1 節載入 YAML，以 `GET /healthz` 確認 external 模式，透過既有 `ExternalPlanSource` 建立 Agent Bridge。
>
> 依第 4 節完整轉接 snapshot，保留 pending、settings、實際摘要與版本；由 Core 保存多階段計畫、協商並明確提供目前決策 tick 的完整 `TickPlan`。bridge 不推斷未來階段、不重播一次性動作、不將缺漏補成空計畫。公開訊息依第 5.1 節附上 `ts`、觀察 tick 與 `payload.conversation_id`；先訂閱 WebSocket 再提交 plan，配對同次實際結算摘要後才發 reflection。
>
> 不可直接改 state、不可改 `WorldEngine` 的結算入口、不可在 bridge / prompt 寫分配策略、不可複製世界數值或啟用 forecaster。控制或資源修改造成 version 改變時作廢舊請求，暫停或失敗時不開始新決策。提交 timeout 不盲目重送；422、validator 拒絕、三次驗證失敗及外部服務中斷分別依第 5.3 節處理，不把待實作的失敗通知、等待期限或去重機制當成既有功能，bridge 不自動解除玩家暫停。
>
> 先完成 mock / fixture contract 測試，再接真實 API key；key 僅限 server 環境。回報 Core multi-stage plan 至單 tick plan 的 adapter 設計及 Plant 耗電差異，runtime 持續採 guide、shared 與已核准偏差。請 Plant owner 對齊建議計算；其他接口與 fixture 測試可繼續，對齊前不宣稱真實數值整合通過。
