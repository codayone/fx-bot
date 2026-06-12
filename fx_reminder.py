from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from io import StringIO

import pandas as pd
from datetime import datetime
import os

print("Script started ✅")


import smtplib
from email.mime.text import MIMEText
import time

def send_email(rate, change, yesterday_rate, overnight_rate, yesterday_overnight_rate, overnight_changed):

    # FX direction
    if change > 0:
        direction = "↑"
    elif change < 0:
        direction = "↓"
    else:
        direction = "-"

    fx_alert = abs(change) > 0.005

    if fx_alert:
        fx_status = "🚨 ALERT: Significant FX movement (>0.5%)"
    else:
        fx_status = "✅ Normal FX movement"

    if overnight_changed:
        overnight_status = f"🚨 ALERT: Rate changed from {yesterday_overnight_rate:.2f}% to {overnight_rate:.2f}%"
    else:
        overnight_status = f"✅ No change ({overnight_rate:.2f}%)"

    # ✅ Email body (text version for simplicity)
    body = f"""
<html>
<body>

<p><b>DAILY MARKET REPORT</b></p>

<p><b>1) SGD/MYR</b></p>

<p>
Today: <b>{rate:.4f}</b><br>
Yesterday: {yesterday_rate:.4f}<br><br>

Change: {direction} {round(change*100,4)}%<br><br>

{fx_status}
</p>

<p><b>2) Malaysia Overnight Rate</b></p>

<p>
Today: <b>{overnight_rate:.2f}%</b><br>
Yesterday: {yesterday_overnight_rate:.2f}%<br><br>

{overnight_status}
</p>

<p>----------------------------------<br>
Auto-generated report</p>

</body>
</html>
"""

    msg = MIMEText(body, "html")
    msg["Subject"] = "Daily FX Report: SGD/MYR"

    # ✅ THIS IS YOUR BOT DISPLAY NAME
    msg["From"] = "FX Bot <tangsuancoco.tan@dayonedc.com>"

    msg["To"] = "tangsuancoco.tan@dayonedc.com"

    # ✅ get from GitHub secrets later
    email = os.getenv("EMAIL")
    password = os.getenv("PASSWORD")

    print("EMAIL:", email)
    print("PASSWORD is None?", password is None)


    server = smtplib.SMTP("smtp.office365.com", 587)
    server.starttls()
    server.login(email, password)
    server.send_message(msg)
    server.quit()

    print("✅ Email sent successfully")


# =========================
# SETUP BROWSER
# =========================
options = Options()
options.add_argument("--disable-gpu")
options.add_argument("--no-sandbox")
options.add_argument("--headless=new")
options.add_argument("--disable-dev-shm-usage")

driver = webdriver.Chrome(options=options)

try: 
    # =========================
    # 1) XE FX RATE (SGD/MYR)
    # =========================
    xe_url = "https://www.xe.com/en-us/currencyconverter/convert/?Amount=1&From=SGD&To=MYR"
    driver.get(xe_url)

    rate_el = None  # ✅ initialize
    
    for i in range(3):
        try:
            rate_el = WebDriverWait(driver, 60).until(
                EC.visibility_of_element_located(("YOUR_LOCATOR_HERE"))
            )
            break
        except Exception as e:
            print(f"Retry {i+1} failed:", e)
            import time
            time.sleep(5)
    
    if rate_el is None:
        raise Exception("❌ FX rate element not found after retries")

    rate_text = rate_el.text
    print("Current FX text:", rate_text)

    rate = float(rate_text.split("=")[1].split("MYR")[0].strip())
    print("Numeric FX rate:", rate)



    # =========================
    # 2) BNM INTEREST RATE PART
    # =========================

    from io import StringIO
    import urllib.request
    
    bnm_url = "https://financialmarkets.bnm.gov.my/data-download-bnm-money-market-operations"
    
    headers = {
        "User-Agent": "Mozilla/5.0"
    }
    
    req = urllib.request.Request(bnm_url, headers=headers)
    html = urllib.request.urlopen(req).read().decode("utf-8")
    
    tables = pd.read_html(StringIO(html))


    target_df = None

    for i, tbl in enumerate(tables):
        temp = tbl.copy()

        # Flatten / clean column names
        temp.columns = [
            " ".join([str(x).strip() for x in col]).replace("\n", " ").strip()
            if isinstance(col, tuple)
            else str(col).replace("\n", " ").strip()
            for col in temp.columns
        ]

        print(f"Checking BNM table {i}: {temp.columns.tolist()}")

        cols_lower = [c.lower() for c in temp.columns]

        if any("date" in c for c in cols_lower) and any("overnight" in c for c in cols_lower):
            target_df = temp
            print(f"✅ Using BNM table {i}")
            break

    if target_df is None:
        raise Exception("Could not find BNM table containing Date and Overnight columns.")

    date_col = next(c for c in target_df.columns if "date" in c.lower())
    overnight_col = next(c for c in target_df.columns if "overnight" in c.lower())

    target_df[date_col] = pd.to_datetime(target_df[date_col], errors="coerce", dayfirst=True)
    target_df[overnight_col] = pd.to_numeric(target_df[overnight_col], errors="coerce")

    target_df = target_df.dropna(subset=[date_col, overnight_col])
    target_df = target_df.sort_values(date_col)

    overnight_rate = float(target_df.iloc[-1][overnight_col])
    print("✅ Current Malaysia Overnight Rate:", overnight_rate)

