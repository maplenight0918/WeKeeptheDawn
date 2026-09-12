# PROMPT：Space Greenhouse 生存經營遊戲 — 前後端設計規格 v2

> 版本：v2.0｜依據 `world-settings-guide.md` v0.12（2026-09-11）重製
> 使用方式：把本文件整份貼給負責產生程式碼／設計稿／圖像的 AI 或團隊。
> **世界數值的唯一真相是 `world-settings-guide.md`。** 本文件把它翻譯成可實作的前後端規格；若兩者衝突，以 guide 為準並回報衝突。
> 第 0–9 節為系統設計 prompt，第 10 節為圖像生成 prompt，第 11 節為驗收，第 12 節為與 v1 的差異與既有程式碼的處置。

---

## 0. 角色設定（給 AI 的指令）

你是一位資深全端遊戲工程師兼系統架構師。請根據以下規格，設計並實作一個「AI Agent 自主決策的火星基地生存經營遊戲」。
輸出必須包含：(1) 前端專案骨架與關鍵元件程式碼；(2) 後端分層架構與關鍵模組程式碼；(3) 前後端共用的資料模型與訊息協定；(4) 可執行的最小 Demo。

三條不可違反的原則：

1. **數值只有一份。** 所有單位、係數、公式來自 guide；前端、後端、三個 Agent 的 prompt 都不得另設一套數值。
2. **策略歸 Core，驗證歸程式。** 水電分給哪些地塊、誰去進食、誰去發電、誰去採收 —— 全部由 Core Agent 的策略決定。後端只驗證庫存、容量、占用與狀態，**不得內建平均分配、固定順序、最危急者優先等任何預設政策**。
3. **結算只有一處。** 後端 tick 結算是庫存的唯一依據。前端動畫、Agent 訊息、控制台操作都不能再次更新資源。

---

## 1. 專案背景與核心概念

- 場景：火星基地，4 名 crew，**持續運行、無通關條件**。結束只有一種：死亡。
- 玩家不是決策者。玩家是「觀察者／干預者」：暫停／調速、**直接修改資源**（造成短缺或補給）。決策者是 AI Agent。
- 三個 Agent：**Core Agent**（決策與分配策略）、**Plant Agent**（作物面建議）、**Human Agent**（crew 存量與工作建議）。Plant／Human 只提供建議，Core 產生本 tick 的執行計畫（`TickPlan`）。
- 視覺參考 **Gather Town**：俯視 2D 地圖佔滿畫面，資源狀態直接呈現在世界物件上，Agent 思考以氣泡浮現在對應設施上方（見 §4）。
- **本版沒有預測 Simulator。** guide §1.3 明定「沒有預測 Simulator，僅有實際世界更新程式」。Core 的決策依據是目前庫存、趨勢與 Agent 建議，不做未來軌跡模擬。
- Agent 決策迴圈（每個決策 tick 必須實作）：
  `Observe → Identify Risks → Collect Advice (Plant / Human) → Compose TickPlan → Validate → Execute → Reflect`

---

## 2. 範圍（v2 第一版）

| 項目 | 設定 |
|---|---|
| 動態資源 | 四種：`water` (L)、`oxygen` (OU)、`food` (遊戲 kcal)、`power` (EU) |
| 作物 | 五種：`lettuce`、`potato`、`tomato`、`wheat`、`soybean` |
| 地塊 | 20 塊，每塊 5 m²；初始五種作物各 4 塊 |
| Crew | 4 名，各自記錄 `food_energy`（遊戲 kcal）與 `water`（L）；**沒有 health** |
| 設施 | 人力發電機（4 工作位）、製水設備、灌溉控制台（共用、僅動畫）、用餐區、飲水點（位置待定）、氧氣供應設備（僅顯示） |
| Agent | Core / Plant / Human 三個 |
| 時間 | 1 tick = 1 模擬小時；預設實際 **2 秒**推進一次，可調速、可暫停 |
| 玩家干預 | 暫停、調速、修改任一公共資源數值 |
| 結束 | 任一 crew 個人能量或水 ≤ 0；或公共氧氣 ≤ 0（全員死亡） |

不做：Crew health、成功通關、穩定計數、預測模擬、灌溉比例滑桿、種子費用。

---

## 3. 世界規則（全部取自 guide，不得改寫數值）

### 3.1 四種公共資源

| key | 單位 | 初始 | 容量 | 警戒線 | 來源 | 去向 |
|---|---|---:|---:|---:|---|---|
| `water` | L | 3,000 | 4,000 | 400 | 製水設備 | 灌溉、轉入個人水 |
| `oxygen` | OU | 8,000 | 15,000 | 600 | 植物產氧 | 呼吸、發電、製水 |
| `food` | 遊戲 kcal | 120,000 | 200,000 | 12,000 | 採收 | 轉入個人能量 |
| `power` | EU | 6,000 | 10,000 | 1,000 | 人力發電 | 植物運轉（灌溉）、製水 |

- 後端以浮點實際數量結算，**不用四捨五入後的 UI 值**。
- 前端百分比 = 庫存 ÷ 容量 × 100%。
- **警戒線不是硬性限制。** 它只觸發「低庫存」事件給 Core；程式不因低於警戒線而拒絕操作。
- **任何操作不得產生負庫存。** 不足時依各公式縮量或不執行。
- 氧氣超出容量的部分流失，必須記錄入庫量與溢出量。
- Food 的單位就是遊戲 kcal，不存在第二次換算。

### 3.2 固定背景條件（無控制工具、無另計耗電）

