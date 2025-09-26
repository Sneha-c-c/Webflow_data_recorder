import time
import threading
import os
import platform
import subprocess
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from bs4 import BeautifulSoup

from database.graph_db import store_in_neo4j
from database.vector_db import store_in_pgvector, update_page_actions  # Added update_page_actions import
from util.signals import signals

# Global variables
browser = None
capture_thread = None
stop_capturing = False
flows = {}
TARGET_WEBSITE = ""
all_windows = set()

# Page actions accumulator per URL (keeps list of structured actions and counter if needed)
page_action_logs = {}  # { url: {"actions": [ ... ]} }


# Check if browser is still alive
def is_browser_alive():
    global browser
    try:
        if browser is None:
            return False
        # A simple operation to check if browser is responsive
        browser.current_window_handle
        return True
    except:
        return False


# Find Chrome installation
def find_chrome_executable():
    # Default locations for Chrome executable by platform
    if platform.system() == "Windows":
        paths = [
            r"C:\Program Files\Google\Chrome\Application\chrome.exe",
            r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
            os.path.expanduser(r"~\AppData\Local\Google\Chrome\Application\chrome.exe"),
        ]
    elif platform.system() == "Darwin":  # macOS
        paths = [
            "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
            "/Applications/Chrome.app/Contents/MacOS/Chrome",
            os.path.expanduser("~/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"),
        ]
    else:  # Linux and others
        paths = [
            "/usr/bin/google-chrome",
            "/usr/bin/google-chrome-stable",
            "/usr/bin/chromium-browser",
            "/usr/bin/chromium",
        ]

    # Check each path
    for path in paths:
        if os.path.exists(path) and os.access(path, os.X_OK):
            return path

    # If not found in default locations, try to find using 'which' (Unix-like systems)
    if platform.system() != "Windows":
        try:
            chrome_path = subprocess.check_output(["which", "google-chrome"], text=True).strip()
            if chrome_path:
                return chrome_path
        except:
            pass

        try:
            chrome_path = subprocess.check_output(["which", "chromium"], text=True).strip()
            if chrome_path:
                return chrome_path
        except:
            pass

    # If all fails, return None
    return None


# Initialize and start browser with Chrome DevTools Protocol enabled
def start_browser():
    global browser, all_windows

    if is_browser_alive():
        # Browser already running
        return True

    try:
        # Configure Chrome options
        chrome_options = Options()
        chrome_options.add_argument("--window-size=1366,768")  # More standard size
        chrome_options.add_argument("--remote-debugging-port=9222")  # Enable DevTools Protocol
        chrome_options.add_argument("--no-sandbox")
        chrome_options.add_argument("--disable-dev-shm-usage")

        # Disable automation flags
        chrome_options.add_experimental_option("excludeSwitches", ["enable-automation"])
        chrome_options.add_experimental_option('useAutomationExtension', False)
        chrome_options.add_experimental_option("detach", True)  # Keep browser open

        # Add user data directory for persistent session
        chrome_options.add_argument("--user-data-dir=./chrome_data")

        # Set binary location if we can find Chrome
        chrome_path = find_chrome_executable()
        if chrome_path:
            print(f"Found Chrome at: {chrome_path}")
            chrome_options.binary_location = chrome_path

        # Initialize browser
        service = Service()
        browser = webdriver.Chrome(service=service, options=chrome_options)

        # Store the initial window handle
        all_windows = {browser.current_window_handle}

        # Test that browser is working
        browser.get("about:blank")
        print("Successfully loaded about:blank")

        return True
    except Exception as e:
        print(f"Error starting browser: {e}")
        signals.error.emit("Browser Error", f"Failed to start browser: {e}")

        # Try alternative method if first method fails
        try:
            print("Trying alternative browser setup...")
            chrome_options = Options()
            chrome_options.add_argument("--disable-extensions")
            chrome_options.add_argument("--disable-gpu")
            chrome_options.add_argument("--no-sandbox")
            chrome_options.add_argument("--disable-dev-shm-usage")

            browser = webdriver.Chrome(options=chrome_options)
            all_windows = {browser.current_window_handle}
            browser.get("about:blank")
            print("Alternative setup successful")
            return True
        except Exception as e2:
            print(f"Alternative method also failed: {e2}")
            return False


