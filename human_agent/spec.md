# Human Agent — 最終重建規格

規格版本：4.0｜日期：2026-09-11｜目標世界：world rules v0.12｜Human API schema：2.0

> 給 Codex：閱讀本檔後直接建立或修改專案，完成程式、測試、文件與 HTTP 串接範例。此檔已包含重建 Human Agent 所需的世界常數、結算順序、API 與驗收條件，不必依賴先前聊天或舊 spec。不要只交計畫。
> 本檔是新世界的實作規格，不是已完成實作的證明。來源文件所載的舊測試結果只作遷移參考，新 API 與世界規則必須重新驗證。

## 1. 來源、優先順序與本次範圍

本規格整合兩份使用者附件：

1. `3f2e61c4-7543-42ea-a869-646cc7a869f1.md`：**世界共用設定：資源、轉換公式、Crew 互動，v0.12，2026-09-11**。世界數值、資源單位、死亡條件、工作占用與結算順序以此為準。
2. `6817b305-2aa3-4821-8183-fdf73fbfc6f1.md`：**Human Survival Agent v3.0，含 2026-09-09 實作狀態**。沿用可驗證的檢索、provider、快取與 HTTP 工程；移除與新世界衝突的舊模型。

世界文件提到的 `world-rules-spec.md`、世界程式、checks 腳本及舊 corpus 並未隨本次附件提供。本檔不假裝已讀過它們。Codex 若在重建目錄找到相關檔案，先比對；若與 v0.12 矛盾，記錄至 `docs/integration_notes.md`，不得默默更改遊戲公式。缺少檔案不阻止按本規格建立獨立服務。

權責：

| 元件 | 責任 |
| --- | --- |
| Human Agent（本次實作） | 分析公共資源與四人的個人存量、補給時效、工作負荷、下一 tick 的消耗風險，回傳建議與依據 |
| Core Agent（隊友） | 決定四人工作、補給份額與順序、製水量、灌溉分配、種植策略；判斷何時重新規劃 |
| Plant Agent（隊友） | 作物領域分析、種植／採收建議 |
| 世界後端（隊友） | 唯一實際狀態來源；驗證並執行每個 tick，扣資源、增加產出、判死亡 |
| 前端（隊友） | 畫面與動畫；不決定或重複執行結算 |

Human Agent **不執行世界操作、不呼叫 Plant、不更新 state、不控制暫停、不排定或自動採用整體策略**。本次不建立完整世界引擎、前端、預測 Simulator、多 tick 搜尋規劃器或健康值系統。

本檔第 5 節的「單 tick 核算」只是輸入快照與明確安排的純函式算術檢查，輸出帳目與風險；不提供世界 step API，不推進時鐘，也不預測作物未來收成。

## 2. 必須取代的舊設計

| 舊版 | 本版 |
| --- | --- |
| `crew.count` 與一份公共水／食物庫存 | `crew[]` 四名個體＋公共 `resources`，兩種存量分開 |
| L、真實 kcal、kg O₂、day 為主 | L、**遊戲 kcal**、OU、EU、tick；tick=1 模擬小時 |
| mission.remaining_days、任務完成覆蓋率 | 持續運行；移除通關期限、成功穩定計數 |
| 公共 water 扣 reserve 再算存活天數 | 警戒線只提示，不保留扣款；個人水／能量與公共氧氣決定死亡 |
| 水回收率／外部流入作核心模型 | 依 v0.12 的製水公式；不增加污水、採冰、Sabatier 或氫氣模型 |
| 熱量與產氧平滑成每日淨流量 | 按 tick 的明確階段；食物只在成功採收時入庫 |
| 隨意提高產量／回收率的 override | 只核算合法補給、工作量、製水請求；作物分配交 Core／Plant |
| `estimated_resource_support_days` | 個人「不補給餘裕」＋下一 tick 階段風險，明示假設與未覆蓋範圍 |
| scientific／demo profile 決定計算常數 | **world_v0_12** 唯一正式遊戲規則；科學文獻提供來源與限制，不覆寫遊戲 |

`POST /human-agent/analyze` 路徑保留，但 input／output 改為 schema 2.0。舊 schema 1.0 回 422 並提示遷移，不能把舊 oxygen_kg、每日產出或 crew count 猜成新 state。提供 `docs/api_migration.md`。

## 3. 世界規則快照：精確實作，禁止自行再平衡

將本節常數集中至 `data/world_rules_v0.12.json` 或等效 typed config，產生 rules_hash；計算器、prompt 與範例共用，不在不同模組重抄常數。若已有團隊共用 rules package，優先讀取同版本且核對 hash 的資料。

### 3.1 單位、時間與公共庫存

| key | 單位 | 初始值 | 容量 | 警戒線 |
| --- | --- | ---: | ---: | ---: |
| water | L | 3000 | 4000 | 400 |
| oxygen | OU | 8000 | 15000 | 600 |
| food | 遊戲 kcal | 120000 | 200000 | 12000 |
| power | EU | 6000 | 10000 | 1000 |

- 四種資源使用實際數量，不能用前端百分比結算；不得產生負庫存。
- 警戒線不是禁止使用的 reserve，不能先從可用資源扣除。個人低存量事件條件見下節。公共線的 UI 邊界未精訂；Human 顯示採 `< 警戒線` 為 low、等於為 at_threshold，這是顯示約定，不更改世界扣款。
- 公共 water／food／power=0 不直接判 crew 死亡。公共 oxygen<=0，所有存活 crew 立即死亡；任一 crew 死亡即任務失敗。
- 1 tick=1 模擬小時，預設每 2 秒現實時間推進。**人類日需求除以 24；只有作物文獻 1 天壓縮為 1 個有效生長 tick**。暫停、Core 規劃、錯誤暫停時不結算。
- OU、EU 與遊戲 kcal 屬遊戲單位。本模型非物理封閉系統，不以真實能量守恆改寫係數。

### 3.2 四名 crew 的個人資源

| 項目 | 個人初始值 | 個人容量 | 低存量條件 | 每次補充請求上限 |
| --- | ---: | ---: | --- | ---: |
| food_energy（遊戲 kcal） | 2400 | 3000 | <700 | 1000 |
| water（L） | 1.5 | 2 | <0.4 | 0.5 |

初始公共值和個人值分別給定，不從公共初始值再扣個人初始值。不使用 Crew Health、體重個別化、疾病或職業加成。

固定基礎消耗：

```text
每人能量／tick = 3054 / 24 = 127.25 遊戲 kcal
每人水／tick   = 3.217 / 24 L
每人氧氣／tick = 0.895 * 1000 / 24 OU

四人能量／tick = 509 遊戲 kcal
四人水／tick   = 3.217 / 6 L
四人氧氣／tick = 895 / 6 OU
```

世界文件將 3054、3.217、0.895 定為不得變更的文獻基準，舊實作報告追溯至 BVAD Table 3-31；在本次未重新取得原文前，來源狀態是「世界已定、舊報告稱核對過」，不能宣稱本次重新科學驗證。即使文獻不完整，遊戲常數仍能使用，並註明來源缺口。

基礎能量與水扣個人；呼吸扣公共 oxygen。每次消耗使個人任一值<=0即死。即使補給安排在同 tick，補完仍不足以支付基礎消耗也會死亡。已死亡者不得補充復活。

### 3.3 補給與工作占用

進食／飲水：實際轉入 = min(請求量, 該次上限, 公共可用庫存, 個人剩餘容量)。公共減多少、個人加多少，轉移不算另一筆代謝消耗。

| 工作 | 占用 | 額外個人消耗 |
| --- | --- | --- |
| eat | 一人一 tick，可四人同時，但共享不足時需 Core 順序 | 無；仍有基礎消耗 |
| drink | 同上；同人不能同 tick 又吃又喝 | 無；仍有基礎消耗 |
| generate | 一人一 tick，請求工作量 0–1，四個位置 | 100 遊戲 kcal／實際工作單位 |
| plant / harvest / clear | 每塊一人一 tick | 無；仍有基礎消耗 |
| idle | 不工作，仍有基礎消耗 | 無 |
| 製水／灌溉控制台、移動動畫 | 不占工作 tick，不另扣資源 | 無 |

一人同 tick 只能一項占用工作，部分發電不能再搭配播種或補給。縮量或零量補給仍占該 tick；已安排的作物工作即使執行失敗，也不能由 Human 自動改為發電。四人並無固定職業能力。

