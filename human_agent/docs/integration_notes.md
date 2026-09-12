# 整合紀錄

最新澄清及實作：使用者修正為 Agent 討論期間世界暫停。`/discuss` 缺省 planning／between_ticks，alive 可省略並保留未知；原 Core 請求可直接回 200。新增 current_plan 已知完整格式轉換、schema／規則 metadata 相容處理、失灌風險修正，以及使用者確認的 1 EU = 3.9745 kWh。122 測試通過，原始 Core 請求與兩輪 Live HTTP 均 200（25.05／28.71／34.46 秒）。以下「Core 必須補三類狀態」及「預設 running」是歷史紀錄，已由本次適配取代。詳見 `docs/core_handoff_alignment.md`。

2026-09-12 Core handoff v1.3：新增 `/discuss`，共用 Human 分析流程；轉換訊息外層、檢查規則內容及跨輪引用，實際兩輪live200。Core仍需提供 crew[].alive、world.world_status、world.snapshot_phase；可選明確next_tick_plan／water_production_available。詳細責任分配與待确认項目請轉交 [core_handoff_alignment.md](core_handoff_alignment.md)。以下較早紀錄的「尚無正式DTO」以此最新對照為補充，尚未取得Core程式或完成跨機聯測。

最新live修正：dense＋BM25正常合併排名並回mixed，數字命中已通過10/10；embedding呼叫與cache hits使用每request ContextVar，兩個並行live已驗證。Core-side範例新增完整識別檢查與`response_is_current`採用前檢查，adapter契約測試通過；正式隊友DTO與跨電腦LAN仍沒有外部目標可驗證。`.env`保持使用者的live設定，未再改寫。

公開reason改由已知規則與工具audit產生；LLM原始自由文字不當作科學結論發布。evidence.reviewed_claims綁定BVAD原文hash；只核對所列有限語句，不擴張成整份文獻已認證。此調整沒有改世界公式、向量policy或既有corpus。

2026-09-12 初始盤點只有 `.env`、`spec.md`、`AGENTS.md`、`world-settings-guide.md`；沒有 raw、chunks、向量、cache、舊程式或共用 rules package。這次從零建立，未繼承舊 790 chunks、38 passed 或 7,200 tick 歷史結果。

`world-settings-guide.md` 開頭提到「依種植面積自動供應」，但同文件與 spec 的資源競爭、配額順序交由 Core。此次以 spec 4.0 的明確 adapter 計畫為準；沒有 plan／allocation 就不自動分配。所有算術係數照 world v0.12，沒有重平衡。

既有 `.env` 的 `PARAMETER_PROFILE=scientific` 已遷移為 `world_v0_12`，程式比較確認其餘 setting 值保持一致。現有 key 有設定且通過 provider 實測，未输出或互相代用。其餘新增設定從 loader 的明確預設值讀取；`.env.example` 中 key 為空。

OpenAI GPT-6 的首次工具呼叫收到 HTTP 400：此模型目前 reasoning 工具流程要求 Responses API。已使用 Responses function_call／function_call_output，並完成實際 live 候選核算。OpenRouter LLM 使用獨立 Chat Completions 路徑；不以 key 前綴推斷協定。官方 Voyage query/document adapter 未做遠端驗證。

本模組只有明確排程的單 tick 純函式核算。作物採收／清除／播種仍由世界執行；不預支食物、不推進時鐘，也不自動釋放作物工作者。crop_operation_order 的人員、占用、引用有 schema 驗證；能明確判斷死亡地塊不可採收時附註，其餘連鎖操作交世界驗證。

死亡階段內跨 crew／資源微順序未定。本模組回全部可判定致命條件與最早階段，fatal phase 不發布已提交的完整扣款 ledger 或完整終止 state。以 Fraction 計算，JSON 只在輸出時轉 float；Core 若輸入有限小數，按輸入的十進位值判定，不用 epsilon 改動等號死亡。

schema2.0 是本專案 adapter DTO，正式 Core／世界欄位映射尚待對齊。Core 必須在採用前核對最新 state_id／tick。LAN 沒有第二台設備驗證；localhost 成功不表示 LAN 可達。本次未部署公網、未更改防火牆、未通知隊友。

API 不自動下載或建索引；不同 policy／模型／維度／corpus mapping 的 dense 索引拒絕載入。immutable generation + atomic current pointer 防止半套索引被讀取。舊生成目錄可供人工回溯；active chunk_ids 僅含當前 corpus，已刪除 chunk 不參與檢索。
