# 粵語配音台 · Cantonese Dubbing Desk

> 想快速上手？睇 **[速查.md](速查.md)** 就夠，一頁紙。

將普通話 podcast 或者影片，轉成一男一女對話嘅廣東話配音，並可以配返落原片加中文字幕。

專為處理 NotebookLM 產生嘅普通話 Audio Overview 同 Video Overview 而做。

---

## 用嚟做咩

| 輸入 | 輸出 |
|---|---|
| 普通話 podcast（mp3 / m4a / wav） | 廣東話配音 MP3 |
| 普通話影片（mp4 / mov / webm） | 廣東話配音 MP4 + 繁體中文字幕 |
| 直接貼文字稿 | 廣東話稿件 + 配音 |

處理流程：**轉錄 → 分講者 → 譯廣東話 → 人手校對 → 語音合成 → 影片合成**

---

## 快速開始

### 1. 安裝 ffmpeg（只有影片功能先需要）

```bash
# Windows
winget install Gyan.FFmpeg

# macOS
brew install ffmpeg

# Ubuntu / Debian
sudo apt install ffmpeg
```

裝完開一個**新嘅**終端機視窗（舊視窗食唔到新 PATH），確認：

```bash
ffmpeg -version
```

### 2. 啟動

五個檔案擺喺同一個資料夾（`index.html`、`serve.py`、`launch.bat`、`launch.command`、`速查.md`），然後：

- **Windows** — 雙擊 `launch.bat`
- **macOS** — 雙擊 `launch.command`（第一次可能要先喺終端機行 `chmod +x launch.command`）
- **其他 / 慣用命令列** — `python3 serve.py`

瀏覽器會自動打開。啟動視窗會列出實際狀態：

```
  粵語配音台
  ──────────────────────────────────────────────
  資料夾    D:\dub
  應用程式  index.html   （2026-07-29 15:10）
  影片合成  可用
  ──────────────────────────────────────────────
  網址      http://localhost:8000
  停止      喺呢個視窗按 Ctrl+C
  ──────────────────────────────────────────────
```

用完喺呢個視窗按 `Ctrl+C`，或者直接閂咗佢。

**啟動器會自動處理呢幾樣：**

| 情況 | 處理 |
|---|---|
| 由 `C:\Windows\System32` 之類嘅目錄啟動 | 自動 `cd` 返去檔案所在資料夾 |
| 8000 埠畀人佔用 | 順住試 8001、8002…最多 20 個 |
| 資料夾有幾個舊版 HTML | 自動用最新嗰個，並列出建議刪走嘅 |
| 未裝 Python | 提示下載網址 |
| 未裝 ffmpeg | 提示安裝指令，音檔功能照用 |
| `serve.py` 唔喺隔籬 | 講明實際資料夾路徑 |

> 啟動器刻意寫成純 ASCII。`cmd.exe` 用系統編碼（繁中 Windows 係 CP950）讀批次檔，如果入面有 UTF-8 中文會變亂碼並被當成指令執行。所有中文訊息由 `serve.py` 輸出。

指定埠：`python3 serve.py 9000`。唔想自動開瀏覽器：加 `--no-browser`。

> **唔可以直接雙擊個 HTML 檔開。** `file://` 之下所有 API 呼叫都會被瀏覽器擋。頁面頂部會有自檢提示話你知。

> **亦唔可以部署上 GitHub Pages / Vercel / Netlify。** 呢個 app 需要 `serve.py` 提供 CORS 代理同 ffmpeg，靜態寄存冇呢啲，部署咗只會得個殼。呢個 repo 係俾人下載返本機行嘅。

### 3. 填 API 金鑰

撳右上角「設定」。金鑰只會存喺你部機嘅 `localStorage`，唔會傳去任何第三方。

---

## 需要邊啲服務

### Azure Speech（轉錄 + 語音合成）— 必需

