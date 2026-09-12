# Core Agent 討論結果摘要

> 歷史討論紀錄：最新規則請以 [world-rules-spec.md](../specs/world-rules-spec.md) 為準。後續已移除預測 Simulator、更新資源與作物模型；本摘要保留舊討論，不再作為實作依據。

日期：2026-09-10

## 1. 專案核心想像

本專案是一個偏「遊戲模擬」的太空溫室 / 封閉生態系統。

畫面中會有人類、植物、設備與資源流動。系統平常會依照 Core Agent 訂出的策略自動運轉，人物和設備會根據行動計畫做出動畫行為，目標是讓整個基地的資源維持平衡，讓 crew 能永續活下去。

使用者可以隨時暫停遊戲，手動調整環境資源來製造 emergency。恢復後，agents 會協作討論策略，Core Agent 做出最終決策，讓資源逐步回到穩定狀態。

## 2. 呈現方式

已確認：

- 畫面偏遊戲模擬，不是純 dashboard。
- 需要有動畫人物 / 植物 / 設備行為。
- 使用者可以暫停並調整環境資源。
- emergency 主要針對「環境資源」調整。
- 成功條件是 crew alive，且資源回歸穩定。

## 3. Agent 架構

第一版只使用三個 agents：

```text
Plant Agent
Human Agent
Core Agent / Mission Agent
```

### Plant Agent

Plant Agent 只負責從植物角度提供建議。

它關心：

- 作物健康
- 植物產氧能力
- 未來食物產量
- 水、光照、溫度對植物的影響

它只提供建議，不直接執行工具。

### Human Agent

Human Agent 只負責從人類生存角度提供建議。

它關心：

- crew alive
- Oxygen 是否安全
- CO2 是否過高
- Water 是否足夠
- Food 是否足夠
- Crew Health 是否持續下降

它只提供建議，不直接執行工具。

### Core Agent

Core Agent 是目前主要負責範圍。

Core Agent 負責：

- 接收世界狀態
- 接收 Plant Agent 建議
- 接收 Human Agent 建議
- 主持多輪討論
- 找出兩邊建議的衝突
- 產生候選策略
- 呼叫 Simulator 預測策略結果
- 根據 safety constraints 和 scoring 選出最終 plan
- 輸出可執行 actions 給遊戲世界
- 解釋為什麼採用該策略

Core Agent 不負責：

- 植物模型細節
- 人類營養模型細節
- 動畫怎麼畫
- UI 怎麼做
- Plant Agent / Human Agent 內部邏輯

## 4. 世界狀態

目前確定的 world state 有 7 個數值：

```text
Power
Water
Oxygen
CO2
Food
Crop Health
Crew Health
```

所有數值第一版都用 0-100 的抽象 scale。

### Power

Power 是基地電力 / 電池能源，不是人類體力。

它代表：

- 太陽能輸入
- 電池儲量
- LED 消耗
- 溫控消耗
- 水循環消耗
- 生命維持系統消耗

### Food

Food 是人類可食用能量 / 食物庫存。

它可以先簡化代表 calories，不細拆 protein / vitamins。

### Crew Health

Crew Health 代表人類整體生存狀態，受到 Oxygen、CO2、Water、Food 影響。

## 5. 時間單位

已確認：

```text
1 tick = 1 simulated hour
```

意思是 simulator 每更新一次，世界時間前進 1 小時。

例如 emergency 發生後，Core Agent 可以請 Simulator 預測未來 72 小時：

```text
simulate(plan, 72 hours)
```

## 6. 工具與 Mode

Tool 是 Core Agent 可以呼叫的操作。

Mode 是某些工具 / 設備系統的運轉檔位，不是 agent 的模式。

### 已確認工具列表

```text
set_led_intensity(crop, percentage)
set_irrigation(crop, percentage)
set_life_support_mode(mode)
set_water_recycling_mode(mode)
set_temperature_target(value)
ration_food(level)
```

### set_led_intensity(crop, percentage)

調整某種作物的 LED 強度。

影響：

- Power
- Crop Health
- Oxygen
- Food

Trade-off：

```text
Power <-> Crop Health / Oxygen / Food
```

LED 越高越耗 Power，但有利植物健康、氧氣與未來食物產出。

### set_irrigation(crop, percentage)

調整某種作物的灌溉量。

影響：

- Water
- Crop Health
- Oxygen
- Food

