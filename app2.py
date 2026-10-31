#!/usr/bin/env python3
"""
Multi-account claimer - BATCH 1
TOR ports: 9050-9052 (3 threads)
Emails: first half
"""

import requests
import re
import time
import random
import string
import threading
import cloudscraper
from bs4 import BeautifulSoup
from colorama import init, Fore, Style
from stem import Signal
from stem.control import Controller

init(autoreset=True)

# ============================================================
# KONFIGURASI
# ============================================================

BASE_URL = "https://claimfree.site"
REFERRAL = "1021"
SITEKEY = "0x4AAAAAAEZUFG95efQw5vdR"

TOR_PORTS = [9050,9051]               # 3 port
CONTROL_PORTS = [10050,10051]        # 3 control port

SOLVER_URLS = [
    
    
    "https://silit.up.railway.app"
]

DEFAULT_PASSWORD = "Qonita1"
MAX_RENEW_RETRY = 5
SOLVER_RETRY_DELAY = 15
RENEW_WAIT = 10
MAX_RELOAD_PER_ATTEMPT = 5
WITHDRAW_MIN_BALANCE = 0.01
MAX_CLAIM_RETRY = 3

# ============================================================
# USER-AGENT DAN HEADER BROWSER NYATA
# ============================================================

USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:109.0) Gecko/20100101 Firefox/121.0",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:109.0) Gecko/20100101 Firefox/120.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.1 Safari/605.1.15",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64; rv:109.0) Gecko/20100101 Firefox/121.0",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/118.0.0.0 Safari/537.36 Edg/118.0.2088.76",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/117.0.0.0 Safari/537.36 OPR/103.0.0.0",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:122.0) Gecko/20100101 Firefox/122.0",
]

def random_user_agent():
    return random.choice(USER_AGENTS)

# ============================================================
# FUNGSI BANTUAN
# ============================================================

def generate_username(email):
    username = email.split('@')[0]
    username = re.sub(r'[^a-zA-Z0-9]', '', username)
    if len(username) > 9:
        username = username[:9]
    if len(username) < 3:
        username += ''.join(random.choices(string.digits, k=3))
    if not username[0].isalpha():
        username = 'u' + username
    return username.lower()

# ============================================================
# TURNSTILE SOLVER (ROUND ROBIN)
# ============================================================

class TurnstileSolver:
    def __init__(self):
        self.current_index = 0

    def solve(self, domain, sitekey):
        if not domain.startswith(('http://', 'https://')):
            domain = f"https://{domain}"
        headers = {"Content-Type": "application/json"}
        payload = {"type": "turnstile", "domain": domain, "siteKey": sitekey}

        for attempt in range(3):
            solver_url = SOLVER_URLS[self.current_index % len(SOLVER_URLS)]
            self.current_index += 1
            try:
                resp = requests.post(f"{solver_url}/solve", headers=headers, json=payload, timeout=60)
                if resp.status_code != 200:
                    continue
                result = resp.json()
                task_id = result.get("taskId")
                if not task_id:
                    continue

                for _ in range(40):
                    time.sleep(4)
                    poll = requests.post(f"{solver_url}/solve", headers=headers, json={"taskId": task_id}, timeout=30)
                    if poll.status_code != 200:
                        continue
                    poll_data = poll.json()
                    if poll_data.get("status") == "done":
                        token = poll_data.get("token") or poll_data.get("solution", {}).get("token")
                        if token:
                            return token
                    elif poll_data.get("status") == "error":
                        break
            except:
                continue
            if attempt < 2:
                time.sleep(SOLVER_RETRY_DELAY)
        return None

# ============================================================
# SESSION TOR dengan cloudscraper + USER-AGENT
# ============================================================

