# Core Agent 串接協定 v1.2（團隊確認草案）

這份文件是本次新增的接口實作約定，補充世界 spec，不改動其资源係數。Python 3.11+；JSON使用有限數值，不能傳NaN或Infinity。

## 1. 世界輸入

世界快照嚴格格式見 [World Snapshot Schema](../../schemas/world-snapshot.schema.json)，公共資源四欄均必填；Core呼叫專家前驗證。參考 `examples/snapshot.json`。必備：`world_version`（整數）、`rules_version`、`tick`、`resources`、`crew`、`plots`。個人欄位為 `food_energy`／`water`；地塊欄位為 `crop_type`、`status`、`growth_ticks`、`consecutive_unirrigated_ticks`。ID必須唯一且在本次討論期間固定。

完整共用規則透過 `get_rules()` 取得，不要求專家自己猜產量或消耗。最近的世界事件與正在執行的plan可另傳 `history`、`current_plan`。在討論期間玩家修改世界時，呼叫端應取消舊討論；即使舊結果回來，也必須根據版本拒絕套用。

## 2. Plant／Human HTTP服務

Core向設定的endpoint發送POST JSON：

```json
{
  "message_id": "msg-core-001",
  "display_text": "目前氧氣正在下降，請評估作物供氧與種植取捨。",
  "discussion_id": "uuid",
  "round": 1,
  "sender": "core",
  "recipient": "plant",
  "world_version": 0,
  "content": {
    "question": "請評估目前作物需求與可接受的讓步",
    "world": {},
    "rules": {},
    "previous_messages": [],
    "reason": "low_oxygen"
  }
}
```

`world`／`rules`實際會填入完整資料。回覆必須為HTTP 200，保留discussion_id、round、world_version，產生自己的message_id與display_text，交換sender／recipient：

```json
{
  "message_id": "msg-plant-001",
  "display_text": "我建議保留供氧較高的地塊。減少其他地塊可以省水電，但會降低未來食物產量。",
  "discussion_id": "同一個uuid",
  "round": 1,
  "sender": "plant",
  "recipient": "core",
  "world_version": 0,
  "content": {
    "observations": ["觀察"],
    "priorities": ["需求"],
    "suggested_actions": [],
    "acceptable_tradeoffs": ["可以接受的讓步"],
    "evidence_and_unknowns": ["依據及不確定處"]
  }
}
```

Human使用 `sender: human`。content五欄必備，內容可使用陣列、物件或文字；建議保留來源引用。response必須是訊息本體，不能再包一層 `data`。支援選填 Bearer token，Core提供獨立的PLANT_AGENT_TOKEN／HUMAN_AGENT_TOKEN。

同一輪沒有直接專家互連，Core下一輪轉送双方完整建議與自身追問。錯誤版本、錯誤round、錯誤recipient、缺欄、timeout任一發生，Core不產出可執行plan。這版不自動忽略失聯專家，也不自動重試外部API。

## 3. GPT 決策與最終輸出

決策schema位於 `core_agent/contracts.py`。每次GPT回應包含 `kind`（consult/final）、公開摘要、兩個追問與可空的plan。consult不能帶plan，final必須帶plan。

最終結果為：`discussion_id`、`plan`、`transcript`。transcript記錄訊息與公開決策摘要，不要求模型提供內部思考鏈。

Plan欄位：

| 欄位 | 語意 |
|---|---|
| plan_id | 本次策略識別碼 |
| rules_version | 與輸入相同規則版本 |
| based_on_state_version | 與輸入相同世界版本；執行前再次核對 |
| reason | 給玩家看的策略理由 |
| entry_stage_id | 起始階段 |
| stages | 至少一階段，可多階段或條件分支 |

Stage欄位：

| 欄位 | 語意 |
|---|---|
| stage_id / purpose | ID及目的 |
| max_ticks | 階段最長tick數；屆滿沒有有效切換就暫停並重規劃 |
| water_liters_per_tick | 製水設備每tick請求量0–250 L，**不是灌溉水量** |
| irrigation_order | Core指定分配順序；列入地塊各取得固定8.7 L＋0.208339030887 EU完整配額，未列入者無配額 |
| actions | 按陣列順序處理的crew工作 |
| transitions | 按順序檢查，第一個符合的分支於下tick生效 |

Action欄位：`action_id`、`crew_id`、`kind`、`tick_offset`、`repeat`、`plot_id`、`crop_type`、`amount`。不適用的ID欄位必須為null，不可省略。

