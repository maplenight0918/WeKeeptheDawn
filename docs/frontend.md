# 前端展示與 Phase 6 驗收

前端是 React／PixiJS 俯視基地；遊戲內 Core、Plant、Human 的決策由隊友提供。聊天視窗呈現收件者、回覆關係、決策回合、計畫與實際結算結果，不實作 Agent 決策。

## 啟動

```bash
cd frontend
npm ci
npm run dev:mock
```

開啟 `http://localhost:5173/?mock=1`。若該 port 已被其他專案使用：

```bash
npm run dev:mock -- --port 5174
```

本次驗收使用 `http://localhost:5174/?mock=1`，未停止原有 5173 服務。

## 操作

- 拖曳基地平移，滾輪縮放；滑過物件查看 tooltip，點擊查看詳細卡，Esc 關閉。
- 下方工具列可暫停、調速、修改資源與重新開始。
- 右下「Agent 對話」展開聊天回合；地圖氣泡按序展示協商摘要。
- 獨立 mock 支援電力改為 300 的干預與恢復，以及氧氣改為 0 的失敗展示。其他資源編輯須使用真後端模式，不在前端計算資源。
- 飲水點位置仍是 `TODO(guide-pending)`，不指定房間、不播放虛構飲水路線；clear 玩家入口與設備故障也不自行新增。

暫停會凍結權威 tick、作物進度、crew 路徑、設備流光、資源飄字及 Agent 氣泡；恢復才繼續。×1／×5／×20 同時套用後端 tick 排程與前端世界動畫。mock 只播放後端預錄的 60 tick snapshot，不在瀏覽器計算資源；×20 約可在 10 秒內走完整段展示。

移除 `?mock=1` 後使用後端連線；預設 API 為 `http://127.0.0.1:8001`，可用 `VITE_API_URL` 調整。OpenAI key 僅在後端，設定見 [模型接入](model_connection.md)。

中文使用隨應用程式打包的 `@fontsource/noto-sans-tc`（SIL Open Font License）；沒有运行時字型 CDN 依賴。Pixi 場景等待字型載入後才建立文字。

## 可重跑驗證

```bash
cd frontend
npm run build
npx playwright-core install chromium
cd ..
FRONTEND_ROOT=http://127.0.0.1:5174 node checks/smoke_frontend.mjs
FRONTEND_ROOT=http://127.0.0.1:5174 node checks/smoke_frontend_interactions.mjs
FRONTEND_ROOT=http://127.0.0.1:5174 node checks/smoke_mock_transport.mjs
```

本次測試環境將瀏覽器裝在 `/tmp/greenhouse-browsers`，因此額外設定 `PLAYWRIGHT_BROWSERS_PATH=/tmp/greenhouse-browsers`。截圖與機器可讀結果輸出到 `artifacts/`，不提交產物到 Git。

Phase 6 是獨立前端／預錄 mock 驗收，不代表 Phase 7 真後端展示或真實模型決策已驗收。

若要驗真實前後端控制，先在另一 terminal 以 `PLAN_SOURCE=mock WORLD_DB=:memory: .venv/bin/python -m uvicorn backend.main:app --host 127.0.0.1 --port 8010` 啟動服務，再將 `VITE_API_URL=http://127.0.0.1:8010 npm run dev -- --port 5175` 與 `FRONTEND_ROOT=http://127.0.0.1:5175 node checks/smoke_live_frontend_controls.mjs` 配合使用。
