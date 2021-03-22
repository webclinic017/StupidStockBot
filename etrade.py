# Work in progress for wrapping e-trade API: https://apisb.etrade.com/docs/api/market/api-quote-v1.html
import os
import json
from rauth import OAuth1Service
import undetected_chromedriver.v2 as uc
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.common.action_chains import ActionChains
from selenium.webdriver.common.by import By
from datetime import datetime
from datetime import timedelta
import time
import pprint
import secret


class CurrentAccount(object):
    def __init__(self, account_list=None):
        self.id = None
        self.id_key = None
        self.description = None
        self.mode = None
        self.name = None
        self.status = None
        self.type = None
        self.institution_type = None
        self.closed_date = None
        self.cash_available = None
        self.positions = None
        self.total_account_value = None
        self.__account_list = account_list

    def __call__(self):
        return self.get()

    def get(self):
        return {'id': self.id, 'id_key': self.id_key, 'description': self.description, 'mode': self.mode,
                'name': self.name, 'status': self.status, 'type': self.type,
                'institution_type': self.institution_type, 'closed_date': self.closed_date,
                'cash_available': self.cash_available, 'total_account_value': self.total_account_value,
                'positions': self.positions}

    def set(self, account_dict):
        self.id = account_dict['accountId'] if 'accountId' in account_dict else None
        self.id_key = account_dict['accountIdKey'] if 'accountIdKey' in account_dict else None
        self.description = account_dict['accountDesc'] if 'accountDesc' in account_dict else None
        self.mode = account_dict['accountMode'] if 'accountMode' in account_dict else None
        self.name = account_dict['accountName'] if 'accountName' in account_dict else None
        self.status = account_dict['accountStatus'] if 'accountStatus' in account_dict else None
        self.type = account_dict['accountType'] if 'accountType' in account_dict else None
        self.institution_type = account_dict['institutionType'] if 'institutionType' in account_dict else None
        self.closed_date = account_dict['closedDate'] if 'closedDate' in account_dict else None
        if 'cashAvailable' in account_dict:
            self.cash_available = account_dict['cashAvailable']
        if 'positions' in account_dict:
            self.positions = account_dict['positions']
        if 'totalAccountValue' in account_dict:
            self.total_account_value = account_dict['totalAccountValue']
        return

    def set_by_id(self, id):
        account_dict = None
        idx = 0
        for i in range(len(self.__account_list)):
            if self.__account_list[i]['accountId'] == id:
                account_dict = self.__account_list[i]
                idx = i
                break
        if account_dict is None:
            raise ValueError(f'Invalid account ID: {id}')
        else:
            self.set(self.__account_list[idx])
        return

    def set_by_id_key(self, id_key):
        account_dict = None
        idx = 0
        for i in range(len(self.__account_list)):
            if self.__account_list[i]['accountIdKey'] == id_key:
                account_dict = self.__account_list[i]
                idx = i
                break
        if account_dict is None:
            raise ValueError(f'Invalid account ID Key: {id_key}')
        else:
            self.set(self.__account_list[idx])
        return

    def set_by_index(self, index):
        try:
            self.set(self.__account_list[index])
        except Exception as e:
            raise ValueError(f'Account index is out of range. Expecting value between 0 and {len(self.__account_list)}')
        return

    def update_account_list(self, account_list):
        self.__account_list = account_list
        return