光強度 250 µmol/m²/s、光週期 14 h/day、22°C、65% RH、CO₂ 500 ppm。種植密度 27 plants/m²（每塊 135 株，不逐株模擬）。每塊地 5 EU/tick 是抽象運轉成本，包含在灌溉公式內。

### 3.3 作物參數

| key | 成熟 ticks | 產氧 OU/tick/塊 | 產量 g/m²/day | 每塊每輪產物 g | 熱量係數 kcal/g | 每塊每輪食物 kcal |
|---|---:|---:|---:|---:|---:|---:|
| `lettuce` | 30 | 16 | 19.5 | 2,925 | 0.2 | 585 |
| `potato` | 90 | 16 | 16.25 | 7,312.5 | 1.2 | 8,775 |
| `tomato` | 90 | 22 | 13 | 5,850 | 0.3 | 1,755 |
| `wheat` | 90 | 10 | 9.75 | 4,387.5 | 3.0 | 13,162.5 |
| `soybean` | 90 | 12 | 6.93 | 3,118.5 | 3.9 | 12,162.15 |

採收公式：`食物 = 產量 × 5 × 成熟ticks × 1 × 熱量係數`。文獻 1 天已映射為 1 tick，**不再乘除 24**。

### 3.4 Crew 個人存量

| 欄位 | 單位 | 容量 | 初始 | 警戒線 | 單次補充 |
|---|---|---:|---:|---:|---:|
| `food_energy` | 遊戲 kcal | 3,000 | 2,400 | 700 | 1,000 |
| `water` | L | 2 | 1.5 | 0.4 | 0.5 |

基礎消耗（文獻 ÷ 24，後端保留完整精度）：

| 項目 | 每人每 tick | 四人每 tick | 扣哪裡 |
|---|---:|---:|---|
| 食物能量 | 127.25 kcal | 509 | 個人 `food_energy` |
| 氧氣 | 37.291667 OU | 149.166667 | **公共** `oxygen` |
| 水 | 0.134042 L | 0.536167 | 個人 `water` |

- 個人初始存量與公共初始庫存分別給定，不互扣。
- 補充量 = min(單次補充量, 公共庫存, 個人剩餘容量)。1：1 搬移，不是消耗。**縮量補充仍占用該 tick。**
- 低於警戒線 → 發 `crew_low_supply` 事件給 Core；**世界不自動替 crew 進食**。

### 3.5 轉換公式

**灌溉（自動，每塊每 tick）**
```
需求：8.7 L water + 5 EU power  → 生長 +1 tick、產氧 +該作物 OU
成功條件：Core 有分配該地塊 且 兩項庫存都足夠 → 原子扣除、計數歸零
失敗：任一不足或未分配 → 兩項皆不扣、consecutive_unirrigated_ticks += 1（同時缺兩項只 +1）
```
| 連續未灌溉 | 效果 |
|---|---|
| 1 | 暫停生長、停止產氧，事件 `plot_unirrigated` |
| 2 | 持續暫停，事件 `plot_critical` |
| 3 | **當 tick 在作物更新階段死亡**，不可採收，必須 `clear` 後才能重種 |

- 恢復灌溉保留原進度；重種則進度與計數歸零。
- 成熟未採收作物同樣適用（仍耗水電、仍產氧、不再增加食物）。
- 空地與死亡地塊不耗水電、不產氧。
- **省水只有一種方法：減少種植面積。** 沒有比例滑桿。
- 世界暫停時不累加計數。

**採收（一次性）**
```
food += 產量 × 5 × 成熟ticks × 熱量係數        （§3.3 表最右欄）
條件：作物成熟 且 food 容量足以容納完整收成；否則不採收、作物保持成熟
成功後地塊清空
```

**播種（一次性）**：指定空地與作物，進度歸零，**下一 tick 開始生長**，無費用。

**清除（一次性，前端入口待定）**：死亡或活體作物皆可清除，地塊變空。

**人力發電**
```
1 工作單位 = 100 kcal 個人能量 + 25 OU 公共氧氣 → 250 EU 公共電力
每人請求上限_i = min(請求_i, 1, 該人基礎消耗後能量 / 100)
實際總量      = min(Σ 請求上限, 剩餘氧氣 / 25, 電池剩餘容量 / 250)
縮量時按各人請求上限比例分配；總請求為 0 則不工作
個人扣 100 × 自己實際量；公共氧氣扣 25 × 總量；公共電力加 250 × 總量
```
- 不能用別人的能量支付；不再扣公共 food。
- **公式不保命**：工作恰好耗盡個人能量即死亡。Core 必須預留。
- 四人滿額：每 tick 消耗 909 kcal、249.166667 OU、0.536167 L 個人水，產 1,000 EU。

**製水**
```
2 EU + 0.2 OU → 1 L
實際製水 = min(請求, 250 L/tick, 剩餘電力 / 2, 剩餘氧氣 / 0.2, 水箱剩餘容量)
```
按實際量扣除。例：174 L → 扣 348 EU + 34.8 OU。

### 3.6 Tick 結算順序（嚴格，不得調換）

