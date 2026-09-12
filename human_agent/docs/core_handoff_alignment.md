# Human 配合 Core 的整合說明

更新：2026-09-12。本次已修改程式，對照 `specialist-agent-api-handoff.md` v1.3；以本文件取代先前「世界不停、原始請求回 422」的說明。

交付確認：使用者回報 Core 已接受本文件，Human 即依此約定交付，不再等待額外格式確認。本文所列未知資料採用已約定的未知／未驗證行為；只有未來實際資料或規則偏離本文件時才另作適配。人工測試入口見 [START_TESTING.md](START_TESTING.md)。

## 可以先告訴 Core 的內容

Human 提供 `POST /discuss`，接收既有 discussion 訊息，回覆你們的外層、content 五欄及 explanation 七欄。**以 Core 契約為基準，由 Human 轉接，不要求 Core 全面採用 Human API 2.0。**

`content.world` 就是此次 snapshot，不需再建立 snapshot 物件、檔案或額外 API。使用者已澄清：**Agent 討論期間世界會暫停**。Human 缺省使用 `planning`，將完整 world 視為 tick 結算之間的狀態；不發出暫停、恢復或推進世界的命令。明確傳入其他有效狀態仍會保留。

原始 Core 範例現在可直接進入分析。`alive`、`snapshot_phase`、`world_status` 都不再是 `/discuss` 的額外必填條件。缺 `alive` 時保留未知，不因能量和水為正就默認存活；一般問題仍正常回覆，依賴存活狀態的計畫可行性不會標已驗證。

使用者新增 **1 EU = 3.9745 kWh = 3974.5 Wh**。Human 已加入雙向換算與來源標記，覆蓋先前「無 EU 換算」的敘述。這是使用者確認的世界單位設定，非 NASA 文獻結論；原發電、製水、灌溉係數沒有改變。API 公共 power 仍傳 EU，kWh = EU × 3.9745；kW 是功率，不能省略時長直接換成能量。

## Human 已完成的適配

| 項目 | 目前行為 |
|---|---|
| Core 原始請求 | `core_original_human.json` 不增加 Human 必填欄位即可回 200；缺少事實列入 uncertainties |
| 討論暫停 | 缺省 `world_status=planning`、`snapshot_phase=between_ticks`；明確中途階段仍拒絕，以免重複扣款 |
| 存活狀態 | `alive` 選填、缺省未知；明確死亡或死亡數值仍按世界規則處理，不會復活 |
| ID 與版本 | 保留 Core crew／plot ID，內部產生 state_id；外層回原 discussion_id／round／world_version |
| 規則比對 | 允許 metadata、相容版本別名；必要數值、單位、布林與 tick 順序不相容仍回 409 |
| 規則說明變更 | 不因說明改寫直接拒絕討論；涉及執行語意的文字變更會揭露尚未核對，暫不驗證量化計畫 |
| explanation_schema | 接受無關註解、required 排序及可解析的本地非循環 `$ref` 差異；沒有宣稱能判定所有 JSON Schema 的數學等價性 |
| 無 plan | 回覆狀態、需求與本輪問題；不只因未提供可選計畫就要求再開一輪 |
| 候選計畫 | 接受既有 `world.next_tick_plan`，以及 `world.current_plan`／`content.current_plan` 中可辨識的完整 Plan 或 candidate_plan 包裝 |
| 計畫資訊不足 | 過期、不一致、不可辨識的 current_plan 保留給模型討論，不猜補任務或宣稱完成核算 |
| 歷史討論 | 傳入 question、Core explanation、追問理由及 previous_messages；reviews 必須引用真實歷史 message_id／proposal_id |
| 中文回覆 | display_text 提供建議重點；公開量化效果來自後端核算，模型評論另外標示性質 |
| 植物風險 | 第二次連續失灌為 critical，尚未死亡；第三次失灌為植物死亡，audit 標 unsafe_in_scope，不誤標 feasible 或全員死亡 |
| EU 換算 | `data/unit_conversions.json` 保存來源、版本；回覆附換算依據，6000 EU 對應 23847 kWh |
| 錯誤與時限 | 結構錯誤 422、不相容 409、服務失敗 502、逾時 504；入口 44 秒保護，配合 Core 45 秒 HTTP timeout |

