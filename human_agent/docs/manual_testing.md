# Core 討論適配更新（2026-09-12）

最新版完整操作請看 [START_TESTING.md](START_TESTING.md)：Swagger 可直接選範例，`discussion_client.py` 支援保存回覆及三輪討論。以下兩輪耗時為前次紀錄；最新 130 測試及三輪 Live 結果見 [validation_report.md](validation_report.md)。

重啟服務後，在 `/docs` 選 `POST /discuss`，先貼 `examples/discussion_requests/core_original_human.json`，預期 200，會揭露存活未知，沒有 plan 也可正常討論。再貼 `with_plan.json` 測完整候選；該例採 planning，符合討論期間世界暫停。Human 不自行恢復世界。

`normal.json` 仍送 `/human-agent/analyze`。回應 power 的換算為 1 EU = 3.9745 kWh；第三次失灌應看到 unsafe_in_scope 與植物 critical，不能把它當成原計畫安全或全員死亡。第二次失灌為 critical 但 will_die=false。

本次 Live 原始請求／首輪／追問耗時約 25.05／28.71／34.46 秒；完整請求與結果在 `examples/discussion_responses/live/`。第二輪請沿用該次回覆的 message_id、proposal_id、discussion_id、world_version。

# 人工 live 測試

目前 `.env` 已由使用者設為 live，本次沒有改寫任何設定或金鑰。請在專案根目錄執行；不需要重新建索引。

## 1. 啟動

```powershell
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

若8000已有你先前啟動的Human服務，先在它的終端按Ctrl+C，再執行上述命令，讓服務載入新程式。本次自動測試使用臨時port，結束後均已關閉。

另開終端：

```powershell
Invoke-RestMethod http://127.0.0.1:8000/health
```

預期 `configured_mode=live`、`dense_loaded=true`、`bm25_loaded=true`、`missing_setting_names=[]`。若不是live，檢查該終端是否有舊的 `AGENT_MODE` 環境變數蓋過 `.env`，清除舊override後重啟服務。health不會額外呼叫付費模型。

## 2. 跑六個情境

```powershell
python examples/brain_client.py --all
```

每筆輸出都會列HTTP狀態、execution_mode、analysis_status、critical數與JSON檔案位置。人工結果在`examples/manual_responses/`，可以直接用編輯器開啟。

| 情境 | 應觀察的重點 |
| --- | --- |
| normal | live；next_tick_audit.status=feasible_in_scope；公共water3000、food120000、power6552、oxygen約8020.0333；核算僅到灌溉後、作物操作前 |
| critical | live；base階段fatal；同人無法同tick吃與喝，不能假造救援；後段not_reached |
| oxygen_early | live；base階段缺氧fatal；不拿後面的植物產氧救回 |
| refill_competition | live；依Core順序crew-2先取得食物；crew-1實轉0仍占用工作；檢查候選audit而非只讀reason |
| irrigation_third_failure | live；plot-1為plant_dependency critical；不得把LLM候選當成自動更改灌溉 |
| partial | live＋partial；next_tick_audit=null；已知個人餘裕仍存在，無verified完整計畫 |

`retrieval.actual_mode=mixed` 是預期的dense＋BM25正常結果，不代表故障。`critical`表示遊戲風險，`partial`表示輸入資訊不足，都不是HTTP服務失敗。建議條數與方案可因LLM而不同，不要要求逐字相同。

如果 `execution_mode=degraded`，先看warnings；provider暫時錯誤或總deadline仍可能發生。原baseline與critical應保留。不要只因HTTP200就把建議視為通過。

## 3. 用 Swagger 修改輸入

瀏覽 `http://127.0.0.1:8000/docs`，展開POST `/human-agent/analyze`，按Try it out，把`examples/requests/normal.json`的完整內容貼入，再修改個人存量／任務。每人只能一個任務，補給任務須同步更新refill_order。

想只看固定核算，設 `analysis.include_recommendations=false`；預期execution_mode=deterministic、retrieval=not_used，不呼叫LLM／embedding。

可以把schema_version改成1.0、把for_tick改成2（tick仍0）、或重複crew_id，確認回422。不要把真實key貼進request body。

## 4. Core／區網

`examples/brain_client.py`提供map_core_snapshot、validate_response_identity及response_is_current，已做本機契約測試。Core採用前需用最新state_id／tick再次檢查；即使此HTTP回應自身識別相符，等待LLM期間世界也可能已產生新快照。

第二台電腦測試時，在服務電腦改以 `--host 0.0.0.0` 啟動，對方執行：

```powershell
python examples/brain_client.py --fixture normal --url http://服務電腦的LAN_IP:8000
```

先確認兩台在同一區網及作業系統允許該port。本次未修改防火牆，也沒有第二台電腦，因此跨機LAN及正式Core／世界API仍須現場確認。不要把0.0.0.0當成用戶端目標位址。

## 已完成的自動驗證

- 86個單元／契約測試通過。
- BM25與目前混合檢索各10/10。
- 六個live HTTP情境全部通過，約5.5–23.3秒，無warnings。
- 兩個並行live請求通過，約18.6–19.3秒；每個embedding_calls=1、cache_hits=0，互不累加。
- 全部live回應的固定核算欄位均與deterministic baseline比對一致；錯版與壞JSON實際回422。
