# Repository 交接

GitHub 僅提交程式、測試、必要規格、係數表及驗收摘要。大型 corpus 索引另行交付；不可只 clone repo 就假設資料已齊。

首次上傳前的檢查：以明確檔案清單提交，不使用全目錄批次加入。對清單逐檔比對本機 `.env` 的實際秘密值，以及常見 API token／private key 樣式；檢查檔案大小與 symbolic link。此檢查不等於完整的安全稽核。

不提交：`.env`、`.venv/`、`.tools/`、`.cache/`、`data/index/`、其他原始 catalog、PDF、HTML、完整檢索回應 `docs/acceptance_results.json`。真實網路驗收結果的摘要在 `docs/IMPLEMENTATION_REPORT.md`。

本服務沒有使用者驗證或用量限制，預設僅監聽 localhost。若日後部署供外部使用，需先配置 API 存取控制與用量限制，避免他人透過 `/analyze` 消耗你的 OpenRouter 額度。私人 repository 不代表部署出去的服務會自動受保護。

執行方式及索引放置路徑見根目錄 README。