Core 決定補給對象、量與順序；Human 可建議危急者先補，但不得把它偷偷當作世界自動政策。沒有排程不等於四人會自動吃喝或自動滿額工作。

### 3.4 發電與製水

發電每工作單位：**100 遊戲 kcal 個人能量＋25 OU 公共氧氣 → 250 EU 公共電力**。不是早期 125 EU。

在補給、基礎消耗與呼吸均完成且未失敗後：

```text
a_i = min(requested_work_i, 1, personal_energy_after_base_i / 100)
      # 只對該 tick task=generate 的存活 crew 計算，其餘為 0
A = sum(a_i)
W = min(A, public_oxygen / 25, (10000 - public_power) / 250)
w_i = 0 if A == 0 else W * a_i / A

個人能量_i -= 100 * w_i
公共 oxygen -= 25 * W
公共 power  += 250 * W
```

共享限制造成縮量時，**按 a_i 比例分配**是此階段固定公式，不是 Core 自訂排序。不得用他人能量付費、不得再扣公共 food。

世界公式允許恰好用盡個人能量／氧氣，之後立即判死；計算器不得私自縮量「保命」。Human 的建議需明確降低工作請求或保留餘裕，但 execution 真正決策由 Core 負責。發電的額外消耗是遊戲設定；不再自行添加工作用水。

製水：**2 EU＋0.2 OU → 1 L 水**。

```text
actual_water = min(requested_liters, 250, public_power / 2,
                   public_oxygen / 0.2, 4000 - public_water)
public_power  -= 2 * actual_water
public_oxygen -= 0.2 * actual_water
public_water  += actual_water
```

只按實際量扣款，並立即檢查公共 oxygen。設備不可用時產量 0；設備狀態未知時結果 unknown，不暗中視為正常。本版不追蹤污水、氫氣或其他原料，不加入回收率與外部補給。

### 3.5 植物的已知交換規則（作人類風險背景）

固定背景：22°C、65% RH、CO₂ 500 ppm、光強 250 µmol/m²/s、14 h/day 光週期。無對應調整工具、不另算維持背景耗電，不加日夜變化。

20 塊地，每塊 5 m²，初始五種各四塊。密度 27 plants/m²=135 plants/塊，只供背景，以下每塊數值不得再乘株數／面積。

每存活已種地塊，每成功供應 tick：**8.7 L＋5 EU 原子性扣除**，生長+1、產氧。缺任一完整配額／庫存時兩者皆不扣，不生長、不產氧，consecutive_unirrigated_ticks+1；成功則歸零。連續失敗 1 tick 通知、2 ticks 危急、3 ticks 當下死亡不可採收。空地／死地不消耗、不產氧；成熟未收成仍需灌溉且成功時持續產氧。

| crop_type | 成熟有效 ticks | OU/tick/塊 | 產量 g/m²/day | 遊戲 kcal/g | 每塊完整收成（遊戲 kcal） |
| --- | ---: | ---: | ---: | ---: | ---: |
| lettuce | 30 | 16 | 19.5 | 0.2 | 585 |
| potato | 90 | 16 | 16.25 | 1.2 | 8775 |
| tomato | 90 | 22 | 13 | 0.3 | 1755 |
| wheat | 90 | 10 | 9.75 | 3.0 | 13162.5 |
| soybean | 90 | 12 | 6.93 | 3.9 | 12162.15 |

收成公式=產量×5×成熟 ticks×1×遊戲熱量係數，不再除／乘24，不追加鮮乾重／可食比例。只在採收成功一次入 food；容量放不下完整一塊則不採收；成功地塊清空，重種後下一 tick 開始長。不得把成熟前的潛在收成預支給 crew。

灌溉對象、配額與執行順序由 Core 決定，不能自行固定地塊排序或平均分配。只有完整供應才有效，無灌溉比例滑桿。省水可藉減少種植面積，Human 只能提出需求／風險，由 Plant／Core 選地塊。clear 有底層能力但前端入口待定，不能假稱 UI 已可用。

### 3.6 一個 tick 的先後順序

1. 按 Core 安排先處理進食／飲水，共享不足時按明確順序轉入。
2. 扣個人基礎能量、水與公共呼吸，做立即死亡檢查。
3. 未被補給或作物工作占用、且 task=generate 的 crew 發電，立即死亡檢查。
4. 製水，立即公共缺氧檢查。
5. 按 Core 分配灌溉、作物生長、產氧；超過氧容量部分流失。
6. 按 Core 明確順序採收／清除／播種，各由指定 crew 完成，世界驗證地塊狀態。

任一階段死亡就停止該 tick 後續階段。**同 tick 新電可製水、新水可灌溉；新產氧與新收成不能救回較早階段已死亡的人。** 同 tick 新水也不能回到已完成的飲水階段。

基礎消耗內部的跨 crew 與資源扣款微順序、發電致死時最後帳目如何提交未由來源細定；本模組記錄所有可判定的致命條件與最早「階段」，不自創誰先死的微順序。發現該階段必死時，不發布假裝精確的末端完整世界 state。世界後端實際事件才是權威。

## 4. Human API：可獨立實作的 adapter 契約

### 4.1 路由與快照規則

- `GET /health`：不付費探測 provider，顯示設定／索引／規則版本。
- `POST /human-agent/analyze`：唯讀同步分析。Core 負責送同一時點的一致 snapshot；計畫若有則為**下一個未結算 tick**。
- Swagger `/docs` 與 `/openapi.json`。
- HTTP 200：分析成功或有清楚 unknown／降級；422：錯版、格式／單位／欄位錯誤、無效計畫；500：非預期服務錯誤，回 request_id 不含秘密。

以下是 **Human Agent 提出的 adapter DTO**，不是聲稱隊友正式 API 已定。Core 可將自身欄位映射到此契約；提供 JSON Schema 與一個純映射範例，缺少正式世界介面也能獨立測試。補給／灌溉正式工具名與 payload 仍待團隊對齊。

### 4.2 最小有效輸入

```json
{
  "schema_version": "2.0",
  "request_id": "human-demo-001",
  "state_id": "state-0-r1",
  "world_rules_version": "0.12",
  "tick": 0,
  "snapshot_phase": "between_ticks",
  "world_status": "paused",
  "resources": {"water": 3000, "oxygen": 8000, "food": 120000, "power": 6000},
  "crew": [
    {"id": "crew-1", "alive": true, "food_energy": 2400, "water": 1.5},
    {"id": "crew-2", "alive": true, "food_energy": 2400, "water": 1.5},
    {"id": "crew-3", "alive": true, "food_energy": 2400, "water": 1.5},
    {"id": "crew-4", "alive": true, "food_energy": 2400, "water": 1.5}
  ],
  "plots": null,
  "water_production_available": null,
  "next_tick_plan": null,
  "analysis": {"include_recommendations": true}
}
```

- 必填：version、request_id、state_id、tick、snapshot_phase、world_status、resources、crew。crew 必須恰好四筆、id 唯一；alive 必填；世界存量欄位可為 null（未知），不能省略後默認初始值。初始值僅供明確初始化 fixture 使用。
- `world_status`：running / paused / planning / error_paused / failed。暫停仍可分析「恢復後下一 tick」，不得真的扣資源或以現實經過時間補扣。status=failed 或 alive=false 任一筆，分析標 already_failed，不產生復活或可執行的補救計畫。
- 數值 finite、非負、存量不超過第3節容量；拒絕 NaN、Infinity、負庫存與重複 crew ID。`snapshot_phase` 只接受 between_ticks；中途階段必須先由 Core 轉成一致快照，不猜測已扣哪些費用。
- alive=true 但 energy／water=0，或 oxygen=0：回傳 world failure 條件與狀態不一致 warning，不讓安排進食將其「救活」。未知 alive 不接受；未知存量可 partial。
- extra 欄位預設 forbid；本契約不接收 oxygen_kg、電量百分比、remaining_days 或 recycling_efficiency。若需要前端 metadata，放獨立明訂且不參與計算的欄位，不能從自由文字讀數改規則。
- `plots=null` 代表沒有植物明細；`plots=[]` 不代表20塊空地，視為不完整。提供時要有20個唯一 id，否則回422。每塊 `{id, status, crop_type, growth_ticks, consecutive_unirrigated_ticks}`；status=empty/growing/mature/dead。空地 crop_type=null；其餘為五種 enum；growth_ticks 使用非負整數且不超過成熟 ticks；mature 必須等於成熟值。活地失灌計數0–2，dead 可為3或其他世界死亡原因。未知植物資料整組用 null，不編造初始成熟度。
- `water_production_available` 為 true / false / null，由 Core 映射設備實際可用性。本版未增加發電機故障／電力影響 crew 生命維持的額外公式。

