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

## 2. 世界規則與模型估算的差異

Core目前每塊5 EU／tick，20塊為100 EU／tick；Plant物理模型在1小時tick下估算約4.166781 EU。保留模型公式與EU換算，但模型不覆蓋遊戲規則。

`/discuss` 的資源分配一律採傳入 `rules.irrigation.power_per_plot`，不要求Core先改規則；差異列入公開說明，兩者不可相加。Core拒絕改規則後，Plant應回應該review並修改或撤回舊提案，繼續討論灌溉與水電安排。傳入tick時間不同也不再觸發固定衝突回覆。

製水合計同樣採世界扣電：若全田灌溉100 EU、補回174 L水需348 EU，條件式總需求為448 EU；不含crew與其他用途，也不代表已安排製水。

## 3. API格式與角色

`POST /discuss`，本機URL：`http://127.0.0.1:8000/discuss`。

- 接收Core v1.3世界、規則、問題、歷史與explanation格式。
- 回傳直接訊息JSON，message_id重新產生，discussion_id／round／world_version原樣帶回；sender=plant、recipient=core。
- explanation七欄與各proposal／review嚴格驗證；content五欄由同份解釋衍生，無data wrapper。
- 每輪只提建議，不執行世界、不宣稱已跑未來模擬。Core負責決策與分配，世界負責驗證扣除。
- 第一輪fixture：`tests/fixtures/discuss_round1.json`，故意保留Core原始5 EU規則以測試衝突辨識。後續輪引用真實歷史proposal，拒絕虛構ID。
- 世界、crew、plot允許附加狀態；資源固定四欄，驗證版本、ID及數值。Plant不改外層通訊欄位。

每輪以三個文獻查詢加一次LLM產生精簡公開解釋；世界扣電與模型參考由程式分別計算。差異不再提前結束討論；LLM接收Core本輪reviews與歷史提案。

## 4. 錯誤與連線

輸入不符回422；上游或模型格式／引用錯誤回503；超過42秒回504。Core保持世界暫停，無自動重試。逾時不保證已送到供應商的請求能取消，仍可能計費。

目前無Bearer驗證，服務只監聽localhost，供本機開發。Core若在另一台電腦，還需提供實際可連線位址及部署存取保護；這是交付配置，不是待決定的植物模型。

## 5. 驗證與剩餘事項

```bash
.venv/bin/python -m unittest discover -s tests -p 'test_*.py' -v
PYTHONPATH=. .venv/bin/python tests/discuss_http.py
PYTHONPATH=. .venv/bin/python tests/discuss_http.py --aligned
```

原始fixture保留遊戲5 EU規則，兩輪HTTP測試現在也會呼叫OpenRouter；`--aligned` 使用人工同步電力規則的測試快照，會傳送範例世界與檢索文獻至OpenRouter。結果分別保存在忽略上傳的 `.tools/discuss-http-results.json` 與 `.tools/discuss-http-aligned.json`。測試快照不是實際Core已更新的證據。

整合端需拉取最新版本並重啟Plant，再用實際Core程式跑第一輪與拒絕改規則的追問。Core可保留現行扣電規則；Plant的面積、株數、EU換算與保守模型公式仍作參考。

製水比較亦由程式提供：範例植物灌溉174 L/tick低於製水上限250 L/tick，餘量76 L/tick；補回此水量需348 EU與34.8 OU。這些是既有rules的算術，不含其他用水，也不是已安排的製水工作。

## 本次修正驗證

以下為修正前的歷史測試：18項離線測試通過。當時舊規則會直接回固定同步建議，該行為現已移除。使用已同步電力的人工測試快照，真實OpenRouter第一輪 15.11秒、第二輪 18.00秒，皆200、回覆格式與歷史引用正確；檢查耗電及製水比較無上述錯誤。這是單次本機契約與回覆檢查，不是Core實機串接或未來策略安全性的保證。

2026-09-12 修正驗證：19項離線測試通過，新增Core引用舊提案並拒絕改規則的回歸案例，確認會進入討論模型、保留review及原快照、按100 EU及448 EU合計計算。LLM採mock驗證，尚未重跑本版真實OpenRouter或Core端整合；歷史HTTP時間不代表本版效能。