`current_plan` 目前映射的是已知完整欄位：for_tick、crew_tasks、refill_order、water_production_request_liters、irrigation_allocations、crop_operation_order。正式 Core 計畫若採另一種表示，收到實際 DTO 後由 Human 加映射；**不要求 Core 為此重做內部排程格式，也不宣稱現在已支援尚未提供的格式。** 歷史候選只作討論，不會自動變成已指定安排。

## 整合邊界（不阻擋本版交付）

1. **死亡如何表示。** 原始 world 未提供 alive 時，若還有既有終止狀態或死亡欄位可用，請提供範例讓 Human 映射；不限定增加名為 alive 的欄位。一般討論不受阻，但未知者不能通過存活可行性核算。
2. **完整候選與設備狀態的實際表示。** 需要精確核算時，才依本輪候選釐清缺少的任務、執行順序、配額或製水可用性；不用每次討論都補完整計畫。
3. **未完整寫出的正式規則。** 共享氧氣或電力容量不足時的發電分配，以及死亡階段內的微順序，需要與世界引擎案例比對。Human 應依正式定義調整，不能要求世界遷就 Human。

目前 Human 依世界 v0.12 的發電公式為：

- a_i = min(請求工作量, 1, 基礎消耗後個人能量 / 100)
- W = min(sum(a_i), 公共氧氣 / 25, 電力剩餘容量 / 250)
- sum(a_i) = 0 時工作量為 0，否則 w_i = W × a_i / sum(a_i)

既有交接的容量、警戒線、需求、補給上限、發電／製水係數、灌溉及作物數值相容。上述分配公式是提供對照依據；尚未取得世界程式，不宣稱已完成引擎差異測試。死亡微順序未定時不發布完整末端世界狀態。

## 暫停期間的訊息用途

同 discussion 依 Core v1.3 使用同 world_version。Human 讀取固定 world、分析下一個尚未結算的 tick，回覆供 Core 比較的建議。Core 沿用既有採用與世界驗證職責，再恢復世界；Human 不自行恢復。tick 與 world_version 不必相等。

即使暫停，也不把舊提案當成新狀態；目前跨版本歷史會明確拒絕。若 Core 日後改成跨版本討論，再由 Human 適配新契約。

## 啟動、人工測試與驗證

```powershell
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
python scripts/discussion_smoke.py
python scripts/discussion_smoke.py --live
```

重啟服務後開 `/docs`，選 `POST /discuss`：

- 原始 Core 請求：`examples/discussion_requests/core_original_human.json`，測沒有額外狀態和 plan 的正常討論。
- 完整候選：`examples/discussion_requests/with_plan.json`，使用 planning，測量化候選核算。
- 第二輪實際訊息與回覆：`examples/discussion_responses/live/round2.request.json`、`round2.json`。previous_messages 必須沿用同 discussion／版本，不能只把 round 改成 2。
- `normal.json` 仍送原端點 `/human-agent/analyze`，不要把兩種請求混用。

本次單元／契約測試 122 項通過；原 Human 六種 mock HTTP 情境通過；Core 原始請求及兩輪 mock HTTP 均 200。最新 Live 執行結果見 `docs/discussion_http_live.json`，完整回覆在 `examples/discussion_responses/live/`。驗證報告 `docs/validation_report.md` 記錄本次結果。

本機真實模型 HTTP 測試不等於雙方聯測。尚未測試隊友 Core 接收器、真正 Plant 服務、世界引擎及第二台電腦 LAN。跨機服務需綁定 `--host 0.0.0.0`，Core 使用 Human 電腦可達 IP；現有接口沒有配置 Bearer token／HTTPS。此次未修改 `.env`、防火牆，也未對外傳送交接訊息。

本次交付再驗證：130 項測試通過；Core mock HTTP 11 個案例通過，包含原始請求、三輪討論與七個適配／邊界情境；原 Human mock 六情境通過。Live 原始請求 22.689 秒，三輪 28.533／31.750／34.135 秒，全數 HTTP 200；第二、三輪各有 2／3 項有效歷史評論。Swagger 已提供六種可執行範例，`examples/discussion_client.py` 可直接呼叫現有服務、保存每輪請求／回覆／耗時。
