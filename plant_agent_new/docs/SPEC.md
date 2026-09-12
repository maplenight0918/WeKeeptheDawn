# Plant Agent 復現規格書

> **用途**：黑客松現場不得攜帶預先寫好的程式碼。這份文件是**規格**不是程式——把它貼給 AI 助手（Codex / Claude / Cursor），或照著手寫，都能重建整條管線。
>
> **設計原則**：不綁特定廠商。Embedding 與 LLM 都只在一個地方指定模型名，換供應商只改那一行。

---

## 0. 現場最短路徑

**全部四層已實作完成並實測通過**（見 §11 實作紀錄）。這份文件同時是規格與踩坑紀錄，
現場照著重建即可。

如果時間只夠做一件事，做這個順序：

| 順序 | 做什麼 | 實測耗時 | 沒做會怎樣 |
|---|---|---|---|
| 1 | 載入預先備好的 corpus 與向量（§7） | 5 分 | 要花 3 小時重抓重算 |
| 2 | 檢索層（§5） | 20 分 | Agent 沒有文獻依據 |
| 3 | 物理換算層（§4） | 40 分 | 只有敘述沒有數字 |
| 4 | Agent 推理層（§6） | 40 分 | 退化成查表系統 |
| 5 | FastAPI 端點（§3） | 20 分 | 前端接不上 |

§1、§2 是資料蒐集，**現場不要重跑**——那是 3 小時的事。

實作總量約 1400 行 Python，分四個模組：`src/retrieval`、`src/models`、
`src/agent`、`src/api`。

### 0.1 環境（現場第一件事）

```bash
python -m venv .venv                      # 系統 Python 是 PEP 668 externally-managed，裝不了套件
.venv/Scripts/python.exe -m pip install numpy fastapi uvicorn
cp .env.example .env                      # 填 OPENROUTER_API_KEY
.venv/Scripts/python.exe -m uvicorn src.api.main:app --reload --port 8000
```

- **Python ≥ 3.10**（程式用 `float | None`、`list[str]` 語法；實作環境 3.12）。
- 只依賴 `numpy`、`fastapi`、`uvicorn`；HTTP 一律用標準庫 `urllib`，不裝 SDK。
- **Windows 中文環境要設 `PYTHONUTF8=1`**（或 `PYTHONIOENCODING=utf-8`）。
  預設 cp950 終端印到 `µmol/m²/s` 會 `UnicodeEncodeError` 直接炸掉；
  所有讀寫檔案都明確帶 `encoding="utf-8"`。
- 專案根目錄要有 `paths.py`（`ROOT / data / catalog / index`），
  每個模組開頭 `sys.path.insert(0, parents[2])` 後 `from paths import ...`。

---

## 1. 文獻蒐集（現場不要重跑）

四個來源，各自的 API 特性與踩過的坑。留著是為了萬一 corpus 遺失時能重建。

### 1.1 NASA NTRS — 主力

```
搜尋  GET https://ntrs.nasa.gov/api/citations/search?q="片語"&page.size=100&page.from=N
詳情  GET https://ntrs.nasa.gov/api/citations/{id}
全文  回應的 downloads[].links.fulltext（.txt），不要抓 pdf
```

**三個坑**

1. **官網搜尋框的引號無效**。網站表單送的是 `title` 參數，會把片語拆成 OR——搜 `"plant growth chamber"` 回傳真空艙、晶體成長。只有 API 的 `q` 參數支援片語（同一查詢 total 從 180 縮到 50）。
2. **不要用 Document Type 當搜尋條件**。實測 233 筆 Conference Paper 中只有 11 篇屬 Life Support，最多的反而是固態物理。類型過濾要在拿到結果後做。
3. **會回 429 限流**，被擋的查詢回空結果，會被誤記成 0 筆。必須指數退避重試（5s→10s→20s…），重試耗盡就中止而非記 0。

**片語控制在 2–3 字。** 多概念拼接（`crop transpiration water use`、`energy requirement life support`）必然回 0 筆。

**保留的文件類型**（有完整敘述性內文，可切 chunk）：
`CONFERENCE_PAPER`、`CONFERENCE_PROCEEDINGS`、`REPRINT`、`PREPRINT`、`ACCEPTED_MANUSCRIPT`、`TECHNICAL_MEMORANDUM`、`TECHNICAL_PUBLICATION`、`CONTRACTOR_REPORT`、`CONTRACTOR_OR_GRANTEE_REPORT`、`SPECIAL_PUBLICATION`、`BOOK`、`BOOK_CHAPTER`

**排除**：`PRESENTATION`（最大宗，442 筆中佔 171，條列短句無上下文）、`POSTER`、`ABSTRACT`、`EXTENDED_ABSTRACT`、`VIDEO`、`OTHER`

**27 組片語與實測筆數**（原始／過濾後）：

| 類別 | 片語 | 原始 | 論文 |
|---|---|---:|---:|
| 作物生長 | `plant growth chamber` | 50 | 30 |
| 作物生長 | `Veggie` | 198 | 32 |
| 作物生長 | `crop growth model` | 5 | 5 |
| 作物生長 | `harvest index` | 33 | 26 |
| 作物生長 | `biomass production` | 126 | 93 |
| 作物生長 | `edible biomass` | 40 | 22 |
| 系統循環 | `bioregenerative life support` | 168 | 96 |
| 系統循環 | `CELSS crop` | 6 | 6 |
| 系統循環 | `advanced life support` | 319 | 206 |
| 系統循環 | `closed loop life support` | 85 | 57 |
| 系統循環 | `atmosphere revitalization` | 133 | 93 |
| 系統循環 | `carbon dioxide removal` | 216 | 154 |
| 系統循環 | `oxygen production plants` | 8 | 5 |
| 水 | `transpiration rate` | 4 | 3 |
| 水 | `crop water use` | 2 | 2 |
| 水 | `water recovery` | 484 | 316 |
| 水 | `hydroponic nutrient solution` | 12 | 11 |
| 水 | `nutrient delivery system` | 47 | 27 |
| 能源 | `photoperiod` | 92 | 73 |
| 環境控制 | `controlled environment agriculture` | 38 | 14 |
| 環境控制 | `controlled ecological life support` | 337 | 300 |
| 情境 | `Mars surface habitat` | 16 | 7 |
| 情境 | `salad crop` | 21 | 5 |

零結果的 4 組：`LED lighting crop`、`light emitting diode plant`、`energy requirement life support`、`space food production`。

去重後 **1314 篇論文，861 篇有全文**。

### 1.2 PubMed Central

```
搜尋  GET https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi?db=pmc&term=...&retmode=json
詳情  GET .../esummary.fcgi?db=pmc&id=...&retmode=json
全文  GET .../efetch.fcgi?db=pmc&id={數字}&retmode=xml   ← 一次可帶多個 id
```

無金鑰限 3 req/s。**OA service（`oa.fcgi`）已停用回 404**，但 `efetch` 照樣拿得到全文。

