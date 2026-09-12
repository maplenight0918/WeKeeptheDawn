# 三 Agent Bridge

bridge 沿用隊友的 `CoreAgent`、`GPTDecisionModel`、`HTTPSpecialist`，以遊戲公開 HTTP／WebSocket 串接。世界仍只有 `WorldLoop → PlanValidator → WorldEngine` 一條 tick 結算流程。此目錄不提供 LLM provider、策略 prompt、Agent 記憶或未來 Simulator。

## 已核對的服務與契約

以下指令的 cwd 分別為表列 Agent 目錄，各自使用依其 README 安裝的環境。整合環境使用 Python 3.11+；既有根目錄 `.venv` 是 Python 3.9，本次保留，另建 `.venv-bridge`。

| 服務 | 啟動／呼叫 | 設定與目前限制 |
| --- | --- | --- |
| Core | repo 根目錄執行 `.venv-bridge/bin/python -m agent_runner`，內部呼叫 `CoreAgent.plan()` | 繼承 `OPENAI_API_KEY`、`OPENAI_MODEL`、`PLANT_AGENT_URL`、`HUMAN_AGENT_URL`；URL 必須包含 `/discuss`。可選兩個 `*_AGENT_TOKEN`。`--core-env` 明確載入 Core dotenv，不共用遊戲 YAML。 |
| Plant | `plant_agent/`：`../.venv-bridge/bin/python -m uvicorn src.api.main:app --host 127.0.0.1 --port 8101` | 依其 README 使用 `OPENROUTER_API_KEY`；模型與 embedding 選擇沿用其實作。已安裝官方 Release `index-v1` 三份索引，SHA-256 均符合 manifest；完整服務健康檢查回報 64,160 chunks。檢索排序測試與數值口徑仍待 owner 修正。 |
| Human | `human_agent/`：`AGENT_MODE=mock .venv/bin/python -m uvicorn app.main:app --host 127.0.0.1 --port 8102` | mock 不用金鑰；live 另需自身 `LLM_API_KEY`、`EMBEDDING_API_KEY` 與匹配的 provider、model、base URL。保留它的 `.env`，不由 bridge 改寫。 |

協議依 Core specialist handoff v1.5：`/discuss` request 是 `{message_id, discussion_id, round, sender:"core", recipient:"plant"或"human", world_version, display_text, explanation, content}`；`content` 含 `question/world/rules/previous_messages/reason/analysis_scope/unit_conversion_policy/response_guidance/explanation_schema`。回覆保留 discussion、round、version，交換 sender／recipient，使用新 message_id；`content` 的 observations、priorities、suggested_actions、acceptable_tradeoffs、evidence_and_unknowns 與 explanation 七欄必須完整。完整 JSON 範例見 [手冊](../docs/three_agent_integration_manual.md) 及其連結的 specialist handoff。

本次 HTTP 聯測實際由 Core 產生上述 request，送到兩個 specialist 的原始 `/discuss` 路由，再由 Core 接收回覆；不是另一份手抄 world fixture。

## 安裝與展示

從 repo 根目錄建立獨立環境（不要覆蓋既有 `.venv`）：

```bash
uv venv --python 3.11 .venv-bridge
uv pip install --python .venv-bridge/bin/python -r agent_runner/requirements-test.txt
```

只有首次尚無 `config/runtime.yaml` 時，將 `config/runtime.example.yaml` 複製為該檔，保留 `plan_source: external`。第一個終端啟動遊戲：

```bash
GREENHOUSE_CONFIG=config/runtime.yaml \
  .venv-bridge/bin/python -m uvicorn backend.main:app --host 127.0.0.1 --port 8001
```

YAML 的 `plan_source` 覆蓋 `PLAN_SOURCE`；`GET /healthz` 應回 `mode: external`。第二個終端可先跑明確標示的 fixture：

```bash
.venv-bridge/bin/python -m agent_runner --fixture --max-ticks 2
```

這會使用真實 Core 協商程式搭配測試 model／specialist，並讓真實後端結算兩個 tick。fixture 僅安排灌溉，不是長期生存策略。結束後遊戲可能開始等待下一請求；要停止展示可由操作人員 pause，或停止遊戲程序，不能把 fixture 無限執行當成策略測試。

前端另開終端：

