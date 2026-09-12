# 2026-09-12 Core 接受契約後的交付驗證

- 全套：`python -m pytest -q -p no:cacheprovider --basetemp .tmp/human-delivery-20260912-01`，130 passed，13.26 秒。
- 新增 Swagger 六份 request 範例可實際進入 API；獨立 discussion_client 驗證三輪、同一 world、真實歷史引用，拒絕錯版本、錯型別、重複 ID 及無法解析的提案引用。
- `python scripts/discussion_smoke.py --all`：11 個 mock HTTP 案例均通過（原始請求、三輪、current_plan、critical、oxygen_early、refill_competition、第二／第三次失灌、already_failed）。
- `python scripts/http_smoke.py --all`：原 Human 六種 mock HTTP 皆通過。
- `python scripts/discussion_smoke.py --live`：原始請求 22689.34 ms，三輪各 28532.88／31750.36／34134.57 ms，全部 HTTP 200、live、低於 45 秒；每輪一項候選，第二／三輪分別 2／3 項有效 reviews。
- 人工 CLI 另以獨立 localhost 服務實跑三輪，HTTP 200，確認保存 3 份 request、3 份 response、3 份 metrics，UTF-8 中文輸出無替代字元。結果見 `docs/manual_client_http.json`；此 CLI 與 Core 呼叫範例不 import app。
- `python scripts/export_schema.py`：已匯出含有效 Swagger 範例的 OpenAPI 與 request／response schemas。
- 實際 Live 回覆與第三輪請求存 `examples/discussion_responses/live/`；報告 `docs/discussion_http_live.json`。先前報告的「兩輪最新耗時」屬歷史，以上述本次結果為準。
- 未宣稱完成：真正 Core／Plant／世界服務及 LAN 聯測。Plant 歷史訊息仍是明示測試 fixture，LLM reviews 則為本次真實呼叫結果。使用既有 .env、corpus、索引，未重新下載或整批重嵌入。

# 2026-09-12 Human 配合 Core 的前次驗證

- `python -m pytest -q -p no:cacheprovider --basetemp .tmp/human-core-compat-20260912-02`：122 passed，10.61 秒。
- 新覆蓋：原 Core 請求、unknown alive 不誤判可行、明確死亡、planning 缺省、current_plan 映射與過期／衝突、schema 本地引用及註解相容、規則 metadata／文字語意／係數差異、EU 精確雙向換算、第二／第三次失灌。
- `python scripts/http_smoke.py --all`：原 Human 六種 mock HTTP 情境均 200、驗收通過，原 normal 資源核算不變。
- `python scripts/discussion_smoke.py`：原始 Core 請求＋兩輪 mock HTTP 均 200，前輪引用檢查通過。
- `python scripts/discussion_smoke.py --live`：原始請求 25046.21 ms、第一輪 28705.36 ms、第二輪 34460.77 ms，均 200 且低於 45 秒；兩輪各有一項候選，第二輪兩項 reviews 引用有效。
- Live 原始請求保留「存活未知」，沒有標成 verified_for_audited_scope 的安排。完整計畫測試使用 planning；Plant 前輪訊息為明示的測試 fixture，並非呼叫真正 Plant 服務。
- 已匯出更新的 request／response schemas 與 OpenAPI。重用原 corpus／index，未修改 .env；本次未重跑文獻檢索評分或所有舊 Live 邊界案例。
- 證據：`discussion_http_live.json`、`discussion_http_mock.json`、`../examples/discussion_responses/`、`../examples/responses/`。
- 未完成外部驗證：Core 實際接收器、尚未提供的正式 plan DTO、世界共享發電／死亡微順序差異測試、第二台設備 LAN。

以下為先前驗證紀錄；與本次狀態衝突時以上述結果為準。

# 本次執行驗證（2026-09-12）

## 最新 live 修正驗收

已完成此次已知程式問題修正，`.env`保持使用者設定的live且檔案內容未改寫。詳細人工操作見 `manual_testing.md`。

| 檢查 | 最新實際結果 |
| --- | --- |
| 全部單元／契約測試 | `python -m pytest -q`：86 passed，5.14秒 |
| BM25檢索 | 10/10 |
| dense＋BM25混合檢索 | 10/10；明確標mixed，原3.217數值題已命中 |
| 六種live HTTP | 6/6通過，無degraded、無warnings |
| 兩個並行live HTTP | 2/2通過，各自1次embedding、0次cache hit，無交叉累計 |
| HTTP錯誤契約 | 錯schema版本、壞JSON回422；OpenAPI可讀 |
| LLM不可改核算 | 每個live response的個人／公共／人力／audit／risks均比對原baseline一致 |

六種live耗時：normal 23.301秒；critical 16.282秒；oxygen_early 6.015秒；refill_competition 17.652秒；irrigation_third_failure 12.961秒；partial 5.500秒。結果在 `http_validation_live_all.json` 與 `../examples/live_responses/`。兩個並行live耗時18.551、19.276秒，結果在 `http_validation_live_concurrent.json`。單次成功不保證provider永不timeout；degraded保留baseline的行為仍由故障測試驗證。

