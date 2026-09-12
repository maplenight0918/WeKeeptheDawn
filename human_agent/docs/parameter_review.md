# 參數與來源審查

最新runtime處理：核心BVAD實體頁72–73中已核對的限定結論由`app/evidence_review.py`綁定原文chunk SHA-256，只有完全相符才放入`evidence.reviewed_claims`。API的建議reason改由規則與實際audit組裝；LLM自由生成的科學說法不直接發布。完整文獻逐頁／視覺審查仍維持本頁下方所列限制。

世界值是唯一計算真值。以下是本次取得 NASA 原文後的核心定位核對；不把文獻模型當遊戲死亡規則，也不宣稱所有來源已逐頁審核。

| 參數 | 世界值 | 本次原文值 | 適用條件／定位 | 核對狀態與限制 |
| --- | --- | --- | --- | --- |
| 每人每日能量基準 | 3054 遊戲 kcal | 12.778 MJ/CM-d，換算約 3054.015 真實 kcal | BVAD Rev2，PDF 實體頁 72–73／印刷頁 58–59，Table 3-31 與 Food Consumed 說明；82 kg 參考 crew、IVA、每日有運動 | 原文數字已核對，3054 為世界採用的取整基準，不能把遊戲 kcal 當完整營養 |
| 每人每日水 | 3.217 L | Potable Water Content 3.217 kg/CM-d | 同表與 PDF 73／印刷59：0.5 kg 食物準備＋2.00 kg 飲用＋0.717 kg 運動／质量平衡調整；另列食物自帶水 0.760 kg | 已核對組成；不是全部生活用水，也不是純飲水量。kg→遊戲 L 是世界既定映射 |
| 每人每日氧 | 0.895×1000 OU | Oxygen Consumed 0.895 kg/CM-d | PDF72／印刷58 Table3-31；参考 82 kg，RQ 0.86，MetMan 更新模型與 sweat-test 相關；PDF73 footnote 以0.90約稱 | 已核對表格文本；OU 不是真實艙內氧分壓或真實生命判定 |
| 活動範圍 | 基礎耗用＋100 遊戲 kcal/發電工作 | BVAD nominal 已包含每日30分鐘有氧、60分鐘阻力運動 | BVAD PDF72、73；2019 Astronaut Mass Balance PDF2 亦有此條件 | 已核對活動範圍。發電額外成本是遊戲係數；若將之硬套生理模型可能重複計活動，不應再改遊戲常數 |
| 食物營養 | 僅追蹤遊戲能量 | 2005 Nutrition Requirements 文件分開列營養素需求、營養狀態與不確定性 | 原文 PDF1–2、各營養素章節；2021 Food and Nutrition 第二版為補充背景 | 原文已取得且有限抽查；能量足夠不等於微量營養素／蛋白質／實際健康充足 |
| 製水 | 2 EU＋0.2 OU→1 L，上限250 | 無 NASA 物理對應 | spec3.4，water_production.conversion | world_defined；非物理守恆系統，不引用 NASA 當轉換證明 |
| 個人容量與歸零死亡 | E容量3000、水容量2；任一<=0死亡 | 不以真實飢餓／脫水天數替代 | spec3.2，crew.personal.death | world_defined；無真實醫療主張 |
| 灌溉與作物死亡 | 8.7 L＋5 EU原子供應；連續3次失敗死亡 | 無本次科學校準 | spec3.5，plant.irrigation.atomic | world_defined；作物分析與操作仍由Plant／Core負責 |

來源： [BVAD Rev2 原文](https://ntrs.nasa.gov/api/citations/20210024855/downloads/BVAD_2.15.22-final.pdf)、[2019 Mass Balance](https://ntrs.nasa.gov/api/citations/20190027563/downloads/20190027563.pdf)、[Nutrition Requirements](https://ntrs.nasa.gov/api/citations/20200001703/downloads/20200001703.pdf)、[2021 Food and Nutrition](https://www.nasa.gov/sites/default/files/atoms/files/human_adaptation_2021_final.pdf)。本機路徑與完整 hash 見 `data/source_manifest.jsonl`。

未完成：完整 PDF 的視覺表格／圖形逐頁檢查、所有歷史來源對當代標準的更新比對、所有檢索片段的語意支持認證。部分 PDF 旋轉文字 extraction 有警告。`research_status=partial` 保留；不是世界公式未知。
