# Codex 任務：Space Greenhouse v2 — 從零建置前後端

你是資深全端遊戲工程師兼系統架構師。在這個 repo（目前是空的）裡，依規格建置一個「AI Agent 自主決策的火星基地生存經營遊戲」的前後端 MVP。

## 0. 先讀，照這個順序，讀完再動手

1. `space_greenhouse_spec_v2.md` — **本任務的實作規格**。資料模型、分層、tick 結算順序、TickPlan 接口、驗收案例都在裡面。
2. `world-settings-guide.md` — **世界數值的唯一真相**。所有單位、係數、公式來源。spec 若與 guide 衝突，以 guide 為準，並在回報中明列衝突處。
3. `OpenAI Hackathon.pdf` — 背景與動機，只需理解「為什麼是 Agent 決策而不是 threshold 自動化」，不從中取任何數值。

spec §12 提到的「既有程式碼」指的是上一版設計，**不在本 repo**；把 §12 當成設計差異對照表讀，不要去找那些檔案。

## 1. 三條鐵律（違反任何一條即視為任務失敗）

1. **數值只有一份。** 所有作物參數、消耗係數、容量、警戒線只能寫在 `shared/crops.json` 與 `shared/world_constants.json`，每個值旁註明 guide 的章節。後端、前端、三個 Agent 的 prompt 都從這兩個檔案載入；任何地方出現第二份硬編數值即為錯誤。
2. **策略歸 Core，驗證歸程式。** 水電分給哪些地塊、誰進食、誰發電多少、誰採收 —— 全部來自 Core Agent 輸出的 `TickPlan`（spec §5.4）。程式只驗證庫存、容量、占用與狀態（spec §5.3 的錯誤碼表）。**程式與 prompt 內不得出現任何預設分配政策**：不准平均分配、不准固定地塊順序、不准「最危急者優先」、不准「總是先灌溉高價值作物」。若你發現自己在寫 `sorted(crew, key=lambda c: c.food_energy)` 之類的東西來決定誰先吃，停下來 —— 那是 Core 的工作。
3. **結算只有一處。** `WorldEngine.settle(state, plan) -> (next_state, TickSummary, events)` 是庫存變動的唯一入口。前端動畫、Agent 訊息、控制台操作、REST 端點都不得直接改資源；玩家修改資源走 spec §5.7 的專用路徑。

## 2. 環境

- Python：目標 3.11。若本機是 3.9，安裝 `eval_type_backport` 讓 `X | None` 語法可跑，不要把型別退化成 `Optional`。
- Node 20+、npm。
- **沒有 LLM API key。** 所有測試與 demo 用 `LLM_PROVIDER=mock`；`openai` / `anthropic` 兩個 provider 的呼叫層要寫，但只需單元測試 response 解析與 schema 轉換。
- 沒有 docker。`docker-compose.yml` 要提供，但不要求你跑。

## 3. 目標目錄結構

```
shared/            crops.json · world_constants.json · types.ts · tick_plan.schema.json
backend/
  domain/          models.py · state.py（StateRepository）
  engine/          world_engine.py（settle）· crew.py · generation.py · water_plant.py · crops.py · harvest.py · irrigation.py
  orchestration/   world_loop.py · plan_validator.py · event_bus.py · ingest.py · player.py（修改資源）
  agents/          core_agent.py · plant_agent.py · human_agent.py · registry.py · llm.py · memory.py · prompts/*.md
  api/             rest.py · ws.py
  persistence/     db.py · repositories.py
  main.py · requirements.txt · Dockerfile
  tests/           test_engine_numeric.py（spec §11 全部案例）· test_validator.py · test_agents_mock.py · test_prompts_no_policy.py · test_loop.py
frontend/
  src/game/        scene.ts · waypoints.ts · world_objects.ts · crew_sprite.ts · crops_sprites.ts · interaction.ts · GameView.tsx · style.ts
  src/overlay/     bridge.ts · describe.ts
  src/components/  MissionBadge.tsx · Toolbar.tsx · ResourceEditor.tsx · AgentDrawer.tsx · Bubble.tsx · Tooltip.tsx · DetailCard.tsx · FailureCard.tsx
  src/store/       gameStore.ts
  src/net/         ws.ts · rest.ts · mockServer.ts
checks/            replay_baseline.py（guide 描述的 7,200 tick 基準策略，作回歸測試用）
docs/              README.md · tick_order.md · adding_a_crop.md
docker-compose.yml
```

## 4. 工作階段 — 每階段結束必須：跑指令、貼結果、寫一段回報，然後才進下一階段

### Phase 0 — 盤點（不寫程式）
輸出：(a) 你對 spec §3.6 七個 phase 的理解，用一張表列出每個 phase 讀哪些欄位、寫哪些欄位；(b) 你找到的 spec 與 guide 的任何衝突或不明處；(c) spec §3.9 四個待定項目你打算怎麼用 `TODO(guide-pending)` 留空。**我會先看這份再放行。**

### Phase 1 — shared
`shared/crops.json`（guide §2.1、§2.2 五種作物全部欄位）、`shared/world_constants.json`（guide §1.1 資源表、§1.3 時間、§2.3 個人容量與基礎消耗、§2.4 發電、§2.5 製水、§2.1 灌溉）、`shared/types.ts` 與 `backend/domain/models.py`（spec §6，欄位名一致、wire format snake_case）、`shared/tick_plan.schema.json`。
驗證：一個腳本把 json 的每個數值印出來對照 guide 的表格；`potato` 每塊每輪 = 8,775 這種推導值要用測試證明是**算出來**的，不是抄的。

