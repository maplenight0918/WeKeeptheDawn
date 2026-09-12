# 三 Agent 整合驗證紀錄

日期：2026-09-12。使用獨立 `.venv-bridge`（CPython 3.11.14、FastAPI 0.119.1、Pydantic 2.13.5、httpx 0.28.1、websockets 15.0.1）。保留原有 Python 3.9 `.venv` 與三個 Agent 的程式、prompt、provider、`.env`。首批驗證未發送付費模型請求；後續經使用者明確同意完成一次真實聯測，見下方專節。

| 範圍 | 實測結果 |
| --- | --- |
| 完整後端回歸 | 202 passed；包含首批 4 個 HTTP／WS 聯測。 |
| 補充網路失敗案例 | 再執行 `test_bridge_http.py` 為 6 passed，新增三次拒絕後空計畫及 specialist 失聯兩項；與前述完整回歸合計 204 個不同案例通過。 |
| Core 既有 unittest | 27 passed。包含多輪、版本、timeout、格式與既有 controller 邊界。 |
| Human mock 既有 pytest | 130 passed。以環境變數 `AGENT_MODE=mock` 覆蓋模式，未改 `.env`。 |
| Plant 既有 unittest | 15 passed；RetrievalTests.setUpClass 因缺 `data/index/embeddings.npy` 失敗，不能報整套通過。 |
| 前端型別與建置 | `npm run typecheck`、`npm run build` 通過；保留原套件與 lockfile。build 有既有大型 bundle 警告。 |
| 真實瀏覽器展示 | `node checks/smoke_three_agent_bridge.mjs` 通過：tick 2、2 組對話、2 張版本配對的計畫卡、2 張結果卡、3 個 Agent、玩家 pause，page_errors 為空。 |

後端測試涵蓋非零 pending、有效 settings、null／非 null summary、控制狀態、行動順序與缺漏拒絕；亦涵蓋 request/version 失效、422 不計入 loop 驗證次數、三次拒絕只結算一次空計畫、逾時／失敗錯誤暫停、去重與同 ID 不同 body 拒絕。網路案例額外模擬後端已收件但 HTTP 回應遺失，同 submission 重試沒有第二次結算。

實際 specialist 路由聯測使用隊友 Core 協商程式、fixture DecisionModel、Plant 原始 `/discuss` 規則衝突分支與 Human 原始 `/discuss` mock 模式。Plant 索引啟動被明確替身取代，只為測接口；沒有啟用其檢索或模型分析，也没有用成功狀態掩蓋完整 Plant 服務缺索引的限制。

瀏覽器最初的測試埠與既有前端重疊，曾誤讀其他服務而逾時；修正為啟動前檢查獨立測試埠後通過。沒有對既有世界執行 pause/reset/資源修改，也沒有停止既有服務。測試自建程序已於結束後停止。

## 補驗結果與待交付範圍

### 真實低電量 emergency（使用者授權一次，通過）

執行 `node checks/live_resource_emergency.mjs --allow-paid`，使用隔離記憶體世界18001、瀏覽器15174，以及既有Plant／Human原始服務。瀏覽器透過「修改資源」將電力從6000 EU降至50 EU；世界仍在tick0，版本由0變1。以舊request/version提交計畫回409，之後才啟動唯一一次Core付費規劃。**沒有先呼叫舊版本模型**；在途模型取消已由先前離線測試涵蓋，本次不重複付費測該分支。

結果：一次Core規劃、一輪協商、一次確認結算。Core明確安排c01發電1工作單位，實際產電250 EU；不製水、不補給；20塊地全部灌溉，耗水約174 L、耗電100 EU。期末電力為 `50 + 250 - 100 = 200 EU`，無crew死亡、無灌溉失敗或作物死亡。200 EU仍低於1000 EU警戒線，不能宣稱危機完全解除或後續長期安全。

Plant仍使用權威耗電衝突回覆分支（未進入Plant LLM），Human服務為live並回覆狀態分析，Core採用shared權威值而非Plant替代係數。報告保存實際Core計畫、公開訊息及結算；未來stage沒有提前執行，沒有編造reflection。