```bash
cd frontend
npm run dev -- --host 127.0.0.1 --port 5175
```

### 完整動作展示（非真實 Agent）

需要觀看設備與人物動作時，改用以下 bridge，**不要與其他 bridge 同時提交**：

```bash
.venv-bridge/bin/python -m agent_runner --fixture-actions
```

此模式沿用真實 Core 協商接口，但 model／specialist 是明確標示的 fixture，不呼叫付費模型。人物依固定七 tick 輪班表飲水、發電、進食；補給上限、製水與灌溉係數都讀取傳入的 shared 權威規則。地塊工作只替換原定發電人員，不搶占補給工作。

從正常 tick 0 開始，第一輪清除 p20，下一輪播種；製水與其他人物工作同時展示。成熟地塊才會採收、空地才會播種，不預先修改成熟度或庫存。初始萵苣到 tick 30 才成熟，採收從之後的決策開始。這是可重現的展示排程，不是長期生存策略或真實模型驗收；本次驗證範圍為初始世界的 40 ticks。

互動展示不加 `--max-ticks`，bridge 會持續等待玩家暫停／繼續；若加上該參數，達上限後 bridge 會退出，再按繼續仍須重新啟動 bridge。bridge 不會自動解除玩家暫停，也不會 reset 失敗世界。需要新展示時請操作人員明確重設，或讓後端使用另一份 `WORLD_DB`，保留舊紀錄。

驗證完整動作（自動啟動隔離後端／前端，不使用現有展示世界）：

```bash
.venv-bridge/bin/python -m pytest backend/tests/test_action_fixture.py -q
node checks/smoke_three_agent_bridge.mjs --actions
```

瀏覽器測試檢查實際 WebSocket 工作、發電／製水結算、自然採收及 c02 抵達 p20 的位置；截圖存於 `artifacts/three-agent-actions.png`。飲水點與清除仍沿用現有呈現，不新增未確認的操作入口。

Plant 索引已齊全；待兩個 specialist 啟動、確認各自模型設定並取得付費聯測同意後，明確提供 Core 環境，再啟動真實串接：

```bash
PLANT_AGENT_URL=http://127.0.0.1:8101/discuss \
HUMAN_AGENT_URL=http://127.0.0.1:8102/discuss \
  .venv-bridge/bin/python -m agent_runner --core-env core_agent/.env
```

`core_agent/.env` 需由部署者建立，含帳號可用的 `OPENAI_MODEL` 與金鑰；範本不猜模型，不將憑證送到前端。此模式會呼叫隊友既有 provider 並可能產生費用；本次驗證未呼叫真實模型。

## 快照與多階段轉接

### 三個實際 Agent 的接線與單次聯測

一次真實低電量emergency的瀏覽器入口：`node checks/live_resource_emergency.mjs --allow-paid`。需操作者重新明確同意付費，並讓Plant8101、Human8102 live服務就緒。腳本檢查18001／15174空閒後啟動隔離世界，由瀏覽器改電力為50 EU，確認舊請求409，再執行一次Core規劃、最多三輪協商和一個結算tick。結束自動關閉自建服務，不操作8001展示。這個固定干預量是測例，不是世界策略或新參數。既有樣本成功將電力提升至200 EU但仍低於警戒線，詳見驗證紀錄。

已接線：Core 在 bridge 程序內呼叫隊友 `CoreAgent + GPTDecisionModel`；Plant 是 `http://127.0.0.1:8101/discuss`；Human 是 `http://127.0.0.1:8102/discuss`。Core 不是缺少 HTTP server，而是此版本以 Python 介面整合。

Human 原始服務從其自己的目錄啟動，使用其自己的 `.env`，不共用 Core 金鑰：

```bash
cd human_agent
AGENT_MODE=live ../.venv-bridge/bin/python -m uvicorn app.main:app --host 127.0.0.1 --port 8102
```

Plant 啟動命令見上方服務表。服務啟動與 `/health` 不付費探測 provider；發送分析則可能付費。兩個服務都啟動後，由操作者明確授權以下命令：

```bash
.venv-bridge/bin/python -m checks.live_three_agents --allow-paid
```

