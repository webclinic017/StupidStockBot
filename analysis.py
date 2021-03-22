import pandas_ta as ta
from datetime import date
from datetime import timedelta
import yfinance as yf
import consolecontrol as console
import etrade as etd


class SwapTrader:
    def __init__(self, longTicker, shortTicker, minTradePercent, monitorInterval, useSwapStrategy, production=False):
        self.etrade = etd.Etrader(production=production)
        self.longTicker = longTicker
        self.shortTicker = shortTicker
        self.minTradeDeltaPercent = minTradePercent
        self.monitorInterval = monitorInterval
        self.useSwapStrategy = useSwapStrategy
        self.longData = None
        self.shortData = None
        self.oneYearLongData = None
        self.log = []
        self._query_data()
        # Get 1 year picture on long stock
        self.inLongTermCorrection, self.inLongTermPotentialReversal = self._check_for_correction()
        self.isLongTermBuy, self.isLongTermSell = self._check_CCI_for_1yr_relative_value()
        if not self.inLongTermCorrection:
            # Get indicators for current monitoring timeframe
            self.cci_indicator = self._calc_cci()
            self.macd_indicator = self._calc_macd()
            self.longSignal, self.shortSignal, self.isSwapTrade = self._get_current_signal()

    @console.BlockPrinting
    def _query_data(self):
        currentDate = date.today()
        dayIdx = currentDate.weekday()
        weekendAdjust = {0: 3, 1: 4, 2: 0, 3: 0, 4: 0, 5: 1, 6: 2}
        resolution = {'1d': {'freq': '15m', 'queryDelta': 2 + weekendAdjust[dayIdx]},
                      '5d': {'freq': '15m', 'queryDelta': 14 + weekendAdjust[dayIdx]},
                      '1mo': {'freq': '60m', 'queryDelta': 60},
                      '3mo': {'freq': '1d', 'queryDelta': 180},
                      '6mo': {'freq': '1d', 'queryDelta': 365},
                      '1y': {'freq': '5d', 'queryDelta': 700},
                      '2y': {'freq': '5d', 'queryDelta': 1400},
                      '5y': {'freq': '1wk', 'queryDelta': 1825},
                      '10y': {'freq': '1wk', 'queryDelta': 1825}}

        self.longData = yf.download(self.longTicker,
                               start=currentDate - timedelta(days=resolution[self.monitorInterval]['queryDelta']),
                               end=currentDate, interval=resolution[self.monitorInterval]['freq'])
        self.shortDatart = yf.download(self.shortTicker,
                                start=currentDate - timedelta(days=resolution[self.monitorInterval]['queryDelta']),
                                end=currentDate, interval=resolution[self.monitorInterval]['freq'])
        self.oneYearLongData = yf.download(self.longTicker,
                               start=currentDate - timedelta(days=365),
                               end=currentDate, interval='1d')
        return

    def _check_for_correction(self):
        '''Check for market correction over 1 yr period.  True if 2 of last 3 HA bars are down trend and
        MACD Histogram amplitude is less than -1.5.  Also checks for Doji bars in last three HA bars, indicating reversal'''
        def __is_doji_bar(openVal, closeVal, highVal, lowVal):
            '''Check for doji bnar by determining of HA upper and lower shadows are both > open/close bar body'''
            body = abs(openVal-closeVal)
            topShadow = highVal - max([openVal, closeVal])
            bottomShadow = min([openVal, closeVal]) - lowVal
            return True if topShadow > body and bottomShadow > body else False

        # Convert last three bars to Heikin-Ashi bars
        ha_last_three_close_bars = self.oneYearLongData.ta.ha().HA_close[-3:].values
        ha_last_three_low_bars = self.oneYearLongData.ta.ha().HA_low[-3:].values
        ha_last_three_open_bars = self.oneYearLongData.ta.ha().HA_open[-3:].values
        ha_last_three_high_bars = self.oneYearLongData.ta.ha().HA_high[-3:].values

        # Calculate MACD histogram
        macd_histogram_last_bar = self.oneYearLongData.ta.macd().MACDh_12_26_9[-1]

        # determine if in immediate down trend by checking if low price < min([open,close]) prices of last three bars.
        # Downward shadows suggest downward trend in HA plot
        twoOfThreeLongShadow = True if sum([1 if ha_last_three_low_bars[i] < min([j, ha_last_three_open_bars[i]]) else 0 for i, j in enumerate(ha_last_three_close_bars)]) >=2 else False
        # Verify if market is in correction with MACD amplitudes
        inCorrection = True if (macd_histogram_last_bar <= -1.5 and twoOfThreeLongShadow) else False

        # check for doji bars in last 3 periods which would indicate potential reversal
        isDojiBar = [__is_doji_bar(ha_last_three_open_bars[i], ha_last_three_close_bars[i], ha_last_three_high_bars[i],
                                   ha_last_three_low_bars[i]) for i in range(len(ha_last_three_low_bars))]
        inPotentialReversal = True if True in isDojiBar else False

        if inCorrection:
            self.log.append('> Heikin-Ashi trend bars indicate that the 1 yr long ticker is in a correction. No trading until reversal')
        if inPotentialReversal:
            self.log.append('> Doji bars are present and indicate a potential reversal is comming. Bot will wait for a trend.')
        return inCorrection, inPotentialReversal

    def _check_CCI_for_1yr_relative_value(self):
        cci_last_pt = self.oneYearLongData.ta.cci(length=20).values[-1]
        isBuy = True if cci_last_pt < -100 else False
        isSell = True if cci_last_pt > 100 else False
        return isBuy, isSell

    def _calc_cci(self):
        return {'long': self.longData.ta.cci(length=20), 'short': self.longData.ta.cci(length=20)}

    def _calc_macd(self):
        return {'long': self.longData.ta.macd(), 'short': self.longData.ta.macd()}

    def _get_current_signal(self):
        '''Use CCI cross-over to determine buy sell hold signal'''
        def __get_buy_sell_hold_signal(cci_vec):
            '''check if cci value crosses 100 or -100 signal limits.  If no immediate cross: hold'''
            prior, current = cci_vec[-2:]
            if prior > 100 and current <= 100:
                return 'sell'
            elif prior < -100 and current >= -100:
                return 'buy'
            else:
                return 'hold'

        longsignal = __get_buy_sell_hold_signal(self.cci_indicator['long'].values)
        shortsignal = __get_buy_sell_hold_signal(self.cci_indicator['short'].values)
        # determine if swap trade or long trade only
        swapsignal = True if longsignal != shortsignal and 'hold' not in [longsignal, shortsignal] and self.useSwapStrategy else False

        # If ticker is in global correction, override all values to avoid losses
        if self.inLongTermCorrection:
            longsignal = 'hold'
            shortsignal = 'hold'
            swapsignal = False

        # update log
        self.log.append(f'\nAlgorithm advises:\n\t{self.longTicker} : {longsignal}'
                        f'\n\t{self.shortTicker} : {shortsignal}'
                        f'\n\tSwap trading set to : {swapsignal}.\n')
        return longsignal, shortsignal, swapsignal