### 4.3 下一 tick 計畫（可選）

```json
{
  "for_tick": 1,
  "crew_tasks": [
    {"crew_id": "crew-1", "task": "eat", "amount": 1000},
    {"crew_id": "crew-2", "task": "drink", "amount": 0.5},
    {"crew_id": "crew-3", "task": "generate", "work_fraction": 1},
    {"crew_id": "crew-4", "task": "idle"}
  ],
  "refill_order": ["crew-2", "crew-1"],
  "water_production_request_liters": 174,
  "irrigation_allocations": [],
  "crop_operation_order": []
}
```

這段物件放入 `next_tick_plan`；示例 irrigation_allocations=[] **明確表示這個 tick 不給任何地塊配額**，不是自動全部灌溉；若有活作物會有停長／停氧與失灌風險。

- `for_tick=tick+1`。`crew_tasks` 四人各一筆，task 為 idle / eat / drink / generate / plant / harvest / clear。使用 discriminated union；eat/drink amount>0且不超過上限、generate work_fraction介於0–1；作物工作需 plot_id，plant 另需 crop_type。禁止無關 payload 或同人重複。無整份 plan 可分析個人餘裕，但有 plan 就必須完整指定四人，不默認未列者發電。
- `refill_order` 恰好列出所有 eat/drink crew ID，一人一次；即使資源充足也保留順序，不由引擎／Human 自排。空陣列只在沒有補給任務時合法。
- `water_production_request_liters` 必填且>=0，允許請求大於250並按設備上限縮量。
- `irrigation_allocations` 可為 null（未知）或陣列。每項 `{plot_id, water_quota_liters, power_quota_eu}`；陣列順序就是 Core 執行順序，plot_id 不重複。quota 非負，僅達8.7 L及5 EU才有資格供應，成功只扣固定8.7／5，不消耗多餘配額；未列的活地視為當 tick 未分配。null 時不能推定供應結果；不得自動平均配額。
- `crop_operation_order` 恰好列出 task=plant/harvest/clear 的 crew ID，依序執行語意由世界控制。同地塊可多個不同 crew 操作，但需逐項合法；Human 只驗占用、引用與可明確識別的前提，不為它建造作物操作模擬器。
- world fields 缺資料導致預估 unknown 不等於422；結構不合法／重複任務／錯 tick 才是422。明確安排合法但會導致死亡，應回200＋critical分析，不把致命決策隱藏成格式錯誤。
- 若 `plots=null`，作物 task 的對象／成熟合法性與灌溉結果標 unknown；人員被作物工作占用仍是已知，可照算不能發電。

## 5. Deterministic 分析：數字由工具產生

### 5.1 個人餘裕與補給風險

至少輸出每人：目前值／比例、low flags、idle_no_refill、requested_work_no_refill、下一 tick 補給後數值、基礎後數值、實際工作量與致命條件。

```text
idle_energy_rate = 127.25
idle_water_rate = 3.217 / 24
requested_energy_rate = 127.25 + 100 * requested_work_fraction
continuous_margin = stock / rate
first_fatal_tick_offset = ceil(stock / rate)  # stock>0、rate>0
safe_complete_ticks = first_fatal_tick_offset - 1
```

stock<=0為已死亡條件，first_fatal_tick_offset=0，safe_complete_ticks=0。未知值回null及reason。tick餘裕可轉同值模擬小時；不以2秒動畫速度推算現實存活時間。若 E=2×127.25，第二次扣款恰好歸零即死，安全完整tick數為1，不是2。

`requested_work_no_refill` 是假設請求工作量固定且共享資源充足的耗用估算；不是實際未來工作結果，也不是生存保證。當 tick 不是 generate，使用0；plan缺失時這個欄位unknown，仍可輸出idle_no_refill。不把四人平均值取代最短個人餘裕。

另計 `oxygen_respiration_only`=公共O₂／(895/6)，附相同致死tick語意，明示只含呼吸、不含發電製水及植物產氧。公共食物／水不能直接相除推斷個人死亡，必須考慮補給占用與可達量。

### 5.2 下一 tick 核算

以 state 副本按第3.6節計算，函式例如 `audit_next_tick(snapshot, plan)`。這是 Human 領域預檢，不是對外世界 Simulator；不可輸出新世界供 Core 當權威 state。

必須做：

1. 先檢查當前終止條件；已失敗立即停止後續核算。
2. 依 refill_order 原子轉移公共水／food至個人；記錄 requested、actual、capacity_limited／stock_limited；未來製水／收成不得用於此步。
3. 計算個人基礎扣款與公共呼吸，任何消耗不夠或恰好歸零判critical。回最早fatal_stage=base，停止後續核算；後續欄位為 not_reached，不能算植物產氧把O₂補回。
4. 遵守占用算 a_i、W、w_i；共享限制依比例縮量；若個人或公共值恰好耗盡，fatal_stage=generation，停止。
5. 核算製水資源與上限，fatal_stage=water_production 時停止。若 availability 或依賴存量未知，標 incomplete 並停止依賴鏈，不能拿0假裝已知。
6. 若完整植物資訊及分配已提供，可做**當 tick 供應帳目**：按序原子扣水電、統計成功地塊產氧、溢出及失灌計數達3風險。只報供應與「該 tick 將失灌／達死亡規則」，不建立多tick植物狀態、收成排程或執行採收。沒有完整資料即unknown，不自行分配。
7. 作物工作只標明占用與尾段依賴：成功收成與新播種由世界執行；輸出 `coverage_end=after_irrigation_before_crop_operations`。不輸出 `world_safe=true`，通過僅代表已核算範圍內沒有致命條件。

中途遇到 unknown 時，依賴它的後續量也unknown；獨立結果仍回傳。工具回傳 stage_results、consumption／transfer ledger、known_after_values、fatal_conditions、unknown_dependencies、scope_limitations，不混淆 hypothetical 與 actual。

基礎與比例共享階段可能同時有多項致命條件，輸出陣列，不因本地 crew 排序創造死亡優先序。fatal stage 的完整「最終帳目」如需精確對接，需世界引擎規定微順序後再加；當前只輸出可確定數值與全部致命條件。

### 5.3 人力與系統壓力

- 計算當 tick 各 task 人數，補給／作物占用人數、可發電請求人數、requested／actual工作總量、滿額產電上限與實際值。**四人1000 EU只是一tick上限，不是長期保證**。
- 對完整活地資料回報滿供需水8.7×活地數、需電5×活地數；實際成功供應另列。缺地塊明細時不默認全部20塊存活。
- 可算維持目前種植面積的平均補水／耗電壓力，但需標 `steady_rate_reference`，不當排程或完整生存預測。
- 五種各四塊都成功供應時：需水174 L、需電100 EU、產氧304 OU。補回174 L需348 EU及34.8 OU。若另平均補回四人基礎用水，製水目標=174+3.217/6 L、植物加製水耗電=449.072333… EU/tick；這不代表每tick剛好有該補給轉移量，個人飲水是離散0.5 L請求。
- Human 可告知 Core「補給會減少當 tick 發電人數」「維持種植面積有這些供水需求」，不可自行清除作物、提高光強、增加產氧係數或觸發不存在的工具。

### 5.4 風險與規則依據

`severity=critical`：已死亡、下一tick已知致命條件、或失灌計數已2且安排將再失敗（植物即將死亡，impact_domain=plant_dependency）；`warning`：個人或公共低存量、設備限額、工作與補給競爭；`unknown`：必要資訊缺失；`info`：其餘說明。

區分 entity_id、resource、phase、tick_offset、trigger_values、rule_ids、evidence_ids。警戒線只提示，不令API自動執行補給。風險分類屬報告規則，不是策略。

遊戲critical可直接引用 `world_rule`，不要求 NASA 證明「個人遊戲能量歸零即死」。科學文獻不足不能刪掉由固定規則算出的critical。LLM不得改掉工具產生的critical或自行添加無依據的精確天數。

## 6. LLM 的 Agent 流程與合法建議

Runtime 使用 OpenRouter `anthropic/claude-sonnet-4.6`，embedding 使用 `voyageai/voyage-4`，均可由.env配置。Codex是開發工具，不是此服務執行時的大腦模型。