- `tick_offset=0`：階段開始後第一個執行tick。
- eat／drink：amount是請求遊戲kcal／L，上限1000／0.5。依actions順序處理補給競爭。
- generate：amount是0以上至1的工作量；`repeat=true`表示從offset開始到階段結束每tick工作。
- plant／harvest／clear：amount固定1，plot_id必填；僅plant要填crop_type。
- 為保證可檢查的crew占用，本版只有generate能repeat，其餘可列多個一次性action。
- 每個action_id在plan內唯一；同一crew同tick只能有一個工作。
- 不同crew可在同tick對同一地塊按明確陣列順序採收再播種，必須由世界逐项檢查前置狀態。
- 階段切換時取消舊階段尚未到期的工作。禁止重複執行同一action_id：repeat工作去重鍵為plan_id、stage_id、stage進入次數、action_id、tick_offset；一次性操作亦按階段進入次數區分。重入階段代表重新安排該階段工作。

Transition含 `target_stage_id`、`match`（all/any）、非空conditions陣列。每個condition為 `path`、`op`、`value`；op僅lt/lte/eq/gte/gt。只允許數值狀態路徑：`tick`、`resources.*`、`crew.ID.food_energy`／`water`、`plots.ID.growth_ticks`／`consecutive_unirrigated_ticks`，不接受任意程式碼。

## 4. 執行責任與錯誤

Core本地驗證schema、版本、ID、範圍、crew占用與分支連結。不做未來資源预测，也不在規劃時拒絕目前還未成熟、但計畫未來採收的地塊。

後端仍必須驗證：最新版本、活人、地塊成熟／空地／死亡狀態、實際庫存、原子扣款與死亡時立即停止。UI動畫不授權第二次操作。

建議後端以事件回傳 `world_version`、`tick`、`plan_id`、`action_id`、`status`、`requested`、`actual`、`resource_deltas`、`reason`；目前Core以history資料讀取這些事件，未提供世界HTTP server。

CoreController在運行中主動觀察與GPT評估；需要重規劃時，由Core要求暫停世界再開始專家討論。GPT refusal、不完整回應、網路／專家失敗、非法plan，都保持暫停，不回退到硬編碼救援策略。

## 5. 主動監控的 WorldPort（新增接口草案）

Core持續運作，不以外部暫停事件為唯一入口。世界owner提供adapter：

- `observe()`：回傳世界快照，含必填 `world_status`（running/paused/planning/error_paused/failed）、`snapshot_phase: between_ticks`、各crew的實際`alive`，加、`current_plan`（可null）、`replan_required`（boolean）、`recent_events`（array）。其中 `replan_required` 可表示階段超時、未安排的採收、操作失敗或玩家調整後待規劃；Core另自行偵測公共與個人低存量、惡化及灌溉中斷。
- `pause_for_core(expected_version)`：原子檢查版本與狀態，取得專屬暫停權，回傳新快照及 `pause_token`。手動暫停／死亡／已有其他規劃owner時回null；版本衝突下Core下次重新讀取，不強制暫停。
- `apply_and_resume(plan, expected_version, pause_token)`：原子核對版本、暫停權與操作合法性，成功套用並解除該Core持有的暫停，回true；不成立回false。玩家在規劃中修改／暫停要使token或版本失效。不得只在Core端檢查後用兩個非原子的apply和resume呼叫。

世界預設running並持續推進時間，無策略用current_plan=null表示，Core偵測後才要求重規劃暫停。玩家paused狀態仍受尊重；恢復後轉running。Core不自行推進世界tick。

GPT監控評估輸出為 `{ "decision": "continue" | "replan", "reason": "..." }`。這是決策信號，不是可直接執行的操作；replan會取得最新凍結世界重新規劃，所以不使用背景評估的舊快照提交行動。完整策略繼續使用既有plan schema。

默认輪詢0.5秒、每新tick評估一次，單一評估在途，歷史保留最近24次不同版本觀察。GPT延遲可能跨越多個ticks，期間程式仍檢查風險；可調整assessment_every_ticks節省API呼叫。該間隔不是資源公式，也不改變1 tick的意義。

這是新增接口草案，HTTP路徑與隊友的實際API格式尚待對接；測試以WorldPort替身驗證，未宣稱已連上世界服務。

## 6. 對話呈現

每則通訊訊息均輸出以下欄位供前端使用：

| 欄位 | 用法 |
|---|---|
| message_id | 訊息唯一ID；列表key與事件去重，同一訊息重取不變 |
| discussion_id / round | 同次討論與輪次分組 |
| sender / recipient | 對話角色與對象（Core廣播使用all） |
| display_text | 直接顯示的純文字；建議2至4句繁體中文 |
| content | 原始結構化資料，供Core處理，不應整份丟進聊天泡泡 |

`display_text`描述觀察、建議、理由與取捨，不要求內部思考鏈；未經後端確認不得顯示為「已完成操作」。公開摘要可以和結構化資料並存，前端不要從工具參數自行推論理由。

建議直接按transcript陣列／事件接收順序呈現，以message_id去重，不根據round猜同輪訊息順序。新專家服務應提供display_text；為相容原接口，缺少時Core會從已有summary、question或公開建議文字組成摘要，不從world、工具JSON或任意欄位生成文字；無文字時顯示明確的缺摘要提示。缺少message_id則Core本地補UUID。

