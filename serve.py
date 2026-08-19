#!/usr/bin/env python3
"""
粵語配音台 · 本機伺服器
同時做兩件事：
  1. 派發同一個資料夾入面嘅 HTML 檔
  2. 做 API 代理，繞過瀏覽器嘅 CORS 限制

用法：  python3 serve.py
然後開  http://localhost:8000
"""
import os, re, shutil, socket, subprocess, sys, tempfile, threading, time, webbrowser
import http.server, socketserver, urllib.request, urllib.error, urllib.parse, json

PORT = 8000
# 派發嘅資料夾一律鎖返 serve.py 自己所在嗰個，唔跟命令列嘅工作目錄。
# （Windows「以管理員執行」開嘅視窗，工作目錄係 C:\Windows\System32）
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))

# Windows 主控台預設用系統編碼（繁中版係 CP950），直接印中文會炸。
# 強制 UTF-8 輸出，令啟動訊息喺任何語系嘅 Windows 都顯示得正常。
if sys.platform == 'win32':
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding='utf-8', errors='replace')
        except Exception:
            pass

# ── 影片工作階段：每個 session 一個暫存資料夾 ──────────────────────
SESSIONS = {}
SESSION_LOCK = threading.Lock()
SESSION_TTL = 3 * 3600          # 3 小時後清走
MAX_UPLOAD = 4 * 1024**3        # 單檔上限 4GB

def ffmpeg_path():
    return shutil.which('ffmpeg')

def session_dir(sid):
    if not re.fullmatch(r'[A-Za-z0-9_-]{4,64}', sid or ''):
        raise ValueError('工作階段編號格式唔啱')
    with SESSION_LOCK:
        s = SESSIONS.get(sid)
        if not s:
            s = {'dir': tempfile.mkdtemp(prefix='candub-'), 'at': time.time()}
            SESSIONS[sid] = s
        s['at'] = time.time()
        return s['dir']

def sweep_sessions():
    now = time.time()
    with SESSION_LOCK:
        for sid in [k for k, v in SESSIONS.items() if now - v['at'] > SESSION_TTL]:
            shutil.rmtree(SESSIONS.pop(sid)['dir'], ignore_errors=True)

def probe_duration(path):
    try:
        p = subprocess.run([shutil.which('ffprobe') or 'ffprobe', '-v', 'error',
                            '-show_entries', 'format=duration', '-of', 'csv=p=0', path],
                           capture_output=True, timeout=60)
        return float(p.stdout.decode().strip())
    except Exception:
        return 0.0


def run_ffmpeg(args, label, cwd=None):
    """行 ffmpeg，失敗就掟出帶尾段日誌嘅錯誤"""
    p = subprocess.run([ffmpeg_path()] + args, capture_output=True, timeout=3600, cwd=cwd)
    if p.returncode != 0:
        tail = p.stderr.decode('utf8', 'replace').strip().splitlines()[-12:]
        raise RuntimeError(f'{label} 失敗：\n' + '\n'.join(tail))
    return p

# 只准轉發去呢幾個網域，避免變成開放式代理
ALLOWED = ('generativelanguage.googleapis.com', 'api.minimax.io', 'api-uw.minimax.io', 'api.minimaxi.com', 'api.deepseek.com', 'open.bigmodel.cn',
           'api.elevenlabs.io',
           '.cognitiveservices.azure.com', '.api.cognitive.microsoft.com',
           '.tts.speech.microsoft.com', '.stt.speech.microsoft.com')
# 需要原樣轉發嘅認證標頭
PASS_HEADERS = ('authorization', 'x-api-key', 'xi-api-key', 'anthropic-version', 'x-goog-api-key',
                'ocp-apim-subscription-key', 'content-type',
                'x-microsoft-outputformat', 'anthropic-dangerous-direct-browser-access')


def allowed(host):
    return any(host == a or host.endswith(a) for a in ALLOWED)


def html_files():
    """資料夾入面所有 HTML，最新改動嗰個排頭"""
    out = []
    for n in os.listdir(SCRIPT_DIR):
        if n.lower().endswith('.html'):
            try:
                out.append((n, os.path.getmtime(os.path.join(SCRIPT_DIR, n))))
            except OSError:
                pass
    return sorted(out, key=lambda x: -x[1])


# 明顯係文檔嘅 HTML（唔應該當程式入口）
DOC_KEYWORDS = ('說明', '说明', 'readme', 'manual', 'guide', '手冊', '手册')


