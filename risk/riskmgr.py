import MetaTrader5 as mt5
import requests
import pandas as pd
import numpy as np
import datetime

def initialize_mt5():
    if not mt5.initialize():
        raise RuntimeError(f"MetaTrader5 initialization failed, error code: {mt5.last_error()}")

def convert_to_account_currency(symbol, volume, price, account_currency):
    initialize_mt5()
    symbol_info = mt5.symbol_info(symbol)
    if not symbol_info:
        raise RuntimeError(f"Symbol {symbol} not found")
    contract_size = symbol_info.trade_contract_size
    exposure_base = volume * price * contract_size
    if symbol_info.currency_profit == account_currency:
        return exposure_base
    conversion_pair = f"{symbol_info.currency_profit}{account_currency}"
    conversion_rate = None
    try:
        if mt5.symbol_info(conversion_pair):
            conversion_rate = mt5.symbol_info_tick(conversion_pair).bid
    except Exception:
        conversion_rate = None
    if conversion_rate is None:
        reverse_pair = f"{account_currency}{symbol_info.currency_profit}"
        try:
            conversion_rate = 1 / mt5.symbol_info_tick(reverse_pair).ask
        except Exception:
            conversion_rate = None
    if conversion_rate is None:
        raise RuntimeError(f"Cannot find conversion rate for {symbol_info.currency_profit} to {account_currency}")
    return exposure_base * conversion_rate

def get_open_positions_weight():
    initialize_mt5()
    positions = mt5.positions_get()
    if positions is None:
        raise RuntimeError(f"Failed to retrieve positions, error code: {mt5.last_error()}")
    positions_df = pd.DataFrame(list(positions), columns=positions[0]._asdict().keys())
    balance = mt5.account_info().balance
    account_currency = mt5.account_info().currency
    if balance <= 0:
        raise ValueError("Account balance is zero or negative.")
    positions_df['volume'] = positions_df['volume'].astype(float)
    positions_df['price'] = positions_df['price_open'].astype(float)
    positions_df['exposure'] = positions_df.apply(
        lambda row: convert_to_account_currency(row['symbol'], row['volume'], row['price'], account_currency), axis=1
    )
    positions_df['direction'] = positions_df['type'].apply(lambda x: -1 if x == mt5.ORDER_TYPE_SELL else 1)
    positions_df['weight'] = (positions_df['exposure'] * positions_df['direction'] / balance).round(3)
    positions_df['weight_formatted'] = positions_df['weight'].apply(lambda x: f"{x: .0%}")
    return positions_df[['symbol', 'weight', 'weight_formatted', 'time']]

def get_monthly_statistics():
    DUPLIKUM_API_URL = "https://www.trade-copier.com/webservice/v4/reporting/getReporting.php"
    AUTH_USERNAME = "SaadFK"
    AUTH_TOKEN = "jExYzYwMzk1ZWJkZjgwN2JlYTM1ZTQ"
    now = datetime.datetime.now()
    response = requests.get(DUPLIKUM_API_URL, headers={"Auth-Username": AUTH_USERNAME, "Auth-Token": AUTH_TOKEN},
                            params={"month": now.month, "year": now.year, "limit": 1000})
    if response.status_code != 200:
        raise RuntimeError(f"Failed to fetch monthly statistics: {response.text}")
    stats_data = response.json().get('reporting', [])
    if not stats_data:
        raise ValueError("No reporting data found.")
    stats_df = pd.DataFrame(stats_data)
    account_currency = mt5.account_info().currency

    def convert_pnl(row):
        if row['currency'] == account_currency:
            return float(row['pnl'])
        conversion_pair = f"{row['currency']}{account_currency}"
        conversion_rate = None
        try:
            if mt5.symbol_info(conversion_pair):
                conversion_rate = mt5.symbol_info_tick(conversion_pair).bid
        except Exception:
            conversion_rate = None
        if conversion_rate is None:
            reverse_pair = f"{account_currency}{row['currency']}"
            try:
                conversion_rate = 1 / mt5.symbol_info_tick(reverse_pair).ask
            except Exception:
                conversion_rate = None
        if conversion_rate is None:
            raise RuntimeError(f"Cannot find conversion rate for {row['currency']} to {account_currency}")
        return float(row['pnl']) * conversion_rate

    if {'currency', 'pnl'}.issubset(stats_df.columns):
        stats_df['pnl_converted'] = stats_df.apply(convert_pnl, axis=1)
    else:
        raise KeyError("Missing required columns: 'currency' or 'pnl'")
    return stats_df['pnl_converted'].sum()

def calculate_beta_vs_benchmark():
    initialize_mt5()
    us500_data = mt5.copy_rates_from_pos("US500", mt5.TIMEFRAME_D1, 0, 3 * 252)
    if us500_data is None:
        raise RuntimeError(f"Failed to retrieve US500 data, error code: {mt5.last_error()}")
    us500_df = pd.DataFrame(us500_data)
    us500_df['return'] = us500_df['close'].pct_change()
    positions_df = get_open_positions_weight()
    betas = []
    for _, row in positions_df.iterrows():
        symbol = row['symbol']
        weight = row['weight']
        symbol_data = mt5.copy_rates_from_pos(symbol, mt5.TIMEFRAME_D1, 0, 3 * 252)
        if symbol_data is None:
            print(f"Failed to retrieve data for {symbol}, skipping.")
            continue
        symbol_df = pd.DataFrame(symbol_data)
        symbol_df['return'] = symbol_df['close'].pct_change()
        merged_df = pd.merge(symbol_df, us500_df, left_index=True, right_index=True, suffixes=("_symbol", "_benchmark"))
        covariance = np.cov(merged_df['return_symbol'].dropna(), merged_df['return_benchmark'].dropna())[0, 1]
        variance = np.var(merged_df['return_benchmark'].dropna())
        beta = covariance / variance
        betas.append(beta * weight)
    weighted_average_beta = sum(betas)
    return f"{round(weighted_average_beta, 1)}x"

if __name__ == "__main__":
    initialize_mt5()
    print("Open Positions and Weights:")
    print(get_open_positions_weight())
    print("Monthly Statistics:")
    print(get_monthly_statistics())
    print("Weighted Average Beta vs US500:")
    print(calculate_beta_vs_benchmark())
    mt5.shutdown()
