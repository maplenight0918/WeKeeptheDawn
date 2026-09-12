# Provider 協定

OpenAI (`LLM_PROVIDER=openai_compatible`，官方 `api.openai.com` endpoint) 使用 `/v1/responses`，function tools 平坦欄位、function_call／function_call_output 往返、store=false。實際 GPT-6 工具流程已驗證成功。其他 openai-compatible endpoint 與 OpenRouter 使用 `/chat/completions`；不依 key 字串猜 provider。

參考：[OpenAI Function calling](https://developers.openai.com/api/docs/guides/function-calling)、[GPT-6 Astra model](https://developers.openai.com/api/docs/models/gpt-6-astra)。本次 Chat Completions 接收簡單訊息成功，但帶 reasoning 的 function tools 回400，故修正為 Responses 並重新做完整HTTP驗證。

OpenRouter embedding 使用 `/embeddings`，model=`voyageai/voyage-4`、dimensions=1024、encoding_format=float，預設不送 input_type。參考：[OpenRouter Embeddings API](https://openrouter.ai/docs/api_reference/embeddings)。回傳的 index 會排序與驗證，拒絕重複、遺漏、維度錯誤、非有限或零向量。

官方 Voyage adapter 使用 input_type=query/document、output_dimension 與 truncation=false；須設定 `EMBEDDING_PROVIDER=voyage`、官方 endpoint／model，policy=`query_document` 並重建索引。此 adapter 只有程式路徑，未以官方帳號遠端驗證。

HTTP client 不跟隨重新導向，避免將 Authorization 轉送其他 endpoint。錯誤只傳遞固定分類／HTTP status；不輸出 headers、key、遠端正文。LLM、embedding key 分別讀取，沒有互相借用。
