# Plant／Human Agent API 通訊規格交接文件

版本：1.3｜日期：2026-09-12｜狀態：符合目前Core程式，供三方確認與串接

**這一份檔案即可轉交，不需要另外取得程式碼或其他文件。** 附錄包含目前程式產生的完整請求（世界快照、共用規則及詳細說明JSON Schema）和兩個agent的回覆範例。範例是靜態展示，並非真實GPT或文獻分析結果。

## 1. 你們需要提供什麼

Plant與Human各提供一個可由Core後端呼叫的HTTP API。Core主動POST，不需要你們輪詢Core，也不需你們直接互連。

| 項目 | 約定 |
|---|---|
| 方法 | POST |
| 路徑 | 由你們決定，例如 `/discuss`；交付完整URL |
| Content-Type | application/json；UTF-8 |
| 成功回覆 | HTTP 200，body直接是訊息JSON，不包data/result |
| 驗證 | 可不設或使用Bearer token；請提供方式及token交付管道，不放入共享文件 |
| 連線 | 正式使用HTTPS，本機開發可用localhost／127.0.0.1 HTTP |
| 時限 | Core HTTP timeout預設45秒，可協調調整；完整單一專家等待上限預設60秒 |
| 失敗 | 回傳適當非2xx狀態，不用200偽裝成空建議；Core會保持世界暫停 |

目前不使用webhook或串流回覆，也不自動重試。可用非阻塞服務接受請求，但本次POST須在timeout前回完整JSON。

## 2. 討論流程與角色

1. Core持續監控運行中的世界；需要新策略時主動要求暫停並取得最新快照。
2. 同一輪Core向Plant、Human發出各自的問題，兩方取得相同world與rules。
3. 兩方回覆建議，Core整理衝突與理由，由GPT決定追問或完成策略。
4. 若需下一輪，Core再次POST，提供新question、前輪完整訊息與再次討論的原因。
5. 同次討論最多3輪，可提早結束。兩位專家只提供建議；Core統一產生plan，世界後端驗證執行。

同一discussion的世界版本固定。資料不同或有新事件時，Core使用新discussion，不混用舊回覆。專家不得自行更新世界、增加資源、執行工具或修改規則。沒有預測Simulator，不能宣稱建議已經試跑。

## 3. 共用訊息外層

| 欄位 | 型別 | 請求與回覆規則 |
|---|---|---|
| message_id | string | 每則訊息唯一且非空；回覆自行產生，不能複製請求ID |
| discussion_id | string | 回覆原樣帶回 |
| round | integer | 1–3；回覆原樣帶回 |
| sender | string | 請求core；回覆plant或human（全小寫） |
| recipient | string | 請求plant或human；回覆core |
| world_version | integer | 回覆原樣帶回，不自行遞增 |
| display_text | string | 2–4句繁體中文對話摘要，前端直接顯示 |
| explanation | object | 詳細策略、理由與取捨；結構見第5節，必填且不能null |
| content | object | 機器使用的輸入或建議，方向不同其欄位不同 |
| detail_text | string | Core產生的完整敘述，請求／歷史訊息可能出現；專家回覆不需提供 |

本版外層沒有schema_version、type、in_reply_to或rules_version欄位，請勿自行增加，以免目前接收器拒絕。規則版本讀 `content.rules.rules_version` 與 `content.world.rules_version`。本文1.3是協定文件版本，不是現有傳輸欄位。

Core程式對message_id與display_text保留舊版缺省相容，但**新服務請一律提供**。explanation已強制要求；content五項回覆欄位也必填。detail_text若由專家回傳，Core會忽略並重新生成。

## 4. Core傳入的content

