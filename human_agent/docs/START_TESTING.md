# Human Agent：啟動與人工測試

此版本依雙方已接受的 `core_handoff_alignment.md` 運作。交付範圍是完整 Human 分析服務：個人／公共資源、單 tick 核算、RAG、LLM 工具流程、Core 三輪討論、API 與測試。Core 負責決策和世界操作；Agent 討論期間世界暫停。

## 1. 啟動現有專案

在專案根目錄（含 `app/`、`requirements.txt` 的目錄）開終端。第一次從 GitHub clone 請先依 README 建立 Python 環境並將 `.env.example` 複製為 `.env`；預設 mock、不需金鑰。若舊的 8000 服務仍開著，先在該終端按 Ctrl+C 停止，再執行：

```powershell
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

模型、金鑰及模式讀取自己的 `.env`；不用重新下載文獻或建立索引。若是在新 Python 環境，先 `python -m pip install -r requirements.txt`。使用虛擬環境時，以下 python 命令請以該環境的 Python 執行。

開 `http://127.0.0.1:8000/health`，確認 configured_mode 符合你選擇的模式、索引已載入。mock 下沒有金鑰是正常情況；要測 Live 才需確認 missing_setting_names 為空。health 不會額外付費測試遠端模型。若終端曾設 `$env:AGENT_MODE='mock'`，可執行 `Remove-Item Env:AGENT_MODE -ErrorAction SilentlyContinue`，再啟動以採用 `.env`。

## 2. 先用 Swagger 測一輪

開 `http://127.0.0.1:8000/docs`，展開 **POST /discuss**，按 Try it out，從 Examples 選 **正常：使用 current_plan 核算**，按 Execute。範例已是完整有效 JSON，不必自己拼接 schema。

回覆應為 HTTP 200。依序看：

1. `display_text`：這輪摘要。
2. `explanation.decision_reason`：模型針對問題的中文評估。
3. `content.suggested_actions`：交給 Core 決策的建議。若有量化候選，查看 feasibility、audit_result_id、expected_effect。
4. `explanation.uncertainties`：資訊與核算範圍限制。
5. `content.evidence_and_unknowns`：規則、換算來源、live 模式、後端耗時和 LLM 次數。

`verified_for_audited_scope` 只代表灌溉後、作物操作前的單 tick 算術通過，不代表已執行或長期生存保證。LLM 可選擇沒有改善方案，故 suggestions 數量不是固定值。部分發電依然占用整個 tick 的任務，不能兼做飲水。

## 3. 用測試程式保存完整結果

另開終端，服務保持運行：

```powershell
# 正常計畫：顯示秒數、中文結論並存檔
python examples/discussion_client.py --fixture current_plan

# 原始 Core 訊息：沒有額外存活欄位或計畫，應正常討論並揭露未知
python examples/discussion_client.py --fixture core_original_human

# 自動帶入真實前輪回覆，測試三輪（會呼叫三次 API）
python examples/discussion_client.py --fixture current_plan --rounds 3

# 改成本輪想問的問題
python examples/discussion_client.py --fixture current_plan --question "目前電力是否足夠？降低發電會影響什麼？"

# 使用你自己從 Core 拿到的 JSON
python examples/discussion_client.py --request .\my_core_request.json
```

結果存至 `examples/manual_discussion_responses/<時間與唯一編號>/`，每輪有 request.json、response.json、metrics.json。終端及 metrics 顯示客戶端總秒數；後端耗時在回覆 evidence_and_unknowns，兩者量測範圍不同。程式不修改 world，也不執行 proposed_changes。

HTTP／網路／格式錯誤會以非零退出；非 2xx 的服務 JSON 會存檔。請先查看該錯誤，不要把 502／504 當成完成的模型建議。每次 HTTP timeout 為 45 秒。

## 4. 邊界情境

可替換 `--fixture`，或直接貼 `examples/discussion_requests/` 對應 JSON：

| fixture | 預期重點 |
|---|---|
| current_plan | 原計畫 feasible_in_scope，候選與原計畫分別核算 |
| critical | 個人能量與水同時不足，原計畫 base 階段致命，不能同 tick 吃又喝 |
| oxygen_early | 呼吸階段致命，不能用後段植物產氧救回 |
| refill_competition | 依 refill_order 分配公共食物，不假設兩人都補滿 |
| irrigation_second_failure | critical、will_die=false；尚未死亡不能標全員失敗 |
| irrigation_third_failure | unsafe_in_scope、植物死亡；不可將原計畫標可行 |
| already_failed | 當前已失敗，不復活、不產生可執行救援 |
| core_original_human | 存活未知且無計畫，200 一般討論，沒有已驗證具體安排 |

改錯 world_version／rules、重複人員 ID 等無效資料時，預期 409 或 422。正常回 200 不等於資源安全，要看回覆的風險與可行性。

## 5. Core 串接與舊接口

Core 使用 `POST http://<Human電腦IP>:8000/discuss`、`Content-Type: application/json`，傳原有訊息外層。回覆直接是 Human 訊息，無 data wrapper。沿用同 discussion_id、round、world_version；同討論最多三輪，previous_messages 放已取得的公開訊息。精確核算使用已約定的完整 current_plan 表示；alive 未知時仍可討論。

跨電腦時把啟動命令改成 `--host 0.0.0.0`；Core 的 URL 填 Human 電腦實際可達 IP，不能填 0.0.0.0。localhost 驗證不代表區網已連通。

舊的 `examples/requests/normal.json` 仍送 **POST /human-agent/analyze**，測試命令 `python examples/brain_client.py --fixture normal`。不要把 normal.json 貼到 /discuss，也不要把 discussion 訊息貼到 analyze。

## 自動驗收與範圍

```powershell
python -m pytest -q
python scripts/discussion_smoke.py --all
python scripts/discussion_smoke.py --live
python scripts/http_smoke.py --all
```

最新實際結果見 `docs/validation_report.md`。研究證據仍有明示的 partial 範圍；正式 Core／世界引擎與跨機 LAN 需在雙方服務運行時聯測。這些外部驗證不會阻止你現在測試已交付的 Human API。