此命令讀取 `core_agent/.env`，建立臨時埠、記憶體資料庫的隔離 external 世界；只允許一次 Core 規劃、最多三輪協商、最多一個結算 tick。不會重啟或改動 8001 展示世界。需要再次付費規劃的 schema／驗證錯誤直接終止，不自動擴大付費範圍。公開對話與真實結算保存為 `artifacts/live-three-agents-<timestamp>.json`，測試世界結束後關閉。

2026-09-12 經使用者同意，已成功完成一次真實聯測：Core 模型產生計畫，Plant 與 Human 原始 HTTP 服務回覆，bridge 配對確認 tick 0 → 1。Plant 因權威耗電衝突走其既有規則回覆分支，**不是 Plant LLM 已通過驗收**；Human 為 live 設定，但此結果不提供所有內部模型呼叫數的保證。詳見驗證紀錄。

若要將瀏覽器的 8001 世界切換成持續真實 Agent，必須先停止唯一的 fixture bridge，保留／確認世界狀態，再用以下命令替換；每 tick 可能付費，不屬於上述一次性測試的授權：

```bash
PLANT_AGENT_URL=http://127.0.0.1:8101/discuss \
HUMAN_AGENT_URL=http://127.0.0.1:8102/discuss \
  .venv-bridge/bin/python -m agent_runner --core-env core_agent/.env
```

### 轉接規則

五 tick 瀏覽器短測入口為 `python -m checks.live_five_tick_demo --allow-paid`（使用 `.venv-bridge`）。需先由操作人員準備獨立、tick 0 的 8001 external 世界並停止原 fixture bridge；腳本不 reset 或替換資料庫、不自動解除玩家暫停。最多五次 Core 規劃，每次最多三輪，達五個已確認 tick 後暫停並退出。

為限制費用，每個 tick 最多啟動一次規劃；規劃期間若 pause/resume、調速或改資源使版本失效，舊請求作廢，這次短測不會自動追加同 tick 規劃。上游已送出的請求即使取消仍可能計費，重新執行須取得新的明確同意。公開結果存於 `artifacts/live-five-ticks-<timestamp>.json`。

`contracts.core_snapshot()` 保留所有 WorldState 資料：Core 的 `resources` 使用 `.value` 數值，原資源物件完整保留於 `resource_details`；crew 轉成列表但 ID、工作與存活資訊不變；plot 增加 `crop_type/status/growth_ticks` 別名並保留原欄位。pending、settings、last_summary、paused、paused_reason、failed、failure_reason、speed 原樣保留。Core 的 world schema 允許這些附加欄位，無需捨棄資訊。

`game_rules()` 從 shared JSON 產生 Core／specialist DTO 與內容雜湊版本；共用數值不取自 `core_agent.rules.get_rules()`。原始數值與來源也保留在 rules.metadata。`kcal` 在 specialist rules 中對應既有 `game_kcal` 單位名稱；snapshot 的原始 unit 仍保留。

每個決策請求都重新呼叫 Core。新 plan 的 `entry_stage_id` 與 offset 0 是 Core 明確指定的目前行動；actions 陣列順序映射至 refill 順序及 plot_ops.order。bridge 不計算 transitions、不推進 stage，也不將 future offsets 排入後端。上次 Core plan 與實際結果透過 `current_plan/history` 交回 Core，下一輪由 Core 重新決定當前階段。這是逐 tick 重新規劃模式，沒有在 bridge 實作持續多階段排程器。

新 TickPlan 設定全部明確提供；缺漏或解析失敗報契約錯誤。bridge 的 REST 422 修正上限為 3 次，與 Core 最多 3 輪協商、loop 最多 3 次 PlanValidator 驗證各自計數。Core 內部規劃錯誤目前直接通知後端錯誤暫停，不補空計畫。

## 新增決策請求接口

| API | 契約 |
| --- | --- |
| `GET /decision` | 目前 request 或 null；含 request_id、tick、state_version、status、deadline_ts、validation_errors。只有 awaiting 可開始規劃。 |
| `POST /ingest/decision-plan` | `{request_id, submission_id, plan: TickPlan}`；202 僅表示已排隊。相同 submission_id 與相同 body 重送只回 receipt、不再入隊；不同 body 或過期 request 回 409。 |
| `POST /ingest/decision-failure` | `{request_id}`；仍有效才接受，loop 在鎖內轉 error pause 並推送 plan_failed/state_update；過期通知 409，不能暫停新世界。 |

