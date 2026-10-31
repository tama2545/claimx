#!/usr/bin/env python3
"""
LTCHash - Login/Register + Withdrawal Auto-Submit
Menggunakan proxy residential dengan pengecekan IP dan retry cerdas.
"""

import asyncio
import json
import os
import re
import random
import time
from urllib.parse import urlparse
from bs4 import BeautifulSoup
from colorama import init, Fore
from playwright.async_api import async_playwright, TimeoutError as PlaywrightTimeoutError

init(autoreset=True)

# ============================================================
# CONFIG
# ============================================================
BASE_URL = "https://ltchash.site"
HOME_URL = f"{BASE_URL}/"
ACCOUNT_URL = f"{BASE_URL}/account"
EMAIL_FILE = "emailscrap.txt"
CHROME_BIN = os.getenv("CHROME_BIN", "/usr/bin/google-chrome")
HEADLESS = True
PAGE_TIMEOUT = 45000
WITHDRAW_THRESHOLD = 0.00001
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/120.0.0.0 Safari/537.36"
)

DRY_RUN = False
HUMAN_DELAY_MIN = 0.1
HUMAN_DELAY_MAX = 0.4
MOUSE_STEPS = 8

LOOP_WAIT_HOURS = 5
LOOP_WAIT_SECONDS = LOOP_WAIT_HOURS * 3600

MAX_RETRIES_PER_EMAIL = 15  # maksimal retry
MIN_RETRIES = 10            # minimal retry sebelum skip
RETRY_DELAY_BASE = 60       # detik untuk delay normal
RETRY_DELAY_VPN = 600       # 10 menit jika terdeteksi VPN
REFERRAL_CODE = "757939840"

# ============================================================
# PROXY RESIDENTIAL
# ============================================================
PROXY_URL = "http://c45a1e9e3ec2de25-sess-zf3rxixu-life-600:ebefef8d2ac02138@gate-eu.vaultproxies.com:80"

def parse_proxy(url):
    parsed = urlparse(url)
    if parsed.username and parsed.password:
        return {
            "server": f"{parsed.scheme}://{parsed.hostname}:{parsed.port}",
            "username": parsed.username,
            "password": parsed.password
        }
    else:
        return {"server": url}

PROXY_CONFIG = parse_proxy(PROXY_URL)

# ============================================================
# LOG
# ============================================================
def ok(msg):
    print(f"{Fore.GREEN}[OK] {msg}")

def warn(msg):
    print(f"{Fore.YELLOW}[WARN] {msg}")

def error(msg):
    print(f"{Fore.RED}[ERROR] {msg}")

def log_status(msg):
    print(f"{Fore.CYAN}[STATUS] {msg}")

# ============================================================
# FUNGSI BANTU
# ============================================================
def load_emails():
    if not os.path.exists(EMAIL_FILE):
        raise FileNotFoundError(f"{EMAIL_FILE} tidak ditemukan")
    result = []
    with open(EMAIL_FILE, "r", encoding="utf-8") as f:
        for line in f:
            email = line.strip()
            if not email or "@" not in email:
                continue
            result.append(email)
    return result

def generate_username(email):
    name = email.split("@", 1)[0]
    username = re.sub(r"[^a-zA-Z0-9]", "", name)
    username = username[:20]
    if not username:
        username = "user"
    return username

def get_balance(html):
    if not html:
        return None
    soup = BeautifulSoup(html, "html.parser")
    selectors = ["#statAvailableBalance", "#dashUserBalance"]
    for selector in selectors:
        el = soup.select_one(selector)
        if not el:
            continue
        text = el.get_text(" ", strip=True)
        match = re.search(r"(\d+(?:\.\d+)?)\s*LTC", text, re.I)
        if match:
            try:
                return float(match.group(1))
            except:
                pass
    text = soup.get_text(" ", strip=True)
    match = re.search(r"Available\s+Balance.*?(\d+(?:\.\d+)?)\s*LTC", text, re.I)
    if match:
        try:
            return float(match.group(1))
        except:
            pass
    return None