| 欄位 | 型別 | 用途 |
|---|---|---|
| question | string | 這一輪請你處理的具體問題 |
| world | object | 完整資源、4名crew、20塊地與時間／版本 |
| rules | object | 本版所有agents共用的固定公式與限制 |
| previous_messages | array | 同次討論完整前輪訊息，第一輪為空；包含另一專家的建議與Core評估 |
| reason | string | 最初啟動討論的原因，不一定等於本輪追問原因 |
| response_guidance | string | 公開敘述的語言與格式要求 |
| analysis_scope | string[] | 本角色評估的資源範圍，見下方分工 |
| unit_conversion_policy | string | 文獻換算責任與回覆單位要求 |
| explanation_schema | object | 回覆explanation的完整JSON Schema，可以直接用於你們的結構化輸出 |

**Core再次討論的原因**讀取外層 `explanation.follow_up_reason`；具體問題讀 `content.question`。不要只看reason而忽略新一輪問題。

### 資源分工與文獻換算（已確認）

| 角色 | 評估範圍 | 責任 |
|---|---|---|
| Plant | 電、水、二氧化碳 | 評估植物需求與策略；植物產氧、收成是策略效果，公共氧氣／食物平衡由Core整合 |
| Human | 水、氧氣、電、食物 | 評估crew存活、補給與工作建議 |
| Core | 全部世界資源 | 持續監控、整合建議、分配水電與crew工作、提交策略 |

`analysis_scope`表示分析責任，不是資料存取限制；兩方仍收到完整world與rules供理解上下文。二氧化碳位於`rules.environment.carbon_dioxide`，固定500 ppm、不可調整，不是可耗盡庫存，不加入world.resources。

Core傳送原始世界數量，不預先換成文獻單位。Plant／Human自行完成文獻與世界的單位及時間換算；回覆可執行建議使用世界單位，換算依據、假設與缺少映射寫入`evidence_and_unknowns`及公開說明。Core依世界規則整合建議，不承擔文獻換算。

現有映射：人類參考1 kcal對應1 game_kcal、1 kg氧氣對應1000 OU、水以L計；作物產能的game_kcal係數是遊戲設定。人類1 tick是1小時，作物1有效生長tick對應文獻1天，不可把所有速率用同一時間倍率換算。EU尚未定義Wh／kWh映射，專家須標示此限制，不得自行創造比例或改寫世界公式。

### 世界資料與單位

- world.resources.food：公共食物，遊戲kcal。
- world.resources.water：公共水，L。
- world.resources.oxygen：公共氧氣，OU。
- world.resources.power：公共電力，EU。
- world.crew[]：id、food_energy（遊戲kcal）、water（L）；實際後端可能附alive等狀態。
- world.plots[]：id、crop_type、status（empty/growing/mature/dead）、growth_ticks、consecutive_unirrigated_ticks。
- world.tick：模擬tick；1 tick為1模擬小時。人類每日需求除24；只有作物一天壓成1 tick。

Human必須同時考慮公共及個人庫存；個人能量或水歸零死亡，公共氧氣歸零全員死亡。水／電有任一不足，該地塊灌溉不扣任何投入，連續3次失敗植物死亡。精確數值由rules取得，不在你們的prompt硬編另一份。

world可含後端額外欄位（例如當前plan與暫停資訊），請容忍未知輸入欄位。Core不保證每次專家請求都另帶current_plan；可用的前輪候選計畫見previous_messages，其他缺資料請寫uncertainties，不自行猜測。

## 5. 專家回覆內容

### content：五欄都要有

| 欄位 | 建議型別 | 內容 |
|---|---|---|
| observations | array of strings | 觀察到的狀態與風險 |
| priorities | array of strings | 本領域的優先需求 |
| suggested_actions | array of objects | 建議操作，可包含proposal_id、description及其他建議參數；不是執行命令 |
| acceptable_tradeoffs | array of strings | 可讓步的部分與代價 |
| evidence_and_unknowns | array of strings | 遊戲規則／文獻依據，以及未知項目 |

目前Core對content只驗證五欄存在，內部可用文字、陣列或物件。為方便三方對齊，新服務建議採表列型別。若無內容填空陣列，不省略欄位。

