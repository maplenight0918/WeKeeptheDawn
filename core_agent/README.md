# Core Agent

Python 3.11+，僅使用標準函式庫。範圍為 GPT 決策、Plant／Human 雙向通訊、最多三輪討論、策略格式與靜態驗證。不實作世界更新、前端、專家邏輯或預測 Simulator。

## 快速驗證

```sh
python3 -m unittest discover -s tests -v
python3 -m examples.offline_demo
```

離線示範使用明確標示的測試替身，不會呼叫 GPT、專家服務或改變世界。

## 實際 GPT 串接

伺服器環境設定見 `.env.example`，不會自動載入 `.env`。必填 `OPENAI_API_KEY`、`OPENAI_MODEL`、`PLANT_AGENT_URL`、`HUMAN_AGENT_URL`。模型由部署者選擇，須支援 Responses API Structured Outputs，不在程式寫死特定 GPT 型號。

```sh
python3 -m core_agent examples/snapshot.json > plan-result.json
```

API key 不傳給專家、模型輸入或前端。使用 OpenAI Responses API 的 JSON Schema strict output；完成後仍在本地驗證版本、範圍、識別碼與工作衝突。官方依據：[Structured Outputs](https://developers.openai.com/api/docs/guides/structured-outputs)。

目前只以替身測試 API payload／回應與錯誤處理，未執行真實付費 API 呼叫，也尚未驗證隊友的 HTTP 服務。

## 持續監控與主動決策

`CoreController` 是長駐服務，啟動一次後由 Core 自己讀取世界，不必等外部發出 emergency 才呼叫。

```python
import asyncio
from core_agent import CoreAgent, CoreController, GPTDecisionModel, HTTPSpecialist
from core_agent.rules import get_rules

core = CoreAgent(GPTDecisionModel(), HTTPSpecialist(plant_url), HTTPSpecialist(human_url))
controller = CoreController(core, world_adapter, get_rules(), on_event=publish_event)
stop = asyncio.Event()
await controller.run(stop)
```

`world_adapter` 由世界owner實作 `WorldPort` 三個async方法：observe、pause_for_core、apply_and_resume，詳見串接協定。此repo不提供世界HTTP server，也不假設尚未協調的隊友API路徑。

- 預設每0.5秒觀察一次；每個新的模擬tick有機會啟動GPT評估（頻率可設定），不重複評估同一tick。
- GPT評估期間世界仍可運行，Core繼續輪詢風險；每次只容許一個GPT評估在途，較慢時合併到最新狀態，不保證每tick都有一次API回應。
- 即時風險可中斷等待，Core主動要求暫停。GPT也可在未觸警戒時基於趨勢要求replan。
- 完整規劃時取新凍結快照，Core主動呼叫Plant／Human API、最多三輪協調、產生plan。
- 後端原子核對世界版本與Core暫停權，通過才套用並恢復；玩家暫停與死亡不能被覆蓋。
- 評估失敗轉入凍結重規劃；規劃失敗保持暫停並拋錯，由服務host明確重試。沒有硬編碼救援plan。

原本 `core.plan(...)` 仍可單獨呼叫以測試一次討論；CLI是單次模式，不能替代長駐controller。`on_event`同步callback可將觀察評估、討論與提交結果轉送前端。

網路timeout有限；取消標準函式庫背景HTTP執行緒可能需等網路timeout，其遲到结果不會被套用。尚未執行真實API或世界服務整合驗證。

## 檔案

- `core_agent/controller.py`：主動監控、GPT評估、暫停與提交控制。
- `core_agent/orchestrator.py`：多輪通訊，routing／版本檢查與事件。
- `core_agent/adapters.py`：GPT Responses API、HTTP專家連線。
- `core_agent/contracts.py`：JSON Schema與策略靜態驗證。
- `core_agent/rules.py`：提供三個agents的共用遊戲規則。
- [串接協定](docs/integration/core-agent-integration.md)：團隊共用的訊息、策略與執行語意。
- `examples/snapshot.json`：初始世界資料示例。

規則變動需同步更新 `rules.py`、世界owner的設定和 rules_version；這份複本目前不是世界引擎的執行設定。尚未驗證策略的未來資源安全，因為本專案已移除預測 Simulator。

## 專案目錄與文件入口

所有執行指令均從專案根目錄執行。

```text
core_agent/          Core Agent 程式
examples/            離線示範與世界輸入範例
tests/               Core Agent 自動化測試
schemas/             可分享的 JSON Schema
checks/              世界收支／工作占用檢查（非預測工具）
docs/
  specs/             現行世界規格與設定說明
  integration/       團隊通訊與後端串接協定
  references/        原始專案 PDF
  archive/           歷史討論，不作實作依據
```

- [文件索引](docs/README.md)
- [世界設定說明](docs/specs/world-settings-guide.md)：跨團隊同步數值與crew互動。
- [世界規則 Spec](docs/specs/world-rules-spec.md)：詳細世界行為。
- [Core 串接協定](docs/integration/core-agent-integration.md)：Plant／Human與後端串接。
- [GPT 決策 JSON Schema](schemas/core-agent-decision.schema.json)：對應 `core_agent/contracts.py`。
