# Human Agent

## 第一次從 GitHub 取得（隊友測試）

以下 PowerShell 命令會建立獨立 Python 環境。`.env.example` 預設 mock，**不用金鑰即可啟動與測試 API**；mock 驗證規則與接口，不代表遠端 LLM 語意分析。

```powershell
git clone https://github.com/lic924/human-agent-api.git
cd human-agent-api
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
if (-not (Test-Path .env)) { Copy-Item .env.example .env }
.\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

開啟 http://127.0.0.1:8000/docs，選 **POST /discuss → Try it out → Examples「正常：使用 current_plan 核算」→ Execute**。另開同目錄終端可跑：

```powershell
.\.venv\Scripts\python.exe examples/discussion_client.py --fixture current_plan --rounds 3
.\.venv\Scripts\python.exe -m pytest -q
```

macOS／Linux 建立同樣的 `.venv` 後，將上述 `.\.venv\Scripts\python.exe` 改成 `.venv/bin/python`，以 `cp -n .env.example .env` 建立設定。已有本倉庫的隊友使用 `git pull --ff-only` 更新，再重新安裝 requirements 並重啟服務。

要測 **Live**，在自己的 `.env` 設定 `AGENT_MODE=live`，填入自己的 `LLM_API_KEY` 與 `EMBEDDING_API_KEY`；provider、base URL、model 必須與該金鑰可用服務一致。現有模型設定只是範本，不會授予模型使用權；不要共用或提交金鑰。修改模型／embedding 設定前請閱讀下方索引相容要求。

倉庫已包含原始文獻、393 chunks、BM25 metadata 與 dense 索引。一般啟動只載入，不需下載 PDF 或重新付費建索引；API query 快取、`.env`、`.tmp`、虛擬環境與個人人工回覆不在 Git 中。自動驗收回覆保留供比對。

## 專案與現有驗證

獨立、唯讀的 Human Agent，使用 world v0.12 與 Human API schema 2.0。分析四人的個人能量／水、公共資源、人力占用與下一 tick 計畫；核算範圍到灌溉結束、作物操作開始前。沒有世界 step API，也不實作 Core、Plant、前端或完整 Simulator。

**開始人工測試請看 [START_TESTING.md](docs/START_TESTING.md)。** 本版依 Core 已接受的 [整合契約](docs/core_handoff_alignment.md) 交付；Swagger `/discuss` 可直接選擇有效範例，亦可用 `python examples/discussion_client.py --fixture current_plan --rounds 3` 測三輪並存檔。服務需先啟動。

## 啟動

在專案根目錄使用 Python 3.11+；本次實際環境為 Python 3.14.0。依賴版本列於 `requirements.txt`。

```powershell
python -m pip install -r requirements.txt
# 只有不存在 .env 時才建立；既有 .env 不要覆蓋
if (-not (Test-Path .env)) { Copy-Item .env.example .env }
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

目前使用者的 `.env` 已設為 `AGENT_MODE=live`，本次修正沒有改寫 `.env`。`.env.example` 仍預設 mock；mock 不連 LLM 或 embedding，但使用真實遊戲規則與本機 BM25。`PARAMETER_PROFILE` 必須是 `world_v0_12`；`scientific`、`demo` 或其他 rules hash 會明確報設定錯誤。設定 loader 以專案位置找 `.env`，環境變數優先，不受呼叫 cwd 影響。

另開終端：

```powershell
python examples/brain_client.py --all
```

健康檢查：`http://127.0.0.1:8000/health`；Swagger：`http://127.0.0.1:8000/docs`；機器契約：`/openapi.json`。健康檢查只讀設定與本機索引，不付費探測模型。

## Core 串接

`POST /human-agent/analyze`，body 可直接採用 `examples/requests/normal.json`。Core 每次送同時點 `between_ticks` snapshot，明確提供四人工作、補給顺序與灌溉配額；有計畫時 `for_tick=tick+1`。沒有計畫可填 null，Human 會保留可知的個人餘裕並標 partial。

```powershell
$body = Get-Content examples/requests/normal.json -Raw
Invoke-RestMethod -Method Post -Uri http://127.0.0.1:8000/human-agent/analyze -ContentType 'application/json' -Body $body
```