```
Phase 0  暫停檢查：玩家暫停 / Core 規劃中 / 錯誤暫停 → 不結算，不累加灌溉計數
Phase 1  已安排的進食／飲水（依 TickPlan.refills）
Phase 2  個人基礎消耗（能量、水）→ 每人逐一死亡檢查
         四人呼吸扣公共 oxygen → 氧氣 ≤ 0 立即全員死亡、任務失敗、停止後續 phase
Phase 3  未補充的 crew 依 TickPlan.generation 發電 → 每次扣除後再檢查個人能量與公共氧氣
Phase 4  製水（TickPlan.water_production_l）→ 檢查公共氧氣
Phase 5  作物：依 TickPlan.irrigation 的順序逐塊嘗試灌溉 → 生長 → 產氧（入庫、記錄溢出）
         → 更新 consecutive_unirrigated_ticks → 第 3 次失敗者死亡
Phase 6  作物操作（TickPlan.plot_ops，嚴格依 Core 給的 order 逐項驗證後執行；程式不預設採收／清除／播種的先後）
Phase 7  低庫存／低存量事件、狀態推播
```

時效規則：
- 本 tick 新發的電可立即用於 Phase 4 製水；新製的水可立即用於 Phase 5 灌溉。
- 本 tick Phase 5 新產的氧氣、Phase 6 新採收的食物，**下一 tick** 才可供人類使用或交換。實作方式：Phase 5／6 的產出先寫入 `pending_oxygen` / `pending_food`，於下一 tick Phase 0 之後併入庫存。

### 3.7 死亡與結束

- 個人 `food_energy` ≤ 0 或 `water` ≤ 0：該 crew **立即**死亡（每次扣除後即檢查，不等 tick 末），不可復活。
- 公共 `oxygen` ≤ 0（含恰好歸零）：所有存活 crew 立即死亡，任務失敗，停止後續 phase。**每次呼吸、發電、製水、玩家修改資源後都要檢查**，不得等植物產氧後再判斷。
- 任一 crew 死亡即任務失敗。
- 公共 food／water／power 歸零**不**直接結束，依補充與灌溉中斷規則繼續。植物死亡不結束任務。
- 沒有穩定計數、沒有成功事件。持續存活即為穩定。

### 3.8 工作占用與設施容量

| 工作 | 占用 | 容量 |
|---|---|---|
| 發電 | 該 crew 該 tick；工作量 0–1 | 4 個工作位 |
| 進食 | 該 crew 1 tick | 4 人可同時 |
| 飲水 | 該 crew 1 tick | 4 人可同時 |
| 播種／採收／清除 | 每塊 1 crew 1 tick | 每塊獨立 |
| 製水設定、灌溉控制台 | **不占用**，動畫而已 | — |
| 移動 | **不計模擬耗時** | — |

- 同一 crew 同一 tick 只能有一項占用工作。部分發電不能換取另一項工作。
- 補給與作物工作只付基礎消耗，不另加工作費；只有發電另扣 100 kcal/單位。
- 同地塊同 tick 多項操作須由 Core 明確指定順序並逐項通過狀態檢查；**同一 crew 不能在一 tick 內完成採收＋播種**。

### 3.9 待定項目（程式與 Agent 均不得擅自假設）

| 項目 | 可用基準 | 不能假設 |
|---|---|---|
| 進食／飲水的正式工具接口 | 對象、份額、順序由 Core 決定；單次上限依 §3.4 | 任何固定分配政策 |
| 飲水點的場景位置 | 必須是一個世界物件 | 具體房間 |
| `clear` 的前端入口 | 底層工具存在 | crew 互動 UI |
| 設備故障類事件 | 玩家可直接修改資源 | 故障規則 |

實作時以 `TODO(guide-pending)` 標記，並提供最小可運作預設，但預設必須是「什麼都不做」而不是一個政策。

---

## 4. 前端設計規格（Gather Town 風格：介面即世界）

### 4.0 核心原則 — Diegetic UI

1. 地圖佔滿視窗，四邊沒有常駐面板。
2. 資源狀態長在世界裡：水看水箱液面、電看電池格數、氧氣看氧氣槽壓力環、食物看儲藏區堆疊。
3. 要看細節就滑過去／點下去，不掃側欄。
4. 正交俯視 2D 方格，32 px tile，角色自由走動。
5. 僅三處極簡 chrome：左上時鐘徽章、下方浮動工具列、右下 Agent 抽屜。

**判斷準則：能做成世界物件的資訊就不准做成 GUI 元件。**

### 4.1 技術棧

React 18 + TypeScript + Vite；PixiJS v8 全視窗；Zustand；WebSocket + REST；Tailwind（僅 overlay）；Recharts（僅詳細卡）。

### 4.2 圖層

```
Layer 5  MODAL        起始畫面 / 任務失敗畫面（死亡）
Layer 4  CHROME       左上徽章 · 下方工具列（含玩家修改資源面板）· 右下 Agent 抽屜
Layer 3  BUBBLES      Agent 氣泡、資源飄字、tooltip、詳細卡
Layer 2  ACTORS       4 名 crew（名牌在腳下；異常 icon 在頭上；死亡倒地）
Layer 1  WORLD OBJ    水箱、氧氣槽、電池、儲藏堆、20 塊地、發電機、製水設備、灌溉控制台、用餐區、飲水點
Layer 0  MAP          地板、牆、走廊
```

### 4.3 地圖與世界物件

建議 48 × 28 tiles（1536 × 896 px），六個區域＋十字走廊：

| 區域 | 位置 | 世界物件 |
|---|---|---|
| Greenhouse | 上方橫跨 | **20 塊地**（4 × 5 排列，每塊 64 × 32）、灌溉控制台（單一，位於溫室入口） |
| Power Bay | 左中 | 人力發電機 **4 個工作位**、電池組 |
| Water Plant | 右中 | 製水設備＋控制面板、水箱 |
| Life Support | 右下 | 氧氣槽（僅顯示） |
| Galley | 左下 | 食物儲藏堆、用餐區（4 座位）、飲水點 `TODO(guide-pending)`（暫放 Galley，標為待定） |
| Quarters | 下中 | 4 張床（純裝飾，休息不是本版動作） |