### explanation：所有欄位必填，禁止多餘欄位

| 欄位 | 型別 | 說明 |
|---|---|---|
| observations | string[] | 可公開的觀察與風險 |
| proposals | object[] | 本輪具體策略，逐項列理由、預期效果和代價 |
| reviews | object[] | 回應前輪某項建議；第一輪通常空陣列 |
| conflicts | string[] | 辨識出的需求衝突，沒有就空陣列 |
| follow_up_reason | string | 如希望進一步討論，說明原因；無則空字串 |
| decision_reason | string | 本輪推薦此方向的公開理由；專家不做最終決策，無則空字串 |
| uncertainties | string[] | 未知與假設，沒有就空陣列 |

每個proposals元素必須完整包含：

| 欄位 | 型別 | 說明 |
|---|---|---|
| proposal_id | string | 同一訊息內唯一且非空；跨輪建議使用新ID |
| strategy | string | 建議做什麼，可包含先後步驟 |
| reason | string | 為什麼建議這樣做 |
| expected_effect | string | 依規則預期的影響，不能假裝已執行 |
| tradeoffs | string[] | 犧牲什麼、會占用哪些資源／人力 |
| evidence | string[] | 對應world／rules欄位或文獻來源與頁碼；不要捏造來源 |

每個reviews元素必須完整包含：

| 欄位 | 型別 | 說明 |
|---|---|---|
| message_id | string | 被評論的原始訊息ID |
| proposal_id | string | 該訊息中被評論的建議ID |
| disposition | enum | accept / modify / reject / needs_clarification |
| assessment | string | 為何同意、調整、不採納或要求釐清 |

reviews應引用previous_messages中真實存在的建議。若修正自己前一輪建議，也引用舊建議並在proposals提出新的方案。content與explanation不得互相矛盾；建議先生成一份資料再衍生摘要，避免兩次獨立生成。

這是公開的策略解釋，不要求內部思考鏈。前端用display_text顯示短對話，explanation展開策略卡片；Core產生detail_text讓前端也可直接顯示完整敘述。

## 6. 回覆驗收清單

- [ ] URL、驗證方式及timeout已提供Core負責人。
- [ ] JSON body直接是訊息，不是字串、Markdown code fence或data wrapper。
- [ ] discussion_id／round／world_version正確回傳。
- [ ] sender為自己角色，recipient固定core，message_id為新值。
- [ ] content五欄齊全，explanation全部七欄齊全且型別正確。
- [ ] proposal_id不空白、不重複；reviews引用真實訊息與建議。
- [ ] display_text是繁體中文，說明建議而非聲稱已操作世界。
- [ ] 第一輪與追問回覆都測過；能讀到對方建議及Core追問原因。
- [ ] 失敗回非2xx，不回假的成功建議；不在錯誤內容洩漏API key。

## 7. 完整範例

以下請求含完整4名crew、20塊地、rules及explanation_schema，可直接用作開發fixture。Human請求的結構相同，需改recipient、message_id、question及analysis_scope；Human的analysis_scope為["water", "oxygen", "power", "food"]。

### 7.1 Core → Plant 請求