def dashboard_logged_in(html):
    if not html:
        return False
    soup = BeautifulSoup(html, "html.parser")
    text = soup.get_text(" ", strip=True).lower()
    has_welcome = "welcome back" in text
    has_balance_element = bool(soup.select_one("#statAvailableBalance") or soup.select_one("#dashUserBalance"))
    balance = get_balance(html)
    has_balance = (balance is not None)
    return has_welcome and has_balance_element and has_balance

async def launch_browser(playwright):
    if not os.path.exists(CHROME_BIN):
        raise RuntimeError(f"Chrome tidak ditemukan: {CHROME_BIN}")
    browser = await playwright.chromium.launch(
        headless=HEADLESS,
        executable_path=CHROME_BIN,
        args=[
            "--no-sandbox",
            "--disable-setuid-sandbox",
            "--disable-dev-shm-usage",
            "--disable-gpu",
            "--disable-software-rasterizer",
            "--no-first-run",
            "--no-default-browser-check",
        ]
    )
    return browser

async def create_page_with_proxy(browser):
    context_options = {
        "viewport": {"width": 1280, "height": 720},
        "user_agent": USER_AGENT,
        "locale": "en-US",
        "timezone_id": "Asia/Jakarta"
    }
    if PROXY_CONFIG:
        context_options["proxy"] = PROXY_CONFIG
    context = await browser.new_context(**context_options)
    page = await context.new_page()
    page.set_default_timeout(PAGE_TIMEOUT)
    return context, page

async def get_current_ip(page):
    """Ambil IP saat ini melalui ipify atau httpbin."""
    try:
        await page.goto("https://api.ipify.org?format=json", timeout=10000)
        content = await page.content()
        match = re.search(r'\{.*\}', content, re.DOTALL)
        if match:
            data = json.loads(match.group())
            return data.get('ip')
    except:
        pass
    return None

async def human_click(page, locator, force=False, delay_before=None, delay_after=None):
    if not force:
        try:
            await locator.wait_for(state="visible", timeout=5000)
        except:
            force = True
    try:
        box = await locator.bounding_box()
        if not box:
            await locator.click(force=force)
            return
    except:
        await locator.click(force=force)
        return

    offset_x = random.uniform(0.1, 0.9)
    offset_y = random.uniform(0.1, 0.9)
    target_x = box["x"] + box["width"] * offset_x
    target_y = box["y"] + box["height"] * offset_y

    current_pos = await page.evaluate("() => ({ x: window.mouseX || 0, y: window.mouseY || 0 })")
    start_x = current_pos.get("x", 0)
    start_y = current_pos.get("y", 0)

    if start_x == 0 and start_y == 0:
        viewport = page.viewport_size
        start_x = viewport["width"] // 2
        start_y = viewport["height"] // 2

    steps = MOUSE_STEPS
    for step in range(1, steps + 1):
        t = step / steps
        ease = t * t * (3 - 2 * t)
        x = start_x + (target_x - start_x) * ease
        y = start_y + (target_y - start_y) * ease
        await page.mouse.move(x, y)
        await asyncio.sleep(random.uniform(0.01, 0.03))

    if delay_before is None:
        delay_before = random.uniform(HUMAN_DELAY_MIN, HUMAN_DELAY_MAX)
    else:
        delay_before = random.uniform(delay_before * 0.8, delay_before * 1.2)
    await asyncio.sleep(delay_before)

    await page.mouse.click(target_x, target_y)

    if delay_after is None:
        delay_after = random.uniform(HUMAN_DELAY_MIN, HUMAN_DELAY_MAX)
    else:
        delay_after = random.uniform(delay_after * 0.8, delay_after * 1.2)
    await asyncio.sleep(delay_after)

    await page.evaluate(f"window.mouseX = {target_x}; window.mouseY = {target_y}")