**PMC 也會 OR 展開**，必須用 `[TIAB]` 欄位限定加引號：`MELiSSA` 不限定回 88267 筆（比對到 melissa 這個字），`"MELiSSA"[TIAB] AND "life support"[TIAB]` 只剩 13 筆。

`efetch` 回 JATS XML，**比 PDF 好處理**——不用解析版面，`<sec><title>` / `<p>` 結構直接對應章節與段落。

29 組查詢去重 **1074 篇，1067 篇有全文**。`"water use efficiency"[TIAB] AND "crop"[TIAB]` 原本 762 筆全是地球田間農業，加上 `AND ("controlled environment" OR "greenhouse" OR "hydroponic")` 後降到 263 筆。

### 1.3 MELiSSA Foundation（ESA）

**沒有 API**，只有一份 42 頁書目 PDF：`https://www.melissafoundation.org/download/971`

流程：pypdf 抽文字 → 全文攤平（表格排版會斷行錯位，逐行解析會失敗）→ 正則抓 DOI → 尾端截掉黏住的 `PMID` / `ISSN` / `Epub` 與「年份+作者姓」→ 丟 Crossref 驗證（`https://api.crossref.org/works/{doi}`，能解析的才算有效，順便拿正確 metadata）→ Unpaywall 查開放取用。

**Unpaywall 的 email 參數不能填假值**，填佔位地址會把 59 篇 OA 全部誤判成非 OA。

下載時 MDPI / Elsevier / Wiley 回 **403 擋機器人**。補救：用 NCBI ID Converter（`https://www.ncbi.nlm.nih.gov/pmc/utils/idconv/v1.0/?ids=...&format=json`）把 DOI 轉 PMCID，改走 PMC efetch，救回 14 篇。

79 篇通過驗證 → 19 PDF + 14 經 PMC = 33 篇。

### 1.4 Frontiers in Space Technologies

Crossref 依 ISSN `2673-5075` 抓全刊 168 篇 metadata，關鍵字篩出 17 篇。

全刊規模太小、核心相關僅 5–6 篇，**不值得建管線**，一次性抓完即可。

---

## 2. Corpus 篩選與切 chunk

### 2.1 篩選

掃 1897 篇全文，兩層評分後分四層。全部本機跑，不花錢。

**主題詞**

```
CORE_TOPIC（每個 +2 分）
  plant growth, crop growth, crop production, plant production,
  photosynth, transpiration, edible biomass, harvest index,
  hydroponic, veggie, plant chamber, growth chamber,
  canopy, leaf area, shoot, cultivar, seedling

SYSTEM_TOPIC（每個 +1 分）
  life support, bioregenerative, celss, melissa, closed loop,
  atmosphere revitalization, controlled environment, oxygen production,
  carbon dioxide removal, water recovery, nutrient recovery,
  mass balance, stoichiometric

CROPS（每個 +2 分）
  lettuce, wheat, potato, soybean, tomato, radish,
  spinach, rice, kale, pepper, spirulina
```

**數值單位樣式**（有數字才抽得出係數）

| 標籤 | 找什麼 |
|---|---|
| `ppfd` | `µmol m-2 s-1` 各種寫法 |
| `biomass_rate` | `g m-2 d-1`、`g/m2/d` |
| `harvest_weight` | `dry weight`、`fresh weight`、`dry matter` |
| `yield_value` | `yield` 或 `productivity` 後 60 字元內出現數字 |
| `per_plant_weight` | `g per plant`、`kg m-2` |
| `growth_rate` | `growth rate` 後 60 字元內出現數字 |
| `water_use` | `L/day`、`liters per day` |
| `energy_use` | `kWh`、`kilowatt` |
| `gas_exchange` | `µmol CO2`、`mmol m-2` |
| `photoperiod` | 數字 + `h light` / `h photoperiod` |
| `nutrient_solution` | `dS m-1`、`mmol L-1` |
| `co2_ppm` | 3–4 位數 + `ppm` / `µmol mol` |
| `temperature` | 數字 + `°C`（可帶 ±） |

**關鍵發現**：論文習慣報「單次收穫乾重／鮮重」而非每日速率。只比對 `g m-2 d-1` 只找得到 27 篇；把 `harvest_weight`、`yield_value`、`per_plant_weight`、`growth_rate` 一併算成產量證據後，涵蓋率從 19 篇跳到 916 篇。除以生長天數就能換算。

**分層規則**

```
topic = core*2 + len(crops)*2 + system
has_yield = 命中任一產量訊號

A_plant_core        core>=3 且 單位種類>=3 且 has_yield
B_usable            core>=2 且 單位種類>=3
                    或 (core>=1 或 topic>=6) 且 單位種類>=2
C_system_peripheral topic>=3
D_excluded          其餘，或全文 < 3000 字元
```

**結果**

| 層 | 篇數 | NTRS | PMC |
|---|---:|---:|---:|
| A_plant_core | 638 | 97 | 541 |
| B_usable | 383 | 151 | 232 |
| C_system_peripheral | 521 | 363 | 158 |
| D_excluded | 355 | 210 | 145 |

**A+B 共 1021 篇入庫**，其中 916 篇（90%）有產量證據。

**清資料**：86 個 NTRS「全文」其實是 HTML（VEG-04 ISS 太空作物飛行測試等真論文包在標籤裡）。去標籤保留，不要直接刪。

### 2.2 切 chunk

```
TARGET   = 1400 字元（約 350 token）
OVERLAP  = 200 字元
MIN      = 300 字元，更短的碎片丟掉
```

優先沿 `## 章節` 邊界切（PMC 的 JATS 轉檔保留了結構），章節過長再按段落累積。NTRS 純文字沒有章節，直接走段落路徑。單一超長段落按句子硬切。

**跳過參考文獻段落**：`references`、`bibliography`、`acknowledg`、`author contributions`、`conflict of interest`、`supplementary`、`funding`、`abbreviations`——沒有推理價值。

**每個 chunk 的 metadata**（全用英文 key，Brain Agent 要吃）

```json
{
  "id": "PMC:PMC5302746:12",
  "text": "...",
  "source": "PMC",
  "doc_id": "PMC5302746",
  "title": "...",
  "year": "2017",
  "tier": "A_plant_core",
  "section": "Materials and Methods",
  "crops": ["lettuce", "wheat"],
  "units": ["ppfd", "harvest_weight", "temperature"],
  "chars": 1387
}
```

`units` 讓檢索能優先撈「真的有數字」的段落——這是這套設計的關鍵。

1021 篇 → **64160 chunks**（平均 62 / 篇），約 26.6M token。

---

## 3. API 介面

四個端點。**`/simulate` 與 `/analyze` 分開是刻意的**——前端拖 slider 時需要即時
反應，但完整 Agent 推理要 40 秒。拖動時打 `/simulate`（17 ms），放開後再打
`/analyze` 拿 citations 與敘事。

