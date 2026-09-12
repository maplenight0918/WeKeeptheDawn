# 重建交付與驗收

日期：2026-09-12。實作依據僅為本資料包的 `docs/SPEC.md` 及 `docs/codex_prompt.md` 指令。
未讀取其他專案的既有實作，也未實作世界設定的遊戲平衡係數。

已建立 `paths.py`、`src/retrieval/`、`src/models/`、`src/agent/`、`src/api/`，包含六個端點。
兩段 system prompt、九組檢索查詢、五個環境修正函式直接從 SPEC 擷取。
`coefficients.json` 為係數與上下界來源；三個 corpus 索引於 lifespan 載入一次。

## 環境

系統 `/usr/bin/python3` 因缺少 Xcode 工具無法執行，改將 uv 與獨立 Python 3.12.14 安裝至專案 `.tools/`，在本專案建立 `.venv`。
已安裝 numpy 2.5.3、FastAPI 0.141.1、uvicorn 0.52.4（及其必要相依套件），`.env.example` 已複製為 `.env`。
本機 macOS 啟動指令是 `.venv/bin/python -m uvicorn src.api.main:app --port 8000`；Windows 的 `.venv/Scripts/python.exe` 路徑需在 Windows 建立 venv 後使用，未做 Windows 執行驗證。

## 驗收表

以下為真正透過 localhost HTTP 的結果，原始輸出保存在 `acceptance_results.json`。
五作物順序為 lettuce / potato / tomato / wheat / soybean。

| 項目 | 實際結果 | 狀態 |
|---|---|---|
| GET /health | chunks = 64160 | 通過 |
| POST /simulate 可食 g/day | 389.934593 / 324.945494 / 259.956395 / 194.967297 / 138.643411；整數顯示為 390 / 325 / 260 / 195 / 139 | 通過 |
| POST /simulate O₂ kg/day | 0.023179 / 0.092718 / 0.027815 / 0.407958 / 0.333784；三位小數為 0.023 / 0.093 / 0.028 / 0.408 / 0.334 | 通過 |
| GET /world/crops 可食 g/m²/day | 19.496730 / 16.247275 / 12.997820 / 9.748365 / 6.932171；兩位小數為 19.50 / 16.25 / 13.00 / 9.75 / 6.93 | 通過 |
| 小麥 40 m² / PPFD 400 / 16 h / 24°C / CO₂ 1000 / 預算 8 kW | 警告「需求 10.41 kW 超出預算 8 kW，PPFD 降到 305 µmol/m²/s。」；effective_ppfd = 304.6 | 通過 |
| 同条件 POST /sweep，PPFD 240 | power_delta_pct = −38.8，edible_delta_pct = −15.8 | 通過 |
| 指定 GET /search 查詢 | HTTP 200，0.92 秒；前三筆 0.809798 / 0.804669 / 0.800031，第一筆 Soilless Cultivation… | 通過 |
| lettuce 預設 POST /analyze | HTTP 200，35.66 秒；citations 3 筆、evidence 4 筆，tradeoff 含百分比 | 通過 |

世界說明端點 O₂ g/m²/day 實測：1.158972 / 4.635889 / 1.390767 / 20.397912 / 16.689201。
所有值均由 `/simulate` 同一換算函式產生，再除以 20；未使用世界結算常數。

另有 10 項 unittest 全數通過：五作物與 daily_rate 合約、降載與 sweep、產量單調性及環境因子、黑暗與低預算邊界、64160×1024 索引對齊與正規化、metadata 過濾與單篇上限、fallback 與查詢、prompt 逐字一致與 JSON 解析、係數上下界退回及 evidence fallback、採用來源傳遞。Agent 測試使用明確 mock，只驗證控制流程，不視為真實 LLM 驗收。

## SPEC 未明確處與採用假設