工具：

| 工具 | 用途 |
| --- | --- |
| `get_world_rule(rule_ids)` | 按ID取得版本化遊戲公式與條件，不依embedding猜常數 |
| `retrieve_evidence(query, top_k)` | 查科學 corpus，回原文片段與來源；不得更改規則 |
| `audit_human_plan(plan)` | 第5節單tick核算；只接受本輸入state副本與合法替代計畫，不改存量／規則 |

流程：Validate → deterministic baseline → LLM辨識風險／查規則與相關文獻 → 提出最多3條建議 → 核算可量化的補給／工作／製水候選 → 後端驗證與組裝JSON。

- baseline包含個人餘裕與已有 next_tick_plan 核算；缺plan不當成idle世界策略。
- include_recommendations=false：跳過LLM與動態檢索，直接回計算與固定依據，retrieval=not_used。
- Live且需要建議時，至少實際呼叫一次情境相關retrieve_evidence；固定附來源不算動態RAG。合理結果也可能是「查無直接科學支持；依世界規則提出」；不得為了滿足引用捏造資料。
- 需要量化效果的建議須附工具核算結果，沒有工具計算則expected_effect=null。結果以當tick個人餘量、實際發電／製水與致命條件變化表示，**不用「延長X天」**。
- Human可提出給Core考慮的補給／工作／製水候選，不能直接執行。候選 `proposal_kind` 使用 eat / drink / adjust_generation / adjust_water_production / reserve_crew_for_refill / request_plant_review；這些是**建議語意**，不是已存在的世界HTTP工具名。
- 可以改完整plan中的crew補給／generate／idle與製水請求；不得動現有plant／harvest／clear占用、irrigation_allocations、crop_operation_order，除非Core另給明確替代計畫。欲挪用已分配給作物工作的crew，回 request_coordination，不自動釋放。
- 缺 baseline plan 時可提出需求／優先建議，不自動合成完整四人世界安排；無完整候選就不呼叫完整tick核算，不標verified。
- 同一人能量和水都不足下一次基礎消耗時，一tick只能吃或喝。若兩者都必須補才能存活，回「本動作空間下無可行補給方案」與critical，不能同tick兩補、跳過代謝或假設可復活。
- 每條建議有proposal_id、target_crew_ids、proposed_changes、reason、constraints、coordination_needed、feasibility（verified_for_audited_scope / requires_core_coordination / unverified / infeasible）、rule_ids、evidence_ids、audit_result_id（可null）。完整plan可供Core人工／程序審核，但永不自動套用。
- 不輸出隱藏思考鏈；tool_trace只包含工具名、公開輸入、摘要、引用與耗時。
- 最多4次LLM、8次工具、總45秒（沿用舊實作的現場建議），為最終結構化回覆保留時間。CPU計算baseline優先，不讓LLM失敗吞掉危急分析。

## 7. Response 契約

Pydantic定義完整schema、固定欄位與nullable語意。至少包含：

| 欄位 | 語意 |
| --- | --- |
| schema_version / request_id / state_id / tick | 回顯2.0與一致快照識別；for_tick=tick+1 |
| world_rules_version / rules_hash | 實際計算用的0.12與hash |
| analysis_status | complete / partial（必要state、plan及依賴是否足以完成要求範圍） |
| execution_mode | live / mock / degraded / deterministic |
| current_world_condition | active / already_failed / inconsistent / unknown；已失敗條件優先，並附不一致warning |
| crew_assessments | 每人energy、水、low flags、不補給餘裕、計畫後數值、fatal_conditions |
| public_resource_assessment | 原始stock、capacity、threshold、status；呼吸基準、供應壓力，不能取代個人風險 |
| workforce_summary | 四人工作／補給／作物占用、requested／actual工作量、產電量 |
| next_tick_audit | status、scope、for_tick、stage_results、ledger、fatal_conditions、unknown_dependencies、limitations；沒有plan為null |
| risks | id、severity、impact_domain、entity_id、resource、phase、tick_offset、description、rule_ids、evidence_ids |
| recommendations | 第6節建議陣列，未要求或無有效輸出時為空 |
| human_requests_to_core | 個人補給需求、工作餘裕、資源競爭與需協調事項；是需求而非已核准動作 |
| evidence | id、type（world_rule / scientific_source / implementation_assumption）、title、document_id、chunk_id／rule_id、locator、source_url、excerpt、verification_status |
| retrieval | requested_mode、actual_mode（dense / bm25 / mixed / none / not_used）、fallback_reason、model、dimensions |
| corpus_version / index_version / research_status | 來源不齊可partial，與遊戲規則完整性分開 |
| assumptions / warnings / missing_fields / integration_gaps | 固定存在的陣列 |
| diagnostics / tool_trace | 耗時、LLM與embedding呼叫次數、cache hits、工具摘要；不含秘密 |

每個horizon物件明訂status=known/unknown/already_failed、continuous_margin_ticks、first_fatal_tick_offset、safe_complete_ticks、assumptions。每個audit為feasible_in_scope / fatal_in_scope / incomplete；已當前失敗為not_applicable。只在所有必需依賴已知且核算範圍無致命條件時回feasible_in_scope。

所有stage有status=evaluated/not_reached/unknown，缺值用null，不使用Infinity或把unknown當0。各種快照數值由後端組裝，LLM不得直接覆寫。`analysis_status=complete`也不代表整個任務安全。

提供一個真實跑出的normal response與一個critical response，schema與OpenAPI一致；不得把本規格手寫範例冒充執行結果。Core應在採用建議前核對state_id／tick，過期建議重新分析；Human不自行取得或修改最新世界。

## 8. Corpus、文獻與已完成資產的遷移

### 8.1 優先重用，保留歷史證據界線

舊附件報告：10份文件（9個獨立來源）、790 chunks、1024維Voyage索引、corpus-7ab79eb29b7e73d6；dense 7/7、BM25 5/7；38 passed、2 xfailed；live情境約19–27秒。**這是舊作者記錄，這次未取得程式／原文／向量，不能直接繼承為新世界驗收結果。**

Codex先檢查工作目錄是否有raw／processed／manifest／chunks／index／embedding cache／provider adapter；存在且hash與embedding policy相符就重用，勿為重建重新下載全部文獻或重嵌全部chunks。缺少則按以下程序重建。與舊世界綁定的計算器、例子、測試、prompt必須遷移，不因舊測試通過就保留。

### 8.2 世界規則與科學證據分層

- `world_rules_v0.12`是計算唯一真值；rule_id如 `crew.base.energy`、`crew.refill.transfer`、`crew.task.exclusive`、`world.oxygen.death`、`generation.proportional`、`water_production.conversion`、`plant.irrigation.atomic`、`tick.order`。所有需引用規則可按ID直接取得。
- Scientific corpus解釋人類需求來源、活動基準、飲水定義與營養限制。未取得原文的「source_checked」只能列legacy_reported，不自行認證。
- 文獻證據可能指出真實生理模型不同；記錄real_world_caveat，不修改3054／3.217／0.895或遊戲死亡規則。
- 抽象製水的2EU＋0.2OU→1L、個人容量、作物OU與3tick死亡是world_rule，不假稱NASA證明。舊水回收文獻可保存為背景，但不能產生increase_recycling建議或引入新設備。
- 移除runtime PARAMETER_PROFILE=scientific/demo切換遊戲常數；新值固定world_v0_12。若.env仍是舊值，提示遷移，不能暗中以scientific模式跑錯世界。Mock只替代外部AI，不改遊戲常數。

### 8.3 從零重建時的資料要求

先核對核心文獻與世界來源，再建檢索與分析程式。目標5–10份高相關可讀正文，最多12份；已有10份就補缺口，不擴量。最多25個候選／45分鐘初核，先到者為止，缺口標partial後繼續工程。

起點保留：NASA NTRS（https://ntrs.nasa.gov/）、BVAD 2022（https://ntrs.nasa.gov/citations/20210024855）、NASA Human Integration Design Handbook（https://www.nasa.gov/human-integration-design-handbook/）、NASA營養文獻、PubMed／PMC可取得全文。這些是來自舊規格的入口，Codex取得原文後才可引用內容。

查核問題：3054 kcal基準的對象與活動、水3.217 L包含範圍、0.895 kg O₂基準條件；飲水與總用水差異；食物遊戲能量不等於完整營養；額外發電耗能是否與文獻活動重複。不得用搜尋摘要作已核對全文。