瀏覽器確認一張結算卡、Core／Plant／Human均有訊息、page_errors=[]。規劃畫面：`artifacts/live-emergency-planning.png`；結果畫面：`artifacts/live-emergency-result.png`；詳細報告：`artifacts/live-three-agents-1789200385198211242.json`。結束後暫停並關閉測試世界、前端與bridge，8001目前展示不受影響。呼叫前離線付費護欄測試3 passed，未追加付費重試。

### 規劃提示與玩家資源 emergency（離線驗證）

只新增左上徽章「Agent 規劃中」及等待說明，不新增控制確認、控制鎖定或測試結束卡。前端每500ms循序讀取既有 `GET /decision`，只有當前 tick/version 的 awaiting 請求才顯示；每次讀取最多3秒，清理時取消。玩家暫停、錯誤暫停、失敗、斷線、舊版本、查詢失敗或無請求時不顯示。這是後端等待計畫的狀態，不保證 bridge/provider 健康在線，也不由自然語言訊息推斷模型正在執行。

`backend/tests/test_resource_emergency_bridge.py` **7 passed**：

最後完整回歸：`.venv-bridge/bin/python -m pytest -q` **216 passed**（保留第三方套件deprecation warnings）。

- power=0、water=0、food=0、oxygen=警戒線的一半：規劃中的舊 Core 呼叫被取消，舊提交與舊失敗通知回409；Core／Plant／Human 都收到修改後的數值與版本，等待期間不推進或消耗；明確測試替身提供新計畫，後端只結算一次。
- oxygen=0：修改當下同tick全員死亡，立即推播 mission_failed，不再啟動新決策或等待植物救援。
- 玩家暫停時修改power=0：世界保持player pause，不自動恢復或呼叫新規劃。
- 即使原本有304 pending oxygen，玩家將公共氧氣改成0仍立即死亡；該項pending清零，其他pending不受影響。

低資源本身不構成後端自選救援策略；沿用既有 player_edit／版本失效流程，沒有新增 emergency endpoint 或引擎隱藏fallback。本測試驗證接口及世界語意，不是「真實模型可以處理所有資源危機」的驗收。

`node checks/smoke_three_agent_bridge.mjs --emergency` 通過：真實瀏覽器由資源編輯器修改電力及氧氣，驗證新請求、過期計畫409、規劃提示版本防護、暫停／繼續、錯誤暫停、重新整理與斷線恢復；page_errors=[]、paid_calls=0。截圖：`artifacts/planning-status.png`、`artifacts/resource-emergency-planning.png`、`artifacts/resource-emergency-oxygen-zero.png`。前端 build通過，有既有大型bundle提示。測試服務為18001／15174，不修改目前8001展示世界。

### 五 tick 再授權展示（完成 4／5 ticks）

使用者再次同意後，從原測試世界 tick 0、version 5 恢復，開始新的一次最多五次規劃的展示。真實 Core 共啟動 **5 次規劃，4 次結算確認**；沒有自動補空計畫、增加第六次規劃或改世界策略。

| 結算 tick | 實際動作 |
| --- | --- |
| 1 | 四人各飲水 0.5 L；完整灌溉20塊地。 |
| 2 | c01、c02 各發電1工作單位，合計500 EU；製水175 L；完整灌溉。 |
| 3 | c03、c04 輪班發電，合計500 EU；製水175 L；完整灌溉。 |
| 4 | 四人各進食900遊戲 kcal；製水175 L；不發電，完整灌溉。 |

前四輪每轮都由 Core 發出新的當前計畫，plan 的 tick/version 與實際結算配對；飲水／進食沒有因沿用旧設定而重播，未來階段未預先入隊。每 tick 灌溉均扣100 EU，未採 Plant 替代耗電；無死亡或灌溉失敗。這個短樣本沒有地塊操作，不能另宣稱真實採收重播驗收。

