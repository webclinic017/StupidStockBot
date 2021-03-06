import yfinance as yf
from plotly.subplots import make_subplots
import plotly.graph_objects as go
from datetime import date
from datetime import timedelta
import dash
import dash_core_components as dcc
import dash_html_components as html
import numpy as np
from timeloop import Timeloop


class swingTrader:
    def __init__(self, longTicker, shortTicker, minTradePercent):
        self.longTicker = longTicker
        self.shortTicker = shortTicker
        self.minTradeDeltaPercent = minTradePercent
        self.monitorInterval = None
        self.reload = 0
        self._verifyLongAndShort()
        self._getMonitoringInterval()
        self._runAnalysis()


    def __calcSlope(self, xVec, yVec):
        '''Use least Sq regression to calculate slope'''
        sumX = np.nansum(xVec)
        sumY = np.nansum(yVec)
        sumMulXY = np.nansum(np.multiply(xVec, yVec))
        sumSqX = np.nansum(np.multiply(xVec, xVec))
        return (sumMulXY - (sumX*sumY)) / (sumSqX - np.power(sumX,2))

    def _verifyLongAndShort(self):
        '''Verify tickers are actually long and short, else swap'''
        print('Verifying long and short stocks for bull/bear trend over last year...')
        currentDate = date.today()
        oneYearLong = yf.download(self.longTicker, start=currentDate - timedelta(days=365), end=currentDate, interval='1wk')
        oneYearShort = yf.download(self.shortTicker, start=currentDate - timedelta(days=365), end=currentDate, interval='1wk')
        startPrice = oneYearLong.Close.values[0]
        slopeLong = self.__calcSlope([i for i in range(len(oneYearLong.index.values))], [((i - startPrice) / startPrice)*100 for i in oneYearLong.Close.values])
        startPrice = oneYearShort.Close.values[0]
        slopeShort = self.__calcSlope([i for i in range(len(oneYearShort.index.values))], [((i - startPrice) / startPrice) * 100 for i in oneYearShort.Close.values])
        if slopeShort > slopeLong:
            # Swap tickers if long case on input is incorrect over 1 yr period
            self.longTicker, self.shortTicker = [self.shortTicker, self.longTicker]
        return

    def _getMonitoringInterval(self):
        '''Check last 60 days of data to determine monitoring interval based on trade frequency and minTradePercent'''

        # variables in scope of getMonitoringInterval
        currentDate = date.today()
        lastSixtyDays = []
        deltaSixtyDaysIntraDay = []
        deltaSixtyDaysWeekly = []
        deltaSixtyDaysMonthly = []

        def __get_last_60_days_of_data():
            '''Query last 60 days of daily trading data'''
            print(f'querying yahoo finance for {self.longTicker} daily data over last 60 days')
            for i in reversed(range(0, 60, 1)):
                queryDate = currentDate - timedelta(days=i)
                if queryDate.weekday() >= 5:
                    # If Sat (5) or Sunday (6) no data
                    continue
                dlData = yf.download(self.longTicker, start=queryDate, end=queryDate + timedelta(days=1), interval='15m')
                if dlData.values.size > 0:
                    # weekend and holiday data will be blankpython how many values in list reerere
                    lastSixtyDays.append(dlData.Close.values)
            print('\n\n\n\n\n')
            return

        def __check_daily_frequency():
            # check daily frequency
            for j, dayData in enumerate(lastSixtyDays):
                deltaSixtyDaysIntraDay.append((np.max(dayData)-np.min(dayData))/np.min(dayData)*100)
            intradaycount = len([i for i in deltaSixtyDaysIntraDay if i > self.minTradeDeltaPercent])
            print(f'{intradaycount} / {len(deltaSixtyDaysIntraDay)} days meet trade threshold in intraday trading')
            if intradaycount/len(deltaSixtyDaysIntraDay) >= 0.5:
                self.monitorInterval = '1d'
            return

        def __check_weekly_frequency():
            # Check Weekly Frequency
            for j in range(0, len(lastSixtyDays), 5):
                try:
                    week = lastSixtyDays[j:j+5]
                except:
                    week = lastSixtyDays[j:]
                deltaSixtyDaysWeekly.append((np.max(week)-np.min(week))/np.min(week)*100)
            weeklycount = len([i for i in deltaSixtyDaysWeekly if i > self.minTradeDeltaPercent])
            print(f'{weeklycount} / {len(deltaSixtyDaysWeekly)} weeks (5day) meet trade threshold in weekly trading')
            if weeklycount/len(deltaSixtyDaysWeekly) >= 0.5 and self.monitorInterval is None:
                self.monitorInterval = '5d'
            return

        def __check_monthly_frequency():
            # Check Monthly Frequency
            for j in range(0, len(lastSixtyDays), 20):
                try:
                    month = lastSixtyDays[j:j+20]
                except:
                    month = lastSixtyDays[j:]
                deltaSixtyDaysMonthly.append((np.max(month)-np.min(month))/np.min(month)*100)
            monthlycount = len([i for i in deltaSixtyDaysMonthly if i > self.minTradeDeltaPercent])
            print(f'{monthlycount} / {len(deltaSixtyDaysMonthly)} months (20day) meet trade threshold in monthly trading')
            if self.monitorInterval is None:
                if monthlycount/len(deltaSixtyDaysMonthly) >= 0.5:
                    self.monitorInterval = '1mo'
                else:
                    self.monitorInterval = '1y'
                    print('Analysis suggests that the trade settings are not appropriate for the desired tickers. Advise against using this script with current settings.')
            return

        __get_last_60_days_of_data()
        __check_daily_frequency()
        __check_weekly_frequency()
        __check_monthly_frequency()
        print(f'Data monitoring interval set to: {self.monitorInterval} using a minimum trade delta of: {self.minTradeDeltaPercent}%')
        return

    def _runAnalysis(self):
        timer1 = Timeloop()

        @timer1.job(interval=timedelta(seconds=60))
        def __plot_stuff():
            resolution = {'1d': {'freq': '15m', 'queryDelta': 3},
                          '5d': {'freq': '60m', 'queryDelta': 15},
                          '1mo': {'freq': '90m', 'queryDelta': 60},
                          '3mo': {'freq': '1d', 'queryDelta': 180},
                          '6mo': {'freq': '1d', 'queryDelta': 365},
                          '1y': {'freq': '5d', 'queryDelta': 700},
                          '2y': {'freq': '5d', 'queryDelta': 1400},
                          '5y': {'freq': '1wk', 'queryDelta': 1825},
                          '10y': {'freq': '1wk', 'queryDelta': 1825}}
            currentDate = date.today()
            dataLong = yf.download(longTicker,
                                       start=currentDate - timedelta(days=resolution[self.monitorInterval]['queryDelta']),
                                       end=currentDate, interval=resolution[self.monitorInterval]['freq'])
            dataShort = yf.download(shortTicker,
                                        start=currentDate - timedelta(days=resolution[self.monitorInterval]['queryDelta']),
                                        end=currentDate, interval=resolution[self.monitorInterval]['freq'])

            allPlots = [dataLong, dataShort]

            fig = make_subplots(rows=len(allPlots), cols=1)

            for i, tickerPlot in enumerate(allPlots):
                fig.add_trace(go.Ohlc(x=tickerPlot.index,
                                    open=tickerPlot.Open,
                                    high=tickerPlot.High,
                                    low=tickerPlot.Low,
                                    close=tickerPlot.Close), i+1, 1)
                fig.update_xaxes(rangeslider={'visible': False}, type='category', row=i+1, col=1)


            fig.update(layout_xaxis_rangeslider_visible=False)
            fig.update_layout(height=800, width=1000,
                              title_text=f'TOP: {longTicker} \nBottom: {shortTicker}',
                              showlegend=False)

            app = dash.Dash()
            app.layout = html.Div([
                dcc.Graph(figure=fig)
            ])

            app.run_server(debug=True, use_reloader=False)
            return

        timer1.start(block=True)
        return

if __name__ == '__main__':
    longTicker = 'QQQ'
    shortTicker = 'SQQQ'
    minTradeDeltaPercent = 3
    tradeForMe = swingTrader(longTicker, shortTicker, minTradeDeltaPercent)