Trade-off：

```text
Water <-> Crop Health / Oxygen / Food
```

灌溉越高越耗 Water，但有利植物健康。

### set_life_support_mode(mode)

調整生命維持系統。

模式：

```text
power_save
normal
emergency
```

影響：

- Power
- Oxygen
- CO2
- Crew Health

Trade-off：

```text
Power <-> Oxygen / CO2 / Crew Health
```

`emergency` 會耗更多 Power，但優先保住 Oxygen、壓低 CO2、維持 Crew Health。

### set_water_recycling_mode(mode)

調整水回收系統。

模式：

```text
low
normal
high
```

影響：

- Power
- Water

Trade-off：

```text
Power <-> Water
```

`high` 會耗更多 Power，但 Water 回復速度提高。

### set_temperature_target(value)

設定基地 / 溫室的目標溫度。

影響：

- Power
- Crop Health
- Crew Health

Trade-off：

```text
Power <-> Crop Health / Crew Health
```

為省電可以允許溫度稍微偏離最佳值，但不能危害 crew。

### ration_food(level)

調整人類食物配給。

模式：

```text
normal
reduced
emergency
```

影響：

- Food
- Crew Health

Trade-off：

```text
Food <-> Crew Health
```

降低配給可以減少 Food 消耗，但會讓 Crew Health 下降。

## 7. Core Agent 多輪討論流程

Core Agent 可以和 Plant Agent、Human Agent 多輪討論。

建議流程：

```text
Emergency occurs
Core Agent observes world state

Round 1:
  Plant Agent 提出植物角度建議
  Human Agent 提出人類生存角度建議

Round 2:
  Core Agent 找出衝突
  Core Agent 要求 agents 修正建議

Round 3:
  Core Agent 整合建議並產生候選策略
  Simulator 測試候選策略
  Core Agent 可把 simulation 結果回饋給 agents

Final:
  Core Agent 選擇最終 plan
  World 執行 actions
```

為了 demo 節奏，emergency mode 最多 3 輪討論。

## 8. 為什麼需要 Core Agent

Plant Agent 和 Human Agent 都是局部專家。

它們分別針對自己負責的領域提出最佳建議，但它們彼此不知道對方的建議會佔用多少資源，也不負責全局 trade-off。

例如：

```text
Plant Agent:
希望提高 LED，保住 Crop Health / Oxygen / Food。

Human Agent:
希望降低 LED，把 Power 留給 life support。

Core Agent:
需要協調兩邊衝突，找出 crew alive 且資源能回穩的策略。
```

## 9. Simulator 定位

Simulator 是 rule-based world model。

它不是 LLM，也不是 agent。

它負責：

- 維護世界物理 / 資源規則
- 根據目前 world state 和 proposed plan 推進時間
- 預測未來狀態
- 回傳 safety violations、final state、trend

它不負責：

- 產生策略
- 跟 agents 討論
- 決定哪個 plan 最好
- 控制動畫

一句話：

```text
Simulator 回答：如果這樣做，會發生什麼？
Core Agent 回答：所以我們應該怎麼做？
```

## 10. Simulator 會不會像作弊

目前共識：

不會，因為 Simulator 不是未來真相，而是基於目前已知條件的 forecast。

它只能預測：

```text
如果未來 72 小時沒有新的突發事件，這個策略大概會造成什麼結果。
```

它不知道：

- 玩家 12 小時後又調整資源
- 新 emergency 會突然發生
- 真實執行是否偏離預測

所以 Core Agent 採用 plan 後，仍然需要持續監控世界。

如果發生以下情況，就重新規劃：

- 新 emergency 發生
- 實際資源變化偏離 simulation prediction
- 任一資源接近 danger threshold
- Crew Health 開始快速下降

這樣才有 agentic AI 的感覺：

```text
Observe
Discuss
Plan
Simulate
Execute
Monitor
Replan
```

## 11. Core Agent 是否知道物理 / 資源規則

目前共識：

Core Agent 應該知道物理 / 資源規則的高層邏輯與粗略 trade-off，但不負責精確計算。

Core Agent 知道：

- LED 越高越耗 Power，但有利 Crop Health / Oxygen / Food
- 灌溉越高越耗 Water，但有利 Crop Health
- water recycling high 會耗 Power，但可以恢復 Water
- life support emergency 會耗 Power，但保 Oxygen / 降 CO2
- ration_food reduced 可以省 Food，但 Crew Health 會下降
- crew alive 永遠優先於 Crop Health