輸出source_manifest.jsonl（title、authors、year/revision、URL、local_path、sha256、topics、access_status、exclusion_reason），parameter_review.md（世界值／來源值／適用條件／定位／核對狀態分欄），research_report.md（候選、納入、缺口與停止原因）。不繞付費牆、不編引文。

### 8.4 檢索與向量索引

- 支援PDF／TXT／Markdown，HTML可先轉帶定位文字。chunk以段落／標題／表格邊界切，300–600英文words、overlap約75words；表格保留欄名、單位與caption。
- chunks保留document_id、chunk_id、正文、來源URL、PDF實體頁與印刷頁／章節、hash。禁止用模型摘要取代所有原文。
- OpenRouter embedding `voyageai/voyage-4`、1024維；**預設input_type_policy=unspecified**，沿用舊實作已記錄的路由選擇，不改成未確認的search_query/search_document而破壞既有向量相容性。若換官方Voyage，model=voyage-4、input_type=query/document，須重建不同policy的相容索引。
- `EmbeddingClient.embed_documents`與`embed_query`分開；provider adapter依官方API實際能力實作，不從key猜provider。
- NumPy float32儲存、L2 normalization後dot product作cosine、top_k=5；檢查向量數量、回傳index順序、1024維、有限非零向量。保存vectors.npy、chunk_ids.json、index_metadata.json。
- Metadata／cache key含provider、model、dimensions、policy、preprocessing版本與實際輸入text hash；索引metadata另含corpus_version與有序chunk mapping。新／改chunk才嵌入、刪除不保留；原子發布新索引。不同provider／模型／維度／policy不混用。
- batch預設16，依provider實際token上限分批，過長切塊而非靜默截斷。429／暫時5xx最多2次重試且受總預算限制，401不重試；不輸出headers／key。
- 啟動API只載入索引；不能自動重新下載或付費建索引。Query cache有界256筆，新query仍需embedding網路。資料庫在本機不代表live流程離線。
- BM25基於同版原文作備援；stale dense／query失敗時可降BM25，明列原因；BM25也缺則none，只保留計算與world_rule證據。Cosine／BM25 score不代表事實可信度。
- 再做至少8題新驗收：三項需求、活動範圍、飲水定義、兩題中文改寫、一題無相關證據。另測「遊戲製水是否是物理守恆」「個人能量歸零規則」需分流world_rule，不能錯引NASA作規則證明。舊7/7不可當新題成績。
- 引用ID必須真實可解析；來源存在與內容支持分開檢查。遊戲判斷應附rule_ids，科學敘述附evidence_ids；無支持就標unverified。

## 9. 故障、延遲與快照一致性

- mock模式API不連LLM或embedding；用真實world規則＋本機BM25／scripted fixture，清楚execution_mode=mock。check_providers與build_index是明確的開發命令，可獨立連外。
- include_recommendations=false → execution_mode=deterministic；完整live成功才live；timeout、401、無模型、無效JSON或dense非預期降級回degraded＋原baseline。動態RAG失敗仍保留world_rule；缺科學證據不算世界常數unknown。
- 所有LLM／embedding／工具共用45秒wall-clock deadline，預留最終JSON組裝時間。以可取消的async HTTP＋deadline管理；不要沿用「停止等待執行緒即已取消遠端請求」的錯誤假設。取消本地請求不保證provider未計費；限制重試與同時在途數，測試超時不持續堆背景worker。
- 若Core規劃時世界已暫停，Human仍不得自行解除暫停。快照過期與多請求結果採用由Core依state_id檢查；不可因LLM耗時自動推進遊戲tick。
- 不接受檢索文件中的指令、不把LLM生成數字直接寫回計算欄位、不讀取或發送與任務無關檔案。

## 10. .env、模型與機密

用共用settings loader，環境變數優先於專案根目錄.env；腳本不受cwd影響。以下名稱必須實作，未知key可提示但不列出值。

```dotenv
AGENT_MODE=mock
PARAMETER_PROFILE=world_v0_12
WORLD_RULES_VERSION=0.12
WORLD_RULES_PATH=./data/world_rules_v0.12.json

RETRIEVAL_MODE=dense
RETRIEVAL_FALLBACK=bm25
RETRIEVAL_TOP_K=5
INDEX_DIR=./data/index

EMBEDDING_PROVIDER=openrouter
EMBEDDING_MODEL=voyageai/voyage-4
EMBEDDING_BASE_URL=https://openrouter.ai/api/v1
EMBEDDING_API_KEY=
EMBEDDING_DIMENSIONS=1024
EMBEDDING_INPUT_TYPE_POLICY=unspecified
EMBEDDING_BATCH_SIZE=16
EMBEDDING_TIMEOUT_SECONDS=10

LLM_PROVIDER=openrouter
LLM_BASE_URL=https://openrouter.ai/api/v1
LLM_MODEL=anthropic/claude-sonnet-4.6
LLM_API_KEY=
LLM_TIMEOUT_SECONDS=30

ANALYSIS_TIMEOUT_SECONDS=45
MAX_LLM_CALLS=4
MAX_TOOL_CALLS=8
HUMAN_AGENT_URL=http://127.0.0.1:8000
BRAIN_CLIENT_TIMEOUT_SECONDS=60
```

- **舊實作曾記錄LLM key與OpenRouter端點不匹配而401**。保留既有.env且不印key；提示使用者將OpenRouter發行的key填入對應欄位。兩個模型都走OpenRouter可由使用者填同一key，但程式不暗中用embedding key代替LLM key。
- `.env.example`只放空key；.gitignore排除.env與.env.*、保留!.env.example。規則數值不開放由任意.env覆寫，版本變更必須換rules package。
- 不必新增Anthropic直連支持來擴大範圍；若使用者明確改provider，必須實作並驗證其協定，不能只換URL就宣稱成功。Voyage官方adapter可沿用，但未測需標未測。
- 新PARAMETER_PROFILE是唯一合法正式profile；舊.env為scientific/demo時，程式清楚報設定遷移錯誤，README提供修改指令，不默默跑舊公式。
- Mock不需要兩組key；live缺key可以降級。錯的規則版本／profile屬設定錯誤，不可降級成其他世界常數。

## 11. 專案交付與重建順序

預設Python 3.11+、FastAPI、Pydantic、NumPy、BM25套件、HTTP client、pytest；沿用可用依賴並鎖版。一般工程決策自行完成，不逐階段等待使用者。

1. 盤點現有檔案／AGENTS.md／舊資產，列遷移差異；建立規則表、schema2.0與規則ID。沒有舊repo就從零建立，不假裝790向量已存在。
2. 驗證／重用文獻與cache，缺檔按第8節限額補齊，標研究缺口後繼續。
3. 純函式crew餘裕、補給、比例發電、製水、階段核算及測試。
4. API、mock、Core adapter、真實HTTP範例。
5. Dense／BM25、live工具流程、deadline與引用驗證。
6. 新世界場景驗收、README、integration_notes、實作狀態。

必須產出：

- `app/main.py`、schemas、settings、world_rules、human_calculator、plan_auditor、agent、retriever、embedding／LLM adapters。
- `data/world_rules_v0.12.json`、來源manifest、原文／chunks／索引及metadata。
- `scripts/prepare_corpus.py --local`、`scripts/build_index.py --mode dense|bm25|both [--offline]`、`scripts/check_providers.py`、`scripts/eval_retrieval.py`。
- `examples/brain_client.py`（只HTTP，不import內部app）、schema2.0 request fixtures、實際產生的response。
- `docs/api_migration.md`、`docs/integration_notes.md`、`docs/parameter_review.md`、`docs/research_report.md`、`docs/retrieval_eval.md`、`docs/validation_report.md`。
- `.env.example`、`.gitignore`、依賴檔、README、tests，以及此spec末尾追加的新實作狀態。

CLI旗標以上述名稱實作或提供相容別名；`build_index --offline`沒有完整向量cache時只允許BM25，不假裝能離線生成Voyage向量。既有不相關檔案不刪除，舊世界範例移至清楚標示的legacy目錄且預設不再使用。

## 12. 驗收：新世界案例，不沿用舊38題當結論

精確數值計算避免用表格約數作常數。建議以Fraction（十進位輸入由字串轉分數）或可與世界一致的高精度算術處理基礎率與邊界；API輸出轉有限JSON數字。死亡等號不能藉epsilon偷改成存活；若世界用浮點則將相容誤差記在整合測試而非更改規則。