第五次規劃期間，tick 4 的 version 10 → 11 狀態差異只有 speed 1.0 → 5.0；控制操作使舊請求失效。短測護欄以 `PaidRetryNotAuthorized` 拒絕同tick再次規劃，轉 error pause，未完成tick5。後續又收到控制操作，收尾時已暫停於 tick4、version18，原進度保留。

報告：`artifacts/live-five-ticks-1789199218023333608.json`；瀏覽器逐tick截圖：`artifacts/live-five-retry-browser-1.png` 至 `-4.png`，終態截圖 `artifacts/live-five-retry-browser-final.png`。瀏覽器可見 Core／Plant／Human 訊息，page_errors 為空；近期三组對話中含未完成第五轮，所以終態只顯示兩張近期結算卡，報告共保存四份已確認結算。完整五tick驗收仍未通過，補跑最後一tick需另行授權。

### 五 tick 瀏覽器真實短測首次嘗試（未完成）

使用者授權五 tick 展示後，原 fixture 在 tick 122 已暫停，保留於 `artifacts/three-agent-actions-demo.sqlite3`。另用 `artifacts/live-five-ticks-demo-20260912.sqlite3` 啟動 8001 真實展示，Plant／Human 仍使用其原始服務。

第一次規劃期間，公開事件紀錄出現 tick 0、version 1 的 player pause，接著 version 2 resume；版本變更取消舊決策。短測每 tick 一次規劃的護欄拒絕再次付費呼叫，後端轉 version 3 error pause，**confirmed_ticks=0、core_calls=1**。沒有編造成功或使用舊計畫。之後世界再次收到 resume，操作收尾已暫停於 tick 0、version 5。

報告：`artifacts/live-five-ticks-1789198791471115405.json`。瀏覽器無 page errors，無結算卡，與零結算結果一致；截圖：`artifacts/live-five-ticks-browser-final.png`。付費次數、同 tick 禁止重試及明確 opt-in 的離線護欄測試 **3 passed**。本次五 tick 驗收未通過；重新啟動付費短測需另行取得同意，不能把一次已通過的單 tick 聯測當成本次成功。

### 首次真實三方串接（2026-09-12，使用者明確授權一次）

執行 `.venv-bridge/bin/python -m checks.live_three_agents --allow-paid`，使用隊友真實 `GPTDecisionModel`、Plant 8101 原始服務、Human 8102 live 原始服務及各自既有設定。沒有改寫 provider、prompt 或世界數值。測試使用臨時埠與記憶體世界，未影響 8001 fixture 展示。

結果：**passed=true、Core 規劃一次、協商一輪、confirmed_ticks=1、無死亡**。Core 計畫經橋接與後端驗證後執行四人各飲水 0.5 L、20 塊地完整灌溉，實際灌溉耗水約 174 L、耗電 100 EU、產氧 304 OU 進入 pending；本 tick 未請求發電或製水。Core 輸出還含未來行動，bridge 僅提交本 tick，沒有提前執行未來階段。

Plant 公開回覆仍主張 4.166781 EU／20 塊／小時，Core 在公開理由中明確採用傳入權威規則，未改成替代係數。Plant 因衝突走其原始 deterministic 回覆，不觸發 Plant embedding／LLM；不能說三個模型都已推理驗收。Human `/discuss` 在 live 設定回 200，公開回覆標示缺完整下一 tick 計畫，先提供狀態分析；不據此宣稱 pending 核算完整。

WS 結算事件已由 bridge 配對並保存實際結果，UI 訊息仍為「Bridge 結算回報」，不是 Core reflection。報告：`artifacts/live-three-agents-1789198363599767031.json`，包含公開訊息、計畫、事件與實際世界，不含金鑰或 provider 原始回應。一次授權已用完；沒有啟動持續付費決策。

### 完整動作與操作恢復補驗（2026-09-12）