```json
{
  "discussion_id": "discussion-example-001",
  "round": 1,
  "sender": "core",
  "recipient": "plant",
  "world_version": 0,
  "content": {
    "question": "請僅以電、水、固定二氧化碳條件評估植物策略、成長與產出，並提供繁體中文摘要。",
    "world": {
      "world_version": 0,
      "rules_version": "greenhouse-2026-09-12-v1",
      "tick": 0,
      "resources": {
        "water": 3000,
        "food": 120000,
        "oxygen": 8000,
        "power": 6000
      },
      "crew": [
        {
          "id": "crew-0",
          "food_energy": 2400,
          "water": 1.5
        },
        {
          "id": "crew-1",
          "food_energy": 2400,
          "water": 1.5
        },
        {
          "id": "crew-2",
          "food_energy": 2400,
          "water": 1.5
        },
        {
          "id": "crew-3",
          "food_energy": 2400,
          "water": 1.5
        }
      ],
      "plots": [
        {
          "id": "plot-0",
          "crop_type": "lettuce",
          "status": "growing",
          "growth_ticks": 0,
          "consecutive_unirrigated_ticks": 0
        },
        {
          "id": "plot-1",
          "crop_type": "lettuce",
          "status": "growing",
          "growth_ticks": 0,
          "consecutive_unirrigated_ticks": 0
        },
        {
          "id": "plot-2",
          "crop_type": "lettuce",
          "status": "growing",
          "growth_ticks": 0,
          "consecutive_unirrigated_ticks": 0
        },
        {
          "id": "plot-3",
          "crop_type": "lettuce",
          "status": "growing",
          "growth_ticks": 0,
          "consecutive_unirrigated_ticks": 0
        },
        {
          "id": "plot-4",
          "crop_type": "potato",
          "status": "growing",
          "growth_ticks": 0,
          "consecutive_unirrigated_ticks": 0
        },
        {
          "id": "plot-5",
          "crop_type": "potato",
          "status": "growing",
          "growth_ticks": 0,
          "consecutive_unirrigated_ticks": 0
        },
        {
          "id": "plot-6",
          "crop_type": "potato",
          "status": "growing",
          "growth_ticks": 0,
          "consecutive_unirrigated_ticks": 0
        },
        {
          "id": "plot-7",
          "crop_type": "potato",
          "status": "growing",
          "growth_ticks": 0,
          "consecutive_unirrigated_ticks": 0
        },
        {
          "id": "plot-8",
          "crop_type": "tomato",
          "status": "growing",
          "growth_ticks": 0,
          "consecutive_unirrigated_ticks": 0
        },
        {
          "id": "plot-9",
          "crop_type": "tomato",
          "status": "growing",
          "growth_ticks": 0,
          "consecutive_unirrigated_ticks": 0
        },
        {
          "id": "plot-10",
          "crop_type": "tomato",
          "status": "growing",
          "growth_ticks": 0,
          "consecutive_unirrigated_ticks": 0
        },
        {
          "id": "plot-11",
          "crop_type": "tomato",
          "status": "growing",
          "growth_ticks": 0,
          "consecutive_unirrigated_ticks": 0
        },
        {
          "id": "plot-12",
          "crop_type": "wheat",
          "status": "growing",
          "growth_ticks": 0,
          "consecutive_unirrigated_ticks": 0
        },
        {
          "id": "plot-13",
          "crop_type": "wheat",
          "status": "growing",
          "growth_ticks": 0,
          "consecutive_unirrigated_ticks": 0
        },
        {
          "id": "plot-14",
          "crop_type": "wheat",
          "status": "growing",
          "growth_ticks": 0,
          "consecutive_unirrigated_ticks": 0
        },
        {
          "id": "plot-15",
          "crop_type": "wheat",
          "status": "growing",
          "growth_ticks": 0,
          "consecutive_unirrigated_ticks": 0
        },
        {
          "id": "plot-16",
          "crop_type": "soybean",
          "status": "growing",
          "growth_ticks": 0,
          "consecutive_unirrigated_ticks": 0
        },
        {
          "id": "plot-17",
          "crop_type": "soybean",
          "status": "growing",
          "growth_ticks": 0,
          "consecutive_unirrigated_ticks": 0
        },
        {
          "id": "plot-18",
          "crop_type": "soybean",
          "status": "growing",
          "growth_ticks": 0,
          "consecutive_unirrigated_ticks": 0
        },
        {
          "id": "plot-19",
          "crop_type": "soybean",
          "status": "growing",
          "growth_ticks": 0,
          "consecutive_unirrigated_ticks": 0
        }
      ]
    },
    "rules": {
      "rules_version": "greenhouse-2026-09-12-v1",
      "tick_hours": 1,
      "environment": {
        "carbon_dioxide": {
          "value": 500,
          "unit": "ppm",
          "adjustable": false
        }
      },
      "resources": {
        "food": {
          "unit": "game_kcal",
          "capacity": 200000,
          "warning": 12000
        },
        "water": {
          "unit": "L",
          "capacity": 4000,
          "warning": 400
        },
        "oxygen": {
          "unit": "OU",
          "capacity": 15000,
          "warning": 600
        },
        "power": {
          "unit": "EU",
          "capacity": 10000,
          "warning": 1000
        }
      },
      "crew": {
        "daily_reference": {
          "kcal": 3054,
          "oxygen_kg": 0.895,
          "water_L": 3.217
        },
        "per_tick": {
          "food_energy": 127.25,
          "oxygen": 37.291666666666664,
          "water": 0.13404166666666667
        },
        "capacity": {
          "food_energy": 3000,
          "water": 2
        },
        "warning": {
          "food_energy": 700,
          "water": 0.4
        },
        "refill_limit": {
          "eat": 1000,
          "drink": 0.5
        },
        "refill_ratio": 1,
        "death": "personal energy or water <= 0; any crew death ends mission"
      },
      "generation": {
        "food_energy": 100,
        "oxygen": 25,
        "power": 250,
        "max_units_per_crew_tick": 1,
        "stations": 4
      },
      "water_production": {
        "power_per_L": 2,
        "oxygen_per_L": 0.2,
        "max_L_per_tick": 250
      },
      "irrigation": {
        "water_per_plot": 8.7,
        "power_per_plot": 5,
        "atomic_inputs": true,
        "misses_until_death": 3,
        "priority": "Core supplied order; omitted living plots receive nothing",
        "failure": "no input deducted, no growth or oxygen; success resets misses",
        "dead": "no consumption or yield; clear before planting"
      },
      "crops": {
        "lettuce": {
          "maturity_ticks": 30,
          "harvest_game_kcal": 585,
          "oxygen_per_tick": 16
        },
        "potato": {
          "maturity_ticks": 90,
          "harvest_game_kcal": 8775,
          "oxygen_per_tick": 16
        },
        "tomato": {
          "maturity_ticks": 90,
          "harvest_game_kcal": 1755,
          "oxygen_per_tick": 22
        },
        "wheat": {
          "maturity_ticks": 90,
          "harvest_game_kcal": 13162.5,
          "oxygen_per_tick": 10
        },
        "soybean": {
          "maturity_ticks": 90,
          "harvest_game_kcal": 12162.15,
          "oxygen_per_tick": 12
        }
      },
      "tasks": {
        "occupancy": "eat, drink, generate, plant, harvest, clear: one crew per tick",
        "controls_and_movement": "visual only, no occupancy",
        "crop_actions": "at tick end, ordered; no premature harvest; full storage blocks harvest",
        "plant": "empty plot only; no seed cost; starts growing next tick"
      },
      "oxygen_death": "public oxygen <= 0 immediately kills all crew, even before plants produce oxygen",
      "tick_order": [
        "ordered refill",
        "personal metabolism",
        "public breathing",
        "generation",
        "water production",
        "ordered irrigation",
        "ordered crop actions"
      ],
      "planning": "world paused while planning; validate state version before apply; no simulator",
      "completion": "no stable/success threshold; continue until death"
    },
    "analysis_scope": [
      "power",
      "water",
      "carbon_dioxide"
    ],
    "unit_conversion_policy": "Core傳送世界原始數值與單位，不轉換文獻單位。專家自行完成文獻與世界單位、時間基準的換算；回覆可執行建議須使用世界單位，並在evidence_and_unknowns說明換算依據或缺少的映射。不得自行假設EU對Wh的比例。電力及跨角色資源分配由Core決定。",
    "previous_messages": [],
    "reason": "initial",
    "response_guidance": "請在外層 display_text 提供2至4句繁體中文對話：觀察、建議、取捨或不確定性。這是公開理由摘要，不是內部思考鏈；不得聲稱操作已執行。另須提供explanation結構：觀察、各項建議策略／理由／效果／代價／依據、回覆其他建議的評估與不確定性。",
    "explanation_schema": {
      "type": "object",
      "properties": {
        "observations": {
          "type": "array",
          "items": {
            "type": "string"
          }
        },
        "proposals": {
          "type": "array",
          "items": {
            "type": "object",
            "properties": {
              "proposal_id": {
                "type": "string"
              },
              "strategy": {
                "type": "string"
              },
              "reason": {
                "type": "string"
              },
              "expected_effect": {
                "type": "string"
              },
              "tradeoffs": {
                "type": "array",
                "items": {
                  "type": "string"
                }
              },
              "evidence": {
                "type": "array",
                "items": {
                  "type": "string"
                }
              }
            },
            "required": [
              "proposal_id",
              "strategy",
              "reason",
              "expected_effect",
              "tradeoffs",
              "evidence"
            ],
            "additionalProperties": false
          }
        },
        "reviews": {
          "type": "array",
          "items": {
            "type": "object",
            "properties": {
              "message_id": {
                "type": "string"
              },
              "proposal_id": {
                "type": "string"
              },
              "disposition": {
                "type": "string",
                "enum": [
                  "accept",
                  "modify",
                  "reject",
                  "needs_clarification"
                ]
              },
              "assessment": {
                "type": "string"
              }
            },
            "required": [
              "message_id",
              "proposal_id",
              "disposition",
              "assessment"
            ],
            "additionalProperties": false
          }
        },
        "conflicts": {
          "type": "array",
          "items": {
            "type": "string"
          }
        },
        "follow_up_reason": {
          "type": "string"
        },
        "decision_reason": {
          "type": "string"
        },
        "uncertainties": {
          "type": "array",
          "items": {
            "type": "string"
          }
        }
      },
      "required": [
        "observations",
        "proposals",
        "reviews",
        "conflicts",
        "follow_up_reason",
        "decision_reason",
        "uncertainties"
      ],
      "additionalProperties": false
    }
  },
  "display_text": "請僅以電、水、固定二氧化碳條件評估植物策略、成長與產出，並提供繁體中文摘要。",
  "message_id": "core-request-plant-001",
  "explanation": {
    "observations": [],
    "proposals": [],
    "reviews": [],
    "conflicts": [],
    "follow_up_reason": "initial",
    "decision_reason": "",
    "uncertainties": []
  },
  "detail_text": "再次討論的原因：initial"
}
```

