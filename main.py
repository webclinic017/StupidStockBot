import preflightcheck
import analysis


class SwingTrader:
    def __init__(self, longTicker, shortTicker, minTradePercent, production=False):
        self.longTicker = longTicker
        self.shortTicker = shortTicker
        self.minTradeDeltaPercent = minTradePercent
        precheck = preflightcheck.SanityCheck(self.longTicker, self.shortTicker, self.minTradeDeltaPercent)
        self.__print_log(precheck.log)
        if not precheck.isPass:
            print('\nBot will not work well with existing inputs.\n'
                  f'Long ticker: {self.longTicker} | Short Ticker: {self.shortTicker} | min. trade %: {self.minTradeDeltaPercent}\n')
            return
        self.monitorInterval = precheck.monitorInterval
        stock_analysis = analysis.SwapTrader(self.longTicker, self.shortTicker, self.minTradeDeltaPercent, self.monitorInterval, precheck.tickersAreSymmetric, production=production)
        self.__print_log(stock_analysis.log)
        if stock_analysis.BuySellHold == 'hold':
            return
        self.useSwapStrategy = stock_analysis.isStockSwap


    def __print_log(self, log):
        [print(i) for i in log]
        return

if __name__ == '__main__':

    longTicker = 'QQQ'
    shortTicker = 'SQQQ'
    minTradeDeltaPercent = 1
    tradeForMe = SwingTrader(longTicker, shortTicker, minTradeDeltaPercent, production=False)