def create_tor_session(port, user_agent=None):
    if user_agent is None:
        user_agent = random_user_agent()
    session = requests.Session()
    session.proxies = {
        'http': f'socks5h://127.0.0.1:{port}',
        'https': f'socks5h://127.0.0.1:{port}'
    }

    scraper = cloudscraper.create_scraper(
        sess=session,
        browser={
            'browser': 'chrome',
            'platform': 'windows',
            'desktop': True,
            'mobile': False
        }
    )

    headers = {
        'User-Agent': user_agent,
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
        'Accept-Language': 'en-US,en;q=0.9',
        'Accept-Encoding': 'gzip, deflate',
        'Connection': 'keep-alive',
        'Upgrade-Insecure-Requests': '1',
        'Sec-Fetch-Dest': 'document',
        'Sec-Fetch-Mode': 'navigate',
        'Sec-Fetch-Site': 'none',
        'Sec-Fetch-User': '?1',
        'Cache-Control': 'max-age=0',
        'Sec-Ch-Ua': '"Not_A Brand";v="8", "Chromium";v="120", "Google Chrome";v="120"',
        'Sec-Ch-Ua-Mobile': '?0',
        'Sec-Ch-Ua-Platform': '"Windows"',
        'Referer': f"{BASE_URL}/?r={REFERRAL}",
        'Origin': BASE_URL,
    }
    scraper.headers.update(headers)
    return scraper

# ============================================================
# TOR MANAGER
# ============================================================

class TorManager:
    def __init__(self):
        self.controllers = {}
        self.used_ips = {}

    def connect_tor_instances(self):
        print(f"{Fore.CYAN}Connecting TOR instances (batch 1)...{Style.RESET_ALL}")
        for socks_port, ctrl_port in zip(TOR_PORTS, CONTROL_PORTS):
            try:
                controller = Controller.from_port(port=ctrl_port)
                controller.authenticate()
                self.controllers[socks_port] = controller
                ip = self.get_current_ip(socks_port)
                self.used_ips[socks_port] = ip
                print(f"{Fore.GREEN}✓ TOR {socks_port} | {ip}{Style.RESET_ALL}")
            except Exception as e:
                print(f"{Fore.RED}✗ TOR {socks_port} failed: {e}{Style.RESET_ALL}")
                self.controllers[socks_port] = None
        time.sleep(2)

    def get_current_ip(self, socks_port):
        try:
            session = requests.Session()
            session.proxies = {'http': f'socks5h://127.0.0.1:{socks_port}', 'https': f'socks5h://127.0.0.1:{socks_port}'}
            resp = session.get('https://checkip.amazonaws.com', timeout=10)
            if resp.status_code == 200:
                return resp.text.strip()
            return "Unknown"
        except:
            return "Unknown"

    def renew_identity(self, socks_port):
        try:
            controller = self.controllers.get(socks_port)
            if controller:
                controller.signal(Signal.NEWNYM)
                time.sleep(3)
                new_ip = self.get_current_ip(socks_port)
                old_ip = self.used_ips.get(socks_port, "Unknown")
                self.used_ips[socks_port] = new_ip
                return old_ip, new_ip
        except Exception as e:
            pass
        return "Unknown", "Unknown"

    def close(self):
        for ctrl in self.controllers.values():
            try:
                if ctrl:
                    ctrl.close()
            except:
                pass

# ============================================================
# AKUN WORKER (dengan retry claim 3x + refresh)
# ============================================================