Core Agent 不自己精算：

- 72 小時後 Power 會是多少
- Crop Health 每 tick 掉多少
- CO2 何時超過安全線

精確預測交給 Simulator。

正式定義：

```text
Core Agent has strategic understanding of world rules.
Simulator is the quantitative source of truth.
```

## 12. 成功條件

已確認成功條件：

```text
crew alive
resources return to stable safe range
```

也就是不是追求植物長最好，而是整個封閉生態系統可持續。

Core Agent 的優先級應該是：

```text
1. Crew alive
2. Avoid hard constraint violation
3. Bring resources back to safe range
4. Stabilize trend
5. Preserve crop health when possible
```

## 13. 策略結構由 Core Agent 自由選擇

已確認：策略不限定為單一設定，也不強制使用固定的多階段流程。

Core Agent 可以依情況選擇：

- 直接調整：一組設備設定即可恢復並維持平衡。
- 分階段調整：先採 A 拉起緊急資源，再切換 B 穩定整體平衡。
- 條件式調整：執行 A 後，依世界狀態決定切換 B 或 C。

Plan 可用「目前的 actions + 選擇性的後續步驟與切換條件」表達。系統限制可用工具、安全條件與模擬預算；是否分階段、如何組合操作，由 Core Agent 決定。階段數量上限尚未定義，不採固定三階段要求。

Simulator 必須模擬完整策略，包括依條件切換設定，不能只把第一階段設定持續執行整個預測期間。預測 72 小時不代表當下設定必須執行 72 小時。

## 14. 持續監控與重新規劃

已確認：Core Agent 需要持續掌握執行情況，但不需要讓 LLM 每個 tick 都運轉。

### 程式監控

每個 tick（1 模擬小時）更新世界後，由程式檢查：

- 資源是否接近危險線。
- 實際變化是否明顯偏離 Simulator 預測。
- 是否達到 plan 的切換條件。
- 某階段是否超時。
- 玩家是否製造新的 emergency。

若達到已規劃的切換條件，程式直接執行後續步驟，不必重新呼叫 LLM。

### Core Agent 介入

若出現策略未涵蓋的狀況，由監控程式喚醒 Core Agent，提供目前狀態、正在執行的操作，以及與預測的差異。

Core Agent 判斷原策略是否仍可繼續，或需要修改、替換；必要時召集 Plant / Human Agent 討論並模擬新方案。

例如：原策略等待 Oxygen 恢復後降低耗電，但 Power 提前逼近危險線，監控就應觸發 Core 重新評估。

如果 Simulator 原本已預測到該危險，Core 應在選方案時處理，不能等執行後才當成意外。監控用於處理新事件、預測偏差及策略未涵蓋的狀況。

整體流程：

```text
Core 規劃
World 執行
程式每個 tick 監控
  → 達到既定條件：按計畫切換
  → 發生未涵蓋的風險：觸發 Core 重新規劃
```

具體安全門檻、預測偏差容許值與超時設定，仍待定義。

## 15. Core 規劃期間的模擬時間

已確認：第一版在 Core 重新規劃期間暫停模擬時間，將「世界減速運行」列為未來目標。

第一版流程：

1. 監控觸發重新規劃時，暫停世界時間與資源、生存狀態的推進。
2. Core 依凍結的世界狀態協調 agents，並以 Simulator 預測候選策略。預測不推進實際世界時間。
3. 畫面仍可呈現待機動畫、討論訊息與策略預測。
4. 套用選定策略後，恢復模擬時間。
5. 已規劃好的階段切換由程式直接執行，無須為此暫停。

這樣可避免 LLM / API 回應延遲直接造成額外資源消耗或影響 crew 生存。

未來目標：Core 思考期間讓世界減速運行。屆時需處理規劃期間狀態持續變動，以及方案執行前的有效性檢查；第一版不實作。

## 16. 下一步討論建議

下一步可以繼續討論 Core Agent spec 的細節：

1. Core Agent 的 input JSON 格式
2. Plant / Human recommendation 的最小接口格式
3. Core Agent 如何偵測 conflict
4. Candidate plan 應該怎麼生成
5. Simulator prediction result 格式
6. Scoring function 怎麼設計
7. Final plan output 給動畫世界的格式
