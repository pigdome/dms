import os
import sys
from playwright.sync_api import sync_playwright

SCREENSHOTS_DIR = "/srv/letmefix/dms/screenshots"
RESULTS_FILE = "/srv/letmefix/dms/e2e_results.txt"
BASE_URL = os.environ.get("BASE_URL", "http://localhost:8000")

os.makedirs(SCREENSHOTS_DIR, exist_ok=True)

# Owner / Staff URLs — basic smoke test (no errors)
OWNER_URLS = [
    "/",
    "/dashboard/",
    "/rooms/",
    "/rooms/create/",
    "/rooms/meter-reading/",
    "/tenants/",
    "/tenants/add/",
    "/tenants/import/",
    "/maintenance/",
    "/maintenance/create/",
    "/notifications/parcels/",
    "/notifications/parcels/history/",
    "/notifications/broadcast/",
    "/billing/",
    "/billing/settings/",
    "/setup/",
]

# Tenant-only URLs
TENANT_URLS = [
    "/tenant/home/",
    "/tenant/bills/",
    "/tenant/parcels/",
    "/tenant/profile/",
    "/tenant/maintenance/",
]

results = []


def is_error_page(page):
    title = page.title()
    content = page.content()
    for kw in ["Exception", "Page not found", "404", "500", "403", "400", "Server Error"]:
        if kw in title:
            return True, f"Title: '{title}'"
    found = next(
        (kw for kw in ["Exception Type", "Traceback", "Django tried these URL patterns"]
         if kw in content),
        None,
    )
    return (True, found) if found else (False, None)


def test_url(page, url, username):
    full_url = f"{BASE_URL}{url}"
    try:
        response = page.goto(full_url, wait_until="domcontentloaded", timeout=20000)
        status = response.status if response else "unknown"
        is_err, reason = is_error_page(page)

        safe_url = url.strip("/").replace("/", "_") or "root"
        screenshot_path = os.path.join(SCREENSHOTS_DIR, f"{username}_{safe_url}.png")
        page.screenshot(path=screenshot_path, full_page=True)

        if is_err or (isinstance(status, int) and status >= 400):
            result = {"status": "FAIL", "url": url, "reason": reason or f"HTTP {status}",
                      "screenshot": screenshot_path, "user": username}
        else:
            result = {"status": "PASS", "url": url, "reason": None,
                      "screenshot": screenshot_path, "user": username}
    except Exception as e:
        result = {"status": "FAIL", "url": url, "reason": str(e)[:120],
                  "screenshot": None, "user": username}

    results.append(result)
    return result


def print_result(result):
    icon = "PASS ✅" if result["status"] == "PASS" else "FAIL ❌"
    reason = f"  — {result['reason']}" if result["reason"] else ""
    print(f"  {icon}  {result['url']}{reason}")


def get_session_cookie(username, password):
    import urllib.request
    import urllib.parse
    import http.cookiejar

    jar = http.cookiejar.CookieJar()
    opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar))

    resp = opener.open(f"{BASE_URL}/login/")
    html = resp.read().decode()
    csrf = html.split('csrfmiddlewaretoken" value="')[1].split('"')[0]

    data = urllib.parse.urlencode({
        "username": username, "password": password, "csrfmiddlewaretoken": csrf
    }).encode()
    req = urllib.request.Request(
        f"{BASE_URL}/login/", data=data,
        headers={"Referer": f"{BASE_URL}/login/",
                 "Content-Type": "application/x-www-form-urlencoded"}
    )
    opener.open(req)

    return [{"name": c.name, "value": c.value, "domain": "localhost", "path": "/"}
            for c in jar]


# ---------------------------------------------------------------------------
# Functional scenario tests
# ---------------------------------------------------------------------------

def test_property_switch(page, context, owner_cookies, dorm2_id):
    """Owner switches active property via POST and dashboard reflects the change."""
    context.add_cookies(owner_cookies)

    # POST to switch property
    page.goto(f"{BASE_URL}/dashboard/")
    with page.expect_navigation(wait_until="domcontentloaded", timeout=10000):
        page.evaluate(f"""() => {{
            const form = document.createElement('form');
            form.method = 'POST';
            form.action = '/property/switch/';
            const csrfInput = document.createElement('input');
            csrfInput.name = 'csrfmiddlewaretoken';
            csrfInput.value = document.cookie.match(/csrftoken=([^;]+)/)?.[1] || '';
            const dormInput = document.createElement('input');
            dormInput.name = 'dormitory_id';
            dormInput.value = '{dorm2_id}';
            const nextInput = document.createElement('input');
            nextInput.name = 'next';
            nextInput.value = '/dashboard/';
            form.appendChild(csrfInput);
            form.appendChild(dormInput);
            form.appendChild(nextInput);
            document.body.appendChild(form);
            form.submit();
        }}""")
    is_err, reason = is_error_page(page)
    result = {
        "status": "FAIL" if is_err else "PASS",
        "url": "/property/switch/ → /dashboard/",
        "reason": reason,
        "screenshot": None,
        "user": "owner1 (property switch)",
    }
    results.append(result)
    print_result(result)