**資源 → 世界呈現**

| 狀態 | 世界內呈現 | 精確數值 |
|---|---|---|
| `water` | 水箱**液面高度** = 庫存 ÷ 4,000；< 400 L 轉琥珀 | hover 水箱 |
| `oxygen` | 氧氣槽**壓力環**弧長 = 庫存 ÷ 15,000；< 600 紅色；溢出時槽頂噴白霧 | hover 氧氣槽 |
| `power` | 電池組**亮格數** = 庫存 ÷ 10,000（10 格）；< 1,000 最後一格閃 | hover 電池 |
| `food` | 儲藏堆**層數** = 庫存 ÷ 200,000（8 層）；< 12,000 露出空棧板 | hover 儲藏堆 |
| 地塊 `crop` / `progress` | 作物貼圖：五種作物各自造型 × 成熟度四階段；空地棕色；**死亡地塊枯黑帶叉** | hover 地塊 → `Plot 7 · potato · 63/90 · 灌溉正常` |
| `consecutive_unirrigated_ticks` | 1：地塊邊框黃；2：邊框紅閃；3：死亡貼圖 | 同上 |
| 灌溉需求 | 灌溉控制台螢幕：`存活地塊 18 · 需求 156.6 L + 90 EU · 供應 18/18` | hover 控制台 |
| 發電 | 每個工作位上有人踩踏，踏板轉速 ∝ 該人實際工作量；電池到發電機的導線有光流 | hover 發電機 → 各人工作量與實際發電 |
| 製水 | 設備運轉燈＋管線流光速度 ∝ 實際製水量；設定值顯示在面板 | hover 設備 |
| `crew.food_energy` / `crew.water` | 頭上**只在低於警戒線時**顯示 🍞 / 💧 並脈動；死亡則倒地變灰 | 點擊 crew |
| 任務失敗 | 全基地燈光熄滅、Layer 5 顯示死亡原因與 tick 數 | — |

不做常駐資源條。唯一像進度條的是控制台與面板螢幕 —— 它們是世界裡的實體設備。

### 4.4 Agent 氣泡

- 錨點：**Core** → 走廊中央主控台；**Plant** → 溫室；**Human** → 用餐區／發電機之間。
- 配色：Core 紫、Plant 綠、Human 琥珀。
- kind 樣式：`observe` 灰、`risk` 琥珀邊框 ⚠、`advice`（Plant／Human 建議）卡片、`plan`（Core 的 TickPlan 摘要）白色粗體 ✔、`validation_error` 紅色並讓對應物件閃紅框、`reflection` 斜體 📝 飄向主控台。
- 逐字打出，4–6 秒淡出，同時寫入右下抽屜。抽屜可展開，含「精簡／完整」切換。

### 4.5 Crew

- Gather 式小人，名牌在腳下，四方向行走。**走路不計模擬耗時**，但動畫要真的走（沿走廊 waypoint、定速、邁步）。
- 任務姿勢：發電（踩踏，慢節奏）、播種／採收／清除（蹲在地塊）、進食（坐）、飲水（站在飲水點）、操作控制台（站在面板前）。姿勢保持靜止、每 2–4 秒一個動作節拍；**不得持續抖動**。
- 頭上 icon 只在 `food_energy < 700` 或 `water < 0.4` 出現。
- 死亡：倒地、變灰、名牌加 ✕；不再移動。
- 點擊 crew → 小卡：能量、水、本 tick 工作、最近動作。

### 4.6 極簡 Chrome

1. **左上徽章**：`TICK 1 337 · DAY 55 · 17:00`（tick 換算日時）＋ 一行存活狀態（`4 / 4 alive`）。持續運行，沒有「/ 500」。
2. **下方工具列**：⏸ ▶、×1 ×5 ×20、`⚙ 修改資源`（彈出小面板：四個公共資源各一個輸入框，套用後立即觸發死亡檢查與 Core 重新規劃）。
3. **右下 Agent 抽屜**：預設收合一行，展開 360 × 320。

### 4.7 互動

拖曳平移、滾輪縮放（0.75×–2×）；物件 hover tooltip、點擊詳細卡（近 24 tick 折線）；資源變動飄字；Esc 關閉。任務失敗時**不得遮住世界**——Layer 5 只在畫面中央放一張半透明卡。

### 4.8 Store

```ts
interface GameStore {
  world: WorldState;                 // 後端推播的全量 state（見 §6）
  thoughts: AgentThought[];          // 上限 500
  plans: TickPlan[];                 // 上限 100
  events: WorldEvent[];              // 上限 500
  camera: { x: number; y: number; zoom: number };
  selected: { kind: 'crew' | 'plot' | 'object'; id: string } | null;
  applyStateUpdate(s: WorldState): void;
  appendThought(t: AgentThought): void;
  appendPlan(p: TickPlan): void;
  appendEvent(e: WorldEvent): void;
}
```

---

## 5. 後端分層架構

### 5.1 技術棧

Python 3.11 + FastAPI + Pydantic v2；asyncio tick 迴圈；純 Python 數值結算；SQLite（事件、thought、memory、snapshot）；LLM provider 可插拔（`LLM_PROVIDER = openai | anthropic | mock`）。

### 5.2 分層