# Stop browser
def stop_browser():
    global browser, stop_capturing

    # First ensure capturing is stopped
    stop_capturing = True

    # Allow capture thread to finish
    time.sleep(1)

    # Now close the browser
    if browser:
        try:
            browser.quit()
        except Exception as e:
            print(f"Error closing browser: {e}")
        browser = None


# -------------------------- Action Recording Utilities (NEW) --------------------------

def inject_action_listeners():
    """
    Inject JS into the current page to capture user interactions:
    - click, change, input, submit, keydown(Enter)
    Captures action as structured JSON and pushes into window.__flowActionQueue.
    Includes masking for sensitive fields.
    This is re-entrant; if injected already, it returns early on subsequent calls.
    """
    if not is_browser_alive():
        return

    try:
        script = r"""
        (function() {
            if (window.__flowListenersInstalled) {
                return "already";
            }
            window.__flowListenersInstalled = true;
            window.__flowActionQueue = [];
            window.__flowActionCounter = 0;

            function isSensitive(el) {
                try {
                    const n = (el.getAttribute('name') || '').toLowerCase();
                    const i = (el.id || '').toLowerCase();
                    const t = (el.type || '').toLowerCase();
                    const ph = (el.getAttribute('placeholder') || '').toLowerCase();
                    const ac = (el.getAttribute('autocomplete') || '').toLowerCase();
                    const label = (el.getAttribute('aria-label') || '').toLowerCase();
                    const needles = ['password','pass','pwd','secret','token','ssn','sin','credit','card','cvc','cvv','pin'];
                    const haystacks = [n, i, ph, ac, label, t];
                    return t === 'password' || haystacks.some(h => needles.some(k => h.includes(k)));
                } catch(e) {
                    return false;
                }
            }

            function getXPath(el) {
                try {
                    if (!el) return "";
                    if (el.id) {
                        return "//*[@id='" + el.id + "']";
                    }
                    const parts = [];
                    while (el && el.nodeType === Node.ELEMENT_NODE) {
                        let nb = 0;
                        let idx = 0;
                        const siblings = el.parentNode ? el.parentNode.childNodes : [];
                        for (let i=0; i<siblings.length; i++) {
                            const sib = siblings[i];
                            if (sib.nodeType === Node.ELEMENT_NODE && sib.nodeName === el.nodeName) {
                                nb++;
                                if (sib === el) idx = nb;
                            }
                        }
                        const tagName = el.nodeName.toLowerCase();
                        const part = (nb > 1) ? tagName + "[" + idx + "]" : tagName;
                        parts.unshift(part);
                        el = el.parentNode;
                        if (el && el.nodeType !== Node.ELEMENT_NODE) break;
                    }
                    return "/" + parts.join("/");
                } catch (e) {
                    return "";
                }
            }

            function getLabelText(el) {
                try {
                    if (!el) return "";
                    // Explicit label via labels or for=id
                    if (el.labels && el.labels.length > 0) {
                        return Array.from(el.labels).map(l => (l.innerText || l.textContent || "").trim()).filter(Boolean).join(" ").trim();
                    }
                    const id = el.getAttribute('id');
                    if (id) {
                        const sel = document.querySelector("label[for='" + id + "']");
                        if (sel) return (sel.innerText || sel.textContent || "").trim();
                    }
                    // aria-label or placeholder
                    const aria = el.getAttribute('aria-label');
                    if (aria) return aria.trim();
                    const ph = el.getAttribute('placeholder');
                    if (ph) return ph.trim();

                    // Nearest label ancestor
                    const nearestLabel = el.closest ? el.closest('label') : null;
                    if (nearestLabel) return (nearestLabel.innerText || nearestLabel.textContent || "").trim();

                    // Try previous sibling text
                    const prev = el.previousElementSibling;
                    if (prev && prev.tagName && prev.tagName.toLowerCase() === 'label') {
                        return (prev.innerText || prev.textContent || "").trim();
                    }
                    return "";
                } catch(e) {
                    return "";
                }
            }

            function buildAction(type, target, evt) {
                try {
                    const form = target && (target.form || (target.closest ? target.closest('form') : null));
                    const fieldType = ((target && (target.type || target.tagName)) || '').toLowerCase();
                    const sensitive = target ? isSensitive(target) : false;
                    const tName = target && target.tagName ? target.tagName.toLowerCase() : '';

                    // Build data depending on event type and element type
                    const dataObj = {};
                    if (type === 'input' || type === 'change') {
                        if (fieldType === 'checkbox' || fieldType === 'radio') {
                            dataObj.checked = !!target.checked;
                        }
                        if (tName === 'select') {
                            dataObj.value = target.value || '';
                            dataObj.text = (target.options && target.selectedIndex >= 0) ? (target.options[target.selectedIndex].text || '') : '';
                        } else if (fieldType !== 'checkbox' && fieldType !== 'radio') {
                            dataObj.value = sensitive ? '***' : (target.value || '');
                        }
                        dataObj.sensitive = sensitive;
                    } else if (type === 'click') {
                        if (tName === 'a') {
                            dataObj.href = target.getAttribute('href') || '';
                        }
                        if (tName === 'button' || (tName === 'input' && ['button','submit','reset'].includes(fieldType))) {
                            dataObj.text = (target.innerText || target.value || '').trim();
                        }
                    } else if (type === 'submit') {
                        const fields = [];
                        if (form && form.elements) {
                            Array.from(form.elements).forEach(el => {
                                const elType = ((el.type || el.tagName) || '').toLowerCase();
                                const sens = isSensitive(el);
                                let value = '';
                                if (elType === 'checkbox' || elType === 'radio') {
                                    value = !!el.checked;
                                } else if (el.tagName && el.tagName.toLowerCase() === 'select') {
                                    value = el.value || '';
                                } else {
                                    value = sens ? '***' : (el.value || '');
                                }
                                fields.push({
                                    name: el.name || '',
                                    id: el.id || '',
                                    type: elType,
                                    value: value,
                                    sensitive: sens
                                });
                            });
                        }
                        dataObj.fields = fields;
                    } else if (type === 'keydown' && evt && evt.key === 'Enter') {
                        dataObj.key = 'Enter';
                    }

                    window.__flowActionCounter = (window.__flowActionCounter || 0) + 1;
                    const action = {
                        action_id: window.__flowActionCounter,
                        type: (type === 'keydown' && evt && evt.key === 'Enter') ? 'keydown_enter' : type,
                        url: window.location.href,
                        title: document.title || '',
                        field_xpath: target ? getXPath(target) : '',
                        field_css: '',
                        field_label: target ? getLabelText(target) : '',
                        field_name: target ? (target.getAttribute('name') || '') : '',
                        field_id: target ? (target.getAttribute('id') || '') : '',
                        field_type: fieldType,
                        form_name: form ? (form.getAttribute('name') || '') : '',
                        form_id: form ? (form.getAttribute('id') || '') : '',
                        form_action: form ? (form.getAttribute('action') || '') : '',
                        form_method: form ? ((form.getAttribute('method') || 'GET').toUpperCase()) : '',
                        form_xpath: form ? getXPath(form) : '',
                        data: dataObj,
                        timestamp_utc: (new Date()).toISOString(),
                        page_x: (evt && typeof evt.pageX !== 'undefined') ? evt.pageX : null,
                        page_y: (evt && typeof evt.pageY !== 'undefined') ? evt.pageY : null
                    };
                    window.__flowActionQueue.push(action);
                } catch(e) {
                    // Swallow single-event capture errors to avoid breaking page
                }
            }

            // Register listeners (capture phase to catch events early)
            document.addEventListener('click', function(evt){ buildAction('click', evt.target, evt); }, true);
            document.addEventListener('change', function(evt){
                const tag = evt.target && evt.target.tagName ? evt.target.tagName.toLowerCase() : '';
                if (['input','textarea','select'].includes(tag)) {
                    buildAction('change', evt.target, evt);
                }
            }, true);
            document.addEventListener('input', function(evt){
                const el = evt.target;
                if (!el) return;
                const type = (el.type || '').toLowerCase();
                // capture common typing events (avoid logging every keystroke for all inputs)
                if (type === 'password') return buildAction('input', el, evt);
                const isTextArea = el.tagName && el.tagName.toLowerCase() === 'textarea';
                const important = ['email','number','tel','search','text','url'];
                if (isTextArea || important.includes(type)) {
                    buildAction('input', el, evt);
                }
            }, true);
            document.addEventListener('keydown', function(evt){
                if (evt && evt.key === 'Enter') {
                    buildAction('keydown', evt.target, evt);
                }
            }, true);
            document.addEventListener('submit', function(evt){
                buildAction('submit', evt.target, evt);
            }, true);

            return "installed";
        })();
        """
        browser.execute_script(script)
    except Exception as e:
        # Non-fatal: just log in console
        print(f"Action listener injection error: {e}")