### 7.2 Plant → Core 成功回覆

```json
{
  "discussion_id": "discussion-example-001",
  "round": 1,
  "sender": "plant",
  "recipient": "core",
  "world_version": 0,
  "content": {
    "observations": [
      "五種作物各4塊，目前生長進度均為0。",
      "20塊地完整灌溉每tick需要174 L水與100 EU電力。"
    ],
    "priorities": [
      "crew存活並維持資源循環"
    ],
    "suggested_actions": [
      {
        "proposal_id": "plant-proposal-001",
        "description": "下一tick為20塊存活地塊安排完整灌溉配額。"
      }
    ],
    "acceptable_tradeoffs": [
      "持續消耗水與電，Core仍需安排製水與人力發電。"
    ],
    "evidence_and_unknowns": [
      "輸入world.plots",
      "輸入rules.irrigation",
      "輸入rules.crops",
      "本建議沒有進行未來模擬；完整資源與工作分配由Core決定。"
    ]
  },
  "display_text": "目前20塊地都剛開始生長。我建議先維持完整灌溉，但要保留後續補充crew與發電所需的資源。",
  "message_id": "plant-reply-001",
  "explanation": {
    "observations": [
      "五種作物各4塊，目前生長進度均為0。",
      "20塊地完整灌溉每tick需要174 L水與100 EU電力。"
    ],
    "proposals": [
      {
        "proposal_id": "plant-proposal-001",
        "strategy": "下一tick為20塊存活地塊安排完整灌溉配額。",
        "reason": "保留生長進度與供氧能力；灌溉連續中斷3 ticks會死亡。",
        "expected_effect": "成功供應時地塊各增加1有效生長tick，合計產氧304 OU。",
        "tradeoffs": [
          "持續消耗水與電，Core仍需安排製水與人力發電。"
        ],
        "evidence": [
          "輸入world.plots",
          "輸入rules.irrigation",
          "輸入rules.crops"
        ]
      }
    ],
    "reviews": [],
    "conflicts": [],
    "follow_up_reason": "",
    "decision_reason": "",
    "uncertainties": [
      "本建議沒有進行未來模擬；完整資源與工作分配由Core決定。"
    ]
  }
}
```

