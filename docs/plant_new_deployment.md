# Plant 修正版部署（2026-09-12）

8101 已由舊 `plant_agent` 切換為使用者提供的 `plant_agent_new`；bridge URL 不變。
新版移除固定規則衝突回覆，依傳入規則計算分配，不改遊戲 5 EU/plot/tick。

部署使用連結，未複製或覆寫原始秘密／索引：

- `plant_agent_new/.env` → `../plant_agent/.env`（git 忽略）
- `plant_agent_new/data/index` → `../../plant_agent/data/index`（git 忽略）

從 repo 根目錄啟動：

```bash
cd plant_agent_new
../.venv-bridge/bin/python -m uvicorn src.api.main:app --host 127.0.0.1 --port 8101
```

切換前需停止原 8101 程序，保持世界暫停。新版 README 尾段保留舊口徑，
本次採新版 `docs/DISCUSS_HANDOFF.md` §2 與交付程式的相容處理，不修改原始文件。
三份索引通過新版 verify_index.py；9 項 discussion 離線測試通過。
未新增付費聯測；健康檢查不等於真實模型分析成功。Human 的 502 與 Core 規劃錯誤未由本次解決。

前端 Human 主對話、收合預覽與地圖氣泡優先採用公開 explanation.decision_reason；
沒有有效文字才沿用原摘要。原摘要保留於訊息內的展開區，不讀取內部 content。
`node checks/human_public_text.mjs` 以展示後端版本 30 的兩筆既有 Human 訊息回放，
只修改測試瀏覽器本地 store，不操作後端世界或模型。