class Etrader():
    def __init__(self,  production=False):
        self.consumer_key = secret.CONSUMER_KEY_PROD if production else secret.CONSUMER_KEY_DEV
        self.consumer_secret = secret.CONSUMER_SECRET_PROD if production else secret.CONSUMER_SECRET_DEV
        self.web_username = secret.WEB_USERNAME
        self.web_password = secret.WEB_PASSWORD
        self.session_start_time = datetime.now()
        self.base_url_prod = r"https://api.etrade.com"
        self.base_url_dev = r"https://apisb.etrade.com"
        self.__base_url = self.base_url_prod if production else self.base_url_dev
        self.__renew_access_token_url = r"https://api.etrade.com/oauth/renew_access_token"
        self.__revoke_access_token_url = r"https://api.etrade.com/oauth/revoke_access_token"
        self.service = OAuth1Service(
                  name='etrade',
                  consumer_key=self.consumer_key,
                  consumer_secret=self.consumer_secret,
                  request_token_url= "%s/oauth/request_token" % self.__base_url,
                  access_token_url="%s/oauth/access_token" % self.__base_url,
                  authorize_url='https://us.etrade.com/e/t/etws/authorize?key={}&token={}',
                  base_url=self.__base_url)
        self.oauth_token = None
        self.oauth_token_secret = None
        self.verifier = None
        self.session = None
        self.__authorization()
        self.current_account = CurrentAccount()
        self.account_list = self.get_list_of_accounts()
        self.current_account.set_by_index(0)

    def __enter__(self):
        '''Permit WITH instantiation'''
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        '''Cleanup when object is destroyd'''
        self.revoke_accesss_token()
        return

    def __authorization(self):
        cache_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'con.cache')

        def __retrieve_connection_cache():
            if os.path.isfile(cache_file):
                with open(cache_file, 'r') as infile:
                    con_cache = json.load(infile)
                    self.oauth_token = con_cache['oauth_token']
                    self.oauth_token_secret = con_cache['oauth_token_secret']
                    self.service.authorize_url = con_cache['authorize_url']
                    self.verifier = con_cache['verifier']
                    self.session = OAuth1Service(**json.loads(con_cache['session']))
                return True
            return False

        def __test_connection():
            res = self.renew_accesss_token()
            if res.status_code == 200:
                return
            __new_authorization()
            return

        def __new_authorization():
            self.oauth_token, self.oauth_token_secret = self.service.get_request_token(params={'oauth_callback': 'oob', 'format': 'json'})
            self.service.authorize_url = self.service.authorize_url.format(self.consumer_key, self.oauth_token)
            self.verifier = self.__get_verifier(headless=False, action_delay_sec=2)
            self.session = self.service.get_auth_session(self.oauth_token, self.oauth_token_secret, params={'oauth_verifier': self.verifier})
            return

        def __set_connection_cache():
            with open(cache_file, 'w') as outfile:
                outfile.write(json.dumps({'oauth_token': self.oauth_token,
                           'oauth_token_secret': self.oauth_token_secret,
                           'authorize_url': self.service.authorize_url,
                           'verifier': self.verifier,
                           'session': {'consumer_key': self.session.consumer_key,
                                       'consumer_secret': self.session.consumer_secret,
                                       'access_token': self.session.access_token,
                                       'access_token_secret': self.session.access_token_secret}}))
            return

        if __retrieve_connection_cache():
            __test_connection()
        else:
            __new_authorization()
        __set_connection_cache()
        return

    def check_token(self):
        age = datetime.now() - self.session_start_time
        if age >= timedelta(hours=4):
            res = self.renew_accesss_token()
            if not res.ok:
                self.__authorization()
        return

    def __get_verifier(self, headless=True, action_delay_sec=2):
        '''Use selenium web driver to grab oAuth confirmation code'''
        num_login_attempts = 10
        options = uc.ChromeOptions()
        options.headless = True if headless else False
        driver = uc.Chrome(options=options)
        print(f'Etrade UI web login with action_delay set to: {action_delay_sec} seconds')

        def __slow_ui_typing(ui_element, text, delay=0.11):
            '''type each letter in text fields of UI to better mimick non-bot user'''
            for t in text:
                ui_element.send_keys(t)
                time.sleep(delay)
            return

        try:
            with driver:
                driver.get(self.service.authorize_url)
                time.sleep(action_delay_sec)
                # log in
                for i in range(num_login_attempts):
                    web_action = ActionChains(driver)
                    print(f'Web UI login attempt: {i+1} / {num_login_attempts}')
                    username = driver.find_element_by_name("USER")
                    web_action.move_to_element(username).perform()
                    __slow_ui_typing(username, self.web_username)
                    password = driver.find_element_by_name("PASSWORD")
                    web_action.move_to_element(password).perform()
                    __slow_ui_typing(password, self.web_password)
                    login_btn = driver.find_element_by_id("logon_button")
                    web_action.move_to_element(login_btn).perform()
                    login_btn.click()
                    time.sleep(action_delay_sec)
                    # Login occasionally fails due to bot detection.  The page it redirects is for human login to non api
                    # in that case we detect that the logon button is still on the page and retry to login to api
                    test_for_button = driver.find_elements(By.ID, "logon_button")
                    if len(test_for_button) > 0:
                        if i == num_login_attempts-1:
                            raise Exception(f'Automated login was not successful after {num_login_attempts} attempts!')
                        time.sleep(action_delay_sec)
                        driver.get(self.service.authorize_url)
                    else:
                        break
                print(f'\tLog in successful!')
                web_action = ActionChains(driver)
                web_action.send_keys(Keys.TAB).send_keys(Keys.RETURN).perform()
                time.sleep(action_delay_sec)
                return driver.find_element_by_tag_name("input").get_attribute("value")
        except Exception as e:
            raise Exception(f'Automated login was not successful!\n{str(e)}')

    def renew_accesss_token(self):
        '''renew_access_token'''
        self._session_start_time = datetime.now()
        return self.session.get(self.__renew_access_token_url)

    def revoke_accesss_token(self):
        '''revoke_access_token'''
        self.session.get(self.__revoke_access_token_url)
        return

    def get_list_of_accounts(self):
        '''Get all accounts related to consumer key'''

        def __get_list():
            end_pt = r"v1/accounts/list"
            api_url = "%s/%s.%s" % (self.__base_url, end_pt, 'json')
            req = self.session.get(api_url)
            __update_current_account_obj(req.json()['AccountListResponse']['Accounts']['Account'])
            return

        def __populate_holdings():
            for i in range(len(self.account_list)):
                account_value = self.get_account_balance(self.account_list[i]['accountId'])
                self.account_list[i]['cashAvailable'] = account_value['Computed']['cashAvailableForInvestment']
                self.account_list[i]['positions'] = self.get_account_positions(self.account_list[i]['accountId'])
                self.account_list[i]['totalAccountValue'] = account_value['Computed']['RealTimeValues']['totalAccountValue']
            __update_current_account_obj(self.account_list)
            return

        def __update_current_account_obj(account_lst):
            self.account_list = account_lst
            self.current_account.update_account_list(account_lst)
            return

        self.check_token()
        __get_list()
        __populate_holdings()
        return self.account_list

    def get_account_balance(self, account_id=None):
        '''Get all account balances'''
        self.check_token()
        if account_id is not None:
            self.current_account.set_by_id(account_id)
        account_id_key = self.current_account.id_key
        account_inst_type = self.current_account.institution_type
        account_type = self.current_account.type
        end_pt = "v1/accounts"
        api_url = "%s/%s/%s/balance.json" % (self.__base_url, end_pt, account_id_key)
        payload = {"realTimeNAV": True, "instType": account_inst_type, "accountType": account_type}
        req = self.session.get(api_url, params=payload)
        req.raise_for_status()
        return req.json()['BalanceResponse']

    def get_account_positions(self, account_id=None):
        '''Get account positions'''
        self.check_token()
        if account_id is not None:
            self.current_account.set_by_id(account_id)
        end_pt = "v1/accounts"
        api_url = "%s/%s/%s/portfolio.json" % (self.__base_url, end_pt, self.current_account.id_key)
        req = self.session.get(api_url)
        return req.json()['PortfolioResponse']['AccountPortfolio'][0]['Position']

    def get_account_transaction_history(self, account_id=None, ticker_symbol=None):
        '''Get Transaction History'''
        self.check_token()
        if account_id is not None:
            self.current_account.set_by_id(account_id)
        end_pt = "v1/accounts"
        api_url = "%s/%s/%s/transactions.json" % (self.__base_url, end_pt, self.current_account.id_key)
        req = self.session.get(api_url)
        return req.json()['TransactionListResponse']['Transaction']

    def get_transaction_details(self, account_id=None, transaction_id=None):
        '''Get Transaction History'''
        if transaction_id is None:
            return []
        self.check_token()
        if account_id is not None:
            self.current_account.set_by_id(account_id)
        end_pt = "v1/accounts"
        api_url = "%s/%s/%s/transactions/%s.json" % (self.__base_url, end_pt, self.current_account.id_key, transaction_id)
        req = self.session.get(api_url)
        return req.json()['TransactionDetailsResponse']

    def get_market_quote(self, stock_ticker):
        '''Get market quote for provided stock ticker'''
        self.check_token()
        if not isinstance(stock_ticker, list):
            stock_ticker = [stock_ticker]
        stock_ticker = ','.join(stock_ticker)
        end_pt = "v1/market/quote"
        api_url = "%s/%s/%s.json" % (self.__base_url, end_pt, stock_ticker)
        req = self.session.get(api_url)
        return req.json()['QuoteResponse']['QuoteData']

    def get_existing_orders(self, account_id=None):
        '''Get existing orders in account'''
        self.check_token()
        if account_id is not None:
            self.current_account.set_by_id(account_id)
        end_pt = "v1/accounts"
        api_url = "%s/%s/%s/orders.json" % (self.__base_url, end_pt, self.current_account.id_key)
        req = self.session.get(api_url)
        return req.json()['OrdersResponse']['Order']

if __name__ == '__main__':
    # Automated Login
    with Etrader(production=True) as etrade:
        # Test Session
        pprint.pprint(etrade.account_list)
        pprint.pprint(etrade.current_account.get())
    print('\n\nexit')

