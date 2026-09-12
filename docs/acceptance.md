# Space Greenhouse v2 驗收追蹤

本文件是驗收規劃，不代表測試已建立、執行或通過。原始規格為 `space_greenhouse_spec_v2.md` §11；世界數值與公式以 `world-settings-guide.md` 為準。下列測試名稱為預定名稱，實作後應同步實際名稱與結果。

## 數值與行為驗收：原表 23 列

所有測試庫存、請求與期望值均由共用設定、公式或明確標示的測試情境建立；不把顯示用近似小數作結算常數。

| # | spec §11 案例 | 階段／預定測試檔 | 預定測試名稱 | 狀態 |
|---|---|---|---|---|
| 1 | potato 單塊採收量由公式推導 | 2／`test_engine_numeric.py` | `test_guide_2_2_potato_harvest` | 待驗 |
| 2 | lettuce 單塊採收量由公式推導 | 2／`test_engine_numeric.py` | `test_guide_2_2_lettuce_harvest` | 待驗 |
| 3 | 正常製水，三種資源按實際量變動 | 2／`test_engine_numeric.py` | `test_guide_2_5_water_production_costs` | 待驗 |
| 4 | 超設備上限的製水請求縮量 | 2／`test_engine_numeric.py` | `test_guide_2_5_water_production_limit` | 待驗 |
| 5 | 四人滿額發電，扣個人能量與公共氧氣 | 2／`test_engine_numeric.py` | `test_guide_2_4_full_generation` | 待驗 |
| 6 | 四人基礎消耗加滿額發電總量 | 2／`test_engine_numeric.py` | `test_guide_2_3_2_4_total_consumption` | 待驗 |
| 7 | 發電受個人剩餘能量及工作上限約束 | 2／`test_engine_numeric.py` | `test_guide_2_4_personal_generation_limit` | 待驗 |
| 8 | 全地塊灌溉成功的水電成本 | 2／`test_engine_numeric.py` | `test_guide_2_1_all_plots_irrigated` | 待驗 |
| 9 | 僅列部分地塊，未列者不扣款且中斷加一 | 2／`test_engine_numeric.py` | `test_guide_2_1_partial_irrigation_plan` | 待驗 |
| 10 | 連續灌溉中斷達死亡界線，當 tick 不可採收 | 2／`test_engine_numeric.py` | `test_guide_2_1_unirrigated_death` | 待驗 |
| 11 | 死亡前恢復灌溉，計數歸零且進度保留 | 2／`test_engine_numeric.py` | `test_guide_2_1_irrigation_recovery` | 待驗 |
| 12 | 氧氣超容量時記錄實際入庫與溢出 | 2／`test_engine_numeric.py` | `test_guide_2_1_oxygen_overflow` | 待驗；原例前提錯誤，見下方 |
| 13 | 當 tick 產氧不可救援較早階段耗氧 | 2／`test_engine_numeric.py` | `test_guide_2_6_oxygen_availability` | 待驗；pending 語意見下方 |
| 14 | 當 tick 發電可供當 tick 製水 | 2／`test_engine_numeric.py` | `test_guide_2_6_new_power_available` | 待驗 |
| 15 | 完整收成放不下時保留成熟作物並發事件 | 2／`test_engine_numeric.py` | `test_guide_2_2_harvest_capacity` | 待驗 |
| 16 | 公共食物不足時縮量轉入，補充仍占用工作 | 2／`test_engine_numeric.py` | `test_guide_2_3_refill_shortage` | 待驗 |
| 17 | 個人水消耗至零立即死亡並停止後續階段 | 2／`test_engine_numeric.py` | `test_guide_2_3_personal_water_death` | 待驗 |
| 18 | 呼吸恰好清空氧氣，全員立即死亡 | 2／`test_engine_numeric.py` | `test_guide_2_3_breathing_zero_oxygen` | 待驗 |
| 19 | 玩家把氧氣設零，立即全員死亡 | 3、5／`test_loop.py`、API 驗證 | `test_guide_2_3_player_zero_oxygen` | 待驗；非純引擎 I/O 責任 |
| 20 | 暫停期間庫存與灌溉計數不變 | 2、3／`test_engine_numeric.py`、`test_loop.py` | `test_guide_1_3_pause_no_changes` | 待驗 |
| 21 | 同 crew 採收加播種回傳指定錯誤 | 3／`test_validator.py` | `test_guide_3_2_same_crew_harvest_and_plant` | 待驗；非數值引擎責任 |
| 22 | 同 crew 進食加部分發電回傳重複占用錯誤 | 3／`test_validator.py` | `test_guide_3_2_crew_double_booked` | 待驗；非數值引擎責任 |
| 23 | prompt 寫入固定分配政策時檢查必須失敗 | 4／`test_prompts_no_policy.py` | `test_policy_detector_rejects_forbidden_prompt` | 待驗；非數值引擎責任 |

