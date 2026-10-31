"""
CLAIMX DUAL CLAIM BOT v14.0 - AUTO-WD & ANTI LOGIN-LOOP
- 12 Threads, Dedicated Port (9050-9061)
- Cek Saldo tiap 15 klaim. Jika >= 0.009, langsung WD dan pindah akun.
- Thread anti-crash (mencegah loop login).
"""

import logging, warnings, threading, sys
logging.disable(logging.CRITICAL)
warnings.filterwarnings("ignore")
for _n in ('urllib3','requests','socks','stem','stem.connection','stem.socket','stem.control','asyncio'):
    _l = logging.getLogger(_n); _l.setLevel(logging.CRITICAL); _l.propagate = False

import requests
from bs4 import BeautifulSoup
import time, re, os, random, string, hashlib, socks, socket
from stem import Signal
from stem.control import Controller
from queue import Queue, Empty
from datetime import datetime
from urllib.parse import urljoin

def _silent_thread_excepthook(args):
    try:
        t = args.thread.name if args.thread else '?'
        print(f"[✗] Thread {t} crash: {type(args.exc_value).__name__}: {args.exc_value}", flush=True)
    except Exception: pass
def _silent_excepthook(t, v, tb):
    try: print(f"[✗] {t.__name__}: {v}", flush=True)
    except Exception: pass
threading.excepthook = _silent_thread_excepthook
sys.excepthook = _silent_excepthook

# ==================== KONFIG ====================
BASE_URL = "https://claimx.online"
LOGIN_URL = f"{BASE_URL}/login"
REGISTER_URL = f"{BASE_URL}/register?ref=gi2h"
POP_FAUCET_URL = f"{BASE_URL}/pop-faucet"
POP_CLAIM_URL = f"{BASE_URL}/pop-faucet/claim"
FAUCET_URL = f"{BASE_URL}/faucet"
CLAIM_URL = f"{BASE_URL}/faucet/claim"
WITHDRAW_URL = f"{BASE_URL}/withdraw"
WITHDRAW_REQUEST_URL = f"{BASE_URL}/withdraw/request"

EMAIL_FILE = "emailscrap.txt"
PASSWORD = "Aprilia1"

POPUNDER_MIN_WAIT = 11.5
FAUCET_MIN_WAIT = 7.5

MAX_RETRY_PER_ACTION = 10
WITHDRAW_THRESHOLD = 0.009
WITHDRAW_EPS = 1e-9
MAX_CLAIMS = 100000

# KUNCI: Cek saldo setiap 15 klaim
WD_CHECK_EVERY_N_CLAIMS = 25

TOR_INSTANCES = {9050 + i: 10050 + i for i in range(12)}

# ==================== BACA EMAIL ====================
def load_emails(file_path=EMAIL_FILE):
    if not os.path.exists(file_path):
        print(f"[✗] File '{file_path}' tidak ditemukan!", flush=True); sys.exit(1)
    emails = []; seen = set(); skipped = 0; invalid = 0
    email_re = re.compile(r'^[^@\s]+@[^@\s]+\.[^@\s]+$')
    with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
        for raw in f:
            line = raw.strip()
            if not line or line.startswith('#') or line.startswith('//'):
                skipped += 1; continue
            if any(sep in line for sep in [' ', '\t', ',', ';', '|']):
                line = re.split(r'[\s,;|]+', line)[0]
            line = line.lower()
            if not email_re.match(line):
                invalid += 1; continue
            if line in seen:
                skipped += 1; continue
            seen.add(line); emails.append(line)
    print(f"[ℹ] Load '{file_path}': {len(emails)} valid, {skipped} skip, {invalid} invalid", flush=True)
    if not emails: sys.exit(1)
    return emails
EMAILS = load_emails(EMAIL_FILE)