| 端點 | 用途 | 實測耗時 |
|---|---|---|
| `POST /simulate` | 純計算，係數用 corpus 中位數，不呼叫 LLM | 17 ms |
| `POST /analyze` | 完整 Agent 推理 | 36–48 s |
| `POST /sweep` | 掃不同光照的 trade-off 表 | 16 ms |
| `GET /search` | 直接查 corpus，做「這數字哪來的」展開檢視 | 1 s |
| `GET /health` | 存活檢查與已載入的 chunk 數 | — |

啟動時載入 251 MB 向量進記憶體，約 1 秒。用 FastAPI 的 `lifespan` 載入一次共用，
不要每個請求重讀。

### Input

```python
class PlantAgentInput(BaseModel):
    crop: Crop           # Literal，11 種作物
    ppfd: float          # µmol/m²/s   ge=0  le=2000
    photoperiod: float   # h/day       ge=0  le=24
    temperature: float   # °C          ge=-10 le=60
    humidity: float      # %           ge=0  le=100
    co2: float           # ppm         ge=100 le=5000
    area: float          # m²          gt=0  le=10000
    density: float       # plants/m²   gt=0  le=500
    power_budget: float | None  # kW   留空表示不限
```

範圍取自 corpus 實測統計（§4 的參數表），不是憑印象定的。

### Output

```python
class PlantAgentOutput(BaseModel):
    supply: Supply       # o2_kg_day, edible_g_day, biomass_g_day,
                         # dry_biomass_g_day, water_recycled_l_day
    demand: Demand       # power_kw, water_l_day, co2_kg_day
    health: float        # 0..1
    daily_rate: dict     # 每日速率，供 Brain Agent 往前推 500 天
    reasoning: str       # Agent 的推理敘述
    tradeoff: str        # 取捨建議，含實際數字
    risks: list[str]
    citations: list[str]                    # 實際採用的文獻 doc_id
    coefficients: dict[str, CoefficientInfo]  # 每個係數的值、單位、出處、備註
    factors: dict[str, float]               # 環境修正因子
    warnings: list[str]                     # 超預算、係數退回、交叉驗算不符
    evidence: list[Evidence]                # 檢索到的文獻與相似度
```

### `daily_rate` 的鍵名（跨組介面，不可自由發揮）

這是要餵給 Brain Agent 的欄位，鍵名不一樣就對接不上。**照抄**：

```python
{
    "o2_kg_per_day":     round(o2_kg_day, 4),
    "edible_g_per_day":  round(edible_g_day, 1),
    "water_l_per_day":   round(water_l_day, 2),      # 毛蒸散量
    "power_kwh_per_day": round(power_kw * 24, 2),    # 瞬時功率 × 24
    "co2_kg_per_day":    round(co2_kg_day, 4),
}
```

五個鍵，不多不少。`power_kwh_per_day` 假設全天供電（含暗期的 HVAC 與泵），
不是只算照明時段——這是保守估計，寧可高估電力需求。

Brain Agent 要模擬 500 天，只給單點值那層很難接，所以這個欄位是刻意保留的。

### 其他欄位

**`Supply` / `Demand` 的完整定義**

```python
class Supply(BaseModel):
    o2_kg_day: float             # 產氧
    edible_g_day: float          # 可食部分鮮重
    biomass_g_day: float         # 總鮮重
    dry_biomass_g_day: float     # 乾重
    water_recycled_l_day: float  # 蒸散冷凝可回收的水 = 蒸散 × 0.92

class Demand(BaseModel):
    power_kw: float              # 瞬時功率，不是日耗電量
    water_l_day: float           # 毛蒸散量，未扣除回收
    co2_kg_day: float            # CO₂ 消耗
```

**`coefficients` 與 `evidence` 是 Demo 的說服力來源。** 前端要能展開看到
「這個數字是 51.95 g/m²/day，來自 PMC11243976 的南極 EDEN ISS 溫室實測」。

```python
class CoefficientInfo(BaseModel):
    value: float
    unit: str
    source: str      # doc_id | corpus_median | agronomy_constant | stoichiometry
    note: str = ""

class Evidence(BaseModel):
    doc_id: str
    source: str      # "NTRS" | "PMC"
    title: str
    year: str = ""
    section: str = ""
    score: float     # 與查詢的 cosine 相似度
```

`evidence` 優先放**實際被採用的**文獻（`citations` 裡有的），
若一篇都沒採用就放檢索結果的前 5 筆——不要回空陣列，前端需要東西展示。

`/simulate` 的回應少了 LLM 產出的四個欄位，多了中間值：

```python
class SimulateOutput(BaseModel):
    supply: Supply
    demand: Demand
    health: float
    daily_rate: dict[str, float]
    factors: dict[str, float]        # 四個環境修正因子
    intermediate: dict[str, float]   # dli / effective_ppfd / env_factor /
                                     # light_response / fresh_g_day / 兩個交叉驗算值
    warnings: list[str] = []
    coefficients: dict[str, CoefficientInfo] = {}
```

### `/sweep` 與 `/search` 的介面

`POST /sweep` — 收跟 `/analyze` 一樣的 `PlantAgentInput`，外加 query 參數
`levels`（相對目前 PPFD 的倍率，逗號分隔，預設 `0.6,0.8,1.0,1.2,1.5`）。

回傳陣列，**第一列是基準**（就是輸入的 PPFD），後續每列的 delta 都相對第一列：

```python
class SweepRow(BaseModel):
    ppfd: float
    power_kw: float
    edible_g_day: float
    o2_kg_day: float
    water_l_day: float
    health: float
    power_delta_pct: float | None = None    # 基準列為 None
    edible_delta_pct: float | None = None
```

`GET /search` — query 參數 `q`（必填）、`k`（預設 8）、`crop`、`units`（逗號分隔）、
`tier`（預設 `A_plant_core,B_usable`）。

```python
class SearchResult(BaseModel):
    doc_id: str
    source: str
    title: str
    year: str = ""
    section: str = ""
    score: float
    text: str
    units: list[str] = []
    crops: list[str] = []
```

---

## 4. 物理換算層（確定性，不由 LLM 算）

**架構決定：Agent 做判斷，程式做算術。**

考慮過讓 Agent 全包——檢索到係數後自己算。彈性最高，但多步算術、單位換算、守恆檢查都不可靠：同樣的輸入會給出不同答案，Demo 現場最容易出包。

這仍然是 Agent 自主決策（沒有把物理規則寫成 if-else），只是把 LLM 不擅長的算術移出去。跟黑客松簡報 §6.1「植物生長模型、能源消耗模型、水循環模型應該固定」一致——固定的是**世界如何運作**，不是 Agent 該做什麼。

| 層 | 負責 | 由誰做 |
|---|---|---|
| 輸入 | 環境參數、作物狀態 | 前端 |
| 檢索 | 從 corpus 找出適用的文獻與係數 | Agent (RAG) |
| 判斷 | 這個情境該用哪組係數、為什麼 | Agent |
| 換算 | 係數 → 生物量 → O₂ / 水 / 電供需 | **程式** |
| 敘事 | trade-off 建議、reasoning | Agent |

### 換算鏈