新增 endpoint 不取代舊 `/ingest/plan`。**舊 endpoint 仍沒有 idempotency key，不能盲目重送**；bridge 只用新 endpoint。去重 receipt 為單程序最近 256 筆，未持久化；已不活躍的 request 即使 receipt 被淘汰或程序重啟仍不能再次入隊。這不提供跨服務重啟的结果恢復保證，也不允許同時混用兩條提交路徑派送同一計畫。

`decision_timeout_seconds` 預設 420 秒，為 Core 最多三輪的 specialist／model 等待保留時間；從每次 loop 決策請求起算，包含 bridge 離線時間。到期由 loop 錯誤暫停，不扣資源、不补跑 tick。pause/resume/speed/edit/reset 都會使舊 request 失效。恢復需操作人員明確 resume；bridge 不會解除玩家暫停。

bridge 在兩次同身分提交都收不到回應時只等待 WS 證據；斷線則記錄未確認並退出，後端仍按請求期限處理。重新啟動 bridge 只處理當前 awaiting request，不重播舊 plan。不宣稱可從 snapshot 單獨復原先前成功結果。

## 結算回饋與已知限制

先訂閱 WebSocket，再提交計畫；以 tick_plan 的輸入 tick/version 配對緊接的 state_update（tick/version 各加一）及 last_summary.tick。控制更新、未知結果與已提交 plan 的縮量均不當成成功證據。三次 validator 拒絕後的後端空計畫與 plan_failed 亦以實際 executed_plan 回報。

結算摘要與事件交入 CorePort 的 24 筆 handoff history，供下一次 Core.plan 使用。隊友 CoreAgent **沒有 reflection 方法**，所以 UI 以 `kind: observe`、`payload.source: bridge_result` 顯示「Bridge 結算回報」，不偽造 Core reflection；真實 reflection 仍需 Core owner 提供接口。所有 Agent 公開訊息保留 ts、觀察 tick、conversation_id、reply_to；不轉送整份 content。

Plant 與 Core 複本約 0.208339 EU/plot/hour，遊戲權威為 5 EU/plot/tick。實際 Plant 路由會回公開 conflicts，bridge 保留該訊息，世界仍使用 shared 規則；須 Plant owner 對齊建議計算後才能驗收真實數值整合。Human mock 已接受權威規則並完成路由聯測，但它內部模型會忽略額外 world 欄位；若要對 pending 做量化核算，仍需 Human owner 明確支援，不能把本次接口測試當成 pending 核算已驗證。

## 驗證

規劃提示及玩家資源 emergency 的不付費驗證：

```bash
.venv-bridge/bin/python -m pytest backend/tests/test_resource_emergency_bridge.py -q
node checks/smoke_three_agent_bridge.mjs --emergency
```

瀏覽器左上「Agent 規劃中」代表當前版本的後端正等待計畫，不保證 provider／bridge 在線。提示不鎖定玩家控制；修改資源仍使舊決策失效。上述測試使用隔離世界與明確fixture驗證重新規劃、暫停、立即缺氧死亡，沒有呼叫真實模型或建立內建救援策略。

```bash
.venv-bridge/bin/python -m pytest -q
cd frontend
npm run typecheck
npm run build
```

`backend/tests/test_bridge_http.py` 使用本機临時埠啟動真實 HTTP／WS，測試結算、玩家暫停、提交回應遺失與實際 specialist 路由。Plant 路由測試刻意停用 lifespan，注入禁止檢索的測試物件，只驗證它原本就不呼叫模型的規則衝突分支；不能當成完整 Plant 服務健康檢查。安裝 Release 索引後已另外完成真實 lifespan／health 驗證，詳見驗證紀錄。

瀏覽器端完整 smoke check（從 repo 根目錄執行）：

```bash
node checks/smoke_three_agent_bridge.mjs
```

此檢查使用獨立埠 18001／15174、記憶體世界及 fixture，僅對測試 app 加入測試 origin；若埠已占用則失敗，不連到或停止既有服務。Chrome 可由 `CHROMIUM_PATH` 指定。截圖存於忽略上傳的 `artifacts/three-agent-bridge.png`。實測結果見 [驗證報告](../docs/three_agent_validation.md)。