第 19、21、22、23 列原規格列在數值表，但分別涵蓋玩家干預、驗證器及 prompt 掃描。Phase 2 提前建立這些跨層純函數，由 `test_engine_numeric.py` 覆蓋全部 23 列；上表後續階段標示為完整流程的再次驗證。不在 WorldEngine 加入 I/O、上層依賴或 prompt 邏輯，不把纯函數通過當成整合完成。

氧氣溢出原測例使用初始氧氣加全地塊單次產氧，依 guide 無法達容量；改用依容量推導的近滿庫存驗證溢出，原始文件不改動。

## 前端驗收

- [x] `npm run build` 通過（2026-09-12，TypeScript + Vite，2942 modules）；可重跑命令見 `docs/frontend.md`。
- [x] `npm run dev:mock -- --port 5174` 可獨立啟動；使用預錄 state／事件，明確標示 mock。5173 被另一專案占用，未停止該服務。
- [x] 畫面為正交俯視火星基地，六區域與走廊可辨識；RimWorld 風格只影響美術，不新增世界規則。
- [x] 無常駐儀表板／資源條；只保留時間徽章、下方工具列、Agent 抽屜三處 chrome。證據：`artifacts/mock-world.png`。
- [x] 水箱液面、氧氣壓力環、電池亮格、食物堆層數對應權威 snapshot；程式檢查與 `artifacts/mock-world.png`、`artifacts/mock-partial-irrigation.png`。
- [x] 20 塊地均在初始 viewport 內；作物四階段縮放呈現，空地標 EMPTY、灌溉中斷有 !、死亡有叉。基本瀏覽器檢查與場景程式檢查。
- [x] hover 水箱出現數值與單位 tooltip；headless 證據：`artifacts/water-tooltip.png`、`artifacts/frontend_smoke.json`。
- [x] 物件詳細卡、近期歷史圖表與 Esc 通過互動測試；拖曳平移與縮放已實作並檢查程式，完整交互回歸留 Phase 7。
- [x] crew 沿 waypoint 定速行走、有邁步與朝向；瀏覽器確認前後位置改變，動畫不改模擬時間或資源。
- [x] 任務姿勢保持靜止為主，每 3.1 秒作短暫動作；進食坐姿、地塊操作蹲姿，走路獨立插值。程式檢查：`crew_sprite.ts`。
- [x] 發電踏板與線路光流依實際工作量；製水管線流光依實際產量比例。程式檢查：`world_objects.ts`。
- [x] crew 低存量以 LOW E／LOW H2O 提示，個人卡可查；死亡倒地與停止路徑由權威 alive 驅動。缺氧失敗與 reset 通過互動測試。
- [x] 飲水點位置仍為 `TODO(guide-pending)`；不擅自指定房間，相關實景與走路動畫待確認。
- [x] Agent 氣泡按角色錨定設施，六種 kind 有對應樣式，逐字呈現與 4.6 秒淡出；驗證錯誤目標紅框，同步保留在聊天抽屜。程式檢查與 `artifacts/agent-conversation.png`。
- [ ] 真後端 mock provider：修改 power 的指定 demo 值後，規定時間內依序出现氣泡、TickPlan 生效、部分地塊邊框轉黃，再恢復供應。
- [ ] 真後端氧氣設零後立即收到 mission_failed；死亡卡顯示原因與 tick，基地仍可見。
- [ ] 斷線狀態可辨識；重連取得權威 snapshot，不重播資源扣款。
- [ ] 新增作物僅增 `shared/crops.json` 資料與對應貼圖；無手寫五值 enum、作物 switch 或第二份參數表需要修改。
- [x] 前端五段 demo 只重播後端引擎產生的預錄 snapshot／訊息；不在 mock server 或畫面計算下一份資源。任意資源修改限連線模式。

## 待定接口與文件差異

- `TODO(guide-pending)`：正式 refill 工具未定；最小 TickPlan 表達需由 Core 指定對象、請求量及順序，缺省為空陣列，不自動补充。
- `TODO(guide-pending)`：飲水點位置未指定；不把 spec 的 Galley 暫放建議當成已確認需求。
- `TODO(guide-pending)`：clear 底層操作保留，前端不新增未確認的玩家／crew 入口。
- `TODO(guide-pending)`：設備故障不實作規則、隨機事件或效果；玩家已有修改公共資源的專用入口。
- pending 入庫：已批准依 spec 下一 tick 入庫，當 tick 用 `resources + pending` 預留容量；玩家編輯該項資源時清該項 pending。這是相對 guide 採收立即入庫文字的明列差異。
- 空計畫 fallback：已批准三輪驗證失敗後以空 TickPlan 結算並發 `plan_failed`；其他明確暫停狀態仍不推進。
- reflection：已批准在 settle 後依實際結果產生。
- 階段調整：已批准 Phase 2 提前建立玩家修改、計畫驗證與政策掃描的純函數，使原表 23 列全部可測。上表後續階段標示為完整流程再驗，不把純函數通過當成整合完成。
- 第六作物：`CropKey` 與各 provider 的作物 schema 須從共用資料推導，不能另維護五個固定 key。
- mock 固定 demo 與 checks 基準策略必須明確標示用途，不進入正式引擎或 prompt 作隱藏政策。