> **這是實際採用的版本。** 早期草稿寫成 `生物量 = DLI × LUE × area`，那個版本有 bug——
> LUE 是乾重基準、biomass_rate 是鮮重基準，量級差一個乾物率，會產生「光照降低產量反而
> 上升」的荒謬曲線。完整經過見 §11「修正一」。**照著實作時請用下面這個。**

```
DLI (mol/m²/day) = PPFD × photoperiod × 3600 / 1e6

env              = 溫度修正 × CO₂修正 × 濕度修正 × 密度修正
                   ↑ 四個都算進去。light_response 不在 env 裡，獨立相乘。

鮮重 (g/day)     = biomass_rate × area × env × light_response(DLI)
乾重 (g/day)     = 鮮重 × dry_matter
可食 (g/day)     = 鮮重 × edible_fraction

O₂  (kg/day)     = 乾重 × 1.07 / 1000
CO₂ (kg/day)     = 乾重 × 1.47 / 1000

蒸散 (L/day)     = transpiration × area × env × light_response(DLI)
回收水 (L/day)   = 蒸散 × 0.92

耗電 (kW)        = (PPFD × area ÷ LED_EFFICACY × (1 + HVAC_FRACTION)
                    + PUMP_W_PER_M2 × area) / 1000
```

**三個容易搞錯的地方**

1. **耗電是「除以」LED_EFFICACY，不是乘。** `LED_EFFICACY = 2.3 µmol/J`，
   µmol/s ÷ (µmol/J) = J/s = W。乘起來量綱不對。
2. **`power_kw` 是瞬時功率**，不是 24 小時平均。要換成每日耗電量請自己乘小時數。
3. **`demand.water_l_day` 是毛蒸散量**，不是扣掉回收後的淨補水。
   `supply.water_recycled_l_day` 是其中可回收的部分（92%）。
   Brain Agent 要算淨補水就用 `water_l_day − water_recycled_l_day`。

`biomass_rate`、`transpiration` 這些係數**由 Agent 從文獻檢索決定**，不寫死。
下面的表是預設值與合理性檢查用，不是硬規則。

### health 怎麼算

```python
health = f_temp * f_humidity * min(f_co2, 1.0)
if dli < 5:
    health *= 0.6      # 光量過低，作物會徒長
health = round(min(max(health, 0.0), 1.0), 3)
```

**不含密度因子**——密度影響的是單位面積產量，不是植株健康。
**CO₂ 因子夾到 1**——高 CO₂ 能增產但不會讓植株「更健康」。

health 表示「離文獻最適環境有多遠」，不是「產量有多高」。這兩件事要分開。

### 從 A/B 層 1021 篇抽出的係數

正則抓「數值 + 單位」，範圍過濾離群值，記下前後文與來源文件。原始命中 1837 筆存在 `coefficients.csv`（含 context 與 doc_id，可回溯），彙總在 `coefficients.json`。

| 係數 | 單位 | 樣本 | 文獻數 | 中位數 | P25–P75 |
|---|---|---:|---:|---:|---|
| `growth_days` | day | 542 | 257 | 23 | 14 – 40 |
| `wue` 水利用效率 | g/L | 511 | 122 | 3.0 | 1.3 – 7.9 |
| `photosyn_rate` | µmol CO₂/m²/s | 449 | 136 | 15.0 | 5 – 35 |
| `led_power` | W/m² | 139 | 51 | 150 | 50 – 255 |
| `biomass_rate` | g/m²/day | 91 | 27 | 12.3 | 6 – 33 |
| `lue` 光利用效率 | g/mol | 44 | 14 | 0.68 | 0.59 – 0.90 |
| `transpiration_total` | L/day | 38 | 20 | 5.5 | 1 – 16 |
| `transpiration` | L/m²/day | 12 | 8 | 5.0 | 4.5 – 6.0 |
| `harvest_index` | 比值 | 11 | 9 | 0.55 | 0.43 – 0.78 |

### 分作物的 biomass_rate（g/m²/day）

| 作物 | 中位數 | P25–P75 | n |
|---|---:|---|---:|
| lettuce | 20.0 | 16 – 40 | 13 |
| wheat | 20.0 | 8 – 33 | 35 |
| potato | 20.0 | 9 – 37.5 | 23 |
| tomato | 20.0 | 14.9 – 33 | 11 |
| soybean | 16.0 | 8 – 33 | 17 |
| spirulina | 13.8 | 12.6 – 69 | 4 |

### O₂ 產率要靠化學計量推

直接找 `g O2/m²/day` **一筆都沒有**——論文不這樣報。改用光合作用的化學計量：

```
CO₂ + H₂O → CH₂O + O₂
每產生 1 g 乾生物量（以 CH₂O 計，分子量 30）
釋放 32/30 ≈ 1.07 g O₂
```

實際乾物質不全是碳水化合物（含蛋白質、脂質），係數落在 **1.0–1.2 g O₂ / g 乾重**。要更準就用 MELiSSA 的化學計量模型（見 §1.3 抓到的文獻），依作物的元素組成 C:H:O:N 算。

**注意 `biomass_rate` 多半報鮮重**，換算 O₂ 前要先乘乾物率。

光合作用固定的是碳，不是水。萵苣長出 100 g 鮮重，其中 95 g 是根部吸的水，只有 5 g 是光合產物——產氧量只跟那 5 g 有關。小麥 100 g 有 88 g 是實體物質，產氧就多 18 倍。

### 乾物率與可食比例（農學常識級常數，不從 corpus 抽）

```python
DRY_MATTER_RATIO = {
    "lettuce": 0.05, "spinach": 0.08, "kale": 0.10, "radish": 0.06,
    "tomato": 0.06, "pepper": 0.08,
    "wheat": 0.88, "rice": 0.88,        # 穀粒本身就是乾的
    "potato": 0.20, "soybean": 0.90,
    "spirulina": 0.07,
}
DEFAULT_DRY_MATTER = 0.10

EDIBLE_FRACTION = {                      # harvest index
    "lettuce": 0.90, "spinach": 0.90, "kale": 0.85, "radish": 0.55,
    "tomato": 0.60, "pepper": 0.55,
    "wheat": 0.45, "rice": 0.45, "potato": 0.75, "soybean": 0.40,
    "spirulina": 1.00,
}

O2_PER_DRY_G  = 1.07                     # 32/30
CO2_PER_DRY_G = 1.47                     # 44/30

DEFAULT_DRY_MATTER = 0.10                # 表裡沒有的作物用這個
DEFAULT_EDIBLE = coefficients.json["global"]["harvest_index"]["median"]   # 0.545
```

這四組是**常數，不開放 Agent 覆寫**——它們是物種特性與化學計量，不會因為檢索到不同論文而改變。

**驗證方法**：看排序合不合直覺。萵苣產量最高但產氧最少，小麥反過來。**兩欄反向變化才是對的**；如果同向變化，反而該懷疑計算有問題。這比檢查單一數字有效——你不知道 0.023 kg 是對是錯，但你知道小麥產氧一定比萵苣多。

### 從文獻掃出的參數範圍（PMC 1076 篇全文統計）

