# GitHub 交付檢查（2026-09-12）

目標倉庫：`https://github.com/lic924/human-agent-api.git`，初始分支 `main`。

推送前以 Git index 中的實際 blob 匯出乾淨副本，未攜帶開發者 `.env`、embedding cache、虛擬環境或個人測試輸出；副本從 `.env.example` 建立無金鑰 mock 設定。

- 全套 pytest：130 passed，13.07 秒。
- Core `/discuss`：11 個 mock HTTP 案例通過，包含原始請求、三輪與邊界情境。
- Human `/human-agent/analyze`：6 個 mock HTTP 案例通過。
- 原文 chunks：393；BM25 與 dense 索引均載入，dense_issue=null。
- 暫存內容掃描：未包含既有真實金鑰；`.env`、`.tmp`、embedding_cache、個人人工回覆均排除。
- PDF 和 numpy 索引以 binary 儲存；Python／Markdown／JSON 使用 LF，避免換行轉換破壞跨平台資料。

此次乾淨副本驗證使用既有 Python 依賴環境，沒有宣稱測過所有作業系統或全新安裝依賴。Live 的實際驗證見 `validation_report.md`；隊友需自行填入有權使用的 provider／模型設定與金鑰。GitHub 不包含開發者金鑰，預設 mock 可直接測接口與規則。

首次取得與更新方式見根目錄 README；人工案例見 `START_TESTING.md`。