class AccountWorker:
    def __init__(self, email, password, socks_port, tor_manager, thread_id):
        self.email = email
        self.password = password
        self.username = generate_username(email)
        self.socks_port = socks_port
        self.tor_manager = tor_manager
        self.thread_id = thread_id
        self.user_agent = random_user_agent()
        self.session = create_tor_session(socks_port, self.user_agent)
        self.logged_in = False
        self.csrf_token = None
        self.current_ip = tor_manager.used_ips.get(socks_port, "Unknown")
        self.renew_count = 0
        self.solver = TurnstileSolver()
        self.cooldowns = {
            'free': 0,
            'vip': 0,
            'lucky': 0,
            'fortune': 0
        }
        self.email_registered = False

    def log(self, msg, color=Fore.WHITE):
        print(f"{color}[{self.email}] {msg}{Style.RESET_ALL}")

    def random_delay(self, min_sec=1.5, max_sec=4.0):
        time.sleep(random.uniform(min_sec, max_sec))

    # ------------------------------------------------------------
    # DETEKSI PERLU RELOGIN
    # ------------------------------------------------------------
    def is_login_required(self, response_text):
        indicators = [
            'Invalid Captcha',
            'Please complete verification',
            'login',
            'Login',
            'Session expired',
            'session expired',
            'Unauthorized',
            '401',
            '403',
            'You need to login',
            'Silakan login',
            'redirected to login',
            'not logged in'
        ]
        lower_text = response_text.lower()
        for ind in indicators:
            if ind.lower() in lower_text:
                return True
        return False

    # ------------------------------------------------------------
    # LOGIN DENGAN RETRY (exponential backoff)
    # ------------------------------------------------------------
    def login_with_retry(self, max_retries=5, base_delay=5):
        for attempt in range(1, max_retries + 1):
            if attempt > 1:
                self.renew_ip()
            self.user_agent = random_user_agent()
            self.session = create_tor_session(self.socks_port, self.user_agent)
            self.csrf_token = None
            self.logged_in = False

            if self.login():
                return True

            if attempt < max_retries:
                wait_time = base_delay * (2 ** (attempt - 1))
                self.log(f"Waiting {wait_time}s before next login attempt", Fore.YELLOW)
                time.sleep(wait_time)
        return False

    def login(self):
        try:
            login_page = self.session.get(f"{BASE_URL}/auth/login")
            if login_page.status_code != 200:
                return False
            html = login_page.text
        except:
            return False

        soup = BeautifulSoup(html, 'html.parser')
        csrf_input = soup.find('input', {'name': 'csrf_token_name'})
        if csrf_input and csrf_input.get('value'):
            self.csrf_token = csrf_input['value']
        else:
            return False

        token = self.solver.solve("claimfree.site", SITEKEY)
        if not token:
            return False

        data = {
            'csrf_token_name': self.csrf_token,
            'email': self.email,
            'password': self.password,
            'cf-turnstile-response': token
        }

        try:
            resp = self.session.post(f"{BASE_URL}/auth/login", data=data, allow_redirects=True)
            if 'dashboard' in resp.url:
                self.logged_in = True
                self.csrf_token = self.session.cookies.get('csrf_cookie_name')
                self.log("✅ Login success", Fore.GREEN)
                return True

            # alternate field
            data['turnstile'] = data.pop('cf-turnstile-response')
            resp2 = self.session.post(f"{BASE_URL}/auth/login", data=data, allow_redirects=True)
            if 'dashboard' in resp2.url:
                self.logged_in = True
                self.csrf_token = self.session.cookies.get('csrf_cookie_name')
                self.log("✅ Login success (alt field)", Fore.GREEN)
                return True

            # cek error captcha
            error_match = re.search(r'<div[^>]*class="alert[^"]*"[^>]*>(.*?)</div>', resp.text, re.DOTALL)
            if error_match and "Invalid Captcha" in error_match.group(1):
                return False
            return False
        except:
            return False

    # ------------------------------------------------------------
    # REGISTER (jika login gagal karena akun belum ada)
    # ------------------------------------------------------------
    def register(self):
        self.log("Registering...", Fore.CYAN)
        for attempt in range(3):
            if attempt > 0:
                time.sleep(3)
            try:
                html = self.session.get(f"{BASE_URL}/register").text
                if not html:
                    continue
                csrf_match = re.search(r'name="csrf_token_name"\s+value="([^"]+)"', html)
                if not csrf_match:
                    continue
                csrf = csrf_match.group(1)

                token = self.solver.solve("claimfree.site", SITEKEY)
                if not token:
                    continue

                data = {
                    'csrf_token_name': csrf,
                    'email': self.email,
                    'username': self.username,
                    'password': self.password,
                    'confirm_password': self.password,
                    'cf-turnstile-response': token
                }

                resp = self.session.post(f"{BASE_URL}/auth/register", data=data, allow_redirects=True)
                if 'dashboard' in resp.url:
                    self.logged_in = True
                    self.csrf_token = self.session.cookies.get('csrf_cookie_name')
                    self.log(f"✅ Register success ({self.username})", Fore.GREEN)
                    return True
                else:
                    error_match = re.search(r'<div[^>]*class="alert[^"]*"[^>]*>(.*?)</div>', resp.text, re.DOTALL)
                    if error_match and ("This email is registered" in error_match.group(1) or "already registered" in error_match.group(1).lower()):
                        self.log("Email already registered", Fore.YELLOW)
                        self.email_registered = True
                        return False
            except:
                continue
        return False

    # ------------------------------------------------------------
    # ENSURE LOGGED IN
    # ------------------------------------------------------------
    def ensure_logged_in(self):
        if self.logged_in:
            try:
                resp = self.session.get(f"{BASE_URL}/dashboard", timeout=10)
                if resp.status_code == 200 and 'dashboard' in resp.url:
                    return True
                else:
                    self.logged_in = False
            except:
                self.logged_in = False

        self.log("Session expired, relogin...", Fore.YELLOW)
        return self.login_with_retry()

    # ------------------------------------------------------------
    # RENEW IP (refresh data)
    # ------------------------------------------------------------
    def renew_ip(self):
        old_ip, new_ip = self.tor_manager.renew_identity(self.socks_port)
        self.current_ip = new_ip
        self.log(f"IP renewed: {old_ip} -> {new_ip}", Fore.CYAN)
        self.user_agent = random_user_agent()
        self.session = create_tor_session(self.socks_port, self.user_agent)
        time.sleep(RENEW_WAIT)
        self.logged_in = False
        self.csrf_token = None

    # ------------------------------------------------------------
    # AMBIL PAGE DENGAN RETRY
    # ------------------------------------------------------------
    def get_page_with_retry(self, url, max_retries=3):
        for attempt in range(max_retries):
            self.random_delay(1.0, 2.5)
            try:
                resp = self.session.get(url, timeout=15)
                if resp.status_code != 200:
                    continue
                return resp.text
            except:
                time.sleep(2)
        return None

    # ------------------------------------------------------------
    # GET CSRF dari HTML
    # ------------------------------------------------------------
    def get_csrf_from_page_html(self, html):
        csrf_match = re.search(r'name="csrf_token_name"\s+value="([^"]+)"', html)
        if csrf_match:
            return csrf_match.group(1)
        return self.session.cookies.get('csrf_cookie_name')

    def get_csrf_from_page(self, url):
        html = self.get_page_with_retry(url)
        if not html:
            return None
        return self.get_csrf_from_page_html(html)

    # ------------------------------------------------------------
    # EXTRACT TIMER & REWARD
    # ------------------------------------------------------------
    def extract_timer(self, html, var_names):
        for var in var_names:
            patterns = [
                rf'var\s+{var}\s*=\s*(\d+);',
                rf'let\s+{var}\s*=\s*(\d+);',
                rf'const\s+{var}\s*=\s*(\d+);',
                rf'{var}\s*=\s*(\d+);',
            ]
            for pat in patterns:
                match = re.search(pat, html, re.IGNORECASE)
                if match:
                    val = int(match.group(1))
                    if val >= 0:
                        return val
        # fallback
        patterns = [
            r'<span\s+id="m"[^>]*>\s*(\d+)\s*</span>.*?<span\s+id="s"[^>]*>\s*(\d+)\s*</span>',
            r'Next Free Roll In[^:]*:\s*(\d+)\s*:\s*(\d+)',
            r'Time left to claim[^:]*:\s*(\d+)\s*:\s*(\d+)',
            r'Time left[^:]*:\s*(\d+)\s*:\s*(\d+)',
        ]
        for pat in patterns:
            match = re.search(pat, html, re.IGNORECASE | re.DOTALL)
            if match:
                if len(match.groups()) == 1:
                    return int(match.group(1))
                elif len(match.groups()) >= 2:
                    mins = int(match.group(1))
                    secs = int(match.group(2))
                    return mins * 60 + secs
        return 0

    def extract_reward(self, html):
        usd = None
        bully = None
        usd_patterns = [
            r'\+\$([0-9.]+)\s*USD',
            r'\+\$([0-9.]+)\s*</small>',
            r'\+\$([0-9.]+)',
        ]
        for pat in usd_patterns:
            m = re.search(pat, html)
            if m:
                usd = m.group(1)
                break

        bully_patterns = [
            r'\+([0-9,]+)\s*🐂',
            r'\+([0-9,]+)\s*\$BULLY',
            r'\+([0-9,]+)\s*BULLY',
        ]
        for pat in bully_patterns:
            m = re.search(pat, html, re.IGNORECASE)
            if m:
                bully = m.group(1).replace(',', '')
                break

        usd = usd if usd else '0.00000'
        bully = bully if bully else '0'
        return usd, bully

    def is_claimed(self, html):
        indicators = [
            'Reward Claimed!',
            'freeClaimModal',
            'vip-modal-content',
            'VIP & BULLY Claimed!',
            'Claimed!',
            'Successfully added',
            'Berhasil!'
        ]
        return any(ind in html for ind in indicators)

    def set_cooldown(self, claim_type, seconds):
        if seconds > 0:
            self.cooldowns[claim_type] = time.time() + seconds

    def get_cooldown_remaining(self, claim_type):
        remaining = self.cooldowns.get(claim_type, 0) - time.time()
        return max(0, int(remaining))

    # ------------------------------------------------------------
    # CLAIM FUNCTIONS DENGAN RETRY 3X + RENEW IP
    # ------------------------------------------------------------
    def claim_free_faucet(self):
        remaining = self.get_cooldown_remaining('free')
        if remaining > 0:
            self.log(f"Free cooldown {remaining//60}:{remaining%60:02d} left", Fore.YELLOW)
            return False

        for attempt in range(MAX_CLAIM_RETRY):
            if attempt > 0:
                self.log(f"Free claim retry {attempt+1}/{MAX_CLAIM_RETRY}", Fore.YELLOW)
                self.renew_ip()
                if not self.ensure_logged_in():
                    continue

            html = self.get_page_with_retry(f"{BASE_URL}/freefaucet")
            if not html:
                continue

            if self.is_login_required(html):
                if not self.ensure_logged_in():
                    continue
                html = self.get_page_with_retry(f"{BASE_URL}/freefaucet")
                if not html:
                    continue

            if self.is_claimed(html):
                usd, bully = self.extract_reward(html)
                self.log(f"Already claimed +${usd} + {bully} BULLY", Fore.GREEN)
                timer = self.extract_timer(html, ['freeWaitTime'])
                if timer > 0:
                    self.set_cooldown('free', timer)
                return True

            timer = self.extract_timer(html, ['freeWaitTime'])
            if timer > 0:
                self.set_cooldown('free', timer)
                return False

            if 'btn-claim-free' not in html and 'Claim 0.00010' not in html:
                self.log("Free faucet not ready (button not found)", Fore.YELLOW)
                return False

            token = self.solver.solve("claimfree.site", SITEKEY)
            if not token:
                continue

            csrf = self.get_csrf_from_page_html(html)
            if not csrf:
                continue

            data = {'csrf_token_name': csrf, 'cf-turnstile-response': token}
            try:
                resp = self.session.post(f"{BASE_URL}/freefaucet/claim", data=data, allow_redirects=True)
                html = resp.text
                if self.is_claimed(html):
                    usd, bully = self.extract_reward(html)
                    self.log(f"✅ Free claimed +${usd} + {bully} BULLY", Fore.GREEN)
                    timer = self.extract_timer(html, ['freeWaitTime'])
                    if timer > 0:
                        self.set_cooldown('free', timer)
                    return True
                else:
                    if self.is_login_required(html):
                        self.log("Claim failed due to login required", Fore.RED)
                        continue
                    self.log("Free claim failed (unknown reason)", Fore.RED)
                    continue
            except Exception as e:
                self.log(f"Free claim exception: {e}", Fore.RED)
                continue
        return False

    def claim_vip_faucet(self):
        remaining = self.get_cooldown_remaining('vip')
        if remaining > 0:
            self.log(f"VIP cooldown {remaining//60}:{remaining%60:02d} left", Fore.YELLOW)
            return False

        for attempt in range(MAX_CLAIM_RETRY):
            if attempt > 0:
                self.log(f"VIP claim retry {attempt+1}/{MAX_CLAIM_RETRY}", Fore.YELLOW)
                self.renew_ip()
                if not self.ensure_logged_in():
                    continue

            html = self.get_page_with_retry(f"{BASE_URL}/vipfaucet")
            if not html:
                continue

            if self.is_login_required(html):
                if not self.ensure_logged_in():
                    continue
                html = self.get_page_with_retry(f"{BASE_URL}/vipfaucet")
                if not html:
                    continue

            timer = self.extract_timer(html, ['waitTime'])
            if timer > 0:
                self.set_cooldown('vip', timer)
                return False

            has_button = 'Claim USD' in html or 'btn-claim-vip' in html or 'Claim USD + 50 $BULLY Now' in html
            if not has_button:
                if self.is_claimed(html):
                    usd, bully = self.extract_reward(html)
                    self.log(f"Already claimed VIP +${usd} + {bully} BULLY", Fore.MAGENTA)
                    self.set_cooldown('vip', 3600)
                    return True
                else:
                    self.log("VIP not ready", Fore.YELLOW)
                    return False

            token = self.solver.solve("claimfree.site", SITEKEY)
            if not token:
                continue

            csrf = self.get_csrf_from_page_html(html)
            if not csrf:
                continue

            data = {'csrf_token_name': csrf, 'cf-turnstile-response': token}
            try:
                resp = self.session.post(f"{BASE_URL}/vipfaucet/claim", data=data, allow_redirects=True)
                html = resp.text
                if self.is_claimed(html):
                    usd, bully = self.extract_reward(html)
                    self.log(f"✅ VIP claimed +${usd} + {bully} BULLY", Fore.MAGENTA)
                    self.set_cooldown('vip', 3600)
                    return True
                else:
                    if self.is_login_required(html):
                        self.log("VIP claim failed due to login required", Fore.RED)
                        continue
                    self.log("VIP claim failed", Fore.RED)
                    continue
            except Exception as e:
                self.log(f"VIP claim exception: {e}", Fore.RED)
                continue
        return False

    def roll_lucky_number(self):
        remaining = self.get_cooldown_remaining('lucky')
        if remaining > 0:
            self.log(f"Lucky cooldown {remaining//60}:{remaining%60:02d} left", Fore.YELLOW)
            return False

        for attempt in range(MAX_CLAIM_RETRY):
            if attempt > 0:
                self.log(f"Lucky roll retry {attempt+1}/{MAX_CLAIM_RETRY}", Fore.YELLOW)
                self.renew_ip()
                if not self.ensure_logged_in():
                    continue

            html = self.get_page_with_retry(f"{BASE_URL}/luckyroll")
            if not html:
                continue

            if self.is_login_required(html):
                if not self.ensure_logged_in():
                    continue
                html = self.get_page_with_retry(f"{BASE_URL}/luckyroll")
                if not html:
                    continue

            timer = self.extract_timer(html, ['timeLeft'])
            if timer > 0:
                self.set_cooldown('lucky', timer)
                return False

            csrf = self.get_csrf_from_page_html(html)
            if not csrf:
                continue

            token = self.solver.solve("claimfree.site", SITEKEY)
            if not token:
                continue

            data = {'csrf_token_name': csrf, 'cf-turnstile-response': token}
            try:
                resp = self.session.post(f"{BASE_URL}/luckyroll/spin", data=data, allow_redirects=True)
                content_type = resp.headers.get('content-type', '')
                if 'application/json' in content_type:
                    result = resp.json()
                    if result.get('status') == 'success':
                        self.log(f"✅ Lucky roll: {result.get('lucky_number')} +${result.get('usd_reward')} + {result.get('bully_reward')} BULLY", Fore.GREEN)
                        timer = result.get('cooldown', 0)
                        if timer > 0:
                            self.set_cooldown('lucky', timer)
                        return True
                    else:
                        self.log(f"Lucky failed: {result.get('message', 'unknown')}", Fore.RED)
                        if self.is_login_required(resp.text):
                            continue
                        return False
                else:
                    html2 = resp.text
                    timer2 = self.extract_timer(html2, ['timeLeft'])
                    if timer2 > 0:
                        self.set_cooldown('lucky', timer2)
                        return False
                    if self.is_login_required(html2):
                        continue
                    self.log("Lucky roll response not JSON", Fore.RED)
                    return False
            except Exception as e:
                self.log(f"Lucky roll exception: {e}", Fore.RED)
                continue
        return False

    def spin_fortune_wheel(self):
        remaining = self.get_cooldown_remaining('fortune')
        if remaining > 0:
            self.log(f"Fortune cooldown {remaining//60}:{remaining%60:02d} left", Fore.YELLOW)
            return False

        for attempt in range(MAX_CLAIM_RETRY):
            if attempt > 0:
                self.log(f"Fortune spin retry {attempt+1}/{MAX_CLAIM_RETRY}", Fore.YELLOW)
                self.renew_ip()
                if not self.ensure_logged_in():
                    continue

            html = self.get_page_with_retry(f"{BASE_URL}/fortune")
            if not html:
                continue

            if self.is_login_required(html):
                if not self.ensure_logged_in():
                    continue
                html = self.get_page_with_retry(f"{BASE_URL}/fortune")
                if not html:
                    continue

            timer = self.extract_timer(html, ['timeLeft'])
            if timer > 0:
                self.set_cooldown('fortune', timer)
                return False

            csrf = self.get_csrf_from_page_html(html)
            if not csrf:
                continue

            token = self.solver.solve("claimfree.site", SITEKEY)
            if not token:
                continue

            data = {'csrf_token_name': csrf, 'cf-turnstile-response': token}
            try:
                resp = self.session.post(f"{BASE_URL}/fortune/spin", data=data, allow_redirects=True)
                content_type = resp.headers.get('content-type', '')
                if 'application/json' in content_type:
                    result = resp.json()
                    if result.get('status') == 'success':
                        self.log(f"✅ Fortune spin: +${result.get('usd_reward')} + {result.get('bully_reward')} BULLY", Fore.GREEN)
                        timer = result.get('cooldown', 0)
                        if timer > 0:
                            self.set_cooldown('fortune', timer)
                        return True
                    else:
                        self.log(f"Fortune failed: {result.get('message', 'unknown')}", Fore.RED)
                        if self.is_login_required(resp.text):
                            continue
                        return False
                else:
                    html2 = resp.text
                    timer2 = self.extract_timer(html2, ['timeLeft'])
                    if timer2 > 0:
                        self.set_cooldown('fortune', timer2)
                        return False
                    if self.is_login_required(html2):
                        continue
                    self.log("Fortune spin response not JSON", Fore.RED)
                    return False
            except Exception as e:
                self.log(f"Fortune spin exception: {e}", Fore.RED)
                continue
        return False

    # ------------------------------------------------------------
    # WITHDRAW (tanpa retry, hanya sekali)
    # ------------------------------------------------------------
    def get_withdraw_balance(self):
        if not self.logged_in:
            return None
        try:
            html = self.get_page_with_retry(f"{BASE_URL}/withdraw")
            if not html:
                return None
            match = re.search(r'Available:\s*<b[^>]*>\s*\$([0-9.]+)\s*USD', html)
            if match:
                return float(match.group(1))
            return None
        except:
            return None

    def withdraw(self):
        balance = self.get_withdraw_balance()
        if balance is None:
            return False
        if balance <= WITHDRAW_MIN_BALANCE:
            self.log(f"Balance ${balance:.6f} <= {WITHDRAW_MIN_BALANCE}, skip", Fore.YELLOW)
            return False

        self.log(f"Withdrawing ${balance:.6f} to {self.email}", Fore.GREEN)
        csrf = self.get_csrf_from_page(f"{BASE_URL}/withdraw")
        if not csrf:
            return False

        data = {
            'csrf_token_name': csrf,
            'method': '1',
            'amount': f"{balance:.6f}",
            'wallet': self.email
        }
        try:
            resp = self.session.post(f"{BASE_URL}/withdraw/submit", data=data, allow_redirects=True)
            if resp.status_code in (200, 302):
                if 'success' in resp.text.lower() or 'withdrawal' in resp.text.lower() or 'pending' in resp.text.lower():
                    self.log(f"✅ Withdraw ${balance:.6f} sent", Fore.GREEN)
                    return True
                else:
                    error_match = re.search(r'<div[^>]*class="alert[^"]*"[^>]*>(.*?)</div>', resp.text, re.DOTALL)
                    if error_match:
                        self.log(f"Withdraw error: {error_match.group(1).strip()}", Fore.RED)
                    else:
                        self.log("Withdraw failed", Fore.RED)
                    return False
            else:
                self.log(f"Withdraw failed (status {resp.status_code})", Fore.RED)
                return False
        except Exception as e:
            self.log(f"Withdraw exception: {e}", Fore.RED)
            return False

    # ------------------------------------------------------------
    # RUN: satu siklus penuh (login/register → claim semua → withdraw)
    # ------------------------------------------------------------
    def run(self):
        self.current_ip = self.tor_manager.get_current_ip(self.socks_port)

        if not self.login_with_retry():
            if not self.register():
                if not self.login_with_retry():
                    self.log("Failed to login/register, skipping", Fore.RED)
                    return

        self.claim_free_faucet()
        self.claim_vip_faucet()
        self.roll_lucky_number()
        self.spin_fortune_wheel()
        self.withdraw()

        self.log("Cycle complete.", Fore.CYAN)