def is_doc(name):
    n = name.lower()
    return any(k in n for k in DOC_KEYWORDS)


def find_app():
    """揀 HTML 嘅次序：
       1. index.html — 約定俗成嘅入口名，一定揀佢
       2. 非文檔類 HTML 入面 mtime 最新（處理 (1)(2) 重複下載）
       3. 保底：mtime 最新嘅任何 HTML"""
    fs = html_files()
    if not fs:
        return None
    for n, _ in fs:
        if n.lower() == 'index.html':
            return n
    non_doc = [(n, m) for n, m in fs if not is_doc(n)]
    if non_doc:
        return non_doc[0][0]
    return fs[0][0]


class Handler(http.server.SimpleHTTPRequestHandler):

    # HTTP/1.0 每次回應都關連線，瀏覽器並行重用時會撞到 RST，
    # 表現就係 fetch 中途「Failed to fetch」。1.1 保持連線就穩定好多。
    protocol_version = 'HTTP/1.1'

    def __init__(self, *a, **kw):
        kw['directory'] = SCRIPT_DIR
        super().__init__(*a, **kw)

    def _cors(self):
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Headers', '*')
        self.send_header('Access-Control-Allow-Methods', 'GET, POST, OPTIONS')

    def do_OPTIONS(self):
        self.send_response(204)
        self._cors()
        self.end_headers()

    def end_headers(self):
        # HTML 唔准快取，否則換咗檔案都仲係開舊版
        if self.path == '/' or self.path.lower().split('?')[0].endswith('.html'):
            self.send_header('Cache-Control', 'no-store, must-revalidate')
        super().end_headers()

    def do_GET(self):
        if self.path == '/proxy/health':
            self._json(200, {'ok': True})
            return
        if self.path in ('/', '/index.html'):
            app = find_app()
            if app and app != 'index.html':
                self.send_response(302)
                self.send_header('Location', '/' + urllib.parse.quote(app))
                self.send_header('Content-Length', '0')
                self.end_headers()
                return
            if not app:
                self._fail(404, f'{SCRIPT_DIR} 入面搵唔到任何 .html 檔。'
                                f'將 cantonese-dubbing-desk.html 擺埋落 serve.py 隔籬。')
                return
        if self.path == '/mux/health':
            fp = ffmpeg_path()
            ver = ''
            libass = False
            if fp:
                try:
                    out = subprocess.run([fp, '-version'], capture_output=True, timeout=15)
                    full = out.stdout.decode('utf8', 'replace')
                    ver = full.splitlines()[0] if full else ''
                    # 燒錄字幕靠 subtitles filter，個 filter 需要 libass
                    libass = 'enable-libass' in full.lower()
                except Exception:
                    pass
            self._json(200, {'ffmpeg': bool(fp), 'version': ver, 'libass': libass})
            return
        super().do_GET()

    # ── 影片流程 ────────────────────────────────────────────────
    def _q(self):
        return urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)

    def _recv_to(self, path):
        """串流寫入暫存檔，避免大影片食爆記憶體"""
        remain = int(self.headers.get('Content-Length') or 0)
        if remain > MAX_UPLOAD:
            raise ValueError('檔案太大')
        got = 0
        with open(path, 'wb') as f:
            while remain > 0:
                chunk = self.rfile.read(min(1 << 20, remain))
                if not chunk:
                    break
                f.write(chunk)
                remain -= len(chunk)
                got += len(chunk)
        return got

    def _send_file(self, path, ctype):
        size = os.path.getsize(path)
        self.send_response(200)
        self.send_header('Content-Type', ctype)
        self._cors()
        self.send_header('Content-Length', str(size))
        self.end_headers()
        with open(path, 'rb') as f:
            shutil.copyfileobj(f, self.wfile, 1 << 20)

    def handle_upload(self):
        q = self._q()
        sid = q.get('session', [''])[0]
        name = q.get('name', [''])[0]
        if name not in ('video', 'audio', 'srt'):
            self._fail(400, 'name 要係 video / audio / srt')
            return
        d = session_dir(sid)
        ext = {'video': '.mp4', 'audio': '.wav', 'srt': '.srt'}[name]
        n = self._recv_to(os.path.join(d, name + ext))
        print(f'  ↑ {name}{ext} {n/1048576:.1f}MB')
        self._json(200, {'ok': True, 'bytes': n})

    def handle_extract(self):
        sid = self._q().get('session', [''])[0]
        d = session_dir(sid)
        src, out = os.path.join(d, 'video.mp4'), os.path.join(d, 'extracted.wav')
        if not os.path.exists(src):
            self._fail(400, '未上載影片')
            return
        run_ffmpeg(['-y', '-i', 'video.mp4', '-vn', '-ac', '1', '-ar', '16000',
                    '-c:a', 'pcm_s16le', 'extracted.wav'], '抽取音軌', cwd=d)
        print(f'  ✓ 抽音 {os.path.getsize(out)/1048576:.1f}MB')
        self._send_file(out, 'audio/wav')

    def handle_mux(self):
        q = self._q()
        sid = q.get('session', [''])[0]
        burn = q.get('burn', ['0'])[0] == '1'
        extend = q.get('extend', ['0'])[0] == '1'
        bg = max(0, min(100, int(q.get('bg', ['0'])[0] or 0)))   # 原聲保留音量 %
        d = session_dir(sid)
        if not (os.path.exists(os.path.join(d, 'video.mp4')) and
                os.path.exists(os.path.join(d, 'audio.wav'))):
            self._fail(400, '未上載齊影片同音檔')
            return
        srt_path = os.path.join(d, 'srt.srt')
        has_srt = os.path.exists(srt_path) and os.path.getsize(srt_path) > 0
        soft_srt = has_srt and not burn

        # 全部用相對檔名 + cwd，避免路徑有空格、中文或者 Windows 碟符引起嘅跳脫問題
        args = ['-y', '-i', 'video.mp4', '-i', 'audio.wav']
        if soft_srt:
            args += ['-i', 'srt.srt']

        chains, vmap, amap = [], '0:v:0', '1:a:0'

        vd_v = probe_duration(os.path.join(d, 'video.mp4'))
        vd_a = probe_duration(os.path.join(d, 'audio.wav'))

        # 音軌長過影片：凍結最後一格補足，等聲畫等長
        pad = 0.0
        if extend:
            pad = max(0.0, vd_a - vd_v)
            if pad > 0.05:
                chains.append(f'[0:v]tpad=stop_mode=clone:stop_duration={pad:.3f}[vpad]')
                vmap = '[vpad]'
                print(f'  ⧗ 影片 {vd_v:.1f}s → 延長 {pad:.1f}s 配合音軌 {vd_a:.1f}s')

        if burn and has_srt:
            # 檢查 libass。冇嘅話個 filter 會令 ffmpeg 失敗，唔好靜靜跳過。
            fp = ffmpeg_path()
            try:
                out = subprocess.run([fp, '-version'], capture_output=True, timeout=15)
                has_libass = 'enable-libass' in out.stdout.decode('utf8', 'replace').lower()
            except Exception:
                has_libass = False
            if not has_libass:
                print('  ✘ 你部 ffmpeg 冇 libass，燒錄字幕做唔到')
                self._fail(500,
                    '你部 ffmpeg 冇 libass 支援，燒錄字幕做唔到。\n\n'
                    'Mac：brew reinstall ffmpeg（Homebrew 版預設帶 libass）\n'
                    'Windows：winget install Gyan.FFmpeg 亦有 libass\n'
                    '解決之前，可以揀返「內嵌字幕軌」（軟字幕，播放器開字幕先睇到）。')
                return
            # 用絕對路徑 + 明確 fontsdir 避免揾唔到字型
            srt_full = os.path.join(d, 'srt.srt').replace('\\', '/').replace(':', '\\:')
            chains.append(f"{vmap if vmap.startswith('[') else '[0:v]'}"
                          f"subtitles={srt_full}:force_style="
                          "'FontName=Noto Sans CJK TC,FontSize=20,PrimaryColour=&HFFFFFF,"
                          "OutlineColour=&H80000000,BorderStyle=3,Outline=1,MarginV=30'[vout]")
            vmap = '[vout]'
            print(f'  ⧗ 燒錄字幕：{srt_full}')
        # 音訊鏈：原聲墊底 → 補靜音，確保音軌長度啱啱等於目標
        atail = None
        if bg > 0:
            chains.append(f'[0:a]volume={bg/100:.2f}[bgm];[1:a]volume=1.0[voc];'
                          f'[bgm][voc]amix=inputs=2:duration=longest:normalize=0[amix]')
            atail = '[amix]'
        if pad <= 0.05 and vd_a < vd_v - 0.05:
            # 配音短過影片，尾段補靜音，唔好留個唔等長嘅音軌
            chains.append(f'{atail or "[1:a]"}apad[aout]')
            atail = '[aout]'
            print(f'  ⧗ 音軌 {vd_a:.1f}s → 補靜音到 {vd_v:.1f}s')
        if atail:
            amap = atail
        if chains:
            args += ['-filter_complex', ';'.join(chains)]

        args += ['-map', vmap, '-map', amap]
        if soft_srt:
            args += ['-map', '2:0', '-c:s', 'mov_text', '-metadata:s:s:0', 'language=chi']

        reencode = (burn and has_srt) or pad > 0.05
        args += (['-c:v', 'libx264', '-preset', 'veryfast', '-crf', '22', '-pix_fmt', 'yuv420p']
                 if reencode else ['-c:v', 'copy'])
        args += ['-c:a', 'aac', '-b:a', '160k', '-movflags', '+faststart']

        # 唔用 -shortest：佢會連字幕串流都計埋，最後一句字幕幾時完就裁到嗰度。
        # 直接指定目標長度，聲畫必定等長。
        target = (vd_a if pad > 0.05 else vd_v)
        if target > 0:
            args += ['-t', f'{target:.3f}']
        args += ['output.mp4']

        run_ffmpeg(args, '合成影片', cwd=d)
        out = os.path.join(d, 'output.mp4')
        print(f'  ✓ 成品 {probe_duration(out):.1f}s · {os.path.getsize(out)/1048576:.1f}MB'
              f'（{"燒錄" if burn and has_srt else "軟" if has_srt else "無"}字幕'
              f'{"、留原聲 %d%%" % bg if bg else ""}）')
        self._send_file(out, 'video/mp4')

    def handle_cleanup(self):
        sid = self._q().get('session', [''])[0]
        with SESSION_LOCK:
            s = SESSIONS.pop(sid, None)
        if s:
            shutil.rmtree(s['dir'], ignore_errors=True)
        self._json(200, {'ok': True})


    def do_POST(self):
        route = urllib.parse.urlparse(self.path).path
        if route in ('/upload', '/extract', '/mux', '/cleanup'):
            if not ffmpeg_path():
                self._fail(503, '部機揾唔到 ffmpeg。安裝之後重開 serve.py。')
                return
            sweep_sessions()
            try:
                {'/upload': self.handle_upload, '/extract': self.handle_extract,
                 '/mux': self.handle_mux, '/cleanup': self.handle_cleanup}[route]()
            except Exception as e:
                self._fail(500, str(e))
            return

        if not self.path.startswith('/proxy?'):
            self.send_error(404)
            return

        target = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query).get('url', [''])[0]
        host = urllib.parse.urlparse(target).hostname or ''
        if not allowed(host):
            self._fail(403, '唔准轉發去 ' + host)
            return

        length = int(self.headers.get('Content-Length') or 0)
        body = self.rfile.read(length) if length else None

        headers = {k: v for k, v in self.headers.items()
                   if k.lower() in PASS_HEADERS}

        req = urllib.request.Request(target, data=body, headers=headers, method='POST')
        try:
            with urllib.request.urlopen(req, timeout=600) as r:
                data = r.read()
                self.send_response(r.status)
                ct = r.headers.get('Content-Type', 'application/octet-stream')
                self.send_header('Content-Type', ct)
                self._cors()
                self.send_header('Content-Length', str(len(data)))
                self.end_headers()
                try:
                    self.wfile.write(data)
                except (BrokenPipeError, ConnectionResetError):
                    print(f'  ~ {host} 客戶端已斷線')
                    return
                print(f'  → {r.status} {host} ({len(data)} bytes)')
        except urllib.error.HTTPError as e:
            data = e.read()
            self.send_response(e.code)
            self.send_header('Content-Type', e.headers.get('Content-Type', 'text/plain'))
            self._cors()
            self.send_header('Content-Length', str(len(data)))
            self.end_headers()
            self.wfile.write(data)
            print(f'  → {e.code} {host}')
        except Exception as e:
            self._fail(502, f'連唔到 {host}：{e}')

    def _json(self, code, obj):
        body = json.dumps(obj, ensure_ascii=False).encode()
        self.send_response(code)
        self.send_header('Content-Type', 'application/json; charset=utf-8')
        self._cors()
        self.send_header('Content-Length', str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _fail(self, code, msg):
        body = json.dumps({'error': {'message': msg}}, ensure_ascii=False).encode()
        self.send_response(code)
        self.send_header('Content-Type', 'application/json; charset=utf-8')
        self._cors()
        self.send_header('Content-Length', str(len(body)))
        self.end_headers()
        self.wfile.write(body)
        print(f'  ✗ {msg}')

    def log_message(self, fmt, *args):
        try:
            line = fmt % args
        except Exception:
            line = ' '.join(str(a) for a in args)
        # 只顯示 API / 影片相關嘅請求，靜態檔案唔嘈
        if any(k in line for k in ('/proxy', '/mux', '/upload', '/extract', 'code 4', 'code 5')):
            sys.stderr.write(line + '\n')


class Server(socketserver.ThreadingTCPServer):
    allow_reuse_address = True
    daemon_threads = True

    def handle_error(self, request, client_address):
        # 瀏覽器取消請求會令連線中斷，唔使成版 traceback
        et = sys.exc_info()[0]
        if et in (BrokenPipeError, ConnectionResetError, ConnectionAbortedError):
            return
        super().handle_error(request, client_address)


def free_port(start, tries=20):
    """8000 畀人佔咗就順住試落去，唔好一開就死"""
    for p in range(start, start + tries):
        with socket.socket() as s:
            if s.connect_ex(('127.0.0.1', p)) != 0:
                return p
    return None


def banner(port, fs):
    if sys.version_info < (3, 7):
        print('  ⚠ Python 版本太舊，需要 3.7 或以上')
    line = '─' * 46
    print(f'\n  粵語配音台\n  {line}')
    print(f'  資料夾    {SCRIPT_DIR}')

    if fs:
        picked = find_app()
        apps = [(n, m) for n, m in fs if not is_doc(n)]
        docs = [(n, m) for n, m in fs if is_doc(n)]
        stamp = dict(fs)
        print(f'  應用程式  {picked}   （{time.strftime("%Y-%m-%d %H:%M", time.localtime(stamp[picked]))}）')
        # 其他程式檔（舊版）先警告
        others = [(n, m) for n, m in apps if n != picked]
        if others:
            print(f'            ⚠ 仲有 {len(others)} 個舊版程式檔，建議刪走免得搞亂：')
            for n, m in others:
                print(f'              {time.strftime("%Y-%m-%d %H:%M", time.localtime(m))}  {n}')
        # 文檔淨列出，唔警告（係我打包時放入去嘅）
        if docs:
            print(f'            文檔（唔會當入口）：')
            for n, m in docs:
                print(f'              {time.strftime("%Y-%m-%d %H:%M", time.localtime(m))}  {n}')
    else:
        print(f'  應用程式  ⚠ 呢個資料夾搵唔到 .html 檔')
        print(f'            將 index.html 擺埋落 serve.py 隔籬，再重開')

    fp = ffmpeg_path()
    print(f'  影片合成  {"可用" if fp else "⚠ 未裝 ffmpeg（音檔功能唔受影響）"}')
    if not fp:
        print(f'            Windows: winget install Gyan.FFmpeg')
        print(f'            macOS:   brew install ffmpeg')
        print(f'            裝完要開新嘅視窗再行呢個啟動器')

    print(f'  {line}')
    print(f'  網址      http://localhost:{port}')
    print(f'  停止      喺呢個視窗按 Ctrl+C')
    print(f'  {line}\n')


if __name__ == '__main__':
    args = [a for a in sys.argv[1:] if not a.startswith('-')]
    no_open = '--no-browser' in sys.argv

    want = int(args[0]) if args else PORT
    port = free_port(want)
    if port is None:
        print(f'\n  ✘ {want} 到 {want + 19} 埠全部畀人佔用。')
        print(f'    關咗其他伺服器，或者行：python serve.py 9000\n')
        sys.exit(1)
    if port != want:
        print(f'\n  ⓘ {want} 埠畀人佔用咗，改用 {port}')

    banner(port, html_files())

    if not no_open:
        threading.Timer(0.8, lambda: webbrowser.open(f'http://localhost:{port}')).start()

    try:
        Server(('127.0.0.1', port), Handler).serve_forever()
    except KeyboardInterrupt:
        print('\n  已停止\n')