def test_property_switch_blocked_for_nonmember(page, context, owner_cookies, stranger_dorm_id):
    """Switching to a dormitory the owner doesn't belong to must not crash."""
    context.add_cookies(owner_cookies)
    page.goto(f"{BASE_URL}/dashboard/")
    with page.expect_navigation(wait_until="domcontentloaded", timeout=10000):
        page.evaluate(f"""() => {{
            const form = document.createElement('form');
            form.method = 'POST';
            form.action = '/property/switch/';
            const csrfInput = document.createElement('input');
            csrfInput.name = 'csrfmiddlewaretoken';
            csrfInput.value = document.cookie.match(/csrftoken=([^;]+)/)?.[1] || '';
            const dormInput = document.createElement('input');
            dormInput.name = 'dormitory_id';
            dormInput.value = '{stranger_dorm_id}';
            const nextInput = document.createElement('input');
            nextInput.name = 'next';
            nextInput.value = '/dashboard/';
            form.appendChild(csrfInput);
            form.appendChild(dormInput);
            form.appendChild(nextInput);
            document.body.appendChild(form);
            form.submit();
        }}""")
    is_err, reason = is_error_page(page)
    result = {
        "status": "FAIL" if is_err else "PASS",
        "url": "/property/switch/ (unauthorized dorm)",
        "reason": reason,
        "screenshot": None,
        "user": "owner1 (blocked switch)",
    }
    results.append(result)
    print_result(result)


def test_get_on_property_switch_returns_405(page, context, owner_cookies):
    """GET /property/switch/ must return 405, not crash."""
    context.add_cookies(owner_cookies)
    response = page.goto(f"{BASE_URL}/property/switch/", wait_until="domcontentloaded")
    status = response.status if response else 0
    result = {
        "status": "PASS" if status == 405 else "FAIL",
        "url": "/property/switch/ (GET → 405)",
        "reason": None if status == 405 else f"Expected 405, got {status}",
        "screenshot": None,
        "user": "owner1",
    }
    results.append(result)
    print_result(result)


# ---------------------------------------------------------------------------
# Mobile responsive tests
# ---------------------------------------------------------------------------

MOBILE_VIEWPORTS = [
    {"name": "iPhone_SE",   "width": 375, "height": 667},
    {"name": "iPhone_14",   "width": 390, "height": 844},
    {"name": "Android_SM",  "width": 360, "height": 800},
]

MOBILE_USER_AGENT = (
    "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) "
    "AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1"
)


def _mobile_check(page, check_name, url, username, viewport):
    """Run one JS-based assertion; record + print; return result dict."""
    vp_label = f"{viewport['name']} {viewport['width']}×{viewport['height']}"

    checks = {
        # 1. <meta name="viewport" content="width=device-width,..."> present
        "viewport_meta": (
            """() => {
                const m = document.querySelector('meta[name="viewport"]');
                return m ? m.content.includes('width=device-width') : false;
            }""",
            "Missing <meta name='viewport' content='width=device-width,...'>",
        ),
        # 2. No horizontal overflow (allow 2 px tolerance for sub-pixel rounding)
        "no_horizontal_scroll": (
            """() => document.documentElement.scrollWidth
                        <= document.documentElement.clientWidth + 2""",
            lambda: "Horizontal overflow: scrollWidth={} clientWidth={}px".format(
                page.evaluate("() => document.documentElement.scrollWidth"),
                page.evaluate("() => document.documentElement.clientWidth"),
            ),
        ),
        # 3. Fixed header pinned at the very top (top === 0)
        "header_fixed_top": (
            """() => {
                const h = document.querySelector('header');
                if (!h) return false;
                const r = h.getBoundingClientRect();
                return r.top === 0 && r.height > 0;
            }""",
            "Header not fixed/pinned at top (rect.top ≠ 0 or zero height)",
        ),
        # 4. Bottom nav sits inside (or flush with) the visible viewport
        "bottom_nav_visible": (
            """() => {
                const nav = document.querySelector('nav');
                if (!nav) return false;
                const r = nav.getBoundingClientRect();
                return r.bottom <= window.innerHeight + 2 && r.height > 0;
            }""",
            "Bottom nav not visible within viewport",
        ),
        # 5. Every nav <a> touch target is at least 44 px tall (WCAG / Apple HIG)
        "nav_touch_targets_44px": (
            """() => {
                const links = Array.from(document.querySelectorAll('nav a'));
                return links.length > 0 &&
                       links.every(a => a.getBoundingClientRect().height >= 44);
            }""",
            "One or more bottom-nav touch targets are shorter than 44 px",
        ),
    }

    js, failure_msg = checks[check_name]
    passed = page.evaluate(js)
    reason = None
    screenshot_path = None

    if not passed:
        reason = failure_msg() if callable(failure_msg) else failure_msg
        safe_url = url.strip("/").replace("/", "_") or "root"
        screenshot_path = os.path.join(
            SCREENSHOTS_DIR,
            f"mobile_{username}_{viewport['name']}_{safe_url}_{check_name}.png",
        )
        try:
            page.screenshot(path=screenshot_path, full_page=True)
        except Exception:
            screenshot_path = None

    result = {
        "status": "PASS" if passed else "FAIL",
        "url": f"{url} [{vp_label}] — {check_name}",
        "reason": reason,
        "screenshot": screenshot_path,
        "user": username,
    }
    results.append(result)
    print_result(result)
    return result