### 7.3 Human → Core 成功回覆

Human請求使用相同discussion_id／round／world_version，recipient為human時，對應回覆如下：

```json
{
  "discussion_id": "discussion-example-001",
  "round": 1,
  "sender": "human",
  "recipient": "core",
  "world_version": 0,
  "content": {
    "observations": [
      "個人能量與水目前皆高於警戒線。",
      "進食與飲水各占1 tick，同一人該tick不能發電。"
    ],
    "priorities": [
      "crew存活並維持資源循環"
    ],
    "suggested_actions": [
      {
        "proposal_id": "human-proposal-001",
        "description": "在個人基礎消耗後安排合適發電量，並在後續階段安排補充。"
      }
    ],
    "acceptable_tradeoffs": [
      "工作量增加會縮短下一次進食前的餘裕。"
    ],
    "evidence_and_unknowns": [
      "輸入world.crew",
      "輸入rules.crew",
      "輸入rules.generation",
      "本建議沒有進行未來模擬；完整資源與工作分配由Core決定。"
    ]
  },
  "display_text": "四名crew目前各有2400遊戲kcal與1.5 L水。我建議這一tick可考慮安排發電，但後續必須安排進食與飲水，不能持續無限工作。",
  "message_id": "human-reply-001",
  "explanation": {
    "observations": [
      "個人能量與水目前皆高於警戒線。",
      "進食與飲水各占1 tick，同一人該tick不能發電。"
    ],
    "proposals": [
      {
        "proposal_id": "human-proposal-001",
        "strategy": "在個人基礎消耗後安排合適發電量，並在後續階段安排補充。",
        "reason": "電力供應植物與製水，但工作消耗個人能量和公共氧氣。",
        "expected_effect": "每單位工作消耗100遊戲kcal個人能量及25 OU公共氧氣，產出250 EU。",
        "tradeoffs": [
          "工作量增加會縮短下一次進食前的餘裕。"
        ],
        "evidence": [
          "輸入world.crew",
          "輸入rules.crew",
          "輸入rules.generation"
        ]
      }
    ],
    "reviews": [],
    "conflicts": [],
    "follow_up_reason": "",
    "decision_reason": "",
    "uncertainties": [
      "本建議沒有進行未來模擬；完整資源與工作分配由Core決定。"
    ]
  }
}
```