# ============================================================
# LOGIN VIA PLAYWRIGHT (dengan deteksi banned & VPN)
# ============================================================
async def playwright_login(page, email, referral=REFERRAL_CODE):
    try:
        # Buka halaman utama
        await page.goto(HOME_URL, wait_until="domcontentloaded", timeout=PAGE_TIMEOUT)
        await asyncio.sleep(random.uniform(1, 2))

        # Buka modal login
        trigger_selectors = [
            "button.open-login-trigger",
            ".open-login-trigger",
            "button:has-text('Start Mining')",
            "button:has-text('Launch Console')",
        ]
        trigger = None
        for sel in trigger_selectors:
            loc = page.locator(sel)
            if await loc.count() > 0:
                trigger = loc.first
                break
        if trigger:
            await human_click(page, trigger)
            await asyncio.sleep(random.uniform(0.5, 1))

        # Tunggu input email muncul
        try:
            await page.wait_for_selector("#heroLoginInput", timeout=10000)
        except PlaywrightTimeoutError:
            # Mungkin modal tidak terbuka, coba reload
            await page.reload()
            await asyncio.sleep(1)
            if trigger:
                await human_click(page, trigger)
                await asyncio.sleep(1)
            await page.wait_for_selector("#heroLoginInput", timeout=10000)

        email_input = page.locator("#heroLoginInput")
        await email_input.fill(email)
        await asyncio.sleep(random.uniform(0.2, 0.5))

        # Isi referral
        await page.evaluate(f"document.querySelector('input[name=\"ref_id\"]').value = '{referral}'")

        start_btn = page.locator("#startBtn")
        await human_click(page, start_btn)

        # Tunggu beberapa detik untuk response
        await asyncio.sleep(3)

        # Cek banned di seluruh halaman
        html = await page.content()
        if re.search(r"account has been banned|your account has been banned", html, re.I):
            return False, None, "BANNED"
        if re.search(r"vpn detected|proxy detected|vpn not allowed", html, re.I):
            return False, None, "VPN_DETECTED"

        # Cek apakah ada redirect ke account atau my-withdrawals
        if "/account" in page.url or "/my-withdrawals" in page.url:
            await asyncio.sleep(random.uniform(1, 2))
            html = await page.content()
            if re.search(r"account has been banned|your account has been banned", html, re.I):
                return False, None, "BANNED"
            if re.search(r"vpn detected|proxy detected|vpn not allowed", html, re.I):
                return False, None, "VPN_DETECTED"
            if dashboard_logged_in(html) or "welcome back" in html.lower():
                return True, html, None

        # Cek username setup
        if await page.locator("text=Username").count() > 0:
            username = generate_username(email)
            username_input = page.locator("input[wire\\:model='username']")
            if await username_input.count() == 0:
                username_input = page.locator("input[name='username']")
            if await username_input.count() > 0:
                await username_input.fill(username)
                await asyncio.sleep(random.uniform(0.3, 0.6))
                save_btn = page.locator("button[wire\\:click='save']")
                if await save_btn.count() == 0:
                    save_btn = page.locator("button:has-text('Save')")
                if await save_btn.count() > 0:
                    await human_click(page, save_btn)
                    await asyncio.sleep(random.uniform(2, 3))
                    try:
                        await page.wait_for_url(re.compile(r".*account.*"), timeout=10000)
                        html = await page.content()
                        if re.search(r"account has been banned|your account has been banned", html, re.I):
                            return False, None, "BANNED"
                        if re.search(r"vpn detected|proxy detected|vpn not allowed", html, re.I):
                            return False, None, "VPN_DETECTED"
                        if dashboard_logged_in(html):
                            return True, html, None
                    except PlaywrightTimeoutError:
                        pass

        # Cek error message di modal
        error_msg = page.locator(".alert-danger, .error, .text-danger, .login-error-msg")
        if await error_msg.count() > 0:
            msg = await error_msg.first.text_content()
            if re.search(r"banned", msg, re.I):
                return False, None, "BANNED"
            if re.search(r"vpn|proxy", msg, re.I):
                return False, None, "VPN_DETECTED"
            return False, None, f"Login error: {msg}"

        # Coba langsung ke /account
        await page.goto(ACCOUNT_URL, wait_until="domcontentloaded")
        await asyncio.sleep(random.uniform(1, 2))
        html = await page.content()
        if re.search(r"account has been banned|your account has been banned", html, re.I):
            return False, None, "BANNED"
        if re.search(r"vpn detected|proxy detected|vpn not allowed", html, re.I):
            return False, None, "VPN_DETECTED"
        if dashboard_logged_in(html):
            return True, html, None

        return False, None, "Login gagal: tidak ada indikasi sukses"

    except Exception as e:
        return False, None, f"Playwright login exception: {e}"