def drain_action_queue():
    """
    Drain and return the collected actions from the page (if any).
    Returns a list of dictionaries representing actions. After draining, the queue is cleared.
    """
    if not is_browser_alive():
        return []
    try:
        return browser.execute_script("""
            (function() {
                try {
                    var q = (window.__flowActionQueue || []);
                    window.__flowActionQueue = [];
                    return q;
                } catch(e) {
                    return [];
                }
            })();
        """) or []
    except Exception as e:
        print(f"Error draining action queue: {e}")
        return []


def process_new_actions(tab_url, actions):
    """
    Accumulate actions for the given URL and persist to Postgres (page_actions column).
    Sensitive values are already masked in JS. We persist the raw list as JSONB.
    """
    if not actions:
        return

    # Initialize buffer for URL
    url_actions = page_action_logs.setdefault(tab_url, {"actions": []})
    url_actions["actions"].extend(actions)

    # Persist to DB (updates the page_actions JSONB for this URL)
    try:
        update_page_actions(tab_url, url_actions["actions"])
        signals.update_status.emit(f"Recorded {len(actions)} action(s) on {tab_url}")
    except Exception as e:
        print(f"Failed to persist actions for {tab_url}: {e}")


# -------------------------- Scrape Metadata (existing) --------------------------

# Enhanced extract_metadata function for better form capture
def extract_metadata(html):
    soup = BeautifulSoup(html, "html.parser")

    # Extract HTML meta tags
    meta_tags = {}
    for meta in soup.find_all("meta"):
        name = meta.get("name") or meta.get("property")
        content = meta.get("content")
        if name and content:
            meta_tags[name] = content

    # Extract title
    title = soup.title.text.strip() if soup.title else "No Title"

    # Extract headings for summary
    headings = []
    for h in soup.find_all(["h1", "h2", "h3"]):
        headings.append(h.text.strip())

    # Extract forms with enhanced field capture
    forms = []
    for form in soup.find_all("form"):
        # Get form properties
        form_data = {
            "action": form.get("action", ""),
            "method": form.get("method", ""),
            "id": form.get("id", ""),
            "name": form.get("name", ""),
            "class": form.get("class", []),
            "enctype": form.get("enctype", ""),
            "target": form.get("target", ""),
            "fields": []
        }

        # Process all input fields
        for inp in form.find_all("input"):
            field = {
                "name": inp.get("name", ""),
                "type": inp.get("type", "text"),
                "id": inp.get("id", ""),
                "placeholder": inp.get("placeholder", ""),
                "value": inp.get("value", ""),
                "required": inp.has_attr("required"),
                "readonly": inp.has_attr("readonly"),
                "class": inp.get("class", []),
                "max_length": inp.get("maxlength", ""),
                "min_length": inp.get("minlength", ""),
                "pattern": inp.get("pattern", "")
            }
            form_data["fields"].append(field)

        # Process select fields
        for select in form.find_all("select"):
            options = []
            for option in select.find_all("option"):
                options.append({
                    "value": option.get("value", ""),
                    "text": option.text.strip(),
                    "selected": option.has_attr("selected")
                })

            field = {
                "name": select.get("name", ""),
                "type": "select",
                "id": select.get("id", ""),
                "required": select.has_attr("required"),
                "options": options,
                "multiple": select.has_attr("multiple")
            }
            form_data["fields"].append(field)

        # Process textareas
        for textarea in form.find_all("textarea"):
            field = {
                "name": textarea.get("name", ""),
                "type": "textarea",
                "id": textarea.get("id", ""),
                "placeholder": textarea.get("placeholder", ""),
                "value": textarea.text.strip(),
                "required": textarea.has_attr("required"),
                "rows": textarea.get("rows", ""),
                "cols": textarea.get("cols", "")
            }
            form_data["fields"].append(field)

        # Process buttons
        for button in form.find_all("button"):
            field = {
                "name": button.get("name", ""),
                "type": button.get("type", "button"),
                "id": button.get("id", ""),
                "value": button.get("value", ""),
                "text": button.text.strip()
            }
            form_data["fields"].append(field)

        forms.append(form_data)

    # Extract input fields outside forms
    standalone_fields = []
    for inp in soup.find_all("input", recursive=False):
        field = {
            "name": inp.get("name", ""),
            "type": inp.get("type", "text"),
            "id": inp.get("id", ""),
            "value": inp.get("value", ""),
            "placement": "standalone"
        }
        standalone_fields.append(field)

    # Extract buttons/actions
    actions = []
    for btn in soup.find_all("button"):
        action = {
            "text": btn.text.strip(),
            "type": btn.get("type", "button"),
            "id": btn.get("id", ""),
            "class": btn.get("class", []),
            "data_attributes": {attr.replace("data-", ""): btn[attr] for attr in btn.attrs if attr.startswith("data-")}
        }
        actions.append(action)

    # Also capture <a> elements with role="button"
    for a in soup.find_all("a", attrs={"role": "button"}):
        action = {
            "text": a.text.strip(),
            "href": a.get("href", ""),
            "id": a.get("id", ""),
            "class": a.get("class", []),
            "type": "link-button"
        }
        actions.append(action)

    # Extract links
    links = {}
    for a in soup.find_all("a", href=True):
        href = a.get("href")
        text = a.text.strip()
        if href and text:
            links[href] = {
                "text": text,
                "title": a.get("title", ""),
                "target": a.get("target", ""),
                "rel": a.get("rel", "")
            }

    # Extract scripts
    scripts = []
    for script in soup.find_all("script"):
        script_type = script.get("type", "")
        if script.string and script_type != "application/ld+json":  # Exclude JSON-LD
            # Only store script src or a short preview of inline script
            if script.get("src"):
                scripts.append({"src": script.get("src"), "type": script_type})
            else:
                # Only store a preview of inline scripts
                script_content = script.string.strip()
                preview = script_content[:100] + "..." if len(script_content) > 100 else script_content
                scripts.append({"inline": preview, "type": script_type})

    # Create a page summary (first 100 words)
    text_content = soup.get_text().strip()
    words = text_content.split()
    summary = " ".join(words[:100]) + ("..." if len(words) > 100 else "")

    return {
        "title": title,
        "meta_tags": meta_tags,
        "headings": headings[:5],  # First 5 headings
        "forms": forms,
        "fields": standalone_fields,
        "actions": actions,
        "links": links,
        "scripts": scripts,
        "summary": summary
    }