```
L1  Interface      REST（/world, /control, /resources, /ingest/*）· WebSocket /ws
L2  Orchestration  WorldLoop（tick 排程、暫停、調速）· EventBus · PlanValidator · Scheduler
L3  Agents         CoreAgent · PlantAgent · HumanAgent · ToolRegistry · MemoryStore
L4  World Model    WorldEngine.settle(state, plan) → (next_state, events)   ← 唯一結算
                   子模組：crew_model · generation · water_plant · crops · harvest
L5  Domain         Pydantic models · StateRepository
L6  Persistence    SQLite repositories
```

依賴方向：上層可呼叫下層，下層不得 import 上層。**Agent 只能產生 `TickPlan`，不得直接寫 StateRepository。**

L4 沒有 Forecaster。`WorldEngine.settle` 仍設計為純函數（輸入 state + plan，輸出 next_state），以便測試與重播；但**不提供給 Agent 做未來預測**。

### 5.3 PlanValidator（取代 v1 的 ConstraintGuard）

語意改變：v1 是「拒絕違反安全底線的動作」；v2 是「**只驗證可行性，不驗證明智性**」。

驗證項目（全部來自 guide，逐項回傳 `ValidationError{code, target, message}`）：

| code | 條件 |
|---|---|
| `CREW_DEAD` | 計畫指派已死亡 crew |
| `CREW_DOUBLE_BOOKED` | 同一 crew 同 tick 超過一項占用（refill / generation>0 / plot_op） |
| `GENERATION_OUT_OF_RANGE` | 工作量不在 [0, 1] |
| `GENERATION_STATION_FULL` | 發電人數 > 4 |
| `WATER_REQUEST_NEGATIVE` | 製水請求 < 0（> 250 不報錯，結算時縮量） |
| `PLOT_NOT_EMPTY` | 播種到非空地 |
| `PLOT_NOT_MATURE` | 採收未成熟或空地或死亡地塊 |
| `PLOT_DEAD_NEEDS_CLEAR` | 播種到死亡地塊 |
| `PLOT_UNKNOWN` / `CROP_UNKNOWN` | id 不存在 |
| `SAME_CREW_HARVEST_AND_PLANT` | 同一 crew 同 tick 採收＋播種 |
| `IRRIGATION_PLOT_INVALID` | 灌溉清單含空地／死亡地塊 |

**不驗證的**（因為那是策略，不是規則）：是否有人快餓死卻沒安排進食、是否把水電分給低價值作物、是否留了緊急儲備。這些交給 Core 與 Reflection。

驗證失敗：整份 TickPlan 退回 Core 附錯誤清單（最多重試 3 輪）；三輪仍失敗 → 以**空計畫**結算該 tick（無補充、無發電、無製水、灌溉清單為空 → 所有地塊計數 +1），並發 `plan_failed` 事件。空計畫不是政策，是「什麼都不做」。

### 5.4 TickPlan（Core 的策略接口，前後端與 Agent 共用）

```ts
interface TickPlan {
  tick: number;
  refills: { crew_id: string; kind: 'food' | 'water' }[];      // 占用該 crew
  generation: Record<string, number>;                          // crew_id → 工作量 0–1
  water_production_l: number;                                  // 請求 L/tick
  irrigation: string[];                                        // 依順序嘗試灌溉的 plot_id；未列出者本 tick 不供應
  plot_ops: { order: number; crew_id: string; plot_id: string;
              op: 'plant' | 'harvest' | 'clear'; crop?: CropKey }[];
  rationale: string;                                           // Core 的一句話理由（供氣泡／抽屜）
}
```

- `irrigation` 的**順序就是執行順序**：庫存在中途耗盡時，後面的地塊灌溉失敗。這正是 guide 要求「分配對象、份額與執行優先順序由 Core 指定」的表達方式。
- `refills` 的順序就是 Phase 1 的執行順序（公共庫存不足時後面的人拿到縮量）。
- 沒有出現在 `generation` 的存活 crew 視為工作量 0。
- 進食／飲水的正式接口 guide 標待定；本版以 `refills` 作為最小表達，並標 `TODO(guide-pending)`。

### 5.5 每 tick 流程

```
1. WorldLoop.tick()；若暫停 → 跳過（不累加任何計數）
2. 併入上一 tick 的 pending_oxygen / pending_food
3. 若本 tick 是決策 tick（預設每 tick；可設 decision_interval）或有新事件：
     CoreAgent.plan(state, events) →
       a. Observe（公共四資源、四人存量、地塊狀態、上一 tick 結算摘要）
       b. PlantAgent.advise() / HumanAgent.advise()（並行）
       c. 合成 TickPlan
       d. PlanValidator.check()；失敗 → 回 c（≤ 3 輪）
       e. Reflect → MemoryStore
     全程每步 emit agent_thought
   否則沿用上一份 TickPlan（連續設定：generation / water_production_l / irrigation 沿用；refills / plot_ops 清空）
4. WorldEngine.settle(state, plan) 依 §3.6 Phase 1–7 結算，回傳 next_state + events
5. 任一死亡事件 → mission_failed；WorldLoop 停止
6. Ingest 路徑寫回 StateRepository → EventBus → WebSocket 推播 state_update / tick_plan / world_event
```

Core 規劃期間世界暫停（guide §1.3），LLM 延遲不會讓 crew 在無計畫下死亡。

### 5.6 Agent 提示詞結構