拿來當合理性檢查與預設值，不是硬規則。

| 參數 | 單位 | 出現篇數 | 中位數 | 常見範圍 |
|---|---|---:|---:|---|
| 溫度 | °C | 811 | 20 | 7 – 35 |
| 養液 pH | — | 342 | 7.0 | 4.8 – 8.0 |
| 光強度 PPFD | µmol·m⁻²·s⁻¹ | 310 | 255 | 50 – 1000 |
| 光週期 | h/day | 220 | 14 | 6 – 18 |
| CO₂ 濃度 | ppm | 205 | 500 | 300 – 1000 |
| 相對濕度 | % | 148 | 60 | 33 – 80 |
| 功率 | W | 141 | 60 | 3 – 600 |
| 養液 EC | dS·m⁻¹ | 72 | 2.2 | 0.8 – 6.3 |
| 種植密度 | plants·m⁻² | 43 | 27 | 3 – 225 |
| 蒸散量 | L/day | 22 | 4.0 | 0.6 – 10 |
| 生物量產率 | g·m⁻²·day⁻¹ | 3 | 7.4 | 2.2 – 145 |

**作物覆蓋**（A+B 1021 篇）：rice 439、wheat 402、tomato 375、lettuce 約 350，soybean、potato、pepper、spinach、radish、kale、spirulina 皆有。五種 demo 作物全部涵蓋。

---

## 5. 檢索

```
1. 問題文字 → embedding（同一個模型、同一個維度）
2. metadata 預過濾：tier、crops、units
3. 過濾後的子集與向量矩陣算內積（向量已正規化，內積即 cosine）
4. 同一篇論文最多取 max_per_doc 段，避免單篇洗版
5. 取 top-K（K=8），把 text + doc_id + title + year 餵給 Agent
```

**先 filter 再算相似度**，不是算完再篩——這是 chunk metadata 帶 `units` 的理由。
問「萵苣的生物量產率」時只在有產量證據的段落裡找；純語意檢索會撈回大量談論植物
但沒有任何數字的段落，對需要抽係數的 Agent 沒有用。

### `search()` 的完整簽名與預設值

```python
def search(
    self,
    query: str,
    k: int = 8,
    tiers: list[str] | None = ("A_plant_core", "B_usable"),
    crops: list[str] | None = None,
    units: list[str] | None = None,
    require_all_units: bool = False,     # False = 命中任一即可
    max_per_doc: int = 2,                # 同一篇論文最多回幾段
    fallback: bool = True,               # 過濾後不足 k 筆時自動放寬
) -> list[Hit]:
```

`max_per_doc = 2` 這個值會影響 Agent 看到什麼，進而影響 `/analyze` 的每一個數字，
所以必須寫死在規格裡。

**取 top-K 的實作細節**：因為 `max_per_doc` 會砍掉一部分，要先多取一些再篩：

```python
take = min(len(idx), k * max(max_per_doc, 1) * 4)
top = idx[np.argpartition(-scores, take - 1)[:take]]
top = top[np.argsort(-(self.vecs[top] @ qv))]      # argpartition 不保證有序，要再排
```

**自動放寬的順序**（過濾後不足 k 筆時）：

```python
1. 先照 tiers + crops + units 過濾
2. 不足 k 筆且有指定 units → 放掉 units 重篩
3. 還是不足且有指定 crops → 放掉 crops 重篩
4. 仍為 0 → 回空陣列
```

先放 `units` 再放 `crops`，因為作物對不對比有沒有數字更重要。

**不需要 FAISS。** 64160 × 1024 float32 約 251 MB，全部進記憶體，
單次查詢的矩陣乘法約 30 ms。這個規模上向量資料庫是多餘的依賴。

### `Hit` 的欄位

```python
@dataclass
class Hit:
    id: str          # "{source}:{doc_id}:{序號}"
    score: float     # cosine 相似度
    text: str
    doc_id: str
    source: str      # "NTRS" | "PMC"
    title: str
    year: str
    tier: str
    section: str
    crops: list[str]
    units: list[str]

    def citation(self) -> str:
        y = f" ({self.year})" if self.year else ""
        return f"[{self.source}:{self.doc_id}] {self.title}{y}"
```

`as_context(hits, max_chars=12000)` 把結果組成可直接放進 prompt 的文字塊，
每筆的格式是：

```
[1] [PMC:PMC11243976] Biomass Production of the EDEN ISS… (2024)
    section: Lettuce | units: harvest_weight, temperature
<chunk 全文>
```

### `coefficient_evidence()`

把係數名對應到查詢語句與所需 units，Agent 只要說「我要 `biomass_rate` 的依據」。

**查詢語句必須逐字照抄。** 換一組措辭，檢索到的文獻就不一樣，抽出來的係數也會不一樣——
實測過改寫查詢語句會讓相似度從 0.810 掉到 0.775，前三筆只有一筆重疊。

```python
spec = {
    "biomass_rate": (
        ["biomass_rate", "yield_value", "harvest_weight"],
        "edible biomass productivity per unit area per day, "
        "dry weight yield in controlled environment"),
    "lue": (
        ["ppfd", "biomass_rate", "yield_value"],
        "light use efficiency, grams of biomass per mole of photons, "
        "daily light integral and growth"),
    "transpiration": (
        ["water_use"],
        "crop transpiration rate, water consumption per day, "
        "water use efficiency in growth chamber"),
    "o2_rate": (
        ["gas_exchange", "biomass_rate"],
        "oxygen production rate by plants, photosynthetic gas exchange, "
        "stoichiometry of biomass and oxygen"),
    "energy": (
        ["energy_use", "ppfd"],
        "LED lighting power consumption per square meter, "
        "energy requirement of plant growth chamber"),
    "photoperiod": (
        ["photoperiod", "ppfd"],
        "photoperiod and light intensity effect on crop yield"),
    "growth_days": (
        ["growth_rate", "harvest_weight"],
        "days to harvest, crop growth cycle duration"),
    "wue": (
        ["water_use", "yield_value", "harvest_weight"],
        "water use efficiency, grams of biomass per liter of water, "
        "irrigation water productivity in controlled environment"),
    "led_power": (
        ["energy_use", "ppfd"],
        "LED lighting power consumption per square meter, "
        "energy requirement of plant growth chamber"),
}

units, q = spec.get(coeff, ([], coeff))
if crop:
    q = f"{crop}: {q}"          # 作物名加在查詢語句前面
return self.search(q, k=k, crops=[crop] if crop else None, units=units)
```

實測 `coefficient_evidence("biomass_rate", crop="lettuce")` 回傳：

```
0.810  Soilless Cultivation: Dynamically Changing Chemical Properties…
0.805  Yield, nutrition, and leaf gas exchange of lettuce plants…
0.800  Biomass Production of the EDEN ISS Space Greenhouse in Antarctica
```

共 9 個係數。其中 5 個對應 §6 的 `TUNABLE`（Agent 可覆寫），
另外 4 個（`lue`、`o2_rate`、`energy`、`photoperiod`）只供人工查證用。