# Record user action
def record_action(url, metadata, content, referrer=None):
    if url not in flows:
        flows[url] = {"metadata": metadata, "content": content}

    # Get current session ID
    session_id = None
    from database.history_manager import history_manager
    if history_manager.current_session:
        session_id = history_manager.current_session.id

    # Store in databases with explicit session ID
    store_in_neo4j(url, metadata, referrer, session_id)
    store_in_pgvector(url, content, metadata, session_id)


# Capture all tabs and windows
def capture_all_tabs():
    """
    Switches through all window handles to capture URL + content and
    ensures action listeners are installed on each page. Also drains any pending actions.
    Returns (results, current_url) where results is a list of dicts:
      { "url": <url>, "content": <html>, "is_new": bool, "events": [<action dicts>] }
    """
    global browser, all_windows

    current_handle = browser.current_window_handle
    current_url = browser.current_url
    results = []

    try:
        # Check for new windows
        current_handles = set(browser.window_handles)
        new_handles = current_handles - all_windows
        all_windows = current_handles

        # Process all windows
        for handle in browser.window_handles:
            try:
                # Switch to this window
                browser.switch_to.window(handle)

                # Ensure our JS listeners are in place
                inject_action_listeners()

                # Drain any pending actions from this tab
                pending_actions = drain_action_queue() or []

                # Get the URL and content
                url = browser.current_url
                html_content = browser.page_source

                # Skip about:blank pages
                if url == "about:blank":
                    # Still process events if any were captured
                    if pending_actions:
                        process_new_actions(url, pending_actions)
                    continue

                results.append({
                    "url": url,
                    "content": html_content,
                    "is_new": handle in new_handles,
                    "events": pending_actions
                })
            except Exception as e:
                print(f"Error capturing tab {handle}: {e}")
    except Exception as e:
        print(f"Error in tab capture: {e}")
    finally:
        # Switch back to original window
        try:
            browser.switch_to.window(current_handle)
        except:
            # If original window is closed, switch to the first available
            if browser.window_handles:
                browser.switch_to.window(browser.window_handles[0])

    return results, current_url


