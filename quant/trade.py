# -*- coding:utf-8 -*-

"""
Trade Module.

Author: HuangTao
Date:   2019/04/21
Email:  huangtao@ifclover.com
"""

from quant.error import Error
from quant.utils import logger
from quant.tasks import SingleTask
from quant.order import ORDER_TYPE_LIMIT
from quant.const import OKEX, OKEX_MARGIN, OKEX_FUTURE, OKEX_SWAP, DERIBIT, BITMEX, BINANCE, HUOBI, COINSUPER


class Trade:
    """ Trade Module.

    Attributes:
        strategy: What's name would you want to created for you strategy.
        platform: Exchange platform name. e.g. binance/okex/bitmex.
        symbol: Symbol name for your trade. e.g. BTC/USDT.
        host: HTTP request host.
        wss: Websocket address.
        account: Account name for this trade exchange.
        access_key: Account's ACCESS KEY.
        secret_key: Account's SECRET KEY.
        passphrase: API KEY Passphrase. (Only for OKEx)
        asset_update_callback: You can use this param to specific a async callback function when you initializing Trade
            object. `asset_update_callback` is like `async def on_asset_update_callback(asset: Asset): pass` and this
            callback function will be executed asynchronous when received AssetEvent.
        order_update_callback: You can use this param to specific a async callback function when you initializing Trade
            object. `order_update_callback` is like `async def on_order_update_callback(order: Order): pass` and this
            callback function will be executed asynchronous when some order state updated.
        position_update_callback: You can use this param to specific a async callback function when you initializing
            Trade object. `position_update_callback` is like `async def on_position_update_callback(position: Position): pass`
            and this callback function will be executed asynchronous when position updated.
        init_success_callback: You can use this param to specific a async callback function when you initializing Trade
            object. `init_success_callback` is like `async def on_init_success_callback(success: bool, error: Error): pass`
            and this callback function will be executed asynchronous after Trade module object initialized successfully.
    """

    def __init__(self, strategy=None, platform=None, symbol=None, host=None, wss=None, account=None, access_key=None,
                 secret_key=None, passphrase=None, asset_update_callback=None, order_update_callback=None,
                 position_update_callback=None, init_success_callback=None, **kwargs):
        """initialize trade object."""
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
        elif platform == OKEX_MARGIN:
            from quant.platform.okex_margin import OKExMarginTrade as T
        elif platform == OKEX_FUTURE:
            from quant.platform.okex_future import OKExFutureTrade as T
        elif platform == OKEX_SWAP:
            from quant.platform.okex_swap import OKExSwapTrade as T
        elif platform == DERIBIT:
            from quant.platform.deribit import DeribitTrade as T
        elif platform == BITMEX:
            from quant.platform.bitmex import BitmexTrade as T
        elif platform == BINANCE:
            from quant.platform.binance import BinanceTrade as T
        elif platform == HUOBI:
            from quant.platform.huobi import HuobiTrade as T
        elif platform == COINSUPER:
            from quant.platform.coinsuper import CoinsuperTrade as T
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

    @property
    def rest_api(self):
        return self._t.rest_api

    async def create_order(self, action, price, quantity, order_type=ORDER_TYPE_LIMIT, **kwargs):
        """ Create an order.

        Args:
            action: Trade direction, BUY or SELL.
            price: Price of each contract.
            quantity: The buying or selling quantity.
            order_type: Specific type of order, LIMIT or MARKET. (default LIMIT)

        Returns:
            order_no: Order ID if created successfully, otherwise it's None.
            error: Error information, otherwise it's None.
        """
        order_no, error = await self._t.create_order(action, price, quantity, order_type, **kwargs)
        return order_no, error

    async def revoke_order(self, *order_nos):
        """ Revoke (an) order(s).

        Args:
            order_nos: Order id list, you can set this param to 0 or multiple items. If you set 0 param, you can cancel
                all orders for this symbol(initialized in Trade object). If you set 1 param, you can cancel an order.
                If you set multiple param, you can cancel multiple orders. Do not set param length more than 100.

        Returns:
            success: If execute successfully, return success information, otherwise it's None.
            error: If execute failed, return error information, otherwise it's None.
        """
        success, error = await self._t.revoke_order(*order_nos)
        return success, error

    async def get_open_order_nos(self):
        """ Get open order id list.

        Args:
            None.

        Returns:
            order_nos: Open order id list, otherwise it's None.
            error: Error information, otherwise it's None.
        """
        result, error = await self._t.get_open_order_nos()
        return result, error