每個 Agent：System（角色、目標優先序、可用工具、**guide 的公式與數值原文**、輸出 JSON schema）＋ Context（目前 state、近 24 tick 趨勢、待處理事件、top-3 相似 memory）。

- **CoreAgent** 輸出 `TickPlan`。目標優先序：無人死亡 > 公共氧氣不歸零 > 地塊不因缺灌溉死亡 > 食物／水／電長期收支 > 產出最大化。
- **PlantAgent** 輸出 `{ risks[], advice[] }`：哪些地塊該優先灌溉、哪些該採收／重種、換種建議、預估下一輪食物。
- **HumanAgent** 輸出 `{ risks[], advice[] }`：誰需要補充、誰能發電多少而不致命、發電總量建議。
- 三者 prompt 內**只能有 Objective 與 Constraint**，不得寫死「事件 → 動作」規則，也不得寫死分配政策（例如「總是先餵最餓的人」）。策略必須由 LLM 產生。

### 5.7 玩家修改資源

`POST /resources { water?, oxygen?, food?, power? }` → 夾在 [0, 容量] → 寫入 → **立即執行死亡檢查**（氧氣 ≤ 0 全員死亡）→ 發 `player_edit` 事件 → 下一 tick 強制為決策 tick。

---

## 6. 共用資料模型（TypeScript / Pydantic 同步）

```ts
type CropKey = 'lettuce' | 'potato' | 'tomato' | 'wheat' | 'soybean';
type ResourceKey = 'water' | 'oxygen' | 'food' | 'power';

interface ResourceState { key: ResourceKey; unit: 'L' | 'OU' | 'kcal' | 'EU';
  value: number; capacity: number; warning: number; }

interface Plot {
  id: string;                        // 'p01' … 'p20'
  crop: CropKey | null;
  progress_ticks: number;            // 有效生長 tick 數
  mature: boolean;
  dead: boolean;
  consecutive_unirrigated_ticks: number;   // 0–3
  irrigated_last_tick: boolean;
}

interface CrewState {
  id: string; name: string;
  food_energy: number;               // 遊戲 kcal，容量 3000
  water: number;                     // L，容量 2
  alive: boolean; death_reason?: 'food_energy' | 'water' | 'oxygen';
  location: string;                  // 區域 id
  current_task: 'idle' | 'walking' | 'generating' | 'water_plant' | 'irrigation_console'
              | 'planting' | 'harvesting' | 'clearing' | 'eating' | 'drinking' | 'dead';
  work_this_tick: number;            // 實際發電工作量 0–1
}

interface TickSummary {               // 每 tick 結算摘要，供前端飄字與 Agent Observe
  tick: number;
  refills: { crew_id: string; kind: 'food' | 'water'; amount: number }[];
  generation: { requested: number; actual: number; power_out: number; oxygen_used: number };
  water_plant: { requested: number; actual: number; power_used: number; oxygen_used: number };
  irrigation: { attempted: string[]; succeeded: string[]; failed: string[]; water_used: number; power_used: number };
  oxygen_produced: number; oxygen_overflow: number;
  harvested: { plot_id: string; crop: CropKey; food: number }[];
  planted: { plot_id: string; crop: CropKey }[];
  cleared: string[];
  plots_died: string[];
  deaths: { crew_id: string; reason: string }[];
}

interface WorldState {
  version: number;
  tick: number; paused: boolean; speed: number;
  failed: boolean; failure_reason?: string;
  resources: Record<ResourceKey, ResourceState>;
  pending_oxygen: number; pending_food: number;    // 下一 tick 才入庫
  plots: Plot[];
  crew: Record<string, CrewState>;
  settings: { water_production_l: number; generation: Record<string, number>; irrigation: string[] };  // 沿用中的連續設定
  last_summary: TickSummary | null;
}

interface AgentThought { id: string; ts: number; tick: number;
  agent: 'core' | 'plant' | 'human';
  kind: 'observe' | 'risk' | 'advice' | 'plan' | 'validation_error' | 'reflection';
  text: string; payload?: unknown; }

interface WorldEvent { id: string; tick: number;
  type: 'crew_low_supply' | 'resource_low' | 'plot_unirrigated' | 'plot_critical' | 'plot_died'
      | 'oxygen_overflow' | 'harvest_blocked_capacity' | 'crew_died' | 'mission_failed'
      | 'plan_failed' | 'player_edit';
  target?: string; detail: Record<string, unknown>; }
```

Crop 參數表（§3.3）以 `shared/crops.json` 單一檔案提供，前後端與 Agent prompt 皆由此載入，不得各自硬編。

---

## 7. WebSocket 協定

| type | 方向 | payload |
|---|---|---|
| `state_update` | S→C | `WorldState`（每 tick 全量） |
| `tick_plan` | S→C | `TickPlan`（Core 決策通過驗證後） |
| `agent_thought` | S→C | `AgentThought` |
| `world_event` | S→C | `WorldEvent` |
| `mission_failed` | S→C | `{ tick, reason, deaths[] }` |
| `control` | C→S | `{ cmd: 'pause' \| 'resume' \| 'speed'; value? }` |
| `edit_resources` | C→S | `{ water?, oxygen?, food?, power? }` |

REST：`GET /world`、`POST /control`、`POST /resources`、`POST /world/reset`、`GET /healthz`、`POST /ingest/{resource|crew|plot|event}`。

---

## 8. Demo 流程