| 編號 | 測試情境 | 必須驗證 |
| --- | --- | --- |
| T01 | 四人基礎需求 | food=509、water=3.217/6、oxygen=895/6，每tick不再乘24 |
| T02 | 一人2400能量、1.5 L，無補給idle | 首次energy致死offset=19、水=12；安全完整tick分別18、11；不是整體世界存活預測 |
| T03 | 上述個人請求每tick工作1、共享充足假設 | energy rate=227.25、首次energy致死offset=11；不將其宣稱為實際排程 |
| T04 | energy=254.5、idle | 第2次消耗恰好0即死，safe_complete_ticks=1 |
| T05 | crew energy=2900、公共food=50、請求吃1000 | 實轉50，轉移前後公共＋個人總和相等；之後個人扣127.25，當tick不發電 |
| T06 | 兩人energy各500、公共food1000、皆請求吃1000 | 依refill_order首人得1000、次人0且仍占用；換順序結果交換，不平均分配 |
| T07 | 同人eat+drink或harvest+generate | 無效計畫回422；合法多crew補給可並行但轉移按明確順序 |
| T08 | 某人energy=100、水=0.1，其餘公共充足 | 吃也缺水、喝也缺能量；基礎階段致死，不生出一tick兩補解法 |
| T09 | oxygen=895/6，四人呼吸 | 恰好歸零即全員死亡；後續發電、製水、植物產氧not_reached |
| T10 | 基礎後某generate crew能量50、request1、共享充足 | a=0.5，實耗50即死；不得私自降為0.49避免死亡 |
| T11 | 四人request1、能量充足、電池剩餘250 | W=1、每人0.25，各扣25個人能量；O₂共扣25、電力+250 |
| T12 | a_1=1、a_2=0.5、共享只容W=0.6 | w_1=0.4、w_2=0.2，比例分配；其他占用者0 |
| T13 | 製水request174、可用資源／容量充足 | 產174 L、扣348 EU與34.8 OU |
| T14 | 製水request300、水箱只剩10 L空間 | 實量最多10、扣20 EU與2 OU；若當時O₂恰好2則fatal |
| T15 | 公共water=0、某人water不足下一tick、安排drink；本tick會製水 | drink轉0，不能預支稍後新水；基礎階段致死 |
| T16 | 公共food=0、個人皆充足 | 不判當前死亡；成熟作物潛在收成不加入補給可用量 |
| T17 | 初始五種各4塊、全部完整供應 | 174 L、100 EU、304 OU；沒有再乘5m²或135株 |
| T18 | 地塊只分8.7L、0EU，或公共EU不足 | 水電皆不扣，失灌+1；同時缺兩者只+1 |
| T19 | mature且失灌計數2，下一次失敗 | 當tick達死亡規則、不能假設之後能採收；若恢復則計數0、成功產氧 |
| T20 | oxygen接近15000，後段作物產氧 | 入庫受上限、另列overflow；不能把overflow留作額外可用氧 |
| T21 | plan=null、plots=null或關鍵存量null | 明示partial／unknown，無自動策略；仍回已知個人餘裕 |
| T22 | world paused/planning，兩次相同snapshot分析 | 不扣任何真實資源、數值baseline一致；無現實耗時補扣 |
| T23 | 個人dead／alive但存量0、或world failed | 已失敗／不一致，不以補給復活；不輸出verified救援 |
| T24 | schema1.0、oxygen_kg、負值、NaN、錯版rules、過期for_tick | 422且清楚錯誤；不隱式轉換 |
| T25 | LLM造引用、改常數／存量、移走作物工作者 | 攔截違規部分，保留deterministic critical與原baseline |
| T26 | 401／timeout／invalid JSON／stale dense／BM25也缺 | 正確degraded、fallback原因、world_rule依然可查、無隱性key替換 |
| T27 | embedding cache與不相容policy | 原文未變0次embedding、改1段只補1段、刪除不殘留、維度改變拒混用 |
| T28 | 新request語法與response完整性 | OpenAPI一致，HTTP client可解析所有enum／null與scope，不含Infinity或秘密 |
| T29 | 初始公共／個人值、四人皆工作1、製水174、五種各4塊全部供應、無作物操作 | 到灌溉後：每人energy=2172.75、水=1.5−3.217/24；公共water=3000、food=120000、power=6552、oxygen=8020.033333…；不能重扣公共food |

測試工具內的補給／generation／製水可分開給「該階段開始值」，要在fixture標明；不得誤當整個tick起始值而漏掉base扣款。做新normal＋個人危急＋氧氣早期耗盡＋人力補給競爭＋灌溉第三次中斷等端到端案例。至少一個live案例真實完成檢索和候選核算；缺key則記未驗證。

T29 的完整fixture由Codex生成：20個唯一plot ID、五種各4個、growth_ticks=0（此fixture假設）、失灌計數0，Core明確以plot ID順序各配8.7 L與5 EU。這個順序只屬測試輸入，不能變成程式內建分配政策。上列是規格算術預期值，尚不是新程式執行結果。

不用在Human專案重建7,200tick世界迴圈來重現團隊平衡報告。來源文件已報告含採收播種占用的7,200tick可行策略，但這不證明本Human API、所有Core政策或邊界情境安全；引用為外部歷史結果，不能列入本次passed數。

## 13. 已知整合缺口與預設處理

| 未定／缺少事項 | 本版處理 |
| --- | --- |
| Core／世界正式補給、灌溉、任務API | 提供第4節DTO與建議語意，正式工具映射需隊友確認；不虛構可呼叫URL |
| 詳細world-rules-spec.md與實際世界程式 | 以附件v0.12規則建立唯讀核算，非權威世界step；後續對接以相同fixtures差異測試 |
| 基礎／發電致死時的更細扣款順序 | 判定最早致命階段與全部條件，不發布假精確終止state |
| 初始作物growth_ticks | 新normal fixture可明訂全部0作測試假設，不能當世界既定初始成熟度 |
| clear前端入口、飲水位置 | 不在Human實作UI，建議附coordination_needed |
| 舊原文、cache與程式是否隨目錄存在 | 掃描已提供的工作目錄並驗證，缺則按第8節重建，不沿用歷史done標記 |
| LAN串接 | 本次需實際測或標未測，localhost通過不等於隊友可達 |

上述缺口已能用保守明確的adapter／unknown完成獨立Human服務，不須先停止問使用者；最後報告列出讓團隊對齊的項目。

## 14. 給 Codex 的最終執行要求與 Quickstart

開始先簡短說明遷移重點，立刻建立／修改檔案；逐階段簡報後自行繼續。使用本規格取代舊水回收／每日存活模型，不因舊測試、舊.env或舊prompt保留不相容行為。不要改隊友的世界常數。

以下命令是**重建後必須支援的操作介面，尚未在本次執行**；README需依實際專案驗證並說明：

```powershell
# 在放有 spec.md 的專案目錄
python -m pip install -r requirements.txt
# 僅在沒有 .env 時由 .env.example 複製；保留既有key
# PARAMETER_PROFILE=world_v0_12、WORLD_RULES_VERSION=0.12
python scripts/prepare_corpus.py --local
python scripts/build_index.py --mode bm25
python -m pytest -q
python scripts/check_providers.py
python scripts/build_index.py --mode both
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
# 另一個終端；預設mock，測完在.env改live並重啟
python examples/brain_client.py --all
```

`prepare_corpus --local`沒有原文時要列缺檔並提示先完成文獻階段，不假成功。Provider檢查失敗仍能mock／BM25；build_index both若dense缺條件應列部分完成／非成功退出狀態，不能掩飾。

隊友LAN呼叫時服務可綁定`--host 0.0.0.0`，對方HUMAN_AGENT_URL填你電腦實際LAN位址，不能填0.0.0.0或他自己的127.0.0.1。本次不自動部署公網、不寄送訊息。

完成後追加「本次重建結果」：實際檔案、測試命令及passed／failed／未測、模型／索引版本、live／mock、資料缺口、LAN是否已驗證。附正常與critical真實response，明列本tick核算覆蓋至何處。舊38 passed與790向量只可放歷史參考，不提前勾本版done。

當天可直接貼給 Codex：

