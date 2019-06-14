# -*- coding:utf-8 -*-

"""
资产数据

Author: HuangTao
Date:   2019/02/16
"""

import json


class Asset:
    """ 资产
    """

    def __init__(self, platform=None, account=None, assets=None, timestamp=None, update=False):
        """ 初始化
        @param platform 交易平台
        @param account 交易账户
        @param assets 资产信息 {"BTC": {"free": "1.1", "locked": "2.2", "total": "3.3"}, ... }
        @param timestamp 时间戳(毫秒)
        @param update 资产是否更新 True 有更新 / False 无更新
        """
        self.platform = platform
        self.account = account
        self.assets = assets
        self.timestamp = timestamp
        self.update = update

    @property
    def data(self):
        d = {
            "platform": self.platform,
            "account": self.account,
            "assets": self.assets,
            "timestamp": self.timestamp,
            "update": self.update
        }
        return d

    def __str__(self):
        info = json.dumps(self.data)
        return info

    def __repr__(self):
        return str(self)


class AssetSubscribe:
    """ 资产订阅
    """

    def __init__(self, platform, account, callback):
        """ 初始化
        @param platform 交易平台
        @param account 交易账户
        @param callback 资产更新回调函数，必须是async异步函数，回调参数为 Asset 对象，比如: async def on_event_account_update(asset: Asset): pass
        """
        from quant.event import EventAsset
        EventAsset(platform, account).subscribe(callback)
