# 新檢索驗收

本次使用 8 題新 scientific queries（三項需求、活動、飲水定義、兩題中文改寫、一題無相關證據）與2題 world-rule routing。原文 top-5 結果檢查關鍵詞存在，另驗證遊戲製水／個人歸零不能錯引 NASA。這是可重現檢索 smoke test，不是全面語意支持評分。

| 模式 | 通過 | 失敗 | 結果檔 |
| --- | ---: | ---: | --- |
| BM25 | 10/10 | 0 | retrieval_eval_bm25.json |
| Voyage dense | 9/10 | 1 | retrieval_eval_dense.json |

Dense 未通過 `water`：query `nominal potable water content 3.217` 的 top-5 沒有包含該精確數值。原文確實存在（BVAD PDF72）；BM25 該題成功。没有藉由改世界常數或假引用來補足命中。`eval_retrieval --mode dense` 如實以 exit2 表示尚有失敗。

其餘題目包含實際 remote query embedding；世界規則分流不呼叫 embedding。`no_evidence` query 在 corpus 沒有詞彙支持時返回空證據，避免把正 cosine 當成事實可信度。中文 BM25 使用透明小型詞彙映射，原文沒有翻譯或改写；沒有以模型摘要當來源。

corpus=`corpus-4c40231326d1bc2b`；dense index=`index-26765ae220846386`；provider=openrouter；model=voyageai/voyage-4；dimensions=1024；policy=unspecified；L2 float32、dot product。索引建立66個 batch；重跑 `--offline` 實際 0 個 embedding batch，重用已驗證向量。

引用 resolver 檢查 document/chunk/rule ID 是否存在；每個科学 evidence 仍標 `full_text_acquired_support_not_automatically_verified`。來源存在與來源是否支持 LLM 的整句話是兩個檢查，後者未被假稱已完成。世界critical直接引用規則，不依賴科學命中。
