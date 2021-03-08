import numpy as np
from datetime import date
from datetime import timedelta
import yfinance as yf


class SanityCheck:
    def __init__(self, longTicker, shortTicker, minTradePercent):
        self.currentDate = date.today()
        self.longTicker = longTicker
        self.shortTicker = shortTicker
        self.minTradeDeltaPercent = minTradePercent
        self.isPass = True
        self.tickersAreSymmetric = False
        self.tickerPercentSymmetry = 0.0
        self.monitorInterval = None
        self.slopeLong = 0.00
        self.slopeShort = 0.00
        self.log = []
        self._verify_long_and_short()
        self._verify_ticker_symmetry()
        if self.isPass:
            self._get_monitoring_interval()

    def __calc_slope(self, xVec, yVec):
        '''Use least Sq regression to calculate slope'''
        sumX = np.nansum(xVec)
        sumY = np.nansum(yVec)
        sumMulXY = np.nansum(np.multiply(xVec, yVec))
        sumSqX = np.nansum(np.multiply(xVec, xVec))
        return (sumMulXY - (sumX * sumY)) / (sumSqX - np.power(sumX, 2))

    def __vec_to_percent(self, inVec):
        '''convert vector of values to percentages'''
        iVal = inVec[0]
        return [((i - iVal) / iVal) * 100 for i in inVec]


    def _verify_long_and_short(self):
        '''Verify tickers are actually long and short, else swap'''
        print('Verifying long and short stocks for bull/bear trend over last year...')
        oneYearLong = yf.download(self.longTicker, start=self.currentDate - timedelta(days=365), end=self.currentDate,
                                  interval='1wk')
        oneYearShort = yf.download(self.shortTicker, start=self.currentDate - timedelta(days=365), end=self.currentDate,
                                   interval='1wk')
        self.slopeLong = self.__calc_slope([i for i in range(len(oneYearLong.index.values))], self.__vec_to_percent(oneYearLong.Close.values))
        self.slopeShort = self.__calc_slope([i for i in range(len(oneYearShort.index.values))], self.__vec_to_percent(oneYearShort.Close.values))
        if self.slopeLong > 0 and self.slopeShort > 0:
            self.log.append(f'Neither ticker is a short(bear) stock. Swap strategy turned off.')
        elif self.slopeLong < 0 and self.slopeShort < 0:
            self.log.append(f'Neither ticker is a long(bull) stock.')
        elif self.slopeShort > self.slopeLong:
            # Swap tickers if long case on input is incorrect over 1 yr period
            self.longTicker, self.shortTicker = [self.shortTicker, self.longTicker]
            self.log.append(f'1 yr Bull and Bear case for input tickers is incorrect.')
        else:
            self.log.append(f'1 yr Bull and Bear case for input tickers is confirmed.')
        self.log[-1] += f' Long Ticker: {self.longTicker} | Short Ticker: {self.shortTicker}'
        return

    def _verify_ticker_symmetry(self):
        '''Verify Long and Short tickers have approximate mirror symmetry'''
        if (self.slopeLong > 0 and self.slopeShort > 0) or (self.slopeLong < 0 and self.slopeShort < 0):
            self.tickerPercentSymmetry = 0
            self.tickersAreSymmetric = False
            if self.slopeLong < 0 and self.slopeShort < 0:
                self.isPass = False
            return

        oneMonthLong = yf.download(self.longTicker, start=self.currentDate - timedelta(days=30), end=self.currentDate,
                                  interval='1h')
        oneMonthShort = yf.download(self.shortTicker, start=self.currentDate - timedelta(days=30), end=self.currentDate,
                                   interval='1h')
        tickLong = self.__vec_to_percent(np.nan_to_num(oneMonthLong.Close))
        tickShort = self.__vec_to_percent(np.nan_to_num(oneMonthShort.Close))
        self.tickerPercentSymmetry = 100 - np.average((tickLong + tickShort))
        self.tickersAreSymmetric = False if self.tickerPercentSymmetry < 90 else True
        return

    def _get_monitoring_interval(self):
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
                dlData = yf.download(self.longTicker, start=queryDate, end=queryDate + timedelta(days=1),
                                     interval='15m')
                if dlData.values.size > 0:
                    # weekend and holiday data will be blank python
                    lastSixtyDays.append(dlData.Close.values)
            return

        def __check_daily_frequency():
            # check daily frequency
            for j, dayData in enumerate(lastSixtyDays):
                deltaSixtyDaysIntraDay.append((np.max(dayData) - np.min(dayData)) / np.min(dayData) * 100)
            intradaycount = len([i for i in deltaSixtyDaysIntraDay if i > self.minTradeDeltaPercent])
            if intradaycount / len(deltaSixtyDaysIntraDay) >= 0.5:
                self.monitorInterval = '1d'
            self.log.append(
                f'{intradaycount} / {len(deltaSixtyDaysIntraDay)} days meet trade threshold in intraday trading')
            return

        def __check_weekly_frequency():
            # Check Weekly Frequency
            for j in range(0, len(lastSixtyDays), 5):
                try:
                    week = lastSixtyDays[j:j + 5]
                except:
                    week = lastSixtyDays[j:]
                deltaSixtyDaysWeekly.append((np.max(week) - np.min(week)) / np.min(week) * 100)
            weeklycount = len([i for i in deltaSixtyDaysWeekly if i > self.minTradeDeltaPercent])
            if weeklycount / len(deltaSixtyDaysWeekly) >= 0.5 and self.monitorInterval is None:
                self.monitorInterval = '5d'
            self.log.append(f'{weeklycount} / {len(deltaSixtyDaysWeekly)} weeks (5day) '
                            f'meet trade threshold in weekly trading')
            return

        def __check_monthly_frequency():
            # Check Monthly Frequency
            for j in range(0, len(lastSixtyDays), 20):
                try:
                    month = lastSixtyDays[j:j + 20]
                except:
                    month = lastSixtyDays[j:]
                deltaSixtyDaysMonthly.append((np.max(month) - np.min(month)) / np.min(month) * 100)
            monthlycount = len([i for i in deltaSixtyDaysMonthly if i > self.minTradeDeltaPercent])
            self.log.append(
                f'{monthlycount} / {len(deltaSixtyDaysMonthly)} months (20day) meet trade threshold in monthly trading')
            if self.monitorInterval is None:
                if monthlycount / len(deltaSixtyDaysMonthly) >= 0.5:
                    self.monitorInterval = '1mo'
                else:
                    self.monitorInterval = '1y'
                    self.log.append('Analysis suggests that the trade settings are not appropriate for the desired '
                                    'tickers. Advise against using this script with current settings.')
                    self.isPass = False
            return

        __get_last_60_days_of_data()
        __check_daily_frequency()
        __check_weekly_frequency()
        __check_monthly_frequency()
        self.log.append(f'Data monitoring interval set to: {self.monitorInterval} using a minimum'
                        f' trade delta of: {self.minTradeDeltaPercent}%')
        return
