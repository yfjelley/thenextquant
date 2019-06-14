# -*- coding:utf-8 -*-

"""
Trade 交易模块，整合所有交易所为一体

Author: HuangTao
Date:   2019/04/21
"""

from quant.error import Error
from quant.utils import logger
from quant.tasks import SingleTask
from quant.order import ORDER_TYPE_LIMIT
from quant.const import OKEX, OKEX_FUTURE, DERIBIT, BITMEX, BINANCE, HUOBI


class Trade:
    """ 交易模块
    """

    def __init__(self, strategy=None, platform=None, symbol=None, host=None, wss=None, account=None, access_key=None,
                 secret_key=None, passphrase=None, asset_update_callback=None, order_update_callback=None,
                 position_update_callback=None, init_success_callback=None, **kwargs):
        """ 初始化
        @param strategy 策略名称
        @param platform 交易平台
        @param symbol 交易对
        @param host 交易平台REST API地址
        @param wss 交易平台websocket地址
        @param account 交易账户
        @param access_key 账户 ACCESS KEY
        @param secret_key 账户 SECRET KEY
        @param passphrase 账户交易密码(OKEx使用)
        @param asset_update_callback 资产更新回调，async异步函数 async asset_update_callback(asset): pass
        @param order_update_callback 订单更新回调，async异步函数 async order_update_callback(order): pass
        @param position_update_callback 持仓更新回调，async异步函数 async position_update_callback(position): pass
        @param init_success_callback 初始化成功回调，async异步函数 async init_success_callback(success, error): pass
        """
        kwargs["strategy"] = strategy
        kwargs["platform"] = platform
        kwargs["symbol"] = symbol
        kwargs["host"] = host
        kwargs["wss"] = wss
        kwargs["account"] = account
        kwargs["access_key"] = access_key
        kwargs["secret_key"] = secret_key
        kwargs["passphrase"] = passphrase
        kwargs["asset_update_callback"] = asset_update_callback
        kwargs["order_update_callback"] = order_update_callback
        kwargs["position_update_callback"] = position_update_callback
        kwargs["init_success_callback"] = init_success_callback

        if platform == OKEX:
            from quant.platform.okex import OKExTrade as T
        elif platform == OKEX_FUTURE:
            from quant.platform.okex_future import OKExFutureTrade as T
        elif platform == DERIBIT:
            from quant.platform.deribit import DeribitTrade as T
        elif platform == BITMEX:
            from quant.platform.bitmex import BitmexTrade as T
        elif platform == BINANCE:
            from quant.platform.binance import BinanceTrade as T
        elif platform == HUOBI:
            from quant.platform.huobi import HuobiTrade as T
        else:
            logger.error("platform error:", platform, caller=self)
            if init_success_callback:
                e = Error("platform error")
                SingleTask.run(init_success_callback, False, e)
            return
        kwargs.pop("platform")
        self._t = T(**kwargs)

    @property
    def assets(self):
        return self._t.assets

    @property
    def orders(self):
        return self._t.orders

    @property
    def position(self):
        return self._t.position

    async def create_order(self, action, price, quantity, order_type=ORDER_TYPE_LIMIT):
        """ 创建委托单
        @param action 交易方向 BUY/SELL
        @param price 委托价格
        @param quantity 委托数量(当为负数时，代表合约操作空单)
        @param order_type 委托类型 LIMIT/MARKET
        @return (order_no, error) 如果成功，order_no为委托单号，error为None，否则order_no为None，error为失败信息
        """
        order_no, error = await self._t.create_order(action, price, quantity, order_type)
        return order_no, error

    async def revoke_order(self, *order_nos):
        """ 撤销委托单
        @param order_nos 订单号列表，可传入任意多个，如果不传入，那么就撤销所有订单
        @return (success, error) success为撤单成功列表，error为撤单失败的列表
        """
        success, error = await self._t.revoke_order(*order_nos)
        return success, error

    async def get_open_order_nos(self):
        """ 获取未完成委托单id列表
        @return (result, error) result为成功获取的未成交订单列表，error如果成功为None，如果不成功为错误信息
        """
        result, error = await self._t.get_open_order_nos()
        return result, error