`examples/brain_client.py` 僅透過 HTTP 存取服務，包含 `map_core_snapshot()` 的明確欄位映射範例。回應會檢查 schema、rules version、request_id、state_id、tick 與 for_tick；Core 在真正採用前再以 `response_is_current()` 檢查最新 state。這些 adapter 行為已測試，正式 Core／世界欄位仍待隊友提供。人工呼叫的回應存於 `examples/manual_responses/`，不覆寫自動驗收紀錄。

HTTP 200 可能是 complete、partial、critical 或 degraded；請檢查 `execution_mode`、`next_tick_audit.status`、`fatal_conditions`、`risks` 與 `coverage_end`。422 是 schema／版本／計畫錯誤。500 只回錯誤類型與 request_id，不回秘密或 traceback。

## Live

本次實測使用 `.env` 中的 `openai_compatible / gpt-6-astra`（OpenAI Responses API 工具呼叫）與 `openrouter / voyageai/voyage-4`（1024 維、`unspecified` policy）。OpenRouter LLM 維持 Chat Completions 協定。官方 Voyage adapter 支援 `query_document` policy，但未做官方 Voyage 真實呼叫。

```powershell
python scripts/check_providers.py
# 不改寫 .env，即可在此終端啟用 live
$env:AGENT_MODE = 'live'
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
# 回 mock：停止服務後 Remove-Item Env:AGENT_MODE，再重啟
```

所有 LLM／embedding／工具共用最多 45 秒，保留 1 秒組裝 JSON；最多 4 次 LLM、8 次工具。429／暫時 5xx 最多重試 2 次；401 不重試。HTTP 請求以 async timeout 取消；取消不保證 provider 不計費。失敗保留原 deterministic baseline，標 degraded。缺 key 時回報 `LLM_API_KEY`／`EMBEDDING_API_KEY` 等欄位名，沒有 key 互相代用。

LLM 最多提供三條建議。補給、發電與製水候選須通過固定快照核算才能有 `expected_effect`；不允許改寫原本的作物工作、灌溉或作物操作順序。LLM 可用 `audit_result_id` 引用已核算候選，後端補回完整 plan 與 audit，避免重複傳送。公開 `reason` 由規則與核算組裝，不將 LLM 自由文字當成事實。`evidence.reviewed_claims` 只包含已對原文文字核對且 hash 相符的核心結論；其他原文仍是未全面語意核對的背景證據。文件不是指令。`analysis.include_recommendations=false` 可完全跳過 LLM 與動態檢索。

`diagnostics.embedding_calls` 與 `cache_hits` 為每個請求獨立的 ContextVar 計數，即使共用 client／query cache 也不會互相計入。兩個並行 live 請求已實測；這不是任意高並行負載的保證。

## 文獻與索引

現有交付含 5 份 NASA 原始 PDF、來源 SHA-256 manifest、選定相關頁面的原文 extraction、393 chunks、BM25 與 Voyage dense 索引。科學資料狀態是 partial；遊戲規則完整性與研究狀態分開。完整 PDF 在本機，不代表所有頁面皆已納入索引或逐頁科學核對。

```powershell
# 只處理已下載原文；缺原文時非成功退出
python scripts/prepare_corpus.py --local
python scripts/build_index.py --mode bm25
python scripts/build_index.py --mode both --offline
# 有缺少的向量時，此命令才使用 API，按 text hash 重用 cache
python scripts/build_index.py --mode both
# 只有真的缺原文才執行明確下載命令
python scripts/acquire_sources.py
```

索引原子發布於 `data/index/generations/<generation>/`，內有 `vectors.npy`、`chunk_ids.json`、`index_metadata.json`，`current.json` 是原子切換指標。API 啟動只載入，絕不自動下載或付費建索引。cache 包含 provider、model、dimensions、policy、preprocessing 與實際 text hash。變更 policy 必須重建相容索引。`--offline` 沒有完整 cache 時不能建立 dense，回非零退出狀態；BM25 不受影響。

