# 粵語配音台

任何語言嘅影片／podcast → 廣東話配音 + 字幕。純本機運行。

## 指令

```bash
python3 serve.py          # 起服務（預設 8000，自動試到 8020）
python3 serve.py 9000 --no-browser
node test.js              # 純邏輯回歸測試，唔使 API key。改完 index.html 一定要跑
```

配套工具：`粵語聲試聽.html`（同一句話派去各家每一把粵語聲，並排試聽）。
由 `http://localhost:8000/粵語聲試聽.html` 開，同主程式共用 `candub.cfg.v1` 金鑰。

`test.js` 直接由 `index.html` 抽頂層函數出嚟跑，所以佢永遠對住真實 code。
新增嘅頂層函數要加入 `test.js` 嘅 `NEEDED`／`CONSTS` 先抽到。

## 架構

- `index.html` — 成個 app（HTML + CSS + JS 一個檔）。冇 build，冇 npm，冇框架。
- `serve.py` — 靜態派檔 + CORS 代理 + ffmpeg 影片處理。**只用 Python 標準庫。**
- 狀態存 `localStorage`；音檔／影片存 `serve.py` 嘅 session 暫存夾，3 小時後自動清。

## 紅線

- `serve.py` 只 bind `127.0.0.1`。金鑰經 localhost 傳，**唔可以寫入任何檔案或者日誌**。
- 加新 API 供應商 → 一定要同時加網域入 `serve.py` 嘅 `ALLOWED`，唔係代理會擋。
- **金鑰一定要放 header，唔可以放 query string。** `serve.py` 個 `log_message` 會印出所有含
  `/proxy` 嘅請求行，個 URL 喺入面。`?key=xxx` 會直接印落終端機。Google API 收
  `X-Goog-Api-Key` header，用佢。
- 代理 `/proxy?url=` 支援 GET 同 POST 兩種（攞聲清單係 GET，合成係 POST）。
- `launch.bat` 要保持純 ASCII。`cmd.exe` 用 CP950 讀批次檔，入面有 UTF-8 中文會變亂碼並被當成指令執行。中文訊息一律由 `serve.py` 印。
- 唔可以用 `file://` 開，亦唔可以部署上靜態寄存——冇 `serve.py` 個 app 得個殼。

## 語言處理

源語言可以係任何語言，輸出一定係廣東話。所有「呢段字係中文定係拼音文字」嘅判斷
集中喺三個函數，**唔好喺其他地方另外寫字數啟發式**：

- `isCJKText(t)` — 逐字排版定係按空格排版（決定斷行同字數上限）
- `isChineseText(t)` — 係咪真中文（決定行唔行簡繁轉換）。日文韓文有漢字但會畀轉換表誤傷
- `endsSentence(t)` / `segCharLimit(t)` — 斷句。英文句號算句末，但要避開 `Dr.`、`U.S.`、`3.5`

## TTS 引擎現況（2026-09 實測，香港）

- **Azure `zh-HK`** — 得 3 把聲。穩定，免費層夠用，但做多講者唔夠。
- **Google Chirp 3: HD `yue-HK`** — 官方 30 把，Preview。**已整合**（`oTTS = 'google'`，
  `gSpeak()`）。Cloud TTS 收 API key，唔使 service account。要喺 Cloud Console 開啟
  API + 喺 key 嘅 API restrictions 加埋 Cloud Text-to-Speech。
  Chirp 3 HD **唔收 SSML**，所以只可以用純文字 + `speakingRate`，音高調唔到。
- **Gemini TTS**（`generativelanguage.googleapis.com`）— **香港封鎖**，回
  `User location is not supported for the API use`。而且官方語言清單本來就冇粵語。
  唔好行呢條路。
- ⚠ **一條 Google key 要同時授權兩個 API**：`generativelanguage`（翻譯 + Gemini 轉錄）
  同 `texttospeech`（Chirp 3 HD）。喺 Credentials 個 API restrictions 度加新嗰個
  好易踢走舊嗰個，一踢走主程式嘅翻譯就會靜靜壞埋，錯誤訊息係
  `Requests to this API ... are blocked`。
- **MiniMax** — 大陸版同國際版係兩套獨立帳戶，key／Group ID／域名全部唔通用。
  1004 `login fail` 多數就係揀錯區域讀錯欄。

## 已知限制

- **講者硬性兩個。** `absorbSegs` 將任何講者數目壓成 A／B，`num_speakers`／`maxSpeakers` 寫死 2，聲線得 `vA`／`vB`。第三個講者會靜靜併入 B。
- **`/mux` 個 `bg` 參數唔係真・保留背景音樂。** 佢係將原本成條音軌（連原本把人聲）降音量疊返落去，所以會聽到原聲漏音。真正做法要人聲分離。
- 說明書（`使用說明書.md`／`.html`、`README.md`、`速查.md`）要同 code 一齊更新。