1. **開場**：初始世界（3,000 L / 8,000 OU / 120,000 kcal / 6,000 EU；五種作物各 4 塊；四人 2,400 kcal / 1.5 L）。Core 給出第一份 TickPlan：誰發電、製水多少、灌溉 20 塊。
2. **常態運轉**：crew 在發電機、溫室、用餐區之間走動；水箱液面、電池格、氧氣環隨 tick 變化；Plant Agent 偶爾建議採收成熟的萵苣（30 tick 就熟）。
3. **玩家干預**：工具列 `⚙ 修改資源` 把 `power` 改成 300 EU。
4. **自主重規劃**：Core 觀察 → Human Agent 建議四人滿額發電但提醒誰的能量不足 → Plant Agent 建議暫停灌溉低價值地塊（例如番茄，每輪只有 1,755 kcal）保住馬鈴薯與小麥 → Core 產出 TickPlan：`irrigation` 只列 12 塊、`generation` 三人滿額一人先進食 → 驗證通過 → 執行 → 8 塊番茄／萵苣邊框轉黃 → 兩 tick 後電力回升，Core 恢復全部灌溉 → Reflection 寫入 memory。
5. **可選的失敗展示**：把 `oxygen` 改成 100 → 下一 tick 呼吸扣完 → 全員死亡 → 燈光熄滅、死亡卡。

---

## 9. 交付物

- [ ] `shared/crops.json`、`shared/types.ts`、`backend/domain/models.py`（三者同步）
- [ ] `backend/`：L1–L6，`WorldEngine.settle` 有 §11 全部數值測試
- [ ] `frontend/`：Gather 版 GameView（六區域、20 地塊、五種作物貼圖、四種資源世界物件）＋ 三處 chrome
- [ ] `checks/`：guide 提到的 7,200 tick 基準策略重播（作為回歸測試，不是 Core 的政策）
- [ ] README：tick 結算順序圖、TickPlan 範例、如何新增資源／作物／Agent

---

## 10. 圖像生成 Prompt

統一風格：`top-down 2D orthogonal pixel art, Gather Town style, 32px tile grid, flat shading with subtle dithering, muted Mars palette (rust orange, dusty ochre, cool steel grey), accents: neon green plants, cyan water, warm amber power, pale blue oxygen, no text`。**視角一律正交俯視，不得產生 isometric。**

### 10.1 主地圖
```
Top-down 2D pixel-art map of a compact Mars habitat interior, straight overhead orthogonal view, Gather Town style, 32-pixel tile grid, no perspective.
A wide GREENHOUSE across the top with a 4-by-5 grid of twenty hydroponic troughs under magenta-white LED bars and a single irrigation control console by its entrance.
Below it a cross-shaped corridor with grated floor and yellow safety stripes connecting: left — a POWER BAY with four pedal generators in a row and a wall of battery cells; right — a WATER PLANT with a tall cylindrical tank showing a liquid level strip, pipes, and a control panel; lower-right — a LIFE SUPPORT nook with a spherical oxygen tank and a round pressure gauge; lower-left — a GALLEY with a stack of food crates on pallets, a four-seat table, and a water dispenser; bottom-centre — CREW QUARTERS with four bunks.
Each room has a distinct floor tile pattern. Empty of characters. Flat lighting, crisp pixel art, no text.
```
### 10.2 五種作物 × 四階段貼圖
```
Sprite sheet of top-down pixel-art hydroponic trough tiles, 64x32 px each, five crops in rows and four growth stages in columns:
lettuce (round rosettes), potato (bushy dark-green leaves), tomato (vines with red fruit at maturity), wheat (tall stalks turning gold), soybean (low bushy plants with pods).
Stages: sprouts / young / dense / mature-ready. Plus three shared variants: empty trough (bare foam), dead crop (blackened, wilted), and a yellow-outline "unirrigated" overlay frame.
Transparent background, consistent tile size, no text.
```
### 10.3 設施物件
```
Top-down pixel-art object sprites on transparent background, 32px grid:
(1) pedal generator with a crew seat, three animation frames of the pedal turning;
(2) battery wall of ten cells, provide lit-count variants 0..10, last cell amber when low;
(3) cylindrical water tank with a side level strip, variants 100/75/50/25/10% fill, cyan liquid, low variants amber;
(4) spherical oxygen tank with an arc pressure gauge, variants full/half/low(red), plus a white vent-mist frame for overflow;
(5) food crate stack on a pallet, variants 8/6/4/2/0 crates;
(6) irrigation control console with a small screen; (7) water plant control panel; (8) floor console for the Core agent.
Flat pixel art, no readable text.
```
### 10.4 太空人 sprite sheet
```
Top-down pixel-art sprite sheet of four astronauts, ~32x48 px, slim white indoor suits with teal / orange / violet / yellow accents, no helmets.
Per character: 4-direction walk (4 frames each), idle, pedalling (seated), kneeling at trough, seated eating, standing drinking, standing at console, and a lying-down "dead" pose in desaturated grey.
Transparent background, no text.
```
### 10.5 任務失敗畫面
```
Same top-down habitat map with all lights off except dim red emergency strips along the corridor; the greenhouse LEDs dark; four astronauts lying still in grey. A small translucent card centred on the map (placeholder glyphs). Quiet, sombre, no text.
```

---

## 11. 驗收標準

**數值驗收（`WorldEngine` 單元測試，必須全部通過）**