目前 corpus：`corpus-4c40231326d1bc2b`；dense index：`index-26765ae220846386`。本次重用所有原文與向量，沒有重新嵌入 corpus。設定 `RETRIEVAL_MODE=dense` 搭配 `RETRIEVAL_FALLBACK=bm25` 時，正常檢索也使用 RRF 合併兩種排名；明確數字以原文完整 token 命中優先，回 `actual_mode=mixed`、`ranking_method=rrf_with_numeric_anchors`，不是 degraded。单純 dense 模式仍可設 fallback=none，但無混合檢索補強。新 query 仍可能需要網路 embedding；mock 使用本機 BM25。真正的 provider／索引故障仍如實降級。

## 驗證

```powershell
python -m pytest -q
python scripts/eval_retrieval.py --mode bm25
python scripts/eval_retrieval.py --mode dense
python scripts/http_smoke.py
python scripts/http_smoke.py --live --all
python scripts/http_smoke.py --live --concurrent
python scripts/export_schema.py
```

最新：86 passed；6/6 live HTTP情境通過，約5.5–23.3秒；另2/2並行live請求通過，約18.6–19.3秒，均無degraded或warnings。BM25 10/10、目前設定的dense＋BM25混合檢索10/10，原先3.217精確數值問題已修正。這是原文關鍵詞／分流驗收，不是任意科學敘述的entailment認證。詳見 `docs/validation_report.md`、`docs/retrieval_eval.md`，人工測試步驟見 `docs/manual_testing.md`。

`examples/responses/` 與 `examples/live_responses/` 都是實際 HTTP 產物。完整正常案例的公共 water=3000、food=120000、power=6552、oxygen≈8020.033333；個人 energy=2172.75。critical 案例在 base 階段停止，沒有假造完整死亡末端 state。

## 待對齊與限制

- Core handoff v1.3 原始請求可直接送 `/discuss`；alive 選填並保留未知，討論期間缺省 planning，snapshot_phase 由轉接層處理。正式未知 plan 格式與死亡微順序仍待聯測，詳見下方交接文件。
- LAN 未由第二台電腦驗證。需對外區網服務時綁定 `--host 0.0.0.0`，Core 填服務電腦的實際 LAN IP，不能填 `0.0.0.0` 或自己電腦的 `127.0.0.1`。
- PDF 部分旋轉文字 extraction 不完整，印刷頁號只在參數審查的核心定位人工確認；圖表與其餘文獻尚未逐頁核對。
- 已修正本次驗收的精確數字檢索與公開理由的無依據敘述；原始 corpus 仍未逐頁認證，只有列在 reviewed_claims 的有限結論經本次原文文字核對。規則計算不依賴科學向量命中。

## Core handoff v1.3

新增 `POST /discuss`，供 Core 討論訊息直接呼叫。Human 負責適配，必要事實才請 Core 釐清；對齊結果、可選計畫、錯誤與操作步驟見 [Core交接對齊文件](docs/core_handoff_alignment.md)。原 `/human-agent/analyze` 繼續提供 Human API 2.0。

服務重啟後可在 `/docs` 貼入 `examples/discussion_requests/core_original_human.json` 測原始 Core 請求；完整候選為 `examples/discussion_requests/with_plan.json`。缺 alive 仍回 200 並揭露未知，不能宣稱計畫已驗證。討論期間世界暫停，Human 不自行暫停或恢復世界。

使用者確認 `1 EU = 3.9745 kWh`，換算設定見 `data/unit_conversions.json`；輸入 power 仍為 EU，回覆附換算依據。第三次失灌的 audit 新增 `unsafe_in_scope`，與人員死亡的 `fatal_in_scope` 區分。

```powershell
python scripts/discussion_smoke.py
python scripts/discussion_smoke.py --live
```

本次最新單元／契約測試 **130 passed**；原始 Core 請求及三輪 Live HTTP 均 200，約 **22.69／28.53／31.75／34.13 秒**，第二／三輪各有 2／3 項有效前輪評論。Core 11 情境與原 Human 六情境 mock HTTP 亦通過。這是本機轉接＋真實模型驗證，尚未連到隊友 Core／Plant 服務或第二台電腦。