1. [portal.azure.com](https://portal.azure.com) → Create a resource → 搜尋 **Speech** → Create
2. Region 揀近你嗰個（例如 `southeastasia`），Pricing tier 揀 **F0**（免費）
3. 部署完 → **Keys and Endpoint** → 複製 KEY 1 同 Location/Region
4. 設定入面填：Key、區域（細楷冇空格，例如 `southeastasia`）、資源名稱（資源頁左上角嗰個名）

**F0 免費層額度**：每月 5 小時轉錄、50 萬字元語音合成。TTS 每 60 秒 20 次請求上限——app 已經內建節流同批次合成應付。

> 金鑰同區域一定要對得上。用 `southeastasia` 建嘅 key 填 `eastasia` 會直接 401。

> Azure 三個欄（Key、區域、資源名）就算轉錄改用第二個引擎都建議照填 —— 佢同時係預設嘅語音合成引擎。

### 轉錄引擎（設定可揀）

| 引擎 | 收費 | 切段 | 時間碼 | 備註 |
|---|---|---|---|---|
| **Azure 快速轉錄**（預設）| F0 免費層每月 5 鐘 | 8 分鐘 | 聲學對齊，準 | zh-CN + diarization，最多 2 個講者 |
| **ElevenLabs Scribe v2** | 約 US$0.22/鐘 | **唔切段** | 逐字，最準 | 冇免費層，要先充值 |
| **Gemini 音頻理解** | 用返翻譯個 key | 4 分鐘 | 模型估，會飄 | 唔使另外開戶 |

**ElevenLabs**：去 [elevenlabs.io](https://elevenlabs.io) 個人頁 → API Keys 攞 key，填落設定「ElevenLabs API Key」。
成個檔一次過送去 `api.elevenlabs.io/v1/speech-to-text`（`model_id=scribe_v2`、`language_code=cmn`、`diarize=true`）。
因為唔切段，講者標籤可以貫穿全片，唔會好似 Azure 咁逐段重新編號。上限 250MB（本機代理一次過轉發嘅限制），超過就要剪短或者轉用 Azure。

**Gemini**：用返「翻譯供應商 = Google Gemini」嗰個 `kGoogle` key，另外可以喺「Gemini 轉錄模型」指定型號（預設 `gemini-2.5-flash`）。
切段 4 分鐘係為咗避開 `inline_data` 20MB 請求上限；免費層 10 RPM，程式每段之間自動隔 7 秒。
⚠ **時間碼係模型估出嚟嘅，唔係聲學對齊**。短片可以接受，長片會愈估愈飄，做字幕同聲畫對齊要留意。

### 語音（可選升級）— MiniMax 官方 API

預設用 Azure 語音已經免費夠用。想要更自然嘅粵語聲，可以去 [platform.minimax.io](https://platform.minimax.io) 開戶，攞 **API Key** 同 **Group ID**（兩樣都喺帳戶管理頁），設定入面「語音引擎」轉「MiniMax 官方」。

- 型號：`speech-2.8-hd`（質素最高）或 `speech-2.8-turbo`（快啲平啲）
- 預設聲：官方粵語主持聲 `Cantonese_ProfessionalHost（M)` / `（F)`（ID 入面個括號係全形，官方原樣）
- 已自動設 `language_boost: Chinese,Yue`，確保當粵語讀
- 收費按字元計，HD 每千字約 US$0.05–0.10，一集 20 分鐘節目約 US$0.2–0.4
- 逐句合成，速度慢過 Azure 批次；音高語速有效，但語氣選項只影響翻譯用詞

### 翻譯 — Google Gemini

推薦 Gemini，預設用 `gemini-2.5-flash`。免費層限額因模型而異，程式會自動按模型調節請求間隔：

| 模型 | 每分鐘 | 每日 | 198 句需時 |
|---|---|---|---|
| `gemini-2.5-flash` | 10 | 250 | 約 2 分鐘 |
| `gemini-2.5-flash-lite` | 15 | 1000 | 約 1.5 分鐘 |


---

## 主要功能

### 分講者
Azure Fast Transcription 自動分辨兩位主持，男聲配 `zh-HK-WanLungNeural`，女聲配 `zh-HK-HiuMaanNeural`。校對頁每句都可以單獨調換，或者用 `⇅` 由該句起全部調轉（修正分段接駁位嘅錯亂）。

### 語氣
五種：生動活潑、嚴肅專業、好奇提問、溫和親切、原汁原味。影響翻譯用詞同語氣詞密度，亦會微調語音音高同句間停頓。校對頁可以直接換語氣重譯，唔會再用轉錄額度。

### 口語化把關
提示語以「改寫」而非「翻譯」為框架，並附正反例示範（「呢項政策對佢哋嘅就業有正面影響」✘ vs「呢個政策對佢哋搵工幾有幫助」✔），避免模型保留書面語句法逐字換詞。

譯完會自動掃描「的、是、不、了、我們、非常」呢類書面語標記；超標會警告，校對頁亦會將有問題嘅句子標黃。「重譯書面語句子」只重譯標黃嗰啲，而且新譯文冇改善就唔會覆蓋。

### 聲畫對齊
廣東話同普通話長度唔同，直接接駁會同畫面脫節。三種對齊方式：

- **壓縮音軌**（預設）— 超出槽位嘅句子自動加快語速，音軌啱啱等於影片
- **延長影片** — 凍結最後一格補足秒數
- **唔處理** — 保持自然語速

三種都保證輸出嘅視訊同音訊等長。

### 字幕
用普通話原文，時間碼跟轉錄嘅原始時間，所以同畫面完全同步。預設輸出繁體中文（香港用字），每行 20 字、每格最多兩行，過長嘅句子會拆成多個時間段。可以選內嵌字幕軌（快）或者燒錄入畫面（慢但一定睇到）。

簡繁轉換表源自 [zhconv](https://github.com/gumblex/zhconv) 嘅 MediaWiki 轉換表，包含 2797 個單字對應同 4539 條消歧詞組（頭髮、乾淨、麵條、幹活 呢類逐字轉會出錯嘅）。完全離線運作。

### 斷點續做
轉錄結果會存喺 `localStorage`。翻譯失敗、換模型、換語氣都唔使重新轉錄，重開頁面會提示「繼續校對」。

---

## `serve.py` 做咩

單一 Python 檔，只用標準庫，唔使 `pip install`：

1. **派發靜態檔案** — 鎖定自己所在嘅資料夾，唔跟命令列嘅工作目錄
2. **API 代理** — 繞過 CORS。有網域白名單，只轉發去 Google、Azure 同 MiniMax
3. **影片處理** — 呼叫 ffmpeg 抽音軌同合成成品

金鑰喺瀏覽器同伺服器之間經 `localhost` 傳遞，唔會寫入任何檔案或者日誌。伺服器只綁定 `127.0.0.1`，同一個網絡嘅其他裝置連唔到。

---

## 常見問題

**頁面頂部出現黃色警告框**
自檢已經講明係咩問題——`file://` 開檔案、開錯埠、`serve.py` 未更新、或者未裝 ffmpeg。

**`insufficient_quota` / `credit balance is too low`**
該平台冇 API 額度。換個供應商，或者去該平台增值。轉錄結果已保留，撳「重新翻譯」即可。

**合成語音途中不斷 `Failed to fetch`**
Azure F0 層速率限制。確認設定入面「Azure 定價層」揀咗 F0，app 會自動節流。純音檔模式會將多句合併成一個請求。

**輸出全部係普通話原文**
翻譯靜靜失敗咗。睇 log 尾段嘅「翻譯完成：N/M 句成功」同錯誤訊息。多數係模型名唔啱該供應商。

**字幕溢出畫面**
設定入面調細「字幕每行字數」（16 字適合手機）。

---

## 授權

MIT