> **`wue` 與 `led_power` 是後來補的。** 它們在 `TUNABLE` 裡卻漏了查詢語句，
> 會走 `spec.get()` 的 fallback——用裸詞當查詢、不做 units 過濾。補上之後
> `led_power` 的命中從無關文獻變成 `energy_use` 標記的節能照明論文（0.793）。
> **實作時檢查一遍：`TUNABLE` 的每一項都要有對應的查詢語句。**

---

## 6. Agent 推理層

**兩次 LLM 呼叫，中間夾一次確定性計算。**

```
1. 選係數   檢索文獻 → LLM 判斷這個情境該用哪組數值、為什麼
2. 計算     程式做算術（src/models/greenhouse.py）
3. 敘述     LLM 就算出來的結果寫 reasoning 與 trade-off
```

LLM 不做算術。它負責「哪篇論文的條件跟現在最接近」「這個數字能不能外推」——
這是它擅長而 if-else 做不到的部分。

### 步驟 1 的 system prompt（逐字）

```
你是封閉生態系統的作物生理專家，正在為火星基地的維生規劃系統挑選模型參數。

任務：根據檢索到的論文段落，決定每個係數該用什麼數值。

規則：
1. 只能用段落裡實際出現的數字。段落沒提到就回傳 null，不要憑印象填。
2. 每個數值都要指出來自哪一段（用段落編號前的來源標記，例如 PMC:PMC11243976）。
3. 優先選實驗條件與目標情境接近的論文——同作物、相近光照與溫度、
   受控環境而非田間。
4. 若最接近的論文條件仍有落差，照樣採用，但在 note 說明落差與外推風險。
5. 注意單位。文獻的生物量多半是鮮重，若段落報的是乾重要換算或說明。

輸出純 JSON，不要加說明文字：
{
  "biomass_rate":  {"value": 數字或null, "source": "來源標記", "note": "為何選這篇、有何落差"},
  "transpiration": {...},
  "wue":           {...},
  "growth_days":   {...},
  "led_power":     {...}
}
```

**user 訊息的組法**：目標情境（作物、面積、密度、PPFD、光週期、溫濕度、CO₂）
＋ 需要的係數與單位清單 ＋ 檢索到的段落。段落是對 `TUNABLE` 每一項各檢索 4 筆，
用 `as_context(hits, 5000)` 組成，前面加 `### 關於 {係數名}` 當小標。

**參數**：不設 temperature，用模型預設。不使用 structured output——
`parse_json()` 會處理模型加上的 ` ```json ` 圍欄與前後說明文字。

### 哪些係數開放給 Agent 覆寫

```python
TUNABLE = ["biomass_rate", "transpiration", "wue", "growth_days", "led_power"]
```

只有這五個。判準是：**這個量會因為作物品種、栽培方式、實驗條件而不同嗎？**
會的才開放。乾物率、可食比例、化學計量係數不會，所以寫死。

`lue` 與 `photosyn_rate` 也不開放——它們只用於交叉驗算，不參與主要計算。

每個係數在 `Coefficients` 物件裡都帶 `source` 欄位：

| source 值 | 意義 |
|---|---|
| `doc_id`（如 `PMC:PMC11243976`） | Agent 從這篇文獻抽到的 |
| `corpus_median` | Agent 沒找到，或找到但沒通過合理性檢查 |
| `agronomy_constant` | 乾物率、可食比例 |
| `stoichiometry` | 化學計量 |

`sources()` 只回傳第一種，那就是 API 回應的 `citations` 欄位。

### 合理性檢查是必要的，不是保險

實測抓到的真實錯誤：Agent 讀到論文寫「垂直農場萵苣蒸散率 0.2–0.5 L/day/**plant**」，
它在 note 裡自己算出「密度 27 plants/m² 下為 9.45 L/m²/day」，
但 `value` 欄填的是**未換算的 0.35**。耗水量因此少算 14 倍（7.6 vs 108 L/day）。

Demo 現場沒人看得出 7.6 L 是錯的。所以：

```
超出 corpus P25–P75 三倍 → 退回中位數，並在 warnings 記錄它原本想填什麼
```

這正是「架構決定 B」的實證——LLM 在單位換算上不可靠，即使它自己寫對了推導過程。

### 步驟 3 的 system prompt（逐字）

```
你是火星基地維生系統的作物 Agent，正在向任務指揮官報告溫室的資源收支。

已經有人算好數字了，你的工作是解釋與建議，不要重算任何數字。

輸出純 JSON：
{
  "reasoning": "3-5 句話說明這組環境參數下作物的狀態、資源收支是否合理、關鍵限制在哪。
                要提到採用的係數來自哪些文獻。寫成完整句子，前端會轉成敘事。",
  "tradeoff": "1-2 句具體的取捨建議，必須引用 trade-off 表裡的實際數字，
               例如「光照降到 X 可省 Y% 電力，可食產量只減 Z%」。",
  "risks": ["風險或不確定性，每項一句"]
}

語氣：專業、直接。不要空泛的鼓勵語。數字一律沿用給定的值。
```

**`risks` 是這一步產生的**，不是程式算的。

**user 訊息**是一包 JSON，含情境、採用的係數與出處、算出的供給與需求、健康度、
環境修正因子、中間值、系統警告，以及 `sweep_ppfd()` 的結果。

最後那項是關鍵——把 trade-off 表餵進去，Agent 才寫得出
「降到 240 可省 38.8% 電力，產量降幅控制在 15.8%，每度電的糧食效率實際更高」
這種有數字的建議。沒有那張表它只會講空話。

### `/analyze` 內部呼叫 sweep 的掃描點

```python
levels = [ppfd, ppfd * 0.6, ppfd * 0.8, ppfd * 1.2]
sweep = sweep_ppfd(coeffs, inp, [round(x) for x in levels])
```

**第一個是原始請求的 PPFD，不是降載後的。** 這點會影響 trade-off 的百分比基準——
用降載後的值會算出完全不同的數字（實測差異：240 / −38.8% / −15.8%
變成 182.7 / −38.4% / −18.4%）。

---

## 7. 現場如何載入預備好的 corpus

**這三個檔案是資料不是程式**，可放雲端現場下載：

| 檔案 | 大小 | 內容 |
|---|---:|---|
| `chunks.jsonl` | 101 MB | 64160 個 chunk 與 metadata |
| `embeddings.npy` | 250 MB | 64160 × 1024 float32，已正規化 |
| `ids.json` | 1.5 MB | 與矩陣列序對應的 chunk id |

載入約 5 秒：

```python
import json, numpy as np
vecs = np.load("embeddings.npy")
ids = json.load(open("ids.json"))
chunks = {json.loads(l)["id"]: json.loads(l)
          for l in open("chunks.jsonl", encoding="utf-8")}
