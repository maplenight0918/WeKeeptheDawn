# 真實 Agent 整合交付清單

核對日期：2026-09-12。這是待交付與驗收條件，不代表功能已存在。前後端與 bridge 不改寫隊友的模型、提示詞、決策或記憶。

## 目前可以確認的範圍

- 完整動作 fixture 已在真實後端結算、WebSocket 與瀏覽器跑完 40 ticks，涵蓋製水、六種人物工作與自然成熟後採收。
- 瀏覽器按暫停後，超過一個預設 tick 間隔，完整世界 snapshot 與角色座標均不變；暫停期間重啟 bridge 不會自行恢復，按繼續後可推進到 tick 40。
- Core → specialist 原始 HTTP 路由的聯測通過，但使用 fixture model、Human mock 與 Plant 明確替代的索引啟動；不能當作真實模型或 Plant 檢索驗收。
- 初批測試不呼叫付費模型；後續使用者已授權並完成一次真實三方串接，Core 一次規劃、一輪協商、後端確認一個 tick。詳見驗證紀錄；沒有修改目前互動展示世界或啟動持續付費決策。

## 各 owner 的交付

| 負責者 | 本地證據／缺口 | 完成交付的驗收條件 |
| --- | --- | --- |
| Plant 索引（已完成） | 已由官方 Release `index-v1` 安裝 `data/index/ids.json`、`chunks.jsonl`、`embeddings.npy`。 | ZIP 官方 SHA-256、三份檔案大小及 manifest SHA-256 全數一致；真實 lifespan 啟動成功，health 回報 64,160 chunks。沒有付費重建。 |
| Plant 檢索排序 | `src/retrieval/store.py::search` 以批次點積排序，但逐筆重算回傳 score；本機嚴格降序測試出現約 6e-8 倒序。 | owner 對齊排序與回傳分數的計算來源，或明確定義浮點近似的排序契約；保留過濾與每文件上限。此處未改動隊友檢索程式。 |
| Plant | `src/agent/discussion.py` 仍依約 0.20834 EU/plot/hour 推導植物耗電，並將遊戲傳入的成本視為衝突。 | 建議與可執行計算接受 shared 權威值 5 EU/plot/tick；可另列文獻估計，但不能要求世界改值或將兩種成本相加。以 20 塊存活地測得遊戲灌溉需 100 EU/tick，空地及死亡地不計。 |
| Human | `app/discussion_types.py::CoreWorld` 設定 `extra='ignore'`，沒有 pending、settings、last_summary；內部轉接只使用其已定義欄位。 | 補齊需使用的欄位與轉接；以非零 pending、有效 settings、null／非 null summary 驗證不靜默遺失。可用公共庫存與待入庫分開呈現，下一 tick 核算依引擎入庫順序處理，不能把 pending 預加到觀察庫存。若仍無法核算，明確標示 partial 與未覆蓋範圍。 |
| Core | `core_agent/orchestrator.py::CoreAgent` 有 `plan()`，沒有 reflection 方法。bridge 已將實際結果傳入下一輪 history。 | owner 提供結果回饋／公開 reflection 的正式接口與測試。輸入需能綁定 conversation、輸入 tick/version、實際執行計畫、事件及結算摘要；只在結果確認後發訊息，未確認／縮量／空計畫不可聲稱原計畫成功。不要求內部逐步推理。 |
| 部署者 | 一次真實三方聯測已通過，服務 URL 與各自設定已接通；Plant LLM 因規則衝突未進入分析。 | 持續真實決策及進一步付費測試仍需操作者明確授權；本次一次性授權不延伸成無限運行。金鑰不貼入文件、對話或前端。 |

Plant 缺索引的啟動阻擋已解除；剩餘項目仍阻擋真實語意、檢索排序與數值的完整驗收，不阻擋既有接口、fixture 及公開對話測試。不能因 HTTP 200 或模型回覆了一段文字就勾選整合完成。

## 收件後的聯測順序

1. 先在各 Agent 自己的環境核對索引與健康檢查，不直接呼叫付費分析。
2. 從隔離遊戲的 `GET /world` 取得 snapshot，由既有 bridge 傳入 shared 規則；不要手抄世界數值。
3. 先測一個決策 tick：三方公開訊息版本一致、Core 明確輸出設定與一次性動作、後端驗證、配對實際 WS 結算。HTTP 202 不是執行成功。
4. 再測 pending、settings、摘要差異、規則衝突、暫停／修改資源造成請求失效，以及 specialist timeout。不得自動解除玩家暫停。
5. reflection 接口交付後，才驗收「真實結果 → Core 公開反思」；目前 UI 保留「Bridge 結算回報」名稱。

啟動參數及現有接口見 [bridge README](../agent_runner/README.md)，實測紀錄見 [整合驗證](three_agent_validation.md)。未交付前保留目前 fixture 展示，不偷偷切换成付費或未驗收的模式。

## 遠端開發、本機瀏覽器

在本機建立 SSH 隧道，保持連線，將兩個埠都轉發到遠端服務所在環境：

```bash
ssh -N -L 5175:127.0.0.1:5175 -L 8001:127.0.0.1:8001 USER@HOST
```

本機開 `http://localhost:5175`；不要帶 `?mock=1`，該參數會切到前端離線重播。若 SSH 主機與開發容器不是同一個網路環境，需透過開發工具的 Ports 面板轉發容器的 5175、8001。前端目前會連本機 8001，所以只轉前端埠仍可能顯示離線；不必將後端綁定公共網卡。