# Check and process alerts/popups
def check_alerts():
    global browser

    try:
        # Try to switch to an alert with a very short timeout
        alert = WebDriverWait(browser, 0.5).until(EC.alert_is_present())
        alert_text = alert.text

        # Record the alert
        url = browser.current_url
        alert_content = f"<html><body><h1>Alert on {url}</h1><p>{alert_text}</p></body></html>"
        alert_metadata = {
            "title": f"Alert on {url}",
            "meta_tags": {},
            "headings": ["Alert"],
            "fields": [],
            "actions": ["OK", "Cancel"],
            "forms": [],
            "links": {},
            "summary": alert_text,
            "is_alert": True
        }

        # Record this as a special type of action
        alert_url = f"{url}#alert-{int(time.time())}"
        record_action(alert_url, alert_metadata, alert_content, url)
        signals.update_status.emit(f"Captured alert: {alert_text[:30]}...")

        # Accept the alert and continue
        alert.accept()
        return True
    except:
        return False


# Continuously capture web actions
def capture_web_actions():
    global browser, stop_capturing, TARGET_WEBSITE, all_windows

    if not TARGET_WEBSITE.startswith(('http://', 'https://')):
        TARGET_WEBSITE = 'https://' + TARGET_WEBSITE

    # Start by visiting the target website
    try:
        if browser is None or not is_browser_alive():
            signals.error.emit("Browser Error", "Browser is not running. Please start the browser first.")
            return

        browser.get(TARGET_WEBSITE)

        # Update UI
        signals.update_status.emit(f"Opened target website: {TARGET_WEBSITE}")
        print(f"✓ Opened target website: {TARGET_WEBSITE}")

        # Ensure listeners installed on the initial page
        inject_action_listeners()

        # Store initial page
        url = browser.current_url
        html_content = browser.page_source
        metadata = extract_metadata(html_content)
        record_action(url, metadata, html_content)
        signals.update_status.emit(f"Captured initial page: {url}")

        last_url = url
        last_content_hash = hash(html_content)
        processed_urls = {url: last_content_hash}

        # Continuously monitor for page changes
        while not stop_capturing:
            # Check if browser is still active
            if not is_browser_alive():
                signals.error.emit("Browser Error", "Browser window was closed")
                break

            # Check for alerts first
            if check_alerts():
                continue

            try:
                # Capture all tabs/windows (includes draining action logs from each tab)
                tabs_data, current_url = capture_all_tabs()

                for tab_data in tabs_data:
                    tab_url = tab_data["url"]
                    html_content = tab_data["content"]
                    content_hash = hash(html_content)

                    # Process any newly captured actions for this tab
                    events = tab_data.get("events") or []
                    if events:
                        process_new_actions(tab_url, events)

                    # If this is a new URL or content has changed
                    if tab_url not in processed_urls or processed_urls[tab_url] != content_hash:
                        metadata = extract_metadata(html_content)

                        # Determine referrer
                        referrer = None
                        if tab_data.get("is_new", False):
                            referrer = last_url
                        elif tab_url in processed_urls:
                            # Self-referrer for content updates
                            referrer = tab_url

                        # Record the action
                        record_action(tab_url, metadata, html_content, referrer)

                        # Update status
                        if tab_url not in processed_urls:
                            signals.update_status.emit(f"Captured new page: {tab_url}")
                            print(f"✓ Captured new page: {tab_url}")
                        else:
                            signals.update_status.emit(f"Updated page: {tab_url}")
                            print(f"✓ Updated page content: {tab_url}")

                        # Ensure listeners are installed on new/updated page
                        inject_action_listeners()

                        # Update tracking
                        processed_urls[tab_url] = content_hash

                # Update last URL if changed
                if current_url != last_url:
                    last_url = current_url

                # Brief pause to avoid high CPU usage
                time.sleep(0.5)

            except Exception as e:
                # Handle WebDriver exceptions that can occur if the page is navigating
                print(f"Temporary error in capture loop: {e}")
                time.sleep(1)  # Give browser time to settle
                if not is_browser_alive():
                    break

    except Exception as e:
        print(f"Error in capture thread: {e}")
        signals.error.emit("Capture Error", f"Error capturing web actions: {e}")

    signals.update_status.emit("Capture thread stopped")