1. **平台啟動路徑**：SPEC 用 Windows；目前是 macOS，所以使用 `.venv/bin/python`。不建立偽裝 Windows 的 python.exe。
2. **Input 預設值**：schema 未列預設，依 §10/§11 固定條件設定；未指定作物時採 lettuce。`power_budget` 不得為負，數值不得為 NaN/Infinity。
3. **供需數值精度**：SPEC 未規定 supply/demand 四捨五入，保留完整精度；驗收按表中顯示精度比較。daily_rate 完全依指定小數位，effective_ppfd 取一位小數。世界端點亦保留除法結果，前端兩位小數顯示可對上固定表。
4. **sweep 電力預算**：為重現指定 −38.8% / −15.8%，所有掃描點均用未限電需求，保留原始 PPFD 為首列。重複點去重，零產量基準的百分比回 null；掃描倍率可超過輸入 PPFD 的 2000 上限，以遵守倍率介面。
5. **低於泵最低耗電的預算**：SPEC 無停機規則；PPFD 降到 0，仍回報泵最低需求並警告無法滿足預算，不捏造低於設備公式的電力。
6. **交叉驗算的精確形式**：SPEC 未给完整式，採 `DLI × lue × area × env` 估乾重、`乾重 / wue` 估水量，兩者超過主路徑四倍時警告，均不回寫主計算。
7. **未列出的函式簽名和中間值鍵**：採 `Coefficients(crop)`、`simulate(coeffs, inp)`、`sweep_ppfd(coeffs, inp, levels)`；兩個交叉值命名為 `lue_dry_g_day` 與 `wue_water_l_day`，factors 使用 temperature/co2/humidity/density。
8. **合理性區間與來源檢查**：biomass_rate 優先採作物 P25/P75，其他採全域；邊界含等號。LLM 覆寫來源必須對得上該係數實際檢索文獻，否則回中位數並警告，避免虛構 citations。
9. **world/crops schema**：指令只列內容未列 JSON 格式，採 conditions/crops/note；作物列含 crop、edible_g_m2_day、o2_g_m2_day、coefficients。
10. **網路錯誤、效能與上限**：SPEC 未定 HTTP 錯誤合約，缺金鑰/上游錯誤回 503。五項 embedding 以執行緒並行，查询向量有 128 筆記憶體快取，仍維持兩次循序 LLM 呼叫。單次 embedding 逾時 30 秒、LLM 35 秒；沒有有效金鑰前無法保證總延遲小於 40 秒。search 的 k 限 1–100，sweep 限 1–100 個有限非負倍率。

完成網路驗收所需外部條件：在 `.env` 填入有效 OpenRouter 金鑰，重啟 API，重新執行 `tests/acceptance_http.py`。金鑰值不應貼進報告或版控。

## 金鑰填入後的真實網路驗收

使用者明確授權將文獻段落、參數與提示傳至 OpenRouter 後執行。搜尋約 0.233 秒、分析約 0.264 秒即回 HTTP 503，兩者上游皆為 OpenRouter HTTP 401。這些是失敗回應耗時，不代表成功分析效能。確認 .env 已讀取、沒有空白或預先設定環境變數覆蓋；金鑰不符合程式預期的 OpenRouter 前綴。未記錄或輸出金鑰內容。需更換有效 OpenRouter 金鑰後重啟並重驗；本地驗收仍全部通過。

## 更換 OpenRouter 金鑰後的驗收結果

真實 HTTP 驗收全部通過。/search 耗時 0.92 秒，/analyze 耗時 35.66 秒。先前 401 已排除。此次完整推理有 3 筆 citations 與 4 筆 evidence；tradeoff：降低光照至 PPFD 150 可節省 38.1% 電力（降至 49.2 kWh/day），可食產量僅減少 21.7%（至 1089 g/day）；若提升至 PPFD 300，電力增加 19.0%（至 95.4 kWh/day）但產量僅增 7.5%（至 1496 g/day），邊際效益遞減明顯。

這是單次實測通過，不代表外部供應商每次都能在 40 秒內完成。原始結果見 acceptance_results.json；先前失敗紀錄保留為歷史。

## Core討論介面與電力口徑更新

新增 `/discuss`，詳細現行規格見 `DISCUSS_HANDOFF.md`。Plant耗電沿用原模型；每塊5 m²、1 EU=3.9745 kWh、電力每tick一小時。20塊100 m²需求為397.460870 kWh/day、4.166781 EU/tick。原文件中的6端點驗收為初版歷史；現在加上第7個討論端點。未修改Core或Human程式，也未將舊世界數值宣稱為已更新。