# ============================================================
# WITHDRAWAL (UI)
# ============================================================
async def perform_withdrawal(page, balance):
    if balance is None:
        return False, "Balance tidak diketahui"
    if balance <= WITHDRAW_THRESHOLD:
        return False, "Balance terlalu kecil"

    selectors = [
        ".open-withdraw-modal-trigger",
        "button:has-text('Withdraw Funds')",
        "button:has-text('Withdraw')",
        "a:has-text('Withdraw Funds')",
        "a:has-text('Withdraw')",
        "[data-bs-target='#withdrawalModal']",
        "[data-target='#withdrawalModal']",
    ]
    trigger_loc = None
    for sel in selectors:
        try:
            loc = page.locator(sel)
            count = await loc.count()
            for i in range(count):
                item = loc.nth(i)
                if await item.is_visible():
                    trigger_loc = item
                    break
            if trigger_loc:
                break
        except:
            continue
    if not trigger_loc:
        return False, "Trigger tidak ditemukan"

    try:
        await human_click(page, trigger_loc, force=False)
    except Exception as e:
        return False, f"Gagal klik trigger: {e}"
    await asyncio.sleep(random.uniform(0.5, 0.8))

    modal_selectors = ["#withdrawalModal", ".modal.show", ".modal[style*='display: block']"]
    modal = None
    for sel in modal_selectors:
        try:
            loc = page.locator(sel)
            count = await loc.count()
            for i in range(count):
                item = loc.nth(i)
                if await item.is_visible():
                    modal = item
                    break
            if modal:
                break
        except:
            continue
    if not modal:
        return False, "Modal tidak muncul"

    max_selectors = [
        'button[wire\\:click="setMax"]',
        "button:has-text('Max')",
        "[wire\\:click='setMax']"
    ]
    max_loc = None
    for sel in max_selectors:
        try:
            loc = page.locator(sel)
            count = await loc.count()
            for i in range(count):
                item = loc.nth(i)
                if await item.is_visible():
                    max_loc = item
                    break
            if max_loc:
                break
        except:
            continue
    if not max_loc:
        return False, "setMax tidak ditemukan"

    try:
        await human_click(page, max_loc, force=False)
    except Exception as e:
        return False, f"setMax gagal: {e}"
    await asyncio.sleep(random.uniform(0.8, 1.2))

    if DRY_RUN:
        return True, "Dry-run: tidak submit"

    submit_selectors = [
        'button[wire\\:click="withdraw"]',
        'button[wire\\:click="submit"]',
        'button[wire\\:click="withdraw()"]',
        'button[wire\\:click="submit()"]',
        'button[type="submit"]',
        'button#withdrawSubmit',
        '.withdraw-submit',
        '.confirm-withdrawal',
    ]
    text_selectors = [
        "button:has-text('Confirm Withdrawal')",
        "button:has-text('CONFIRM WITHDRAWAL')",
        "button:has-text('Withdraw')",
        "button:has-text('Submit')",
        "button:has-text('Confirm')",
    ]

    submit_loc = None
    for sel in submit_selectors:
        try:
            loc = page.locator(sel)
            count = await loc.count()
            for i in range(count):
                item = loc.nth(i)
                if await item.is_visible():
                    submit_loc = item
                    break
            if submit_loc:
                break
        except:
            continue

    if not submit_loc:
        for sel in text_selectors:
            try:
                loc = page.locator(sel)
                count = await loc.count()
                for i in range(count):
                    item = loc.nth(i)
                    if await item.is_visible():
                        parent = await item.evaluate_handle("el => el.closest('.modal')")
                        if parent:
                            submit_loc = item
                            break
                if submit_loc:
                    break
            except:
                continue

    if not submit_loc:
        return False, "Tombol submit tidak ditemukan"

    await submit_loc.scroll_into_view_if_needed()
    await asyncio.sleep(random.uniform(0.2, 0.4))

    redirect_detected = False
    redirect_url = ""

    async def handle_response(response):
        nonlocal redirect_detected, redirect_url
        if "/livewire/message/" in response.url:
            try:
                data = await response.json()
                effects = data.get("effects", {})
                if effects.get("redirect"):
                    redirect_detected = True
                    redirect_url = effects["redirect"]
            except:
                pass

    page.on("response", handle_response)

    try:
        await human_click(page, submit_loc, force=False)
    except Exception as e:
        page.remove_listener("response", handle_response)
        return False, f"Gagal klik submit: {e}"

    await asyncio.sleep(2)

    if redirect_detected and "/my-withdrawals" in redirect_url:
        return True, "Redirect ke my-withdrawals"

    try:
        await page.wait_for_url(re.compile(r".*my-withdrawals.*"), timeout=5000)
        return True, "Redirect ke my-withdrawals"
    except PlaywrightTimeoutError:
        pass

    try:
        success_loc = page.locator("text=Your withdrawal has been processed successfully!").first
        if await success_loc.count() > 0 and await success_loc.is_visible():
            return True, "Pesan sukses ditemukan"
    except:
        pass

    return False, "Tidak ada indikasi sukses"