# Start the capture process
def start_capturing(target_url):
    global TARGET_WEBSITE, stop_capturing, capture_thread, all_windows

    TARGET_WEBSITE = target_url
    stop_capturing = False

    # Make sure we have a proper URL
    if not TARGET_WEBSITE.startswith(('http://', 'https://')):
        TARGET_WEBSITE = 'https://' + TARGET_WEBSITE

    # Get current window handles
    try:
        all_windows = set(browser.window_handles)
    except Exception as e:
        print(f"Error getting window handles: {e}")
        all_windows = set()

    # Navigate to the target website
    try:
        browser.get(TARGET_WEBSITE)
        print(f"Successfully navigated to {TARGET_WEBSITE}")
    except Exception as e:
        print(f"Error navigating to {TARGET_WEBSITE}: {e}")
        signals.error.emit("Navigation Error", f"Could not navigate to {TARGET_WEBSITE}: {e}")
        return None

    # Start capturing thread
    capture_thread = threading.Thread(target=capture_web_actions, daemon=True)
    capture_thread.start()

    return capture_thread


# Stop the capture process
def stop_capturing_process():
    global stop_capturing
    stop_capturing = True

    # Wait for thread to end
    if capture_thread and capture_thread.is_alive():
        capture_thread.join(timeout=2)
