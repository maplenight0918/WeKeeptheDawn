# Plant 與 Core 交接：已確認基準

本文件是 Plant 對 `specialist-agent-api-handoff.md` v1.3 的補充，說明已確認的面積、EU與時間口徑。Core原始文件及共享 `world-settings-guide.md` 保留原文，不代表其程式已同步。本文件不要求重新選擇耗電公式。

## 1. 耗電與面積已定案

- 每塊5 m²、密度27株/m²、135株；20塊共100 m²、2,700株。
- 固定 PPFD 250。Plant 沿用 SPEC 的 LED、空調、水泵合計功率×24小時保守模型；不改成LED僅算14小時，也不是設備實測耗電。
- `1 EU = 3.9745 kWh`；EU為電量，不是功率。`EU = kWh / 3.9745`。
- 電力按世界時間，1 tick＝1小時。作物1有效生長tick對應文獻1天，不把這個加速倍率套到電力。
- 只有growing／mature地塊列入種植設備需求；empty／dead不列入。基地其他設備的空載需求不在Plant模型內。

| 規模 | 功率 kW | 每日 kWh | 每日 EU | 每1小時tick EU |
|---|---:|---:|---:|---:|
| 1塊，5 m² | 0.828043 | 19.873043 | 5.000137 | 0.208339 |
| API預設20 m²，即4塊 | 3.312174 | 79.492174 | 20.000547 | 0.833356 |
| 20塊，100 m² | 16.560870 | 397.460870 | 100.002735 | 4.166781 |

數值由既有 `simulate()` 的未四捨五入功率計算。對外簡稱的79.49 kWh/day是20 m²的兩位小數顯示值，不是整座100 m²的需求；不能先取79.49再放大作精確結算。按面積放大的完整值是397.460870 kWh/day，先前文件397.45是由顯示值放大所得，已更正。

公式：

```text
每塊功率kW = (250 × 5 ÷ 2.3 × 1.45 + 8 × 5) ÷ 1000
每塊EU/tick = 每塊功率kW × tick_hours ÷ 3.9745
整體EU/tick = 每塊EU/tick × 存活種植地塊數
```

## 2. Core原文件尚未同步之處

原文件說EU沒有物理映射，且要求每塊5 EU／tick。依最新Plant基準，每塊約5 EU是**一天**的用電；若每tick一小時，每塊需求約0.208339 EU，20塊約4.166781 EU，而非原本100 EU／tick。

這不是待決定公式，而是**Core需同步接收規則與扣電時間**。如果Core採用新基準，`rules.irrigation.power_per_plot` 應使用約0.208339030887 EU／塊／1小時tick，並同步其規則版本與相關驗證；不能在舊5 EU扣除外再加Plant需求。此處僅是Plant交付口徑，未操作Core程式。

Plant `/discuss` 先用程式核對「傳入rules目前扣電」與「已定案Plant需求」。兩者或tick時間不符時直接產生明確的規則同步建議，附公開conflicts，不呼叫LLM或文獻服務、不自行修改快照、不假裝新數值已生效。這是可辨識的規則核對回覆，不是假的LLM分析結果。水、產氧與收穫仍按Core傳入rules，不趁電力更新改成文獻值。

程式比較時容許每塊EU數值約0.01%的顯示取位誤差；若tick_hours不是1，會依傳入小時換算並另外指出與既定1小時基準不一致。

## 3. API格式與角色

`POST /discuss`，本機URL：`http://127.0.0.1:8000/discuss`。

- 接收Core v1.3世界、規則、問題、歷史與explanation格式。
- 回傳直接訊息JSON，message_id重新產生，discussion_id／round／world_version原樣帶回；sender=plant、recipient=core。
- explanation七欄與各proposal／review嚴格驗證；content五欄由同份解釋衍生，無data wrapper。
- 每輪只提建議，不執行世界、不宣稱已跑未來模擬。Core負責決策與分配，世界負責驗證扣除。
- 第一輪fixture：`tests/fixtures/discuss_round1.json`，故意保留Core原始5 EU規則以測試衝突辨識。後續輪引用真實歷史proposal，拒絕虛構ID。
- 世界、crew、plot允許附加狀態；資源固定四欄，驗證版本、ID及數值。Plant不改外層通訊欄位。

規則核對一致後，三個文獻查詢加一次LLM產生精簡公開解釋；Plant需求由程式計算並附到explanation與content，而非只依靠LLM算術。衝突狀態先回規則同步建議，不同時生成相互矛盾的種植策略。

## 4. 錯誤與連線

輸入不符回422；上游或模型格式／引用錯誤回503；超過42秒回504。Core保持世界暫停，無自動重試。逾時不保證已送到供應商的請求能取消，仍可能計費。

目前無Bearer驗證，服務只監聽localhost，供本機開發。Core若在另一台電腦，還需提供實際可連線位址及部署存取保護；這是交付配置，不是待決定的植物模型。

## 5. 驗證與剩餘事項

```bash
.venv/bin/python -m unittest discover -s tests -p 'test_*.py' -v
PYTHONPATH=. .venv/bin/python tests/discuss_http.py
PYTHONPATH=. .venv/bin/python tests/discuss_http.py --aligned
```

原始fixture的兩輪測試核對舊規則衝突，完全本地運算；`--aligned` 使用人工同步電力規則的測試快照，會傳送範例世界與檢索文獻至OpenRouter。結果分別保存在忽略上傳的 `.tools/discuss-http-results.json` 與 `.tools/discuss-http-aligned.json`。測試快照不是實際Core已更新的證據。

剩餘僅是Core確認已採用上述每小時數值、提供雙方可連線的地址，並用實際Core程式跑第一輪與追問。Plant的面積、株數、EU換算、保守耗電公式均已定案。

製水比較亦由程式提供：範例植物灌溉174 L/tick低於製水上限250 L/tick，餘量76 L/tick；補回此水量需348 EU與34.8 OU。這些是既有rules的算術，不含其他用水，也不是已安排的製水工作。

## 本次修正驗證

18項離線測試通過。保留舊規則的兩輪HTTP測試皆200，直接回傳規則同步建議，不呼叫LLM。使用已同步電力的人工測試快照，真實OpenRouter第一輪 15.11秒、第二輪 18.00秒，皆200、回覆格式與歷史引用正確；檢查耗電及製水比較無上述錯誤。這是單次本機契約與回覆檢查，不是Core實機串接或未來策略安全性的保證。