# ============================================================
# PROCESS EMAIL (dengan retry cerdas)
# ============================================================
async def process_email_with_retry(playwright, email, referral=REFERRAL_CODE):
    name = email.split("@", 1)[0]
    attempt = 1
    last_error = ""
    permanent_failure = False
    last_ip = None
    vpn_detected = False

    # Tentukan maks retry (10-15)
    max_retries = random.randint(MIN_RETRIES, MAX_RETRIES_PER_EMAIL)
    warn(f"{name} → Maks retry: {max_retries}")

    while attempt <= max_retries and not permanent_failure:
        browser = None
        context = None
        page = None
        success = False

        try:
            browser = await launch_browser(playwright)
            context, page = await create_page_with_proxy(browser)

            # Cek IP saat ini
            current_ip = await get_current_ip(page)
            if current_ip:
                if last_ip and current_ip == last_ip:
                    warn(f"{name} → IP masih sama ({current_ip}), tunggu 10 menit...")
                    await asyncio.sleep(RETRY_DELAY_VPN)
                    continue
                last_ip = current_ip
                ok(f"{name} → IP saat ini: {current_ip}")
            else:
                warn(f"{name} → Gagal mendapatkan IP, lanjutkan...")

            login_success, html_account, login_error = await playwright_login(page, email, referral)
            if not login_success:
                error(f"{name} → Login gagal: {login_error}")
                if login_error == "BANNED":
                    permanent_failure = True
                    warn(f"{name} → Account di-ban, lewati.")
                    raise Exception("BANNED")
                if login_error == "VPN_DETECTED":
                    vpn_detected = True
                    warn(f"{name} → VPN/proxy terdeteksi, tunggu 10-15 menit...")
                    # Delay panjang
                    delay = random.randint(600, 900)  # 10-15 menit
                    await asyncio.sleep(delay)
                    continue
                if login_error and ("not found" in login_error.lower() or "invalid" in login_error.lower()):
                    permanent_failure = True
                raise Exception(f"Login gagal: {login_error}")

            ok(f"{name} → Login OK")

            balance = get_balance(html_account)
            if balance is None:
                await page.goto(ACCOUNT_URL, wait_until="domcontentloaded")
                html_account = await page.content()
                balance = get_balance(html_account)
                if balance is None:
                    warn(f"{name} → Balance tidak ditemukan, set ke 0")
                    balance = 0.0
            ok(f"{name} → Balance: {balance:.8f} LTC")

            if balance > WITHDRAW_THRESHOLD:
                success_wd, msg = await perform_withdrawal(page, balance)
                if success_wd:
                    ok(f"{name} → WITHDRAWAL SUKSES: {msg}")
                    success = True
                else:
                    raise Exception(f"Withdrawal gagal: {msg}")
            else:
                warn(f"{name} → balance di bawah threshold")
                success = True

            ok(f"{name} → SELESAI")
            success = True
            break

        except Exception as e:
            last_error = str(e)
            error(f"{name} → Percobaan {attempt} gagal: {last_error}")
            if context:
                try:
                    await context.close()
                except:
                    pass
            if browser:
                try:
                    await browser.close()
                except:
                    pass
            if attempt < max_retries and not permanent_failure:
                if vpn_detected:
                    delay = random.randint(600, 900)  # 10-15 menit
                    warn(f"{name} → VPN terdeteksi, tunggu {delay//60} menit...")
                else:
                    # Delay eksponensial dengan batas 300 detik
                    delay = min(RETRY_DELAY_BASE * (2 ** (attempt - 1)), 300)
                    warn(f"{name} → Tunggu {delay} detik...")
                await asyncio.sleep(delay)
            attempt += 1

        finally:
            if context:
                try:
                    await context.close()
                except:
                    pass
            if browser:
                try:
                    await browser.close()
                except:
                    pass

    if not success:
        error(f"{name} → Gagal setelah {max_retries} percobaan. Last error: {last_error}")
        return False
    return True

