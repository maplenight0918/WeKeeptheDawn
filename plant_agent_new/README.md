# Plant Agent API

依 `docs/SPEC.md` 從資料包重建。API 使用 numpy、FastAPI、uvicorn；HTTP 使用標準庫 urllib。

## 從 GitHub 取得後的準備

此 repository 不包含大型文獻索引、金鑰或本機虛擬環境。請從 [索引資料 Release](https://github.com/benson103081/plant-agent-api/releases/tag/index-v1) 下載 `plant-agent-index-v1.zip`，在 Plant 專案根目錄解壓，得到 `data/index/chunks.jsonl`、`data/index/embeddings.npy`、`data/index/ids.json`。ZIP已包含 `data/index/` 層級，不要再解壓到該子目錄。檔案大小與 SHA-256 見 `data/index-manifest.json`。缺少索引時 API 無法啟動；不可混用其他 embedding 模型產生的向量。

### 下載與核對索引

附件約271 MB（259 MiB），解壓約371 MB（354 MiB），請預留至少650 MB空間。請下載 Release 的 **plant-agent-index-v1.zip**，不是 GitHub 自動產生的 Source code.zip。

macOS / Linux，在專案根目錄執行：

```bash
curl -L --fail -o plant-agent-index-v1.zip https://github.com/benson103081/plant-agent-api/releases/download/index-v1/plant-agent-index-v1.zip
unzip plant-agent-index-v1.zip -d .
```

Windows PowerShell，在專案根目錄執行：

```powershell
Invoke-WebRequest -Uri "https://github.com/benson103081/plant-agent-api/releases/download/index-v1/plant-agent-index-v1.zip" -OutFile "plant-agent-index-v1.zip"
Expand-Archive -Path plant-agent-index-v1.zip -DestinationPath .
```

若整合專案將本服務放在 `plant_agent/`，就在該目錄執行，結果應為 `plant_agent/data/index/...`。

壓縮包SHA-256：`ab818de08fc96c585015368494311176ead3e3a68e5a0f5ea196f764ce92efd7`。三個解壓檔的完整性可在安裝Python後檢查：

```bash
python3 scripts/verify_index.py
```

Windows使用 `python scripts/verify_index.py`。此檢查只用Python標準庫，不呼叫網路或付費API。

macOS / Linux 首次安裝（需要 Python 3.10 以上）：

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
cp .env.example .env
```

在自己的 `.env` 填入自己的 OpenRouter 金鑰。不要提交 `.env`，也不要將金鑰寫在原始碼、issue 或截圖內。`/analyze`、`/discuss` 會將檢索出的論文段落與情境參數送至 OpenRouter 及模型供應商，並產生 API 使用費用。

macOS / Linux（本機已建立 `.venv`）：

```bash
.venv/bin/python -m uvicorn src.api.main:app --port 8000
```

Windows（重新建立該平台的虛擬環境）：

```powershell
$env:PYTHONUTF8 = "1"
python -m venv .venv
.venv/Scripts/python.exe -m pip install numpy fastapi uvicorn
Copy-Item .env.example .env
.venv/Scripts/python.exe -m uvicorn src.api.main:app --port 8000
```

API 文件：<http://127.0.0.1:8000/docs>。

`POST /simulate`、`POST /sweep`、`GET /world/crops`、`GET /health` 都是本地運算。
`GET /search`、`POST /analyze` 與 `POST /discuss` 需要在 `.env` 填入有效的 `OPENROUTER_API_KEY`，修改後重啟服務。
不會以假資料替代網路服務；金鑰缺少、上游 HTTP 錯誤會回 503；`/discuss` 超過42秒回504。

`/simulate` 與 `/analyze` 的 JSON 輸入預設為 lettuce、20 m²、PPFD 250、14 h、22°C、65% RH、500 ppm CO₂、27 plants/m²，無電力預算。
`/sweep` 比較未限電的各光照點，以原始請求 PPFD 為首列基準；傳入的 `power_budget` 不套用至掃描表。
`/world/crops` 回傳 `conditions`、`crops`、`note`。每種作物有 `edible_g_m2_day`、`o2_g_m2_day` 與係數出處；僅供數字來源說明。

驗證：

```bash
.venv/bin/python -m unittest discover -s tests -p 'test_*.py' -v
# 先啟動 API，再執行：
.venv/bin/python tests/acceptance_http.py
```

HTTP 驗收原始結果写入 `docs/acceptance_results.json`。腳本輸出的 HTTP 503 代表網路項目受阻，不能視為驗收通過。
詳見 [驗收與假設](docs/IMPLEMENTATION_REPORT.md)。


## Plant 與 Core 的交接補充

討論介面與最新耗電口徑見 [DISCUSS_HANDOFF.md](docs/DISCUSS_HANDOFF.md)。Plant預設20 m²的每日用電為79.49 kWh（總功率×24保守估算）；世界每塊5 m²，20塊共100 m²。電量顯示EU，1 EU=3.9745 kWh，電力每tick按1小時計算；不可把每塊約5 EU/day誤作5 EU/hour。此補充不表示世界後端已改用新數值。
