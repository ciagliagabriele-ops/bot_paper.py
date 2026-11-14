name: Bot Dual Momentum Alpaca

on:
  schedule:
    - cron: '40 14 * * 1'
  workflow_dispatch:

jobs:
  esegui-bot:
    runs-on: ubuntu-latest
    steps:
      - name: Scarica codice
        uses: actions/checkout@v4

      - name: Configura Python
        uses: actions/setup-python@v5
        with:
          python-version: '3.11'

      - name: Installa librerie
        run: pip install -r requirements.txt

      - name: Avvia strategia
        env:
          ALPACA_API_KEY: ${{ secrets.ALPACA_API_KEY }}
          ALPACA_SECRET_KEY: ${{ secrets.ALPACA_SECRET_KEY }}
        run: python bot_paper.py
