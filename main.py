import preflightcheck
import analysis


class SwingTrader:
    def __init__(self, longTicker, shortTicker, minTradePercent):
        self.longTicker = longTicker
        self.shortTicker = shortTicker
        self.minTradeDeltaPercent = minTradePercent
        self.monitorInterval = None
        self.useSwapStrategy = False
        precheck = preflightcheck.SanityCheck(self.longTicker, self.shortTicker, self.minTradeDeltaPercent)
        [print(i) for i in precheck.log]
        if precheck.isPass:
            self.useSwapStrategy = precheck.tickersAreSymmetric
            self.monitorInterval = precheck.monitorInterval
            stock_analysis = analysis.Run(self.longTicker, self.shortTicker, self.minTradeDeltaPercent, self.monitorInterval, self.useSwapStrategy)
        else:
            print('\nBot will not work well with existing inputs.\n'
                  f'Long ticker: {self.longTicker} | Short Ticker: {self.shortTicker} | min. trade %: {self.minTradeDeltaPercent}\n')

if __name__ == '__main__':
    longTicker = 'QQQ'
    shortTicker = 'SQQQ'
    minTradeDeltaPercent = 1
    tradeForMe = SwingTrader(longTicker, shortTicker, minTradeDeltaPercent)