```text
請閱讀 spec.md，按 world v0.12 與 Human API schema 2.0 完成 Human Agent 重建。
先盤點並重用可驗證的 corpus、embedding cache 與 provider 程式，將舊每日資源／水回收
模型改成公共資源＋四名 crew 個人存量、tick 次序、補給占用與工作風險核算。
只做 Human Agent，不做 Core、Plant、前端或完整 Simulator。
依規格實際建立檔案、執行測試和 HTTP 範例；不要只給計畫，也不要逐階段等我確認。
保留 .env 金鑰、不輸出秘密；外部條件不足則標示缺口並完成 mock 路徑。
最後更新本次重建狀態與現場啟動步驟，不沿用舊版測試結果宣稱新版本已完成。
```

## 15. 本次重建結果（2026-09-12）

本節記錄本次實際產物與執行結果，不改動上方 world v0.12／schema2.0 規格，也不沿用舊作者的38題、790向量或7,200tick結果。

- 初始盤點：只有spec、world-settings-guide、AGENTS與.env，沒有舊程式、raw、chunks、index或cache。已从零建立獨立Human Agent。
- 已建立：`app/main.py`、`schemas.py`、`settings.py`、`world_rules.py`、`human_calculator.py`、`plan_auditor.py`、`agent.py`、`retriever.py`、`providers.py`；世界規則JSON與固定rule IDs；所有第11節必要scripts、文件、HTTP client、request fixtures、實際responses、依賴檔與測試。
- 核算：Fraction處理基礎率與歸零邊界；個人與公共分帳、Core順序補給、工作占用、比例發電、製水、當tick原子灌溉／產氧／overflow／第三次失灌風險。正常coverage_end=`after_irrigation_before_crop_operations`。未建立世界step、Core／Plant、前端或多tick Simulator。
- 規則：world0.12；rules_hash=`8cb7fc2c70beb48f7c3f2edec3819f33f4b4968f899b3e9f3eeed504ae4a2e93`。
- 設定：既有PARAMETER_PROFILE從scientific遷移為world_v0_12；既有模型、端點與金鑰值均保留。LLM為gpt-6-astra，OpenAI官方端點使用Responses工具協定；embedding為OpenRouter voyageai/voyage-4、1024維、unspecified policy。兩組provider基本呼叫均已實測成功；預設AGENT_MODE仍為mock。
- 資料：5份NASA原始PDF，SHA-256 manifest、選頁原文與393chunks；corpus=`corpus-4c40231326d1bc2b`，dense index=`index-26765ae220846386`。向量在`data/index/generations/`以immutable generation＋atomic current pointer發布。首次66個embedding batches，實際再次`build_index --mode both --offline`為0次新增embedding。
- 核心文獻：已取得並核對BVAD Table3-31及相鄰說明的可讀文字，PDF72–73／印刷58–59。3.217為飲用／食物準備與活動補充的kg日量，0.895為kg氧日量；能量原文12.778MJ對應約3054真實kcal，遊戲單位映射仍由世界定義。其餘原文尚未逐頁／圖形視覺核對，research_status保留partial。
- 測試：`python -m pytest -q`實際68 passed（包含T01–T29核心情境、provider故障、取消、引用與占用保護、cache增量／刪除／維度不相容及Responses工具往返）；沒有xfail承接歷史測試。
- HTTP：`python examples/brain_client.py --all`與`python scripts/http_smoke.py`實際完成6個mock情境HTTP200；normal、critical、oxygen_early、refill_competition、irrigation_third_failure、partial的回應在`examples/responses/`，完整OpenAPI與JSON Schema已輸出。
- Live：`python scripts/http_smoke.py --live`實際HTTP200、execution_mode=live、動態dense RAG＋get_world_rule＋audit_human_plan，3次LLM、1次embedding、3次工具，約27.6秒，回傳1條有audit_result_id的發電候選，無warnings。真實response在`examples/live_responses/normal.json`。
- T29實際正常值：個人food_energy=2172.75、water≈1.3659583333333334；公共water=3000、food=120000、power=6552、oxygen≈8020.033333333334。Critical範例在base終止，後段not_reached，未發布假精確的完整終止state。
- 檢索驗收：BM25 10/10；dense 9/10，精確水需求3.217題top-5未命中，命令如實回exit2，沒有把這一題列passed。結果在`docs/retrieval_eval*.json`；引用存在檢查與科學語意支持檢查分開，後者不宣稱全面自動驗證。
- 尚待外部對齊／未測：正式Core／世界DTO及工具payload、fatal階段微順序、世界引擎差異測試、LAN第二台設備連線；官方Voyage與OpenRouter LLM遠端路徑未實測。PDF旋轉文字部分抽取不完整、完整科學來源支持性仍partial。詳見`docs/integration_notes.md`與`docs/validation_report.md`。

現場啟動（專案根目錄，保留既有.env）：

```powershell
python -m pip install -r requirements.txt
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
# 另開終端
python examples/brain_client.py --all
# GET /health、/docs、/openapi.json；POST /human-agent/analyze
```

欲使用live，在啟動終端設`$env:AGENT_MODE='live'`再啟動；無需把金鑰貼到命令或回覆。API啟動只載入索引，不會重新下載或付費建索引。隊友採用任何建議前仍須核對最新state_id／tick。

## 16. Live 已知問題修正與最新驗收（2026-09-12）

使用者已將.env改為live。本次保留該檔案全部內容與金鑰；現有5份原文、393chunks與1024維Voyage向量皆重用，corpus/index/rules hash不變，未重新付費嵌入corpus。

已完成修正：

- **檢索**：RETRIEVAL_MODE=dense且RETRIEVAL_FALLBACK=bm25時，正常流程以RRF合併排名，並以原文完整數字token＋查詢詞補回明確數值命中。回actual_mode=mixed、ranking_method=rrf_with_numeric_anchors；不假稱純dense提升。原3.217題已命中，同樣十題目前BM25與混合檢索各10/10。
- **並行統計**：embedding_calls／cache_hits改成每request ContextVar；即使共享client／cache也不會互相累計，取消時清理context。已做並行單元測試與兩個真實live HTTP請求。
- **LLM流程**：候選可用audit_result_id引用，後端補回完整plan及audit。給LLM的核算省去重複ledger，保留實際數字與致命條件，降低冗長JSON與超时機率；4次LLM／8次工具／45秒上限不變。
- **文獻支持**：公開建議reason由固定規則與工具核算組裝，不將LLM自由生成的科學說法當成已認證文字。evidence.reviewed_claims列出兩段核心BVAD原文中4项有限結論，綁定精確chunk hash；原文改變就不繼承核對標記。其他原文仍標未全面語意認證。
- **Core adapter**：HTTP client核對schema、rules、request_id、state_id、tick與for_tick；新增response_is_current供Core採用前對最新快照再檢查。純映射與錯版／過期回應拒絕已測試。人工response另存examples/manual_responses，避免覆寫驗收紀錄。

最新實際結果：

| 驗收 | 結果 |
| --- | --- |
| `python -m pytest -q` | **86 passed**，5.14秒 |
| `python scripts/eval_retrieval.py --mode bm25` | **10/10** |
| `python scripts/eval_retrieval.py --mode dense` | **10/10**，正常流程如實回mixed |
| `python scripts/http_smoke.py --live --all` | **6/6 live HTTP通過**，無degraded／warnings |
| `python scripts/http_smoke.py --live --concurrent` | **2/2並行live HTTP通過**，各自embedding_calls=1／cache_hits=0 |
| 錯版／壞JSON、OpenAPI | 實際HTTP422／422／200 |

六種live時間為normal23.301秒、critical16.282秒、oxygen_early6.015秒、refill_competition17.652秒、irrigation_third_failure12.961秒、partial5.500秒。兩個並行請求為18.551與19.276秒。所有個人／公共／人力／audit／risks欄位均與deterministic baseline比對一致，不因LLM而改動；不可救回的情境可以沒有建議，不要求強行產生救援。

真實回應在examples/live_responses；摘要在docs/http_validation_live_all.json與docs/http_validation_live_concurrent.json。新版OpenAPI與JSON Schema已匯出，人工操作見docs/manual_testing.md。

仍需外部配合：正式Core／世界DTO與引擎差異測試，以及第二台電腦的LAN連線。這些介面／設備不在目錄中，不能以本機契約測試冒充已串接。文獻全頁視覺校讀與任意科學語句認證不假稱完成；runtime只發布上述有限核對結論。這些限制不阻擋依manual_testing.md開始本機人工live測試。

## 17. Core handoff v1.3 轉接（2026-09-12）

