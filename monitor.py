import os
import requests
import pandas as pd
from datetime import datetime
import pytz

# --- 策略參數設定 ---
FAST, SLOW, SIGNAL = 20, 74, 36
CSV_FILE = 'pcr_from2011.csv'
BOT_TOKEN = os.environ.get('TELEGRAM_BOT_TOKEN')
CHAT_ID = os.environ.get('TELEGRAM_CHAT_ID')

def get_today_equity_pcr():
    """從 Yahoo Finance API 直接抓取 Cboe Equity Put/Call Ratio (^CPCE)"""
    # 抓取近 5 日資料，確保即使遇到美股休市也能正確取到最後一個交易日的數值
    url = "https://query1.finance.yahoo.com/v8/finance/chart/^CPCE?range=5d&interval=1d"
    headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'}
    try:
        res = requests.get(url, headers=headers)
        data = res.json()
        closes = data['chart']['result'][0]['indicators']['quote'][0]['close']
        # 過濾掉可能為 None 的空白報價
        valid_closes = [c for c in closes if c is not None]
        if valid_closes:
            return round(float(valid_closes[-1]), 2)
    except Exception as e:
        print(f"Yahoo API 抓取失敗: {e}")
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
    today_pcr = get_today_equity_pcr()
    if today_pcr is None:
        send_telegram("⚠️ <b>PCR 監控系統異常</b>\n無法從 Yahoo Finance 獲取今日數據。")
        return

    # 取得美東時間
    tz = pytz.timezone('US/Eastern')
    today_str = datetime.now(tz).strftime('%Y-%m-%d')

    # 讀取並更新 CSV 歷史資料
    df = pd.read_csv(CSV_FILE)
    if df['date'].iloc[-1] == today_str:
        df.loc[df.index[-1], 'pcr'] = today_pcr
    else:
        new_row = pd.DataFrame({'date': [today_str], 'pcr': [today_pcr]})
        df = pd.concat([df, new_row], ignore_index=True)
    
    # 存回 CSV 以便 GitHub Actions 更新檔案
    df.to_csv(CSV_FILE, index=False)

    # 計算 MACD 數值
    df['EMA_Fast'] = df['pcr'].ewm(span=FAST, adjust=False).mean()
    df['EMA_Slow'] = df['pcr'].ewm(span=SLOW, adjust=False).mean()
    df['MACD'] = df['EMA_Fast'] - df['EMA_Slow']
    df['Signal'] = df['MACD'].ewm(span=SIGNAL, adjust=False).mean()
    df['Histogram'] = df['MACD'] - df['Signal']

    hist_today = df['Histogram'].iloc[-1]
    hist_yest = df['Histogram'].iloc[-2]
    
    # 根據 json 檔的邏輯設定動作
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

if __name__ == "__main__":
    main()
