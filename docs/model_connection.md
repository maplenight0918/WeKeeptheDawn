# YAML 與 OpenAI 呼叫接口

`config/runtime.example.yaml` 是可提交的設定範本，只有模型 ID、環境變數名稱與連線設定。實際金鑰放在專案根目錄 `.env`（Git 忽略）：

```dotenv
GREENHOUSE_CONFIG=config/runtime.example.yaml
OPENAI_API_KEY=填入你自己的金鑰
OPENAI_MODEL=填入帳號可使用的模型ID
```

YAML 的 `plan_source` 選 `mock` 播放展示資料，選 `external` 等待隊友提交計畫。設定檔不包含遊戲公式，世界參數仍只有兩份 shared JSON。

OpenAI 的官方文件要求在伺服器端載入金鑰，並以 Bearer 憑證呼叫；本接口依此實作，不將金鑰送到瀏覽器。[API 認證文件](https://developers.openai.com/api/reference/overview)

隊友可以直接使用通用 client：

```python
from backend.integration.settings import load_runtime_settings
from backend.integration.openai_client import OpenAIClient
from backend.domain.models import TickPlan, tick_plan_schema

settings = load_runtime_settings()
client = OpenAIClient(settings.openai)
# teammate_instructions 與 teammate_context 由隊友的 Agent 提供。
payload = await client.complete_json(
    instructions=teammate_instructions,
    input=teammate_context,
    schema=tick_plan_schema(),
)
plan = TickPlan.model_validate(payload)
# 再透過 /ingest/plan 提交；後端仍檢查世界狀態與工作占用。
```

傳輸採 Responses API；以呼叫者提供的 JSON schema 請求輸出，收到後再本地驗證。TickPlan 含動態 dictionary，因此此接口不宣稱符合 strict Structured Outputs 的全部限制。[Responses 入門](https://developers.openai.com/api/docs/quickstart)、[結構化輸出限制](https://developers.openai.com/api/docs/guides/structured-outputs)

此專案沒有實作隊友的決策流程。真實模型展示仍須接上隊友送出的計畫與聊天訊息；填入金鑰本身不會啟動自主決策。測試使用 HTTP fixture，沒有發送付費模型請求。模型 ID 由團隊依帳號權限決定，本範本不猜測可用模型。