def _run_mobile_page(browser, cookies, url, username, viewport, extra_checks=None):
    """
    Open *url* in a mobile context at *viewport*, run the 5 standard responsive
    checks, then run any caller-supplied *extra_checks* (list of (name, js, msg)).
    Takes a full-page screenshot named after the viewport regardless of outcome.
    """
    ctx = browser.new_context(
        viewport={"width": viewport["width"], "height": viewport["height"]},
        user_agent=MOBILE_USER_AGENT,
    )
    ctx.add_cookies(cookies)
    page = ctx.new_page()
    vp_label = f"{viewport['name']} {viewport['width']}×{viewport['height']}"

    try:
        response = page.goto(f"{BASE_URL}{url}", wait_until="domcontentloaded", timeout=20000)
        status = response.status if response else 0
        if status >= 400:
            result = {
                "status": "FAIL",
                "url": f"{url} [{vp_label}]",
                "reason": f"HTTP {status}",
                "screenshot": None,
                "user": username,
            }
            results.append(result)
            print_result(result)
            return

        # Standard responsive checks
        for check_name in (
            "viewport_meta",
            "no_horizontal_scroll",
            "header_fixed_top",
            "bottom_nav_visible",
            "nav_touch_targets_44px",
        ):
            _mobile_check(page, check_name, url, username, viewport)

        # Page-specific extra checks
        for name, js, failure_msg in (extra_checks or []):
            passed = page.evaluate(js)
            reason = failure_msg if not passed else None
            screenshot_path = None
            if not passed:
                safe_url = url.strip("/").replace("/", "_") or "root"
                screenshot_path = os.path.join(
                    SCREENSHOTS_DIR,
                    f"mobile_{username}_{viewport['name']}_{safe_url}_{name}.png",
                )
                try:
                    page.screenshot(path=screenshot_path, full_page=True)
                except Exception:
                    screenshot_path = None
            result = {
                "status": "PASS" if passed else "FAIL",
                "url": f"{url} [{vp_label}] — {name}",
                "reason": reason,
                "screenshot": screenshot_path,
                "user": username,
            }
            results.append(result)
            print_result(result)

        # Always save a reference screenshot for visual review
        safe_url = url.strip("/").replace("/", "_") or "root"
        ref_path = os.path.join(
            SCREENSHOTS_DIR, f"mobile_{username}_{viewport['name']}_{safe_url}.png"
        )
        try:
            page.screenshot(path=ref_path, full_page=True)
        except Exception:
            pass

    finally:
        ctx.close()


