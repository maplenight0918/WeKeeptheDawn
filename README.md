# We Keep the Dawn

> 在星海之間，守住下一個黎明。

離開地球後，飛船裡的黎明，由溫室每天亮起的植物燈開始。

漫長的航程中，四名船員與一座小小的溫室，共同依靠有限的水、氧氣、食物與電力生活。每一次灌溉、每一度電、每一輪收成，都連結著下一天的希望。陪伴他們航行的，是三個各有所長的 AI，共同肩負一項使命：讓下一個黎明如期亮起。

**We Keep the Dawn** 是一個結合多 Agent 協作、資源管理與即時視覺化的太空生存經營專案。玩家可以走進飛船內部，觀察 AI 如何協調船員與作物的需求，並透過資源干預，探索它們面對環境變化時的取捨與應變。

## 三個 AI，一段共同的航程

| Agent | 任務 |
| --- | --- |
| **Plant Agent** | 分析作物生長、灌溉、產氧與收成需求，提供農務建議。 |
| **Human Agent** | 關注船員的個人能量、飲水與工作需求，提出補給與人力安排建議。 |
| **Core Agent** | 整合雙方建議，制定資源分配、船員工作與作物操作計畫。 |

每個決策循環都將觀察轉化為行動，再將實際結果帶回下一次規劃：

```text
觀察世界 → 辨識需求與風險 → 收集建議 → 制定計畫
    ↑                                  ↓
依結果重新規劃 ← 回報結算結果 ← 驗證並執行
```

Agent 的公開對話與決策摘要，讓玩家看見每次安排的依據，以及它對飛船生活造成的影響。

## 飛船裡的日常

飛船內有 **4 名船員、20 塊溫室作物地**，每塊地面積為 5 m²。溫室種植萵苣、馬鈴薯、番茄、小麥與黃豆，串起船員與植物互相支持的資源循環。

| 資源 | 在飛船中的用途 |
| --- | --- |
| 水 `water` | 供應作物灌溉與船員飲水。 |
| 氧氣 `oxygen` | 支援船員呼吸、人力發電與製水。 |
| 食物 `food` | 由成熟作物採收取得，補充船員個人能量。 |
| 電力 `power` | 由船員操作發電設備取得，供應製水與作物運轉。 |

每個 tick 代表一個模擬小時。船員在進食、飲水、發電與農務之間分工，AI 則持續協調當下補給與後續生產的需求。世界使用共用的遊戲係數與明確結算規則，呈現資源與工作安排之間的連動。

## 互動體驗

- **俯視 2D 飛船場景**：在溫室、發電區、製水區與船員生活空間中觀察日常運作。
- **世界物件呈現資源**：水箱液面、電池格數、氧氣設備與食物儲存狀態反映庫存變化。
- **船員與作物動態**：透過角色移動、工作動作與作物生長狀態，理解計畫的執行結果。
- **即時 Agent 訊息**：查看觀察、建議、計畫與結算回報，追蹤 AI 的協作過程。
- **玩家情境干預**：暫停、調整速度或修改公共資源，觀察 AI 如何因應新條件重新安排。

## 技術架構

| 層級 | 技術與責任 |
| --- | --- |
| 前端 | React 18、TypeScript、Vite、PixiJS v8、Zustand；呈現場景、互動與即時狀態。 |
| 介面與圖表 | Tailwind CSS、Recharts；呈現控制介面與詳細資訊。 |
| 後端 | Python 3.11+、FastAPI、Pydantic v2、asyncio；處理計畫驗證、世界排程與結算。 |
| 通訊 | REST API、WebSocket；傳遞控制指令、決策請求與權威狀態。 |
| 紀錄 | SQLite；保存世界狀態與執行紀錄。 |
| Agent 串接 | Bridge 將世界快照交給 Core，並將計畫及公開訊息接回遊戲。 |

Core 負責決策，Plant 與 Human 提供建議；後端統一驗證並結算世界，前端依照權威快照呈現。共用設定與資料契約讓各模組使用一致的欄位、單位與規則。

## 快速開始

以下命令適用於 macOS／Linux shell，從 repository 根目錄開始。請先準備 Python 3.11+、uv、Node.js 與 npm。

### 1. 安裝依賴

```bash
uv venv --python 3.11 .venv-bridge
uv pip install --python .venv-bridge/bin/python -r agent_runner/requirements-test.txt
cd frontend
npm ci
cd ..
```

### 2. 啟動世界後端

在第一個終端執行。範例設定採用 `external` 模式，由 bridge 提交計畫：

```bash
GREENHOUSE_CONFIG=config/runtime.example.yaml \
  .venv-bridge/bin/python -m uvicorn backend.main:app --host 127.0.0.1 --port 8001
```

需要自訂設定時，可將範例另存為 `config/runtime.yaml`，再調整 `GREENHOUSE_CONFIG` 路徑。

### 3. 啟動展示 Bridge

在第二個終端、repository 根目錄執行：

```bash
.venv-bridge/bin/python -m agent_runner --fixture-actions
```

此模式使用明確標示 **MOCK** 的展示排程，透過實際後端驗證與結算，呈現飲水、進食、發電、製水及農務動作，無需模型金鑰。一次啟動一個 bridge，讓同一世界由單一計畫來源驅動。

### 4. 啟動前端

在第三個終端執行：

```bash
cd frontend
npm run dev -- --host 127.0.0.1 --port 5175
```

開啟 <http://127.0.0.1:5175> 進入飛船。

若只想預覽前端，可在 `frontend/` 執行 `npm run dev:mock`，使用內建快照展示模式。

### 5. 串接 Agent 服務

真實 Agent 模式透過 Core Python 介面與 Plant／Human 的 HTTP 服務運作。服務安裝、模型環境設定與啟動流程請參閱 [Agent Bridge 說明](agent_runner/README.md) 及 [三 Agent 整合手冊](docs/three_agent_integration_manual.md)。展示模式與真實 Agent 模式的設定、驗證紀錄也保留於上述文件。

模型金鑰使用後端環境變數或本機未追蹤的 `.env` 保存；公開設定使用不含秘密的範例檔。

## 開發檢查

在 repository 根目錄執行後端測試：

```bash
.venv-bridge/bin/python -m pytest -q
```

前端型別檢查與正式建置：

```bash
cd frontend
npm run typecheck
npm run build
```

## 專案目錄

```text
frontend/        2D 飛船場景、互動介面與狀態同步
backend/         世界引擎、計畫驗證、API 與資料保存
shared/          共用世界設定、作物參數與資料契約
agent_runner/    三 Agent 串接與展示 fixtures
core_agent/      Core Agent
plant_agent/     Plant Agent
human_agent/     Human Agent
config/          執行設定範例
docs/            結算規則與整合文件
checks/          回歸、展示與串接檢查工具
```

## 延伸閱讀

- [世界設定與資源公式](world-settings-guide.md)
- [前後端設計規格](space_greenhouse_spec_v2.md)
- [Tick 結算順序](docs/tick_order.md)
- [Agent Bridge：安裝、模式與接口](agent_runner/README.md)
- [三 Agent 整合手冊](docs/three_agent_integration_manual.md)

早期設計文件沿用 **Space Greenhouse** 名稱；對外專案名稱為 **We Keep the Dawn**，故事舞台為太空飛船內部。

---

**當窗外仍是無盡星夜，我們一起守住黎明。**
