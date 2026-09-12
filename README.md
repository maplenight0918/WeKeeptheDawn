# Space Greenhouse

火星溫室的權威世界後端、2D 前端與三 Agent 接線。世界規則來自根目錄 guide 和 `shared/`；Agent 決策沿用隊友提供的專案。

- [三 Agent bridge：安裝、啟動、fixture、接口與限制](agent_runner/README.md)
- [三 Agent 整合手冊](docs/three_agent_integration_manual.md)
- [Tick 結算順序與已核准偏差](docs/tick_order.md)

本次整合使用 Python 3.11+ 的 `.venv-bridge`，保留既有 `.venv`。前端沿用既有 lockfile，以 `npm ci` 安裝、`npm run dev -- --port 5175` 啟動。後端與 bridge 的完整啟動命令見上方說明。

```bash
.venv-bridge/bin/python -m pytest -q
cd frontend
npm run typecheck
npm run build
```

fixture 模式明確標示 MOCK，不代表即時 LLM 決策。Plant 索引及數值對齊、Core reflection 接口仍待 owner 提供；目前不宣稱三個真實模型已整合驗收。