## 8. 第二輪與過期資料

Core下一輪傳送新message_id、round=2，discussion_id與world_version保持不變。previous_messages包含兩位專家與Core第一輪公開評估。Core外層explanation.follow_up_reason會說明為何需要再次討論，question提供具體追問。

若原世界被修改，後端不能執行基於舊版本的plan。專家依收到的快照回覆即可，不自行讀取另一版本拼入同次回覆；Core負責識別並拒絕過期結果。

三位agent不需要共享記憶體或相同框架，只要依此JSON協定通訊即可。這份格式為目前程式支援的交接基準；如需改動欄位，請同步三方後更新版本，不自行在外層增加不同格式。

## 9. 必填世界狀態 JSON Schema（補充）

**資源不是只有範例：以下schema就是請求content.world的結構約束。** `resources`與其food／water／oxygen／power全部必填；四名crew與20塊地也必填。資源是number，單位由description固定，不能傳字串或不同單位。

套用位置：驗證 `request.content.world`，不是整個request。所有請求使用此完整結構，不能只提供本領域的局部資源。Core在詢問任何專家前會先執行世界驗證。

容量上下限為目前規則版本的值；公式或容量調整時必須同步規則版本和schema。Core另外檢查crew／plot ID唯一、空地對應null作物與作物成熟進度上限。這些跨欄位條件不只靠下方JSON Schema表達。

