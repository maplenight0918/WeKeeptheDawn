# 文件索引

[返回專案首頁](../README.md)

## 專家Agent交接

直接轉交 [Plant／Human API通訊交接文件](integration/specialist-agent-api-handoff.md)。單一檔案包含完整請求、回覆與schema，不需其他附件。

## 現行規格

| 文件 | 用途 |
|---|---|
| [世界設定說明](specs/world-settings-guide.md) | 前後端、Plant／Human Agent 共用的資源、公式與crew互動 |
| [世界規則 Spec](specs/world-rules-spec.md) | 世界結算、死亡、工作占用及監控規則 |
| [Core Agent 串接協定](integration/core-agent-integration.md) | 專家訊息、策略輸出與後端執行責任 |
| [決策 JSON Schema](../schemas/core-agent-decision.schema.json) | GPT 結構化輸出格式 |

- [公開策略說明 Schema](../schemas/agent-explanation.schema.json)
- [詳細對話範例](../examples/dialogue-presentation.json)

- [世界與資源 Schema](../schemas/world-snapshot.schema.json)

## 參考與歷史

- [原始專案概念 PDF](<references/OpenAI Hackathon.pdf>)：早期概念，若有衝突以現行規格為準。
- [歷史討論摘要](archive/core-agent-discussion-summary.md)：保留討論脈絡，不作為實作依據。

## 程式與驗證

- [離線通訊示範](../examples/offline_demo.py)
- [世界狀態範例](../examples/snapshot.json)
- [Core 自動化測試](../tests/test_core_agent.py)
- [含種植工作占用的收支檢查](../checks/check_crew_tasks.py)
- [較早的個人補給檢查](../checks/check_crew_schedule.py)
- [歷史公共收支檢查](../checks/check_resource_balance.py)

文件內的shell命令都從專案根目錄執行；相對文件連結則相對於文件所在目錄。