```

**如果向量不能帶**，只帶 `chunks.jsonl`，現場重算 embedding 約 30–40 分鐘、成本 US$1.6 上下。

**如果全部不能帶**，§1 的搜尋清單（1314 + 1074 筆 Document ID）也是資料，重下載約 1 小時。

---

## 8. 供應商切換

管線只在兩個地方綁廠商，各一行：

| 用途 | 目前的確切設定 | OpenAI 場合改成 | 備註 |
|---|---|---|---|
| Embedding | `voyageai/voyage-4` @ OpenRouter，`dimensions=1024` | `text-embedding-3-large`，指定 `dimensions=1024` | **換模型必須整批重算**，不同模型的向量不能混用 |
| Agent 推理 | `anthropic/claude-sonnet-4.5` @ OpenRouter | `gpt-4o`（或當時可用的型號） | 只影響 §6 的呼叫 |

兩者都走 OpenRouter 的 OpenAI 相容端點：

```
embedding  POST https://openrouter.ai/api/v1/embeddings
LLM        POST https://openrouter.ai/api/v1/chat/completions
```

改用 OpenAI 官方就換成 `https://api.openai.com/v1/...`，其餘 payload 格式相同。

其餘（篩選、切 chunk、檢索、物理換算）全是本機邏輯，與廠商無關。

---

## 9. 對照黑客松簡報，還缺三塊

| # | 缺口 | 簡報出處 | 說明 |
|---|---|---|---|
| 1 | 作物組合規劃 | §3.1 / §13 Phase 1 | 簡報要回答「種什麼、種多少、何時種」——crop allocation、planting / harvest schedule。目前只算「給定環境 → 資源供需」，沒有排程輸出 |
| 2 | Action Space | §6.2 | 簡報列了工具動作 `plant(crop, area)`、`harvest(crop)`、`set_led(crop, intensity)`。目前沒有工具層，只回傳數值不執行動作 |
| 3 | 時間推進模擬 | §9 Digital Twin | 要能回答「LED 降 20%，72 小時後電池剩幾 %」。目前是單點靜態計算 |

**第 3 點最值得補**——Brain Agent 要模擬 500 天，Plant Agent 至少要給每日速率（已放進 §3 的 `daily_rate`）。

---

## 10. 與組員的介面約定

### 已定案

**作物就是簡報 §13 列的五種**：Potato、Soybean、Wheat、Lettuce、Tomato。
API 的 `Crop` Literal 另外還收 radish / spinach / rice / kale / pepper / spirulina，
那些是 corpus 有資料順手支援的，Demo 不會用到。補文獻時只需顧那五種。

**水電是各自回報需求，由 Brain Agent 分配。** Plant Agent 不跟 Human Agent 協商，
只誠實回報 `demand.power_kw` 與 `demand.water_l_day`。

這件事對 `power_budget` 參數的意義：它是**選填**，代表 Brain Agent 已經分配好的額度。

- 留空 → Plant Agent 回報「在這組環境參數下我需要多少」，Brain 據此分配
- 給值 → Plant Agent 在額度內盡量做，超標時自動降 PPFD 並在 `warnings` 說明降到多少

第一輪規劃走留空，Brain 分配完再帶著額度打第二輪。

### 與世界設定（`world-settings-guide.md`）的對應

世界設定文件裡「Core Agent」= 本文的「Brain Agent」，同一個角色。
它的作物產量表（萵苣 19.5、馬鈴薯 16.25、番茄 13、小麥 9.75、黃豆 6.93 g/m²/day）
就是 §11 實測輸出表的「可食 g/day ÷ 20 m²」，條件即世界設定的固定背景
（PPFD 250、14 h、22°C、65%、500 ppm、27 plants/m²）。現場重建後打
`POST /simulate` 用預設值，五個數字對得上就代表物理層正確。

世界設定的用水（8.7 L/塊/tick）、產氧（OU）、耗電（5 EU/塊）是遊戲平衡係數，
**不是**從 Plant Agent 輸出換算的，不要試圖對帳。

### 待定

1. **Brain Agent 需要的欄位還缺什麼？**
   目前回傳 supply / demand / health / daily_rate / reasoning / tradeoff / risks /
   citations / coefficients / factors / warnings / evidence。請項目 4 直接補。

2. **前端要不要接 `/simulate` 做即時預覽？**
   拖 slider 時打 `/simulate`（17 ms）即時反應，放開後再打 `/analyze`（36 s）
   拿完整推理。只接 `/analyze` 的話每次改參數都要等半分鐘。

---

## 11. 實作紀錄

四層全部完成，約 1400 行。以下是照規格寫出來後，實測發現需要修正的地方——
現場重建時直接套用，不用再踩一次。

### 檔案結構

```
src/
├── retrieval/
│   ├── embedder.py     77 行   查詢轉向量，換供應商改 3 個常數
│   └── store.py       224 行   CorpusStore：metadata 預過濾 + cosine
├── models/
│   ├── coefficients.py 142 行   係數容器與 corpus 預設值、合理性檢查
│   └── greenhouse.py  292 行   確定性換算
├── agent/
│   ├── llm.py         103 行   LLM 呼叫，支援 openrouter / openai / anthropic
│   └── plant_agent.py 261 行   選係數 → 算術 → 敘述
└── api/
    ├── schema.py      138 行   Pydantic
    └── main.py        162 行   FastAPI 四端點
```

### 修正一：生物量不要從 DLI × LUE 推

第一版照 §4 的換算鏈寫成 `鮮重 = DLI × LUE × 面積`，另用文獻產率當交叉檢查，
差太多時取幾何平均。結果出現**光照降低反而產量上升**的荒謬曲線：

```
PPFD 250 → 167 g/day
PPFD 200 → 134 g/day
PPFD 150 → 199 g/day   ← 比 200 還高
```

原因：文獻的 LUE 多半以乾重計、`biomass_rate` 多半以鮮重計，兩者差一個乾物率
（萵苣約 20 倍），量級對不上。低光時觸發幾何平均，把數字往上拉。

改成單一路徑：

```
鮮重 = 文獻產率 × 面積 × env × 光反應(DLI)
```

`光反應` 是米氏飽和曲線，在參考光量 `DLI_REF = 12.9 mol/m²/day`
（文獻中位數 PPFD 255 × 14 h）時等於 1，此時輸出即等於文獻報的 `biomass_rate`。
LUE 路徑降級為量級校驗，差超過 4 倍才發警告。

水的處理同理——用文獻蒸散率錨定，WUE 當交叉檢查。

**原則：錨定在文獻實測值上，用修正因子調整；不要從第一原理推導再跟文獻對帳。**

### 修正二：合理性檢查要能退回，不只是警告

見 §6。第一版只把警告寫進 note，數字照用，耗水量少算 14 倍。
改成超出範圍就退回 corpus 中位數。

`simulate()` 的檢查清單第一版漏了 `transpiration` 與 `growth_days`，要補齊。完整清單是六個：
`biomass_rate`、`lue`、`wue`、`led_power`、`transpiration`、`growth_days`——
在算環境因子之前就先跑一遍 `plausible()`，不合理的寫進 `warnings`（這裡只警告不退回，
退回是 Agent 選係數那一步做的）。

### 環境修正因子的實際形式