finally:
    driver.quit()

import pandas as pd
import os
from datetime import datetime
import pytz

# =========================
# TIMEZONE
# =========================
sgt = pytz.timezone("Asia/Singapore")
now = datetime.now(sgt)

file_path = "market_data.csv"

# =========================
# YOUR SCRAPED DATA
# =========================
# assume you already have:
# rate
# overnight_rate

# =========================
# NEW ENTRY (with timestamp)
# =========================
new_data = pd.DataFrame({
    "Timestamp": [now.strftime("%Y-%m-%d %H:%M:%S")],
    "MYR_per_SGD": [rate],
    "Malaysia_Overnight_Rate": [overnight_rate]
})

# =========================
# LOAD EXISTING DATA
# =========================
if os.path.exists(file_path):
    df = pd.read_csv(file_path)
    df["Timestamp"] = pd.to_datetime(df["Timestamp"])
else:
    df = pd.DataFrame(columns=[
        "Timestamp", 
        "MYR_per_SGD", 
        "Malaysia_Overnight_Rate"
    ])

# =========================
# CALCULATE CHANGE (vs LAST RUN)
# =========================
if not df.empty:
    df = df.sort_values("Timestamp")

    prev_rate = float(df.iloc[-1]["MYR_per_SGD"])
    change_pct = ((rate - prev_rate) / prev_rate) * 100
else:
    prev_rate = None
    change_pct = None

# =========================
# APPEND NEW DATA (NO DELETING)
# =========================
df = pd.concat([df, new_data], ignore_index=True)

# =========================
# SAVE
# =========================
df.to_csv(file_path, index=False)

print("Saved to CSV ✅")
print(df.tail())

# =========================
# FORMAT OUTPUT
# =========================
if change_pct is None:
    change_text = "N/A"
else:
    if change_pct > 0:
        arrow = "▲"
    elif change_pct < 0:
        arrow = "▼"
    else:
        arrow = "➜"

    change_text = f"{arrow} {change_pct:.4f}%"

print("Previous Rate:", prev_rate)
print("Current Rate:", rate)
print("Change:", change_text)

# =========================
# CALCULATE FX CHANGE + RATE CHANGE
# =========================
if len(df) > 1:
    today_rate = df.iloc[-1]["MYR_per_SGD"]
    yesterday_rate = df.iloc[-2]["MYR_per_SGD"]
    change = (today_rate - yesterday_rate) / yesterday_rate

    today_overnight_rate = df.iloc[-1]["Malaysia_Overnight_Rate"]
    yesterday_overnight_rate = df.iloc[-2]["Malaysia_Overnight_Rate"]
    overnight_changed = float(today_overnight_rate) != float(yesterday_overnight_rate)

else:
    change = 0.0
    yesterday_rate = rate
    yesterday_overnight_rate = overnight_rate
    overnight_changed = False

print(f"Daily FX change: {round(change*100, 4)}%")
print(f"Malaysia Overnight Rate changed today? {overnight_changed}")


# =========================
# SEND EMAIL
# =========================
send_email(
    rate=rate,
    change=change,
    yesterday_rate=yesterday_rate,
    overnight_rate=overnight_rate,
    yesterday_overnight_rate=yesterday_overnight_rate,
    overnight_changed=overnight_changed
)