| 案例 | 期望 |
|---|---|
| 一塊 potato 採收 | `food += 8,775` |
| 一塊 lettuce 採收 | `food += 585` |
| 製水請求 174 L，資源充足 | `water += 174`，`power −= 348`，`oxygen −= 34.8` |
| 製水請求 400 L | 實際 250 L |
| 四人請求工作量 1，資源充足 | 個人各 `−100 kcal`，`oxygen −= 100`，`power += 1,000` |
| 四人滿額 + 基礎消耗（不含植物製水） | 每 tick 合計 909 kcal、249.166667 OU、0.536167 L |
| 某人基礎消耗後能量 150 | 其工作上限 1.5 → 夾為 1；若能量 80 → 上限 0.8 |
| 20 塊全部灌溉成功 | `water −= 174`，`power −= 100` |
| `irrigation` 只列 12 塊 | 另 8 塊計數 +1、不扣水電、不產氧 |
| 某塊連續 3 tick 未灌溉 | 該塊 `dead = true`，同 tick 不可採收 |
| 第 2 tick 未灌溉後第 3 tick 恢復 | 計數歸零、進度保留 |
| 氧氣 8,000 + 20 塊產氧 > 15,000 | 入庫至 15,000，`oxygen_overflow` 記錄餘量 |
| 本 tick 產氧 | 本 tick 不可用於呼吸／發電；下一 tick 才入庫 |
| 本 tick 發電 | 本 tick 可用於製水 |
| 食物容量剩 500，採收 potato | 不採收，作物保持成熟，發 `harvest_blocked_capacity` |
| 進食請求 1,000，公共 food 300，個人剩餘容量 800 | 轉入 300，該 crew 本 tick 仍占用 |
| 某人 `water = 0.1`，基礎消耗後 ≤ 0 | 立即死亡、`mission_failed`、後續 phase 不執行 |
| 公共 oxygen 恰好被呼吸扣到 0 | 全員死亡，不等植物產氧 |
| 玩家把 oxygen 設 0 | 立即全員死亡 |
| 暫停 5 個真實 tick | 灌溉計數不變、庫存不變 |
| 同一 crew 同 tick 採收＋播種 | `SAME_CREW_HARVEST_AND_PLANT` |
| 同一 crew 進食 + generation 0.5 | `CREW_DOUBLE_BOOKED` |
| PlantAgent 提出「總是先灌溉馬鈴薯」寫進 prompt | 測試失敗（prompt 中不得有分配政策） |

**前端驗收**

- 啟動後畫面上沒有常駐儀表板；只有地圖、角色與三處 chrome。
- 不看任何 GUI 即可從世界讀出四種資源：水箱液面、電池亮格、氧氣壓力環、儲藏堆層數。
- 20 塊地各自呈現作物種類與成熟度；未灌溉 1／2 tick 的邊框變化與死亡貼圖可辨識。
- 發電時能看到誰在踩、踏板轉速差異；製水時管線有流光。
- 用 `⚙ 修改資源` 把 `power` 改 300 後，5 秒內 Agent 氣泡依序浮現在對應設施上，30 秒內看到 TickPlan 生效（部分地塊邊框轉黃、更多人走去發電機）。
- 任務失敗時世界仍可見（燈光熄滅但不遮罩），死亡卡顯示原因與 tick。
- 新增第六種作物只需：`shared/crops.json` 加一列＋一組貼圖；不改任何程式邏輯。

---

## 12. 與 v1 的差異與既有程式碼處置

| 面向 | v1（2026-09-10） | v2（本文件） | 既有程式碼 |
|---|---|---|---|
| 資源 | wheat kg + water L | water / oxygen / food / power | `backend/simulation/*` 全部重寫；`domain/models.py` 重寫 |
| 作物 | 只有小麥，plot 可變面積 | 五種，固定 20 塊 × 5 m² | `wheat_model.py` → `crops.py` + `shared/crops.json` |
| Crew | hunger / hydration / health / fatigue | food_energy / water，無 health | `crew_model.py` 重寫；前端 crew 卡片重做 |
| 灌溉 | `set_irrigation(level)` 比例 | 自動、每塊 8.7 L + 5 EU、3 tick 死亡、Core 排序 | 移除 `set_irrigation` 工具 |
| 預測 | Forecaster 72h 模擬 | **無** | `forecaster.py` 移至 `_legacy/`；`MissionAgent` 的 simulate 步驟移除 |
| 安全機制 | ConstraintGuard 拒絕越線動作 | PlanValidator 只驗可行性；死亡是後果 | `constraints.py` 重寫為 `plan_validator.py` |
| Agent | Mission / Crop / Water | Core / Plant / Human | `agents/` 重寫；prompts 重寫 |
| 工具 | 8 個（含 run_simulation） | `set_generation`、`set_water_production`、`plant`、`harvest`、`clear`、refill（待定） | `registry.py` 重寫 |
| 結束 | 500 天任務 | 持續運行，死亡即結束 | `MissionLoop` → `WorldLoop`；徽章移除 `/ 500` |
| 玩家 | INJECT EMERGENCY | 修改資源 | 工具列改 `⚙ 修改資源` |
| Tick 實時 | 1 s | 2 s | constants |
| 前端 | Gather 版（已完成） | Gather 版，區域從 4 個改 6 個、物件全換 | `scene.ts` / `world_objects.ts` 大改；`waypoints.ts` 重畫；chrome 三元件小改 |
| 可保留 | — | L1 REST/WS 骨架、EventBus、StateRepository、Ingest、`overlay/bridge.ts`、氣泡／抽屜／tooltip 元件、walk 系統、mock server 骨架 | 直接沿用 |

**尚待 guide 補齊、實作時以 `TODO(guide-pending)` 標記**：進食／飲水正式接口、飲水點位置、`clear` 前端入口、設備故障事件。