對話可呈現為：

> Core：目前水量下降，請評估哪些種植地塊應優先保留。
>
> Plant：我建議優先保留即將成熟的作物，放棄其他地塊會減少後續產氧。
>
> Human：兩名crew即將需要飲水，工作安排要保留補充時間。
>
> Core：我會先安排飲水，再分配其餘人力發電，並調整灌溉優先順序。

此為敘述範例，不是固定策略。計畫套用成功應由controller的plan_applied或後端操作結果另外呈現。controller的assessment事件使用reason，planning事件使用type；它們不是專家Message，前端應分成系統事件而非直接當作角色發言。

## 7. 詳細策略討論呈現（v1.2）

前端提供兩層：`display_text`是短對話；`explanation`是可展開的策略卡片；`detail_text`是Core由explanation組成的完整純文字版本。可選擇直接顯示detail_text，不需要解析工具參數生成理由。

| explanation欄位 | 呈現內容 |
|---|---|
| observations | 觀察到的狀態或風險 |
| proposals | 每項建議的proposal_id、strategy、reason、expected_effect、tradeoffs與evidence |
| reviews | 引用message_id＋proposal_id，說明採納／修改／不採納／需要釐清及assessment理由 |
| conflicts | 兩方建議或資源需求的衝突；沒有衝突可為空 |
| follow_up_reason | 為什麼Core要再問一輪，而不是立即決策 |
| decision_reason | 為什麼Core最終選擇這個方案 |
| uncertainties | 尚未確定的事情，不假裝已模擬或證明 |

每個proposal_id在同一訊息內唯一；reviews使用訊息ID＋建議ID共同定位，前端可點擊回到原建議。Core目前會驗證自身reviews引用是否真實存在於討論紀錄。

**接口變更：**新Plant／Human回覆除了既有content五欄，也必須提供外層 `explanation`。舊服務不提供時會明確回報錯誤，避免畫面只剩籠統摘要。`display_text`仍可由既有公開文字補出，但不自動編造缺少的策略理由。`detail_text`由Core生成，專家不用填；如果回傳則忽略其值，依explanation重新生成。

Core的GPT回應必須包含 `explanation`：consult必填非空follow_up_reason；final必填非空decision_reason。Core轉送下一輪問題時也帶入追問原因，專家知道為何被要求修正。完整問題仍在plant_question／human_question與下輪question中。

正式結構檔：[公開說明 Schema](../../schemas/agent-explanation.schema.json)、[GPT決策 Schema](../../schemas/core-agent-decision.schema.json)。

完整展示範例：[對話呈現 JSON](../../examples/dialogue-presentation.json)。該例呈現植物救援、crew飲水、發電人力衝突與Core再次追問的原因，僅供UI設計，不代表真實世界當前狀態。

欄位都是可公開的理由與證據摘要，不蒐集模型內部思考鏈。預期效果必須區分建議與已執行結果；最終plan成立也不能顯示為已套用，仍要等plan_applied／後端結果。

### 資源分工與文獻換算（已確認）

| 角色 | 評估範圍 | 責任 |
|---|---|---|
| Plant | 電、水、二氧化碳 | 評估植物需求與策略；植物產氧、收成是策略效果，公共氧氣／食物平衡由Core整合 |
| Human | 水、氧氣、電、食物 | 評估crew存活、補給與工作建議 |
| Core | 全部世界資源 | 持續監控、整合建議、分配水電與crew工作、提交策略 |

`analysis_scope`表示分析責任，不是資料存取限制；兩方仍收到完整world與rules供理解上下文。二氧化碳位於`rules.environment.carbon_dioxide`，固定500 ppm、不可調整，不是可耗盡庫存，不加入world.resources。

Core傳送原始世界數量，不預先換成文獻單位。Plant／Human自行完成文獻與世界的單位及時間換算；回覆可執行建議使用世界單位，換算依據、假設與缺少映射寫入`evidence_and_unknowns`及公開說明。Core依世界規則整合建議，不承擔文獻換算。

現有映射：人類參考1 kcal對應1 game_kcal、1 kg氧氣對應1000 OU、水以L計；作物產能的game_kcal係數是遊戲設定。人類1 tick是1小時，作物1有效生長tick對應文獻1天，不可把所有速率用同一時間倍率換算。1 EU = 3.9745 kWh；設備耗電按世界小時，不套用作物生長加速，使用未取位的設備公式結算。


Human對齊更新：世界必填實際world_status、snapshot_phase=between_ticks與每名crew的alive，不使用缺省值。完整規範、Human選填next_tick_plan格式及已知限制見[交接文件第10節](specialist-agent-api-handoff.md#10-human串接對齊v14)。
