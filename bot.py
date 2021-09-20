import datetime
import time
import pandas as pd
import pandas_ta as ta
from datetime import timedelta
import numpy as np
from alpaca_trade_api.rest import REST


APCA_API_KEY_ID = 'replace with yours'
APCA_API_SECRET_KEY = 'replace with yours'
APCA_API_BASE_URL = r'https://paper-api.alpaca.markets' # paper trading


class market_scalper():
    '''Defines scalp trading obj'''

    def __init__(self):
        self.api = REST(key_id=APCA_API_KEY_ID, secret_key=APCA_API_SECRET_KEY, base_url=APCA_API_BASE_URL)
        self.all_tickers = []
        self.trending_tickers = []
        self.buyable_tickers = []
        self.sellable_tickers = []
        self.price_data = {}
        self.current_holdings = []

    def __enter__(self):
        '''Permit WITH instantiation'''
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        '''Cleanup when object is destroyed'''
        return

    def close(self):
        '''Cleanup when object is destroyed'''
        self._liquidate_holdings()
        self.__exit__(None, None, None)
        return

    def update(self):
        if self.all_tickers == []:
            self._get_global_trending_tickers()
        if self.all_tickers == []:
            return
        self._get_local_trending_stocks()
        self._get_tradeable_stocks()
        self._sell_stocks()
        self._buy_stocks()
        return

    def update_global_ticker_list(self):
        self._get_global_trending_tickers()
        return

    def is_market_open(self):
        '''Use Alpaca Api to determine if market is open for the day'''
        return self.api.get_clock().is_open

    def __chunk_list(self, in_list, size):
        '''break stock list into querable chunks of length size'''
        return [in_list[i:i + size] for i in range(0, len(in_list), size)]

    def __is_mo_trend_pass(self, df_60_min):
        '''Fxn determins if monthly 1 hr data is trending above 20 SMA, 20 SMA > 50 SMA, and have higher closes [monthly 60 min chart]'''
        sma_20 = ta.sma(df_60_min["close"], length=20)
        sma_50 = ta.sma(df_60_min["close"], length=50)
        last_sma_20 = sma_20.array[-1]
        last_sma_50 = sma_50.array[-1]
        last_close = df_60_min['close'][-1]
        prior_close = df_60_min['close'][-2]
        sma_uptrend = True if (last_sma_50 < last_sma_20) else False
        price_uptrend = True if (last_sma_20 < last_close) else False
        candle_uptrend = True if (prior_close <= last_close) else False
        return True if False not in [sma_uptrend, price_uptrend, candle_uptrend] else False

    def __is_stock_buyable(self, df_15_min):
        '''Fxn determins if stock is trading below 15min CC1 -100 mark (undervalued)'''
        cci = df_15_min.ta.cci(length=20)
        cci_lst = list(cci.array)
        if (cci_lst[-2] < -100 and cci_lst[-1] > -100) or (cci_lst[-2] < 100 and cci_lst[-1] > 100):
            return True
        else:
            return False

    def __is_stock_sellable(self, df_15_min):
        '''Fxn determins if stock is trading above 15min CC1 100 mark (overvalued)'''
        cci = df_15_min.ta.cci(length=20)
        cci_lst = list(cci.array)
        if (cci_lst[-2] > 100 and cci_lst[-1] < 100) or (cci_lst[-2] > -100 and cci_lst[-1] < -100):
            return True
        else:
            return False

    def __calc_stop_limit(self, df_15_min):
        '''Calc stop limit price'''
        buy_price = df_15_min['close'][-1]
        stop_limit = buy_price * (1.005)
        return np.ceil(stop_limit * 100) / 100

    def __is_pass_stop_limit(self, df_15_min):
        buy_price = df_15_min['close'][-1]
        stop_limit = self.__calc_stop_limit(df_15_min)
        return True if buy_price * 1.001 <= stop_limit else False

    def _get_local_trending_stocks(self):
        '''Get list of stocks that are trending upwards'''
        current_date = datetime.datetime.now()
        start_time = (current_date - timedelta(days=40)).strftime('%Y-%m-%d')
        end_time = (current_date).strftime('%Y-%m-%d')
        trending_tickers = []

        symbol_set = self.__chunk_list(self.all_tickers, 100)
        print('\nFinding Trending Stocks...')
        for chunk in symbol_set:
            all_data = self.api.get_barset(chunk, timeframe='15Min', start=start_time, end=end_time, limit=600).df
            for symbol in chunk:
                print(f'Symbol: {symbol}')
                df_15_min = all_data[symbol].dropna()
                if df_15_min.shape[0] == 0:
                    continue
                df_calc = df_15_min.resample("1H", level=0).agg([('open', 'first'), ('close', 'last'), ('high', 'max'), ('low', 'min'), ('volume', 'sum')]).dropna()
                df_60_min = pd.DataFrame({'open': df_calc['open']['open'],'high': df_calc['high']['high'], 'low': df_calc['low']['low'], 'close': df_calc['close']['close'], 'volume': df_calc['volume']['volume']}).dropna()
                if self.__is_mo_trend_pass(df_60_min):
                    trending_tickers.append(symbol)
        df = pd.DataFrame({'Symbols': trending_tickers})
        df.to_csv('short_ticker_list.csv')
        self.current_holdings = [position.symbol for position in self.api.list_positions()]
        self.trending_tickers = list(set(trending_tickers + self.current_holdings))  # add owned tickers so they are constantly monitored
        return

    def _get_tradeable_stocks(self):
        '''determine buyable stocks within trending stocks using cci analysis'''
        buyable_tickers = []
        sellable_tickers = []
        buy_price = []
        sell_price = []
        profit = []
        price_data = {}
        current_date = datetime.datetime.now()
        start_time = (current_date - timedelta(days=40)).strftime('%Y-%m-%d')
        end_time = (current_date).strftime('%Y-%m-%d')
        self.current_holdings = [position.symbol for position in self.api.list_positions()]

        symbol_set = self.__chunk_list(self.trending_tickers, 100)
        print('Finding Tradeable Stocks...')
        for chunk in symbol_set:
            all_data = self.api.get_barset(chunk, timeframe='15Min', start=start_time, end=end_time, limit=600).df
            for symbol in chunk:
                print(f'Symbol: {symbol}')
                df_15_min = all_data[symbol].dropna()
                if df_15_min.shape[0] == 0:
                    continue
                if symbol not in self.current_holdings and self.__is_stock_buyable(df_15_min):
                    if self.__is_pass_stop_limit(df_15_min):
                        buyable_tickers.append(symbol)
                        buy_price.append(df_15_min['close'][-1])
                        sell_price.append(self.__calc_stop_limit(df_15_min))
                        profit.append(sell_price[-1] - buy_price[-1])
                        price_data[symbol] = {'buy': buy_price[-1], 'sell': sell_price[-1], 'profit': profit[-1]}
                elif symbol in self.current_holdings and self.__is_stock_sellable(df_15_min):
                    sellable_tickers.append(symbol)
                else:
                    continue

        self.price_data = price_data
        current_time = datetime.datetime.now().isoformat()
        print(f"\nFound {len(buyable_tickers)} buyable tickers and {len(sellable_tickers)} sellable tickers\n")
        with open("transactions.csv", "a") as ofile:
            for i in range(len(buyable_tickers)):
                ofile.write(f'{current_time},{buyable_tickers[i]},{buy_price[i]},{sell_price[i]},{profit[i]}\n')
        self.buyable_tickers = buyable_tickers
        self.sellable_tickers = sellable_tickers
        return

    def _buy_stocks(self):
        if len(self.buyable_tickers) == 0:
            return
        account = self.api.get_account()
        buying_power = account.buying_power
        open_orders = [order.symbol for order in self.api.list_orders(status='open')]
        current_positions = [position.symbol for position in self.api.list_positions()]
        owned_tickers = list(set(current_positions + open_orders))

        for i in reversed(range(len(self.buyable_tickers))):
            if self.buyable_tickers[i] in owned_tickers:
                self.buyable_tickers.pop(i)

        if len(self.buyable_tickers) == 0:
            return

        max_buy_per_ticker = min([float(buying_power)/len(self.buyable_tickers), 5000])
        non_buyable = 0
        for ticker in self.buyable_tickers:
            buy_price = float(self.api.get_latest_quote(ticker).ap)
            buy_price = buy_price if buy_price > 0.00 else self.price_data[ticker]['buy']
            buy_price = np.floor((buy_price + 0.01)*100)/100
            sell_price = self.price_data[ticker]['sell']
            qty = int(np.floor(max_buy_per_ticker/buy_price))
            if qty > 0 and np.floor((sell_price - buy_price)*100)/100 > 0.01:
                try:
                    # submiting stop limit at once:
                    # r = self.api.submit_order(side="buy", symbol=ticker, type="limit", limit_price=buy_price, qty=qty, time_in_force="day", order_class="oto", take_profit={"limit_price": sell_price})
                    # simple buy
                    r = self.api.submit_order(side="buy", symbol=ticker, type="limit", limit_price=buy_price, qty=qty, time_in_force="day")
                except Exception as e:
                    pass
            else:
                non_buyable += 1
                max_buy_per_ticker = float(buying_power)/(len(self.buyable_tickers)-non_buyable)
        return

    def _sell_stocks(self):
        owned_tickers = [(position.symbol, position.qty) for position in self.api.list_positions()]

        if len(owned_tickers) == 0:
            return

        for ticker, qty in owned_tickers:
            if ticker not in self.sellable_tickers:
                continue
            try:
                sell_price = float(self.api.get_latest_quote(ticker).ap)
                sell_price = np.floor((sell_price - 0.01) * 100) / 100
                r = self.api.submit_order(side="sell", symbol=ticker, type="limit", limit_price=sell_price, qty=qty, time_in_force="day")
            except Exception as e:
                pass
        return

    def _liquidate_holdings(self):
        owned_tickers = [position.symbol for position in self.api.list_positions()]
        self.sellable_tickers = owned_tickers
        self.api.cancel_all_orders()
        self._sell_stocks()
        return

    def _get_global_trending_tickers(self):
        '''Get list of stocks that are trending upwards on longer time scales. Build list of tradable stocks'''

        def __linear_fit(x, y):
            '''Least squares linear fit calculation.  Ruturns tuple(slope, intercept)'''
            x = np.array(x)
            y = np.array(y)
            slope = (((np.average(x) * np.average(y)) - np.average(x * y)) / (
                        (np.average(x) * np.average(x)) - np.average(x * x)))
            intercept = np.average(y) - slope * np.average(x)
            return slope, intercept

        def __calculate_avg_dialy_range_percent(df, look_back_days):
            '''Calculate average daily stock movement over days specified'''
            highs = np.array(df['high'][(look_back_days * -1):])
            lows = np.array(df['low'][(look_back_days * -1):])
            delta = (highs - lows) / lows * 100
            return np.average(delta)

        current_date = datetime.datetime.now()
        start_time = (current_date - timedelta(days=40)).strftime('%Y-%m-%d')
        end_time = (current_date).strftime('%Y-%m-%d')
        trending_tickers = []
        trending_slope = []
        trending_range = []

        col_list = ["Symbols"]
        df = pd.read_csv("full_ticker_list.csv", usecols=col_list)
        all_tickers = df['Symbols'].tolist()

        symbol_set = [all_tickers[i:i + 100] for i in range(0, len(all_tickers), 100)]
        print('\nFinding Trending Stocks...')
        for chunk in symbol_set:
            all_data = self.api.get_barset(chunk, timeframe='day', start=start_time, end=end_time, limit=100).df
            for symbol in chunk:
                print(f'Symbol: {symbol}')
                df_1_day = all_data[symbol].dropna()

                if df_1_day.shape[0] == 0:
                    continue

                sma_20 = ta.sma(df_1_day["close"], length=20)
                sma_50 = ta.sma(df_1_day["close"], length=50)
                last_sma_20 = sma_20.array[-1]
                last_sma_50 = sma_50.array[-1]
                last_close = df_1_day['close'][-1]
                slope_percent_per_day = \
                __linear_fit([1, 2, 3, 4, 5], (df_1_day['close'][-5:] / df_1_day['close'][-5]).array)[0] * 100  # normalize price to percent for global comparison
                average_daily_range = __calculate_avg_dialy_range_percent(df_1_day, 5)
                sma_uptrend = True if (last_sma_50 < last_sma_20) else False
                price_uptrend = True if (last_sma_20 < last_close) else False
                divergent_moving_avg = True if (sma_20.array[-1] - sma_50.array[-1]) > (
                            sma_20.array[-2] - sma_50.array[-2]) else False
                five_day_slope_above_co = True if slope_percent_per_day >= 0.15 else False
                average_daily_range_above_co = True if average_daily_range >= 2.5 else False
                if sma_uptrend and price_uptrend and divergent_moving_avg and five_day_slope_above_co and average_daily_range_above_co:
                    trending_tickers.append(symbol)
                    trending_slope.append(slope_percent_per_day)
                    trending_range.append(average_daily_range)

        return_dict = {'Symbols': trending_tickers, '%_per_day': trending_slope, 'Average_%daily_range': trending_range}
        df = pd.DataFrame(return_dict)
        df.sort_values('%_per_day', ascending=False, inplace=True)
        df.reset_index(drop=True, inplace=True)
        df.to_csv('ticker_list.csv')
        self.all_tickers = trending_tickers
        return



def run_bot():
    scalper = market_scalper()
    while True:
        now_UTC = datetime.datetime.utcnow()  # 09:30EST = 13:30UTC ; 16:00EST = 20:00UTC
        market_open = scalper.api.get_clock().is_open
        if market_open:
            scalper.update()
            print('5 min pause...')
            time.sleep(300)
        elif not market_open and now_UTC.hour + (now_UTC.minute / 60) < 13.59:
            # if market is not yet open, wait short period and check again
            print('Market not open, trying again in 60s')
            time.sleep(60)
        elif now_UTC.hour + (now_UTC.minute / 60) >= 19.5:
            # if market is closed, close class
            print('Market Closed: cleaning up...')
            scalper.close()
            break
    print('Script done for the day, exiting now.')
    return


if __name__ == '__main__':
    print('start')
    run_bot()
    print('complete...')