# ==================== TOR ====================
def check_tor_port(p):
    try:
        s = socks.socksocket(); s.set_proxy(socks.SOCKS5, "127.0.0.1", p)
        s.settimeout(5); s.connect(("1.1.1.1", 53)); s.close(); return True
    except Exception: return False

def wait_for_tor_ports(ports, timeout=90):
    start = time.time()
    while time.time() - start < timeout:
        if all(check_tor_port(p) for p in ports):
            log_info("Semua 12 Tor ports siap."); return True
        time.sleep(3)
    log_error("Tor ports timeout."); return False

def renew_tor_circuit(cp):
    try:
        with Controller.from_port(port=cp) as c:
            c.authenticate(); c.signal(Signal.NEWNYM); return True
    except Exception: return False

def create_session(proxy_port):
    s = requests.Session()
    if proxy_port:
        px = f"socks5h://127.0.0.1:{proxy_port}"
        s.proxies = {'http': px, 'https': px}
    s.headers.update({
        'User-Agent': random.choice([
            'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        ]),
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
    })
    return s

def rotate_port(port):
    cp = TOR_INSTANCES.get(port)
    if not cp: return False
    return renew_tor_circuit(cp)

# ==================== LOG ====================
_log_lock = threading.Lock()
_emit_ts = [0.0]
def _emit(text):
    now = time.time()
    with _log_lock:
        if now - _emit_ts[0] < 0.1: return
        _emit_ts[0] = now
    try: print(text, flush=True)
    except Exception: pass

def log_info(m):    _emit(f"[ℹ] {m}")
def log_success(m): _emit(f"[✓] {m}")
def log_warning(m): _emit(f"[⚠] {m}")
def log_error(m):   _emit(f"[✗] {m}")
def log_balance(e, b): _emit(f"[💰] {e} balance: {b:.8f}")
def log_withdraw(e, a, ok): _emit(f"[💸] {e} withdraw {a:.8f} -> {'OK' if ok else 'FAIL'}")

# ==================== STATE ====================
daily_limit_accounts = {}
dl_lock = threading.Lock()

def is_daily_limited(email):
    with dl_lock:
        d = daily_limit_accounts.get(email)
        if not d: return False
        if d == datetime.now().date(): return True
        del daily_limit_accounts[email]; return False

def mark_daily_limited(email):
    with dl_lock: daily_limit_accounts[email] = datetime.now().date()
    log_info(f"{email} daily limited")

# ==================== PARSE ====================
def request_with_retry(s, method, url, retries=MAX_RETRY_PER_ACTION, **kw):
    for i in range(retries):
        try:
            r = s.get(url, timeout=30, **kw) if method.upper() == 'GET' else s.post(url, timeout=30, **kw)
            if r.status_code >= 500: time.sleep(min(2 ** i, 20)); continue
            return r
        except (requests.ConnectionError, requests.Timeout, socket.error):
            if i == retries - 1: return None
            time.sleep(2 * (i + 1))
    return None

def extract_csrf_and_sitekey(html):
    soup = BeautifulSoup(html, 'html.parser')
    ci = soup.find('input', {'name': 'csrf_token'})
    csrf = ci.get('value') if ci else None
    return csrf, None, None, None

def extract_icon_captcha(html):
    soup = BeautifulSoup(html, 'html.parser')
    target = None; has = False; options = []
    bc = soup.find('div', id='iconCaptchaButtons') or soup.find('div', id=re.compile(r'iconCaptcha', re.I))
    hi = soup.find('input', {'name': 'icon_captcha_selected'})
    if not bc and not hi: return {'target_icon': None, 'options': [], 'has_captcha': False, 'field_name': None}
    has = True
    td = soup.find('div', class_=re.compile(r'border-warning'))
    if td and td.find('i'):
        for c in td.find('i').get('class', []):
            if c.startswith('bi-'): target = c; break
    if bc:
        for b in bc.find_all('button'):
            ie = b.find('i')
            if ie:
                for c in ie.get('class', []):
                    if c.startswith('bi-'): options.append({'key': b.get('data-key'), 'icon': c}); break
    return {'target_icon': target, 'options': options, 'has_captcha': has, 'field_name': hi.get('name') if hi else 'icon_captcha_selected'}

def solve_icon_captcha(html):
    d = extract_icon_captcha(html)
    if not d['has_captcha']: return 'no_captcha', None
    t = d.get('target_icon'); o = d.get('options', []); fn = d.get('field_name')
    for x in o:
        if x['icon'] == t or (t and (t in x['icon'] or x['icon'] in t)): return x['key'], fn
    return None, fn

def extract_alerts(html):
    soup = BeautifulSoup(html, 'html.parser'); a = {}
    for c in ['alert-success','alert-danger','alert-info','alert-warning']:
        e = soup.select_one(f".{c}")
        if e: a[c.split('-')[1]] = e.get_text(strip=True)
    return a

def extract_cooldown_time(html):
    c = BeautifulSoup(html, 'html.parser').find(id='countdownClock')
    if c and c.get('data-seconds'):
        try: return int(c['data-seconds'])
        except Exception: pass
    return None

def check_daily_limit(html):
    soup = BeautifulSoup(html, 'html.parser')
    for a in soup.select(".alert.alert-danger, .alert.alert-warning"):
        t = a.get_text(" ", strip=True).lower()
        if 'daily limit' in t or 'all claims allowed' in t: return True
    for tag in soup.find_all(['h1','h2','h3','h4','h5']):
        if 'daily limit reached' in tag.get_text(" ", strip=True).lower(): return True
    return False

def parse_claim_amount(text):
    m = re.search(r'([+-]?\d+(?:\.\d+)?)\s*(USDT|BTC|ETH|DOGE|LTC)', text, re.I)
    return f"{m.group(1)} {m.group(2).upper()}" if m else None

def parse_cd_alert(text):
    m = re.search(r'(\d+)\s*(second|minute|hour)', text, re.I)
    if m:
        n = int(m.group(1)); u = m.group(2).lower()
        if u.startswith('minute'): return n * 60
        if u.startswith('hour'): return n * 3600
        return n
    return None

def is_ip_cooldown(text):
    t = text.lower()
    return ('recently claimed' in t or 'one claim per ip' in t
            or 'per ip is allowed' in t or ('ip address' in t and 'claim' in t))

def handle_claim_response(s, pr, email, label='claim'):
    if pr is None: return None
    if pr.status_code in [302, 303]:
        loc = pr.headers.get('Location', '')
        if 'login' in loc.lower(): return {'need_login': True}
        f = request_with_retry(s, 'GET', urljoin(BASE_URL, loc))
        if f is None: return None
        fh = f.text
    else: fh = pr.text
    
    if check_daily_limit(fh): return {'limit': True}
    a = extract_alerts(fh)

    if a.get('success'):
        amt = parse_claim_amount(a['success']) or a['success']
        log_success(f"{label} OK {email} -> {amt}")
        return {'amount': amt}
    if a.get('danger'):
        d = a['danger']; dl = d.lower()
        if 'daily limit' in dl or 'all claims' in dl: return {'limit': True}
        if ('verification failed' in dl or 'view the sponsored' in dl
                or 'ad verification' in dl or 'invalid token' in dl):
            return {'verification_failed': True}
        if is_ip_cooldown(dl): return {'ip_cooldown': True}
        if 'cooldown' in dl or 'wait' in dl or 'already' in dl:
            sec = parse_cd_alert(d) or extract_cooldown_time(fh) or 6
            return {'cooldown': sec}
        return None
    if a.get('warning'):
        w = a['warning']; wl = w.lower()
        if 'daily limit' in wl or 'all claims' in wl: return {'limit': True}
        if 'verification failed' in wl or 'invalid token' in wl:
            return {'verification_failed': True}
        if is_ip_cooldown(wl): return {'ip_cooldown': True}
        if 'cooldown' in wl or 'wait' in wl:
            sec = parse_cd_alert(w) or extract_cooldown_time(fh) or 6
            return {'cooldown': sec}
        return None
    c = extract_cooldown_time(fh)
    return {'cooldown': c} if c else None

# ==================== CLAIM LOGIC ====================
def login_with_credentials(s, email, pw, retry=3):
    for _ in range(retry):
        try:
            r = request_with_retry(s, 'GET', LOGIN_URL)
            if r is None or r.status_code != 200: continue
            html = r.text
        except Exception: continue
        csrf, _, _, _ = extract_csrf_and_sitekey(html)
        if not csrf: continue
        ik, ifield = solve_icon_captcha(html)
        if ik is None: continue
        payload = {'csrf_token': csrf, 'email': email, 'password': pw}
        if ik and ik != 'no_captcha': payload[ifield] = ik
        s.headers.update({'Referer': LOGIN_URL, 'Origin': BASE_URL})
        try:
            p = request_with_retry(s, 'POST', LOGIN_URL, data=payload, allow_redirects=True)
            if p is None: continue
            if '/dashboard' in p.url: return {'status': 'success'}
            a = extract_alerts(p.text)
            if a.get('danger'):
                if 'not found' in a['danger'].lower(): return {'status': 'not_found', 'msg': a['danger']}
                return {'status': 'failed', 'msg': a['danger']}
            return {'status': 'failed', 'msg': 'Unknown'}
        except Exception: continue
    return {'status': 'error', 'msg': 'Max retries'}

def register_account(s, email, pw, retry=2):
    for _ in range(retry):
        u = ''.join(random.choices(string.ascii_lowercase + string.digits, k=9))
        try:
            r = request_with_retry(s, 'GET', REGISTER_URL)
            if r is None or r.status_code != 200: continue
            html = r.text
        except Exception: continue
        csrf, _, _, _ = extract_csrf_and_sitekey(html)
        if not csrf: continue
        ik, ifield = solve_icon_captcha(html)
        if ik is None: continue
        payload = {'csrf_token': csrf, 'username': u, 'email': email, 'password': pw, 'confirm_password': pw}
        if ik and ik != 'no_captcha': payload[ifield] = ik
        s.headers.update({'Referer': REGISTER_URL, 'Origin': BASE_URL})
        try:
            p = request_with_retry(s, 'POST', REGISTER_URL, data=payload, allow_redirects=True)
            if p is None: continue
            if '/dashboard' in p.url: return True
            a = extract_alerts(p.text)
            if a.get('danger') and ('already' in a['danger'].lower() or 'registered' in a['danger'].lower()):
                return True
        except Exception: continue
    return False

def do_faucet_claim(s, email):
    t0 = time.time()
    try:
        r = request_with_retry(s, 'GET', FAUCET_URL)
        if r is None or r.status_code != 200: return None
        html = r.text
    except Exception: return None
    if check_daily_limit(html): return {'limit': True}
    csrf, _, _, _ = extract_csrf_and_sitekey(html)
    if not csrf: return {'need_login': True}
    ik, ifield = solve_icon_captcha(html)
    if ik is None: return None
    payload = {'csrf_token': csrf}
    if ik != 'no_captcha': payload[ifield] = ik
    elapsed = time.time() - t0
    if elapsed < FAUCET_MIN_WAIT: time.sleep(FAUCET_MIN_WAIT - elapsed)
    s.headers.update({'Referer': FAUCET_URL, 'Origin': BASE_URL})
    return handle_claim_response(s, request_with_retry(s, 'POST', CLAIM_URL, data=payload, allow_redirects=False), email, 'Faucet')

def do_pop_claim(s, email):
    t0 = time.time()
    try:
        r = request_with_retry(s, 'GET', POP_FAUCET_URL)
        if r is None or r.status_code != 200: return None
        html = r.text
    except Exception: return None
    if check_daily_limit(html): return {'limit': True}
    csrf, _, _, _ = extract_csrf_and_sitekey(html)
    if not csrf: return {'need_login': True}
    ik, ifield = solve_icon_captcha(html)
    if ik is None: return None
    payload = {'csrf_token': csrf}
    if ik != 'no_captcha': payload[ifield] = ik
    elapsed = time.time() - t0
    if elapsed < POPUNDER_MIN_WAIT: time.sleep(POPUNDER_MIN_WAIT - elapsed)
    s.headers.update({'Referer': POP_FAUCET_URL, 'Origin': BASE_URL})
    return handle_claim_response(s, request_with_retry(s, 'POST', POP_CLAIM_URL, data=payload, allow_redirects=False), email, 'Pop')

# ==================== WITHDRAW LOGIC ====================
def extract_withdraw_info(html):
    soup = BeautifulSoup(html, 'html.parser')
    ci = soup.find('input', {'name': 'csrf_token'})
    csrf = ci.get('value') if ci else None
    bal = 0.0
    for card in soup.find_all('div', class_='card'):
        ct = card.get_text(" ", strip=True)
        if re.search(r'Available Balance', ct, re.I):
            h4 = card.find('h4', class_=re.compile(r'text-success'))
            if h4:
                m = re.search(r'([\d.]+)', h4.get_text(strip=True))
                if m:
                    try: bal = float(m.group(1)); break
                    except ValueError: pass
    return csrf, bal

def process_withdrawals(s, email):
    try:
        r = request_with_retry(s, 'GET', WITHDRAW_URL)
        if r is None or r.status_code != 200: return False
        csrf, bal = extract_withdraw_info(r.text)
        if not csrf: return False
        
        # Tampilkan saldo ke log
        log_balance(email, bal)
        
        if bal + WITHDRAW_EPS < WITHDRAW_THRESHOLD: return False
            
        ik, ifield = solve_icon_captcha(r.text)
        payload = {'csrf_token': csrf, 'amount': f"{WITHDRAW_THRESHOLD:.8f}"}
        if ik != 'no_captcha': payload[ifield] = ik
        
        s.headers.update({'Referer': WITHDRAW_URL, 'Origin': BASE_URL})
        pr = request_with_retry(s, 'POST', WITHDRAW_REQUEST_URL, data=payload, allow_redirects=True)
        if pr and 'success' in pr.text.lower():
            log_success(f"[💸] {email} WD 0.009 SUKSES! Target Tercapai.")
            return True
    except Exception: pass
    return False

# ==================== THREAD WORKER ====================
def worker(thread_id, q, stop_event):
    port = 9050 + thread_id
    
    while not stop_event.is_set():
        try:
            email = q.get(timeout=3)
        except Empty:
            break
            
        if is_daily_limited(email):
            q.task_done()
            continue
            
        log_info(f"=== [{email}] Memulai di Thread {thread_id} (Port {port}) ===")
        
        # Rotate IP di awal
        rotate_port(port)
        time.sleep(1.5)
        s = create_session(port)
        
        # Login
        r = login_with_credentials(s, email, PASSWORD)
        if r['status'] == 'not_found':
            if register_account(s, email, PASSWORD):
                r = login_with_credentials(s, email, PASSWORD)
                
        if r['status'] != 'success':
            log_error(f"Login Gagal {email}")
            q.task_done()
            continue
            
        wd_success = False
        cnt = 0
        
        # ---- FASE 1: FAUCET ----
        while not stop_event.is_set():
            try:
                res = do_faucet_claim(s, email)
                if res is None: time.sleep(1); continue
                if res.get('limit'):
                    log_info(f"[{email}] Faucet Limit. Beralih ke Popup.")
                    break
                if res.get('need_login'):
                    r2 = login_with_credentials(s, email, PASSWORD)
                    if r2['status'] != 'success': break
                    continue
                if res.get('ip_cooldown'):
                    rotate_port(port)
                    s = create_session(port)
                    r2 = login_with_credentials(s, email, PASSWORD)
                    if r2['status'] != 'success': break
                    continue
                if res.get('cooldown'):
                    time.sleep(res['cooldown'] + 1)
                    continue
                if res.get('verification_failed'):
                    time.sleep(2)
                    continue
                    
                if res.get('amount'):
                    cnt += 1
                    # LOGIKA PENGECEKAN SALDO
                    if cnt % WD_CHECK_EVERY_N_CLAIMS == 0:
                        if process_withdrawals(s, email):
                            wd_success = True
                            break
                            
            except Exception as e:
                log_error(f"[{email}] Faucet error: {e}")
                time.sleep(2)

        # Jika sudah sukses WD di fase Faucet, tidak perlu lanjut ke Popup
        if wd_success:
            log_success(f"=== [{email}] SELESAI (WD via Faucet) ===")
            q.task_done()
            continue
            
        # ---- FASE 2: POPUP ----
        cnt = 0
        while not stop_event.is_set():
            try:
                res = do_pop_claim(s, email)
                if res is None: time.sleep(1); continue
                if res.get('limit'):
                    log_info(f"[{email}] Popup Limit. Cek saldo terakhir...")
                    if process_withdrawals(s, email): wd_success = True
                    break
                if res.get('need_login'):
                    r2 = login_with_credentials(s, email, PASSWORD)
                    if r2['status'] != 'success': break
                    continue
                if res.get('ip_cooldown'):
                    rotate_port(port)
                    s = create_session(port)
                    r2 = login_with_credentials(s, email, PASSWORD)
                    if r2['status'] != 'success': break
                    continue
                if res.get('cooldown'):
                    time.sleep(res['cooldown'] + 1)
                    continue
                if res.get('verification_failed'):
                    time.sleep(2)
                    continue

                if res.get('amount'):
                    cnt += 1
                    # LOGIKA PENGECEKAN SALDO
                    if cnt % WD_CHECK_EVERY_N_CLAIMS == 0:
                        if process_withdrawals(s, email):
                            wd_success = True
                            break
                            
            except Exception as e:
                log_error(f"[{email}] Popup error: {e}")
                time.sleep(2)

        if wd_success:
            log_success(f"=== [{email}] SELESAI (WD via Popup) ===")
        else:
            mark_daily_limited(email)
            log_warning(f"=== [{email}] SELESAI (Gagal / Limit) ===")
            
        q.task_done()

# ==================== MAIN ====================
def main():
    _emit("=" * 65)
    _emit(f"CLAIMX v14.0 — AUTO WD CHECK (Every {WD_CHECK_EVERY_N_CLAIMS} Claims)")
    _emit(f"Alur: Faucet Habis -> Popup Habis -> WD 0.009 -> Pindah Akun")
    _emit("=" * 65)
    
    if not wait_for_tor_ports(list(TOR_INSTANCES.keys()), 120): sys.exit(1)
    
    stop_event = threading.Event()

    while True: # LOOP NONSTOP
        _emit(f"\n[🔄] MEMULAI PUTARAN BARU (Total Akun: {len(EMAILS)})")
        daily_limit_accounts.clear()
        
        q = Queue()
        for e in EMAILS: q.put(e)
        
        threads = []
        for i in range(12): # 12 Threads
            t = threading.Thread(target=worker, args=(i, q, stop_event), daemon=True)
            t.start()
            threads.append(t)
            
        q.join()
        
        for _ in range(12): q.put(None)
        for t in threads: t.join()
        
        _emit("[✓] Putaran selesai. Mengulang dari awal dalam 10 detik...")
        time.sleep(10)

if __name__ == "__main__":
    main()