# ============================================================
# MULTI-THREADING ENGINE (ROUND-ROBIN) - BATCH 1
# ============================================================

class MultiAccountClaimer:
    def __init__(self, emails, password=DEFAULT_PASSWORD):
        self.emails = emails
        self.password = password
        self.tor_manager = TorManager()
        self.threads = []
        self.running = True
        self.lock = threading.Lock()
        self.email_index = 0

    def start(self):
        self.tor_manager.connect_tor_instances()

        for i in range(len(TOR_PORTS)):  # 3 threads
            socks_port = TOR_PORTS[i]
            t = threading.Thread(target=self.worker_loop, args=(socks_port, i), daemon=True)
            t.start()
            self.threads.append(t)
            print(f"{Fore.CYAN}Thread {i+1} started (port {socks_port}){Style.RESET_ALL}")

        try:
            while self.running:
                time.sleep(1)
        except KeyboardInterrupt:
            self.stop()

    def worker_loop(self, socks_port, thread_id):
        while self.running:
            with self.lock:
                if self.email_index >= len(self.emails):
                    self.email_index = 0
                email = self.emails[self.email_index]
                self.email_index += 1

            print(f"{Fore.CYAN}[{thread_id}] Processing {email}{Style.RESET_ALL}")
            worker = AccountWorker(email, self.password, socks_port, self.tor_manager, thread_id)
            worker.run()
            time.sleep(5)

    def stop(self):
        self.running = False
        self.tor_manager.close()
        for t in self.threads:
            t.join(timeout=2)