- 完整後端回歸已更新為 **206 passed**（前次執行）；前端 build 通過，有既有 bundle 大小提示。
- 本次重新執行 `backend/tests/test_bridge_http.py` 與 `backend/tests/test_action_fixture.py`：**8 passed**，保留第三方套件 deprecation warnings。
- `node checks/smoke_three_agent_bridge.mjs --actions`：tick 40，六種人物工作、製水與自然採收均有實際結算；3 個 Agent 公開訊息可見，無 page errors。
- 新增瀏覽器操作驗收：tick 1 暫停後等待 2.3 秒，完整世界 snapshot 與角色座標均不變；暫停期間重啟 bridge 不自動恢復，玩家按繼續後成功推進到 tick 40。測試最後再次暫停。
- c02 清除 p20 的實際抵達位置已驗證，修正前端將 `plot:p20` 誤比對為裸 ID 的問題。截圖：`artifacts/three-agent-actions.png`。
- 以上在 18001／15174 隔離服務執行，未修改使用者正在操作的展示世界。使用者已回報本機透過 SSH 轉發可開啟；這不是由本測試替代的跨機網路實測。

### 真實 Agent 待交付

- Plant 三份索引已由 Release 安裝並通過 manifest 校驗，完整服務可啟動；檢索排序另有一項測試失敗，詳見下方補驗。
- Plant／Core 複本的灌溉耗電約 0.208339 EU/plot/hour，與遊戲 shared 的 5 EU/plot/tick 不同。bridge 已提供遊戲權威規則，但 Plant 目前回報規則衝突，不能聲稱真實數值建議已對齊。
- Human 可接收請求，但內部忽略額外 snapshot 欄位；pending 的量化核算仍待 owner 明確支援，本次僅驗證完整資料送達 specialist 邊界與既有 mock 回覆。
- CoreAgent 沒有 reflection 接口。已回傳實際摘要供下一輪規劃，UI 清楚標示 Bridge 結算回報，沒有製造 Core reflection。
- 真實 Core 模型與 Human live 服務已完成一次聯測；Plant LLM、長期付費決策、跨機 LAN 自動驗證與跨程序重啟結果恢復仍未驗收。新提交去重僅在程序內保留最近 256 筆，舊 `/ingest/plan` 不具去重。

如何啟動與提供各服務設定見 [bridge README](../agent_runner/README.md)。上述待 owner 提供的功能不以修改世界數值、補寫決策策略或假造模型回覆代替。

耗電衝突及 Human／Core 接口缺口仍存在。逐項交付條件見 [owner 交接清單](three_agent_owner_handoff.md)。

### Plant Release 索引補驗（2026-09-12）

使用者指出索引已放在 [官方 Release index-v1](https://github.com/benson103081/plant-agent-api/releases/tag/index-v1)。下載 `plant-agent-index-v1.zip`（271,191,646 bytes），SHA-256 為 `ab818de08fc96c585015368494311176ead3e3a68e5a0f5ea196f764ce92efd7`，與 GitHub 附件 digest 及 `.sha256` 一致。

壓縮包只含 manifest 列出的三份檔案；逐份串流檢查大小及 SHA-256 全數吻合後，解壓到 `plant_agent/data/index/`。沒有覆写既有資料、修改 Agent 程式或付費重建；三份大型檔案受 Plant `.gitignore` 排除。

使用 `.venv-bridge` 在 Plant 目錄執行完整 unittest：**17 passed、1 failed**。真實向量 shape／ID 對齊與向量正規化測試通過。失敗項為 `RetrievalTests.test_filter_order_scores_and_doc_cap`：回傳分數 `0.6390331387519836` 排在 `0.6390331983566284` 前，違反嚴格降序。程式批次排序後逐筆重算 score，推測為兩種點積計算的浮點差異；未變更其檢索實作或放寬測試，待 owner 處理。

Plant 完整 lifespan 已啟動於 `127.0.0.1:8101`，`GET /health` 實測為 `{"status":"ok","chunks":64160}`。沒有呼叫 `/search`、`/analyze` 或付費 `/discuss`，目前遊戲展示仍使用原 fixture bridge。此補驗取代前述「缺索引無法啟動」的狀態，但不取代數值及真實模型驗收。
