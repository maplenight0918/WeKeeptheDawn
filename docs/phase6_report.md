# Phase 6 — 前端

完成：`frontend/src/game/`、`components/`、`overlay/`、`store/`、`net/`、共用設定載入、Vite/React 建置入口、五作物 SVG、本地中文字型；`checks/smoke_frontend.mjs`、`checks/smoke_frontend_interactions.mjs` 與 `docs/frontend.md`。

分工：場景 Agent 完成世界物件、角色動畫與地圖互動；UI Agent 完成聊天、氣泡及操作元件；Store／網路 Agent 完成同步、預錄 mock 與互動測試；主線完成整合建置、基本瀏覽器驗收、截圖視覺檢查及文件。

驗證（2026-09-12）：

| 指令 | 結果 |
| --- | --- |
| `cd frontend && npm run build` | TypeScript + Vite 成功，2942 modules |
| `cd frontend && npm run dev:mock -- --port 5174` | 獨立 mock 可啟動 |
| `FRONTEND_ROOT=http://127.0.0.1:5174 PLAYWRIGHT_BROWSERS_PATH=/tmp/greenhouse-browsers node checks/smoke_frontend.mjs` | 12 checks 通過，無 browser errors |
| `FRONTEND_ROOT=http://127.0.0.1:5174 PLAYWRIGHT_BROWSERS_PATH=/tmp/greenhouse-browsers node checks/smoke_frontend_interactions.mjs` | 19 checks 通過，無 browser errors |
| `.venv/bin/python -m pytest backend/tests -q` | 174 passed |

截圖：`artifacts/mock-world.png`、`water-tooltip.png`、`mock-chat-interactions.png`、`mock-partial-irrigation.png`、`mock-recovered.png`、`mock-failure.png`。機器結果：`artifacts/frontend_smoke.json`、`artifacts/frontend_interactions.json`。

與 spec/guide 的偏差：5173 已由其他專案使用，本次使用 5174，不停止外部服務；視覺依最新要求採 RimWorld-inspired 風格。作物四階段以同一 SVG 的分階段大小呈現。低存量提示採可讀文字，避免 emoji 缺字。世界數值無修改。依使用者分工，不實作遊戲 Agent 決策，mock 明確標示為預錄展示。

待定項目處置：飲水位置維持 null 與 `TODO(guide-pending)`，不安排飲水路線；不新增 clear 玩家入口、設備故障或自動 refill 政策。

下一階段風險：Phase 7 尚須真後端整合展示、完整前端驗收表、部署文件與最終提交。OpenAI YAML／transport 接口已預留，但真實 Agent 決策由隊友提供；本階段未呼叫付費模型 API。