# ============================================================
# MAIN
# ============================================================
async def main():
    print()
    print(f"{Fore.CYAN}==================================================")
    print(f"{Fore.CYAN} LTCHash Auto-Submit (Proxy Residential + Retry Cerdas)")
    print(f"{Fore.CYAN}==================================================")
    print(f"Chrome   : {CHROME_BIN}")
    print(f"Threshold: {WITHDRAW_THRESHOLD:.8f} LTC")
    print(f"DRY_RUN  : {DRY_RUN}")
    print(f"Referral : {REFERRAL_CODE}")
    print(f"Proxy    : {PROXY_URL[:50]}...")
    print(f"Min Retry: {MIN_RETRIES}, Max Retry: {MAX_RETRIES_PER_EMAIL}")
    print(f"Loop     : {LOOP_WAIT_HOURS} jam")
    print()

    while True:
        try:
            emails = load_emails()
        except Exception as e:
            error(str(e))
            await asyncio.sleep(LOOP_WAIT_SECONDS)
            continue

        if not emails:
            await asyncio.sleep(LOOP_WAIT_SECONDS)
            continue

        log_status(f"Total email: {len(emails)}")
        async with async_playwright() as playwright:
            for index, email in enumerate(emails, 1):
                print()
                print(f"{Fore.WHITE}{'=' * 55}")
                print(f"{Fore.WHITE}[{index}/{len(emails)}] {email}")
                await process_email_with_retry(playwright, email, referral=REFERRAL_CODE)

        print()
        print(f"{Fore.GREEN}==================================================")
        print(f"{Fore.GREEN} Semua email selesai. Menunggu {LOOP_WAIT_HOURS} jam...")
        print(f"{Fore.GREEN}==================================================")
        await asyncio.sleep(LOOP_WAIT_SECONDS)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print()
        warn("Stopping...")