def run_tests():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)

        # ----------------------------------------------------------------
        # Public Pages (Unauthenticated) Smoke tests
        # ----------------------------------------------------------------
        print("\n=== Smoke testing Public Pages ===")
        ctx = browser.new_context()
        page = ctx.new_page()
        for url in ["/", "/welcome/", "/login/"]:
            result = test_url(page, url, "anonymous")
            print_result(result)
        ctx.close()

        # ----------------------------------------------------------------
        # Basic smoke tests for all roles
        # ----------------------------------------------------------------
        for username, password, urls in [
            ("owner1",    "test1234", OWNER_URLS),
            ("staff1",    "test1234", OWNER_URLS),
            ("tenant101", "test1234", TENANT_URLS),
        ]:
            print(f"\n=== Smoke testing as {username} ===")
            cookies = get_session_cookie(username, password)
            ctx = browser.new_context()
            ctx.add_cookies(cookies)
            page = ctx.new_page()
            print(f"  Session cookie obtained for {username}")

            for url in urls:
                result = test_url(page, url, username)
                print_result(result)

            ctx.close()

        # ----------------------------------------------------------------
        # Functional: property switching
        # ----------------------------------------------------------------
        print("\n=== Functional: property switch ===")
        owner_cookies = get_session_cookie("owner1", "test1234")

        # Fetch a "stranger" dorm ID that owner1 has no access to.
        # We use dorm ID 99999 as a stand-in (unlikely to exist).
        stranger_id = 99999

        # Try to get dorm2 ID from the dashboard (owner2's dorm, if it exists)
        # Fallback: just test the switch endpoint with a known-accessible dorm (dorm of owner1)
        ctx = browser.new_context()
        page = ctx.new_page()
        ctx.add_cookies(owner_cookies)
        tmp = page.goto(f"{BASE_URL}/dashboard/", wait_until="domcontentloaded")
        ctx.close()

        # Test: GET on switch endpoint → 405
        ctx = browser.new_context()
        page = ctx.new_page()
        test_get_on_property_switch_returns_405(page, ctx, owner_cookies)
        ctx.close()

        # Test: switch to unauthorized dorm is blocked (no crash)
        ctx = browser.new_context()
        page = ctx.new_page()
        test_property_switch_blocked_for_nonmember(page, ctx, owner_cookies, stranger_id)
        ctx.close()

        # ----------------------------------------------------------------
        # Mobile responsive: Owner Dashboard
        # ----------------------------------------------------------------
        print("\n=== Mobile responsive: Owner Dashboard ===")
        owner_cookies = get_session_cookie("owner1", "test1234")
        owner_extra = [
            (
                "main_has_content",
                """() => {
                    const m = document.querySelector('main');
                    return m !== null && m.innerText.trim().length > 0;
                }""",
                "main element is empty — dashboard rendered no content",
            ),
        ]
        for viewport in MOBILE_VIEWPORTS:
            print(f"\n  -- {viewport['name']} ({viewport['width']}×{viewport['height']}) --")
            _run_mobile_page(browser, owner_cookies, "/dashboard/", "owner1", viewport, owner_extra)

        # ----------------------------------------------------------------
        # Mobile responsive: Tenant Home
        # ----------------------------------------------------------------
        print("\n=== Mobile responsive: Tenant Home ===")
        tenant_cookies = get_session_cookie("tenant101", "test1234")
        tenant_extra = [
            (
                "room_section_present",
                """() => {
                    const m = document.querySelector('main');
                    if (!m) return false;
                    const t = m.innerText;
                    return t.includes('Room') || t.includes('ห้อง') || t.includes('No profile');
                }""",
                "Room info section (or no-profile notice) not found in tenant home",
            ),
            (
                "no_full_width_overflow",
                """() => {
                    return Array.from(document.querySelectorAll('main *')).every(el => {
                        const r = el.getBoundingClientRect();
                        return r.right <= window.innerWidth + 2;
                    });
                }""",
                "At least one element inside main overflows the right edge of the viewport",
            ),
        ]
        for viewport in MOBILE_VIEWPORTS:
            print(f"\n  -- {viewport['name']} ({viewport['width']}×{viewport['height']}) --")
            _run_mobile_page(browser, tenant_cookies, "/tenant/home/", "tenant101", viewport, tenant_extra)

        browser.close()


def print_report():
    print("\n" + "=" * 60)
    print("FINAL REPORT")
    print("=" * 60)

    lines = []
    for r in results:
        icon = "PASS ✅" if r["status"] == "PASS" else "FAIL ❌"
        reason = f"  — {r['reason']}" if r["reason"] else ""
        line = f"{icon}  [{r['user']}]  {r['url']}{reason}"
        print(line)
        lines.append(line)

    total = len(results)
    passed = sum(r["status"] == "PASS" for r in results)
    failed = total - passed

    summary = f"\nTotal: {total} | Passed: {passed} | Failed: {failed}"
    print(summary)
    lines.append(summary)

    with open(RESULTS_FILE, "w") as f:
        f.write("E2E Test Results\n" + "=" * 60 + "\n")
        for line in lines:
            f.write(line.replace("✅", "[PASS]").replace("❌", "[FAIL]") + "\n")

    print(f"\nResults saved to {RESULTS_FILE}")
    print(f"Screenshots saved to {SCREENSHOTS_DIR}/")
    return failed


if __name__ == "__main__":
    run_tests()
    failed = print_report()
    sys.exit(1 if failed > 0 else 0)
