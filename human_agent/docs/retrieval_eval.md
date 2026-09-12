# 檢索修正後的最新驗收

最新：BM25 **10/10**，目前設定的dense＋BM25混合檢索 **10/10**。原本3.217水量題的問題已修正；沒有改題目、替換原文或重新嵌入corpus。完整歷史版本另存 `retrieval_eval_initial.md`。

當retrieval_mode=dense、retrieval_fallback=bm25且兩種索引可用，現在使用RRF（k=60）合併排名。明確數值要求完整數字token與至少一個非數字查詢詞同時在原文出現；數字命中先依覆蓋量及BM25分數排序，再補融合排名。`3.217`不會子字串匹配`13.217`。回傳actual_mode=mixed、ranking_method=rrf_with_numeric_anchors、fallback_reason=null，這是正常流程，不是假稱純dense修成10/10。

最新 `retrieval_eval_dense.json`／`retrieval_eval_bm25.json` 保存相同十題的實際模式、原文ID與定位。新增回歸測試強制將BVAD表格排除在cosine前五名外，仍能補回3.217、0.895與12.778，避免依賴遠端模型偶然排名。

文獻支持另外處理：兩段核心BVAD原文有精確hash綁定的4項限定結論，放在evidence.reviewed_claims；原文變動即失效。公開建議reason由規則與實際候選核算組裝，不直接發布LLM自由生成的科學敘述。其餘corpus仍不宣稱已全面語意審查。所有原始向量與corpus版本保持不變。

以下為首次重建的歷史驗收，9/10不是目前混合流程的結果。

## 首次重建歷史

本次使用 8 題新 scientific queries（三項需求、活動、飲水定義、兩題中文改寫、一題無相關證據）與2題 world-rule routing。原文 top-5 結果檢查關鍵詞存在，另驗證遊戲製水／個人歸零不能錯引 NASA。這是可重現檢索 smoke test，不是全面語意支持評分。

| 模式 | 通過 | 失敗 | 結果檔 |
| --- | ---: | ---: | --- |
| BM25 | 10/10 | 0 | retrieval_eval_bm25.json |
| Voyage dense | 9/10 | 1 | retrieval_eval_dense.json |

Dense 未通過 `water`：query `nominal potable water content 3.217` 的 top-5 沒有包含該精確數值。原文確實存在（BVAD PDF72）；BM25 該題成功。没有藉由改世界常數或假引用來補足命中。`eval_retrieval --mode dense` 如實以 exit2 表示尚有失敗。

其餘題目包含實際 remote query embedding；世界規則分流不呼叫 embedding。`no_evidence` query 在 corpus 沒有詞彙支持時返回空證據，避免把正 cosine 當成事實可信度。中文 BM25 使用透明小型詞彙映射，原文沒有翻譯或改写；沒有以模型摘要當來源。

corpus=`corpus-4c40231326d1bc2b`；dense index=`index-26765ae220846386`；provider=openrouter；model=voyageai/voyage-4；dimensions=1024；policy=unspecified；L2 float32、dot product。索引建立66個 batch；重跑 `--offline` 實際 0 個 embedding batch，重用已驗證向量。

引用 resolver 檢查 document/chunk/rule ID 是否存在；每個科学 evidence 仍標 `full_text_acquired_support_not_automatically_verified`。來源存在與來源是否支持 LLM 的整句話是兩個檢查，後者未被假稱已完成。世界critical直接引用規則，不依賴科學命中。
