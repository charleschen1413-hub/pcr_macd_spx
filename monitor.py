import os
import requests
import pandas as pd
from datetime import datetime
import pytz
import yfinance as yf
import traceback
from io import StringIO

# --- 策略參數設定 ---
FAST, SLOW, SIGNAL = 20, 74, 36
CSV_FILE = 'pcr_from2011.csv'
BOT_TOKEN = os.environ.get('TELEGRAM_BOT_TOKEN')
CHAT_ID = os.environ.get('TELEGRAM_CHAT_ID')

def get_today_equity_pcr():
    """三重繞道機制，確保絕對能抓到 PCR 數據"""
    
    # 方法 1: yfinance 搭配自訂 Session (偽裝真實瀏覽器)
    try:
        session = requests.Session()
        session.headers.update({'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/120.0.0.0 Safari/537.36'})
        ticker = yf.Ticker("^CPCE", session=session)
        hist = ticker.history(period="5d")
        if not hist.empty:
            last_close = hist['Close'].dropna().iloc[-1]
            return round(float(last_close), 2)
    except Exception as e:
        print(f"方法1(yfinance)失敗: {e}")

    # 方法 2: 透過 AllOrigins 代理直連 Yahoo API (完美繞過 GitHub IP 封鎖)
    try:
        url = "https://api.allorigins.win/raw?url=https://query1.finance.yahoo.com/v8/finance/chart/%5ECPCE?range=5d&interval=1d"
        res = requests.get(url, timeout=15)
        data = res.json()
        closes = data['chart']['result'][0]['indicators']['quote'][0]['close']
        valid_closes = [c for c in closes if c is not None]
        if valid_closes:
            return round(float(valid_closes[-1]), 2)
    except Exception as e:
        print(f"方法2(Yahoo Proxy)失敗: {e}")

    # 方法 3: 透過 AllOrigins 代理抓取 Cboe 官網 HTML 表格
    try:
        url = "https://api.allorigins.win/raw?url=https://www.cboe.com/markets/us/options/market-statistics/daily/"
        res = requests.get(url, timeout=15)
        tables = pd.read_html(StringIO(res.text))
        df = tables[0]
        pcr_row = df[df[0] == 'EQUITY PUT/CALL RATIO']
        if not pcr_row.empty:
            return float(pcr_row.iloc[0, 1])
    except Exception as e:
        print(f"方法3(Cboe Proxy)失敗: {e}")
        
    return None

def send_telegram(text):
    """發送 Telegram 訊息"""
    if not BOT_TOKEN or not CHAT_ID:
        print("未設定 Telegram 密鑰，僅印出結果：")
        print(text)
        return
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    payload = {'chat_id': CHAT_ID, 'text': text, 'parse_mode': 'HTML'}
    requests.post(url, data=payload)

def main():
    try:
        today_pcr = get_today_equity_pcr()
        if today_pcr is None:
            send_telegram("⚠️ <b>PCR 監控系統異常</b>\n三種抓取通道(yfinance, Yahoo代理, Cboe代理)全數被擋，無法獲取今日數據。")
            return

        tz = pytz.timezone('US/Eastern')
        today_str = datetime.now(tz).strftime('%Y-%m-%d')

        # 讀取 CSV 並強制將所有欄位轉為小寫、去除空白 (防呆)
        df = pd.read_csv(CSV_FILE)
        df.columns = df.columns.str.lower().str.strip()

        if df['date'].iloc[-1] == today_str:
            df.loc[df.index[-1], 'pcr'] = today_pcr
        else:
            new_row = pd.DataFrame({'date': [today_str], 'pcr': [today_pcr]})
            df = pd.concat([df, new_row], ignore_index=True)
        
        # 存回 CSV 供 GitHub 儲存
        df.to_csv(CSV_FILE, index=False)

        # 計算 MACD
        df['EMA_Fast'] = df['pcr'].ewm(span=FAST, adjust=False).mean()
        df['EMA_Slow'] = df['pcr'].ewm(span=SLOW, adjust=False).mean()
        df['MACD'] = df['EMA_Fast'] - df['EMA_Slow']
        df['Signal'] = df['MACD'].ewm(span=SIGNAL, adjust=False).mean()
        df['Histogram'] = df['MACD'] - df['Signal']

        hist_today = df['Histogram'].iloc[-1]
        hist_yest = df['Histogram'].iloc[-2]
        
        # 根據邏輯設定動作
        signal_msg = "無 0 軸穿越 (維持現有不持倉狀態)"
        
        if hist_yest < 0 and hist_today > 0:
            signal_msg = "🟢 <b>Flag = 1</b> (MACD 向上穿越 0 軸)\n👉 策略設定：<b>若空倉則買空 (open_short)</b>\n⚠️ 執行動作：目前不持倉，<b>請進場建立 SPX_mini 空單！</b>"
        elif hist_yest > 0 and hist_today < 0:
            signal_msg = "🔴 <b>Flag = -1</b> (MACD 向下穿越 0 軸)\n👉 策略設定：<b>平空倉且反手買多 (reverse_long)</b>\n⚠️ 執行動作：目前不持倉，<b>請直接進場建立 SPX_mini 多單！</b>"

        msg = f"""📊 <b>PCR MACD({FAST},{SLOW},{SIGNAL}) 每日監控</b>
────────────────
🔹 <b>標的物</b>：SPX_mini
🔹 <b>目前狀態</b>：<b>不持倉 (Empty)</b>
────────────────
📅 日期：{today_str}
🔸 最新 Equity PCR：{today_pcr}
🔸 MACD 柱狀圖：{hist_today:.5f}

🚨 <b>今日訊號與動作：</b>
{signal_msg}"""

        send_telegram(msg)
        
    except Exception as e:
        # 如果 Python 執行期間發生任何錯誤，會直接把詳細錯誤代碼推送到你的 Telegram
        error_msg = f"⚠️ <b>Python 執行發生嚴重錯誤</b>\n<pre>{str(e)}</pre>\n{traceback.format_exc()[-500:]}"
        send_telegram(error_msg)
        raise e

if __name__ == "__main__":
    main()