# ============================================================
# MAIN - BATCH 1 (first half of emails)
# ============================================================

def main():
    print(f"{Fore.CYAN}╔{'═'*48}╗{Style.RESET_ALL}")
    print(f"{Fore.CYAN}║  MULTI-ACCOUNT CLAIMER - BATCH 1      ║{Style.RESET_ALL}")
    print(f"{Fore.CYAN}╚{'═'*48}╝{Style.RESET_ALL}\n")

    # Daftar email lengkap (sama seperti asli)
    full_emails = [
        
        "gigihlazim7@gmail.com",
        "gigihlazim8@gmail.com",
        "gigihlazim9@gmail.com",
        "gi2h27@gmail.com",
        "gi2h270@gmail.com",
        "gi2h2701@gmail.com",
        "gi2h27010@gmail.com",
        "gi2h27012@gmail.com",
        "gi2h27013@gmail.com",
        "gi2h27015@gmail.com",
        "gi2h27018@gmail.com",
        "gi2h2702@gmail.com",
        "gi2h2703@gmail.com",
        "gi2h2704@gmail.com",
        "gi2h2705@gmail.com",
        "gi2h2706@gmail.com",
        "gi2h2709@gmail.com",
        "gi2h2720@gmail.com",
        "gi2h370@gmail.com"
    
        
        
    ]

    # Ambil separuh pertama
    half = len(full_emails) // 2
    emails = full_emails[:half]

    print(f"{Fore.YELLOW}Emails in batch 1: {len(emails)}{Style.RESET_ALL}")
    print(f"{Fore.YELLOW}Threads: {len(TOR_PORTS)}{Style.RESET_ALL}\n")

    claimer = MultiAccountClaimer(emails, DEFAULT_PASSWORD)
    try:
        claimer.start()
    except KeyboardInterrupt:
        print(f"\n{Fore.CYAN}Stopped{Style.RESET_ALL}")
        claimer.stop()

if __name__ == "__main__":
    main()