已修正：RRF混合檢索與完整數字token錨點；ContextVar隔離各請求統計；取消後清理context；LLM以audit_result_id引用完整候選，縮短重複JSON；公開reason由規則與核算組裝，有限科學結論綁定原文hash；Core client核對全部識別與採用前過期檢查。最新JSON Schema與OpenAPI已輸出。

尚需外部配合：正式Core／世界實際DTO與世界引擎差異測試、第二台電腦的LAN連線；未取得這些外部介面，因此不假稱已驗證。其餘PDF仍不是逐頁科學認證；服務只把reviewed_claims中的有限結論標作已核對。

最後交付檢查：`.env`整檔SHA-256與本輪開始時一致，仍為live；70個程式／文件／驗收文字檔未包含既有API key；8個儲存的live responses全數通過目前Pydantic schema。修改後的`examples/brain_client.py`也另外對臨時localhost mock服務做真實HTTP呼叫，health正常、normal HTTP200，回應存於`examples/core_client_smoke/normal.json`。所有由測試啟動的服務均已停止，未中斷使用者自行啟動的服務。

以下保留重建與修正前的執行歷史；其中68 passed、9/10與「尚未修正並行統計」均已被上述最新結果取代。

## 修正前歷史

環境：Windows、Python3.14.0；依賴使用本機已安裝版本並精確列於 requirements.txt。没有繼承舊38 passed或世界7,200tick的結果。

| 執行 | 結果 |
| --- | --- |
| `python -m pytest -q` | 68 passed，3.83秒，最終無 warning |
| `python scripts/prepare_corpus.py --local` | 5份原文、393chunks；旋轉文字抽取有警告，研究狀態partial |
| `python scripts/build_index.py --mode bm25` | 成功 |
| `python scripts/build_index.py --mode both` | 393筆1024維Voyage向量，66個batch，成功 |
| `python scripts/build_index.py --mode both --offline` | 成功，embedding_batches=0 |
| `python scripts/check_providers.py` | embedding 1024維、gpt-6-astra基本呼叫皆成功 |
| `python scripts/eval_retrieval.py --mode bm25` | 10/10 |
| `python scripts/eval_retrieval.py --mode dense` | 9/10、exit2；水3.217精確數值top-5未命中 |
| `python examples/brain_client.py --all` | health與6個情境HTTP200，response實際寫檔 |
| `python scripts/http_smoke.py --live` | HTTP200，execution_mode=live，dense，1條有核算的候選，無warnings |
| `python scripts/export_schema.py` | request/response JSON Schema、OpenAPI輸出完成 |

測試涵蓋 T01–T29 的核心情境與新增邊界。T12、T13、T14 明確使用階段開始值；其他完整tick測試含base扣款。T25驗證假引用、改state／rules欄位、作物占用與無核算候選拒絕。T26涵蓋401不重試、429/5xx最多兩次重試、無效JSON、timeout取消、missing/stale index及無BM25。T27實際測試未改原文0次嵌入、改1段只嵌1段、刪除不留active mapping、不同維度拒混用且舊active pointer不被失敗覆寫。

首次測試碰到pytest跨帳號暫存權限，擴權後通過；pytest cache權限warning以停用非必要cache provider處理。第一次live工具呼叫返回400，修正OpenAI adapter為Responses後成功；沒有把最初失敗計為live成功。

正常 T29 的實際結果：每人food_energy=2172.75、water=1.3659583333333334；公共water=3000、food=120000、power=6552、oxygen=8020.033333333334；灌溉174L／100EU／304OU。核算coverage_end=`after_irrigation_before_crop_operations`。

Critical情境某人energy100、水0.1，安排eat後仍水不足，在base標fatal；後續generation、water_production、irrigation為not_reached，known_after_values=null。植物第三次失灌為plant_dependency critical，但不假設crew因此直接死亡。

Live正常情境實際耗時27558.19ms、3次LLM、1次embedding、3次工具（retrieve_evidence、get_world_rule、audit_human_plan），最後一條候選附audit_result_id。證據：`http_validation_live.json`、`../examples/live_responses/normal.json`。Mock實際資料在`../examples/responses/`。

未測／未完成的外部項目：正式世界引擎差異測試、正式Core工具payload、LAN第二台設備連線、官方Voyage直連與OpenRouter LLM實際呼叫、PDF逐頁視覺核對與完整科學語意支持審查。Dense精確數字題仍有1題失敗。服務從未執行世界操作或多tick Simulator。

最後重跑6個mock HTTP情境仍全數200；生成程式、文件與response共56個文字檔檢查未含既有API key，.env.example的key皆為空。測試啟動的localhost服務均已關閉，可依README自行啟動。

後續 live 就緒性複查：再次執行 `python scripts/http_smoke.py --live`，HTTP200、execution_mode=live、dense檢索、3次LLM、1次embedding、3次工具、1條已核算候選，32717.51ms，warnings為空。最新JSON已保存；`.env`維持mock，未改寫金鑰。仍只完成normal的實際live驗證，其餘五種情境的實際HTTP結果為mock。

本次檢查另發現：embedding diagnostics目前以共享client累計數的差值計算；並行請求時可能把其他請求的呼叫／cache hit計入，需改為每請求獨立統計並補並行測試。這不會改動deterministic資源核算，但尚未修正，不能宣稱並行diagnostics已驗證。