world與crew／plot允許後端附加狀態；resources固定四個欄位，不接受拼錯或自行增加的資源名稱。`alive`是選填，其他表列核心欄位必填。schema驗證不代表世界仍存活：0是合法數值，但死亡效果仍由世界規則執行。

以下內嵌完整schema，因此轉交本文件不需要另附schema檔：

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "title": "Core shared world snapshot",
  "type": "object",
  "properties": {
    "world_version": {
      "type": "integer",
      "minimum": 0
    },
    "rules_version": {
      "type": "string",
      "minLength": 1
    },
    "tick": {
      "type": "integer",
      "minimum": 0
    },
    "resources": {
      "type": "object",
      "properties": {
        "food": {
          "type": "number",
          "minimum": 0,
          "maximum": 200000,
          "description": "公共食物庫存，遊戲 kcal；Food是欄位名稱，不是另一種單位。"
        },
        "water": {
          "type": "number",
          "minimum": 0,
          "maximum": 4000,
          "description": "公共水庫存，L。"
        },
        "oxygen": {
          "type": "number",
          "minimum": 0,
          "maximum": 15000,
          "description": "公共氧氣庫存，OU。"
        },
        "power": {
          "type": "number",
          "minimum": 0,
          "maximum": 10000,
          "description": "公共電力庫存，EU。"
        }
      },
      "required": [
        "food",
        "water",
        "oxygen",
        "power"
      ],
      "additionalProperties": false
    },
    "crew": {
      "type": "array",
      "minItems": 4,
      "maxItems": 4,
      "items": {
        "type": "object",
        "properties": {
          "id": {
            "type": "string",
            "minLength": 1
          },
          "food_energy": {
            "type": "number",
            "minimum": 0,
            "maximum": 3000,
            "description": "個人能量，遊戲 kcal；與公共food分開。"
          },
          "water": {
            "type": "number",
            "minimum": 0,
            "maximum": 2,
            "description": "個人水存量，L；與公共water分開。"
          },
          "alive": {
            "type": "boolean",
            "description": "選填後端存活狀態。"
          }
        },
        "required": [
          "id",
          "food_energy",
          "water"
        ],
        "additionalProperties": true
      }
    },
    "plots": {
      "type": "array",
      "minItems": 20,
      "maxItems": 20,
      "items": {
        "type": "object",
        "properties": {
          "id": {
            "type": "string",
            "minLength": 1
          },
          "crop_type": {
            "type": [
              "string",
              "null"
            ],
            "enum": [
              "lettuce",
              "potato",
              "tomato",
              "wheat",
              "soybean",
              null
            ]
          },
          "status": {
            "type": "string",
            "enum": [
              "empty",
              "growing",
              "mature",
              "dead"
            ]
          },
          "growth_ticks": {
            "type": "integer",
            "minimum": 0,
            "maximum": 90
          },
          "consecutive_unirrigated_ticks": {
            "type": "integer",
            "minimum": 0,
            "maximum": 3
          }
        },
        "required": [
          "id",
          "crop_type",
          "status",
          "growth_ticks",
          "consecutive_unirrigated_ticks"
        ],
        "additionalProperties": true
      }
    }
  },
  "required": [
    "world_version",
    "rules_version",
    "tick",
    "resources",
    "crew",
    "plots"
  ],
  "additionalProperties": true
}
```