依使用者提供的 `specialist-agent-api-handoff.md` v1.3 新增 `POST /discuss`；外層完全使用 Core 訊息格式，不加 schema_version／rules_version／diagnostics。原 Human API 2.0 仍可用。新增 `app/discussion_types.py` 與 `app/discussion.py`，共用原 Human 計算、RAG、LLM 工具與總預算，不新增世界操作或 Simulator。

本次 Core 的 greenhouse-2026-09-12-v1 規則數值與本規格世界 v0.12 一致。轉接比對規則內容、版本與固定政策文字；派生每 tick 率容許 wire 浮點尾差，但存量／死亡判斷仍不改等號規則。Core 範例缺 crew[].alive、world.world_status、world.snapshot_phase，故原始範例回422；必須由 Core 補明確事實，不能以 adapter 預設值猜測。這三類欄位符合 Core 允許 world／crew 額外欄位的設計。

Core 可省略 next_tick_plan／water_production_available，Human 只回可知分析與需求建議；要核算候選需提供完整且對應下一 tick 的 plan。Core 的 previous_messages 與追問送入模型，但不自動提升為權威狀態或基準排程。reviews 引用檢查同 discussion、world_version、較早 round 的真實 message_id／proposal_id。中文公開評估放入 decision_reason／reviews，不能當成世界操作或科學認證；量化候選仍由後端工具產生。

成功回傳 Core 的 content 五欄、explanation 七欄與2–4句繁體中文 display_text。候選在 content 與 explanation 共用新 proposal_id。舊 analyze 的 provider 降級仍回原契約；discuss 因 Core 的失敗要求回502，外層44秒逾時回504，錯版409、結構錯誤422。

驗證：110個單元／契約測試通過（10.65秒）；新增24個測試涵蓋規則比對、缺少真實狀態、ID／額外欄位、中文fixture、跨輪問題與引用、錯版／歷史／格式、失敗非2xx與不復活。Mock實際HTTP兩輪200。修正PowerShell產生fixture時中文變問號的問題後，重新完成Live兩輪：第一輪33.271秒，1個已核算候選；第二輪34.221秒，1個候選及2個真實前輪提案引用。每輪均為live、HTTP200、低於45秒。首次受限網路執行回502，取得網路執行核准後完成驗證，未暴露金鑰。

真實回覆及第二輪請求存 `examples/discussion_responses/live/`；報告 `docs/discussion_http_live.json`／`docs/discussion_http_mock.json`。來源 Plant 訊息是明示測試 fixture，不冒稱隊友服務回覆。OpenAPI 與 Core request／response schema 已匯出；交接與啟動方式見 `docs/core_handoff_alignment.md`。原 Core 交接文件未改寫，`.env`／既有corpus與向量未改寫或重建。

未完成：Core補足真實狀態欄位、確認共享發電比例／死亡微順序與本地唯讀工具的語意、正式plan DTO映射、Core／世界服務與跨電腦LAN聯測。另已查出植物第二次失灌警示分級與第三次失灌原計畫總結標籤的語意問題，列入交接文件，未在此次轉接中擅改世界規則；Core仍須查看critical／will_die，不能只看feasible_in_scope。

## 18. 持續運行狀態澄清（2026-09-12）

使用者確認目前世界持續運行，沒有規劃暫停流程，優先於交接文件的暫停敘述。`/discuss` 的 content.world.world_status 改為可省略、預設 running；明確狀態仍保留，不覆蓋死亡判定。Core仍需明示crew[].alive與snapshot_phase=between_ticks；快照表示一次完整tick邊界的狀態副本，不要求世界停止。原 Human API 2.0 的必填契約沒有更動。

rules.planning 為Core流程描述，允許非空文字更新，消耗與死亡等世界規則仍逐項比對。世界持續前進時，慢速LLM回應的舊for_tick不可直接採用；Core需要依最新狀態重新驗證策略／安排。新增預設與流程描述測試，26個discussion測試通過（5.76秒），更新OpenAPI／schemas與交接文件；本次沒有重新呼叫Live模型。

## 19. Human 配合 Core 實作與最新世界澄清（2026-09-12）

本節取代第 17、18 節中仍需 Core 補 alive／snapshot_phase、預設 running 及植物風險待修的敘述。使用者最新確認：Agent 討論溝通期間世界暫停；1 EU ↔ 3.9745 kWh。

已完成 Human 端適配：

- `/discuss` 接受 Core 原始請求；world_status 缺省 planning，snapshot_phase 缺省 between_ticks，content.world 本身就是當次 snapshot，無需另外的物件或呼叫。
- alive 選填、未知保持 null；不推定存活，不發布依賴未知存活的已驗證候選。一般問題與歷史評論仍可回 200，明確死亡不復活。原 Human API 2.0 請求仍保留原必填契約。
- 支援可辨識的 world／content.current_plan（完整 Plan 或 candidate_plan 包裝）；過期、衝突、不完整表示保留供模型討論，不自動補排程或當作已指定計畫。未提供的正式 DTO 仍待取得後映射。
- 規則 metadata 與一致的版本別名相容；數值、單位、布林與順序不相容仍拒絕。執行語意描述改變可討論但量化驗證標未知。explanation_schema 接受註解、required 排序及本地非循環引用差異，不宣稱支援所有等價變形。
- 第二次連續失灌標 critical、尚未死亡；第三次植物死亡時 audit 為新增的 unsafe_in_scope，建議可行性為 infeasible。植物死亡不等於 crew 死亡，不觸發 Human 自行停止世界。
- `data/unit_conversions.json` 及 `app/unit_conversions.py` 提供精確雙向換算，回覆附使用者確認來源及版本。6000 EU = 23847 kWh。power 輸入維持 EU，不改 world v0.12 發電／製水／灌溉係數或 rules_hash；kW 需時長才能換算能量。

驗證：122 項單元／契約測試通過（10.61 秒）；原 Human 六種 mock HTTP 情境通過；Core 原始請求與兩輪 mock HTTP 均 200。Live 原始請求 25.046 秒、完整候選首輪 28.705 秒、追問第二輪 34.461 秒，全部 200 且低於 45 秒；第二輪兩項有效前輪評論。已更新 OpenAPI、schemas、README、交接說明及驗證報告；`.env` 未修改，corpus／向量沿用。

尚未完成的是外部聯測與尚未提供的事實：Core 正式候選／死亡表示映射、世界共享發電及死亡微順序比對、真正 Core／Plant 服務與第二台設備 LAN。研究來源仍 partial，非本次宣稱完成的項目。未實作 Core、Plant、前端或世界 Simulator；Human 不發出暫停／恢復／執行指令。最新責任分工見 `docs/core_handoff_alignment.md`。

## 20. Core 接受契約後的 Human 完整交付（2026-09-12）

使用者回報 Core 已接受 `docs/core_handoff_alignment.md`，本版按該文件交付，不再將既有格式／公式列為等待確認才能啟用的條件。缺少 alive、設備狀態或完整候選時，沿用契約明示的未知／未驗證行為；Core 的接受不會被解讀為提供了不存在的世界事實。

Human 的個人／公共分析、tick 核算、RAG、Live 工具流程、Core 訊息轉接與多輪評論已具備。此次補齊交付使用方式：Swagger `/discuss` 六種有效範例、七個可重建的邊界／current_plan 範例、独立 `examples/discussion_client.py`（讀取 JSON、最多三輪、引用檢查、顯示秒數、保存 request／response／metrics）、`docs/START_TESTING.md`。範例生成命令 `python scripts/make_discussion_examples.py` 不修改原始 Core 交接文件。

本次驗證：130 項測試通過（13.26 秒）；Core 11 個 mock HTTP 案例、原 Human 六種 mock HTTP 情境通過；原始 Core Live 請求 22.689 秒，Live 三輪 28.533／31.750／34.135 秒，全部 200 且低於 45 秒，第二／三輪各含 2／3 項有效歷史提案評論。人工 CLI 亦透過獨立服務實際完成三輪 HTTP。OpenAPI／schemas 與交付文件已更新。

啟動：`python -m uvicorn app.main:app --host 127.0.0.1 --port 8000`；人工測試：`python examples/discussion_client.py --fixture current_plan`。仍需真實 Core／世界服務才能完成引擎差異與跨機聯測；此限制不阻擋目前 Human 單機人工測試。沒有擴大實作 Core、Plant、前端或世界 Simulator，沒有改寫 .env 或既有金鑰。