### Phase 2 — WorldEngine（最重要，先做、做完整）
`backend/engine/` 依 spec §3.5、§3.6 實作。純函數，不碰 I/O，不碰 StateRepository。`pending_oxygen` / `pending_food` 的下一 tick 入庫機制要在這層。
驗證：`backend/tests/test_engine_numeric.py` 覆蓋 **spec §11 數值驗收表的每一列**，一列一個測試，測試名稱含 guide 章節。全綠才進 Phase 3。

### Phase 3 — Orchestration
`plan_validator.py`（spec §5.3 全部錯誤碼）、`world_loop.py`（spec §5.5；暫停不結算、不累加計數；決策 tick 沿用連續設定）、`player.py`（spec §5.7，修改後立即死亡檢查）、`event_bus.py`、`ingest.py`。
驗證：`test_validator.py` 每個錯誤碼一個測試；`test_loop.py` 驗暫停 5 tick 後庫存與灌溉計數不變、三輪驗證失敗後以空計畫結算並發 `plan_failed`。

### Phase 4 — Agents
`registry.py`（`set_generation`、`set_water_production`、`plant`、`harvest`、`clear`；refill 接口標 `TODO(guide-pending)` 以 `TickPlan.refills` 為最小表達）、`llm.py`（`LLM_PROVIDER = openai | anthropic | mock`）、三個 Agent、`prompts/*.md`、`memory.py`。
CoreAgent.plan() 必須逐步 emit `agent_thought`：observe → risk → advice（Plant / Human）→ plan → validation_error（若有）→ reflection。
驗證：`test_agents_mock.py` 用 mock provider 跑一次完整決策，斷言 thought 序列的 kind 順序與 TickPlan 通過驗證；`test_prompts_no_policy.py` 掃描所有 prompt 檔，禁止出現 `always`、`優先`、`first`、`平均`、`most critical`、`sorted by` 等政策字眼（詞表寫在測試裡，可擴充）—— **prompt 裡只能有 Objective、Constraint、公式與輸出格式**。

### Phase 5 — API
spec §7 的 REST 與 WebSocket。多客戶端、斷線清理。
驗證：啟動 `uvicorn backend.main:app`，`curl /healthz`，用 websocket client 收到 `state_update` / `tick_plan` / `agent_thought` 三種訊息各至少一則；`POST /resources {"oxygen": 0}` 後下一則訊息是 `mission_failed`。

### Phase 6 — Frontend
依 spec §4 全部。重點順序：`gameStore` → `mockServer.ts`（spec §8 的五段 demo 劇本，讓前端可獨立跑）→ `scene.ts` 六區域 → `world_objects.ts`（四種資源的世界物件、20 塊地、發電機、製水設備、控制台）→ `crew_sprite.ts`（真的走路：沿 waypoint 定速、邁步、朝向；任務姿勢靜止為主、每 2–4 秒一個節拍，**不得持續抖動**；死亡倒地）→ 三處 chrome + `ResourceEditor` → 氣泡／tooltip／詳細卡。
驗證：`npm run build` 通過；`npm run dev:mock` 開 `http://localhost:5173/?mock=1`，用 headless browser 截圖確認：畫面上沒有常駐儀表板、20 塊地可見、四種資源物件可見、hover 水箱出現 tooltip。

### Phase 7 — 整合與驗收
前端接真後端（`LLM_PROVIDER=mock`）跑 spec §8 demo：修改 `power` 為 300 → 氣泡依序出現 → TickPlan 生效 → 部分地塊邊框轉黃 → 恢復。逐條對照 spec §11「前端驗收」勾選。寫 `docs/README.md`（啟動、tick 順序圖、TickPlan 範例）、`docs/adding_a_crop.md`（證明加第六種作物只改 `crops.json` 與貼圖）。
最後：`git add -A && git commit`，commit message 列出各 phase 測試數量。

## 5. 不准做的事

- 不准改 guide 或 spec 的任何數值；發現數值有問題就回報，不要「修正」。
- 不准在結算中四捨五入；UI 顯示才能格式化。
- 不准替 spec §3.9 的待定項目做決定；留 `TODO(guide-pending)` 與「什麼都不做」的預設。
- 不准把 Forecaster / 未來模擬加回來，即使你覺得 Agent 需要它（guide §1.3 明定沒有）。
- 不准為了讓 demo 好看而在前端或 mock server 裡算資源；mock server 只重播預錄的 state。
- 不准跳過任何 phase 的驗證指令，也不准在測試失敗時進下一階段。
- 不准用 `Optional[X]` 取代 `X | None`，不准把 `snake_case` 欄位在前端改成 camelCase。

## 6. 回報格式（每階段）

```
## Phase N — <名稱>
完成：<檔案清單>
驗證：<指令> → <結果摘要，含測試數量>
與 spec/guide 的偏差：<無 / 列點>
待定項目處置：<無 / 列點>
下一階段風險：<一兩句>
```

Phase 0 的回報送出後**等我確認**再繼續。之後各階段可連續進行，但每階段的回報都要留在對話中。
