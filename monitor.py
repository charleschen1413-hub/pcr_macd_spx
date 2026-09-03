name: Daily PCR MACD Monitor

on:
  schedule:
    - cron: '30 21 * * 2-6'
  workflow_dispatch: 

jobs:
  run-monitor:
    runs-on: ubuntu-latest
    permissions:
      contents: write

    steps:
      - name: Checkout Repository
        uses: actions/checkout@v3

      - name: Set up Python
        uses: actions/setup-python@v4
        with:
          python-version: '3.10'

      - name: Install Dependencies
        run: |
          pip install pandas requests pytz yfinance

      - name: Run PCR Monitor Script
        env:
          TELEGRAM_BOT_TOKEN: ${{ secrets.TELEGRAM_BOT_TOKEN }}
          TELEGRAM_CHAT_ID: ${{ secrets.TELEGRAM_CHAT_ID }}
        run: python monitor.py

      - name: Commit and Push Updated CSV
        run: |
          git config --global user.name 'github-actions[bot]'
          git config --global user.email 'github-actions[bot]@users.noreply.github.com'
          git add pcr_from2011.csv
          git diff --quiet && git diff --staged --quiet || (git commit -m "Auto-update daily PCR data" && git push)