```python
def temp_factor(t, opt=22.0, width=11.0):
    return max(0.0, math.exp(-((t - opt) / width) ** 2))

def co2_factor(ppm, ref=400.0):
    km = 300.0
    f = (ppm / (ppm + km)) / (ref / (ref + km))
    return max(0.1, min(f, 1.8))

def humidity_factor(rh):
    if 50 <= rh <= 70:
        return 1.0
    if rh < 50:
        return max(0.6, 1.0 - (50 - rh) * 0.008)    # 到 0% 時 0.6
    return max(0.6, 1.0 - (rh - 70) * 0.010)        # 到 100% 時 0.7，被 max 夾住

def density_factor(density, optimal=27.0):
    if density <= 0:
        return 0.0
    r = density / optimal
    return min(1.15, r / (0.35 + 0.65 * r))

def light_response(dli, ref=12.9, km=9.0):
    if dli <= 0:
        return 0.0
    return (dli / (dli + km)) / (ref / (ref + km))
```

寫成完整函式而不是文字描述，是因為「兩側線性遞減至 0.6」這種寫法會被誤讀成
「遞減到 30% 和 90% 時剛好 0.6」。實際的斜率是 0.008 / 0.010 每個百分點，
左右不對稱（一側跨 50 個百分點、一側跨 30 個）。

**這五個函式在 §11 的測試條件下有四個等於 1.0**（temp 22°C、humidity 65%、
density 27、light_response 0.99），只有 co2 是 1.094。所以那張實測輸出表
**無法驗證** humidity 與 density 有沒有被算進 `env`——答案是有，見 §4 的換算鏈。

設備常數（硬體規格，寫死合理）：

```python
LED_EFFICACY   = 2.3    # µmol/J，現代園藝 LED
HVAC_FRACTION  = 0.45   # 空調耗電約為照明的 45%
PUMP_W_PER_M2  = 8.0
WATER_RECOVERY = 0.92   # 冷凝回收率
```

### 實測輸出

20 m²、PPFD 250、14 h、22°C、CO₂ 500 ppm，係數用 corpus 中位數：

| 作物 | 可食 g/day | O₂ kg/day |
|---|---:|---:|
| lettuce | 390 | 0.023 |
| potato | 325 | 0.093 |
| tomato | 260 | 0.028 |
| wheat | 195 | 0.408 |
| soybean | 139 | 0.334 |

排序符合直覺：萵苣產量高但含水 95%，產氧極少；小麥反過來。這是模型可信的訊號。

`/analyze` 實測（小麥、40 m²、PPFD 400、**光週期 16 h、24°C、65%、CO₂ 1000 ppm**、
密度 27、預算 8 kW）：系統偵測 10.41 kW 超標，
自動降到 305 µmol/m²/s，Agent 在 reasoning 裡主動說明，並給出
「PPFD 240 省 38.8% 電、產量只降 15.8%」的建議。

> **復現時光週期一定要填 16 h。** 電力的 −38.8% 跟光週期無關，但產量降幅是
> `light_response(DLI)` 的比值，DLI 隨光週期變：14 h 會算出 −17.1%、12 h 是 −18.6%、
> 18 h 是 −14.7%。只有 16 h 才是 −15.8%。這組數字跟 Agent 選的 biomass_rate 無關
> （分子分母約掉），所以用 corpus 中位數也能對上。

### 已知限制

現場 Demo 前要知道的：

- **蒸散量不分作物。** corpus 只有全域中位數（12 篇有這個單位），五種作物算出來一樣。
- **`biomass_rate` 每次跑可能不同。** LLM 從同一篇論文抽數字的方式會變
  （實測 52 / 77 / 89 g/m²/day）。要穩定就快取係數，或把選係數的結果存下來重用。
- **小麥的 O₂ 偏高約 2–3 倍。** Agent 選的 89 g/m²/day 可能把乾重當鮮重報。
  交叉驗算會發警告但不自動修正——89 落在 P75×3 = 99 之內，剛好過關。
- **合理性檢查只擋離譜值。** 界線是 corpus 的 `P25 / 3` 到 `P75 × 3`，
  **上下界都有**。三倍以內的偏差不擋。要更嚴就縮小倍率，代價是會擋掉合理的
  極端案例（例如 EDEN ISS 的高產數據）。

### 語料本身的三個問題

這些是 corpus 的既有狀態，不是程式 bug，但會影響檢索品質：

- **PMC chunks 的 `year` 是空字串。** §2.2 的 metadata 範例寫了 `"year": "2017"`，
  但實際上只有 NTRS 的 chunk 有年份（從搜尋清單補回來的），PMC 那 1076 篇沒有。
  要用年份做 filter 的話得先補。
- **NTRS 的 OCR 文字有欄位錯亂。** 部分掃描件的多欄排版被讀成單欄，字詞順序打亂，
  變成沒有語意的詞串。這些 chunk 會進到檢索結果裡但讀不出東西。
- **NTRS 有位元組完全相同的重複文件。** 同一份報告以不同 Document ID 收錄多次。
  `max_per_doc` 是按 `doc_id` 去重的，擋不住這種——實測 `/analyze` 的 8 筆命中裡
  有 4 筆是同一段文字。要修的話得改成按內容雜湊去重。

### 復現測試（2026-09-10，跑了兩輪）

把這份 SPEC 加上 `data/index/` 與 `data/catalog/` 交給一個沒有任何脈絡的 agent，
禁止它讀現有實作，請它從零重建。第一輪找出缺漏、補進 SPEC、再跑第二輪驗證。

| 項目 | 第一輪 | 第二輪 |
|---|---|---|
| 物理層十個數字 | 全部對上 | 全部對上 |
| 電力鏈降載 | 10.407 kW → PPFD 304.6 | 同左 |
| trade-off | −38.8% 電 / −15.8% 產量 | 同左 |
| 單調性 | 五作物全部遞增 | 同左 |
| **檢索層相似度** | **0.775 vs 0.810，三筆只重疊一筆** | **0.810 / 0.805 / 0.800 完全吻合** |
| 評分 | 8.5 / 10 | **9 / 10** |

**兩個讓復現成功的關鍵，值得記下來：**

1. **§11 把五個環境修正因子寫成完整 Python 函式。** 第二輪的 agent 直說
   「那些曲線從文字描述重建不出來」——這是物理層能吻合的唯一原因。
2. **§5 逐字貼上查詢語句。** 第一輪失敗就敗在這裡；補上之後第二輪三筆全中。

**還有一件事是靠散文救回來的**：SPEC 沒明說 `/sweep` 的基準列該用原始 PPFD
還是降載後的 PPFD，但 §6 的散文裡引用了「240 / 38.8% / 15.8%」這組數字——
agent 說它本來會猜錯，是那組數字讓它反推出正確答案。

**教訓：規格裡寫具體數字，比寫抽象描述有用得多。** 數字能讓實作者自我驗證，
描述不能。物理層拿滿分是因為那張實測輸出表讓整層**可被證偽**。

第一輪的 16 處與第二輪的 3 處缺漏都已補進本文件。
