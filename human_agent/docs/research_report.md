# 本次文獻重建

初始目錄沒有任何 corpus／向量可重用。依 spec 入口檢查 NASA NTRS、HIDH 與 NASA 食物營養頁面，以五份公開原始 PDF 作為本次候選並全部取得；沒有付費牆、沒有用搜尋摘要取代原文、沒有擴增到25個候選上限。

| 納入文件 | 原文頁數 | 索引範圍 |
| --- | ---: | --- |
| BVAD Rev2，2022 | 235 | 實體頁68–77：人類代謝／名義介面與需求背景 |
| Astronaut Mass Balance for Long Duration Missions，2019 | 8 | 全文 |
| Nutrition Requirements, Standards, and Operating Bands for Exploration Missions，2005 rev1 | 145 | 可讀全文 |
| Human Adaptation to Spaceflight: The Role of Food and Nutrition，2021 第二版 | 135 | 實體頁1–15、35–50，保留原文及定位 |
| Human Integration Design Handbook Rev1，2014 | 1301 | 包含 potable water、metabolic rate、energy requirements、food and nutrition 的頁面與相鄰頁 |

下載與處理可由 `scripts/acquire_sources.py`、`scripts/prepare_corpus.py --local` 重現。manifest 保存 title、authors、year、URL、local_path、SHA-256、topics、access_status、exclusion_reason；標題與作者以下載 PDF 封面核對。`full_text_acquired` 指檔案取得，並不等於每一個片段已確認支持任意主張。

本次完成 5 個 document、393 個 chunks。原始 PDF 完整保留在 `data/raw/`；`data/processed/` 保存選頁的原文抽取結果。chunk 以段落與頁面定位處理，目標450 words、約75 overlap，超過600 words分段；文件／頁面尾段可短於300。表格布局以 PDF layout extraction 保留行列；特殊旋轉文字有 extraction 警告，未實作 OCR，不隱藏缺口。科學段落不以 LLM 摘要替換。

停止文獻擴增原因：已達5–10份最低目標、取得三項核心基準與其適用條件，按 spec 限額繼續工程。沒有要求做完整醫療文獻審查；需要進一步科學確認的部分保留 partial。NASA表格內的質量、MJ與遊戲 L／OU／遊戲 kcal 明確分層。

BVAD 的三項 baseline 不再僅是 legacy_reported：本次已取得並讀取 Table3-31 與相鄰說明的可讀文本，詳見 `parameter_review.md`。完整視覺表格校讀與全部来源支持性仍未完成，不能提升整份 corpus 為 scientific_verified。

歷史790 chunks／Voyage索引不在目錄，未沿用其數量或測試結果。新 corpus 與索引版本由實際內容產生，不以歷史報告宣稱完成。
