# -*- coding:utf-8 -*-

"""
打电话接口

Author: HuangTao
Date:   2019/03/22
"""

import hmac
import base64
import hashlib
from urllib import parse

from quant.utils import tools
from quant.utils import logger
from quant.utils.http_client import AsyncHttpRequests


class AliyunPhoneCall:
    """ 阿里云语音通知
    """

    @classmethod
    async def call_phone(cls, access_key, secret_key, from_, to, code, region_id="cn-hangzhou"):
        """ 打电话
        @param access_key 公钥
        @param secret_key 私钥
        @param from_ 播出去的号码
        @param to 拨打的号码 如：15300000000
        @param code 语音文件id
        @param region_id 使用阿里云语音服务区，默认使用 cn-hangzhou
        """
        def percent_encode(s):
            res = parse.quote_plus(s.encode("utf8"))
            res = res.replace("+", "%20").replace("*", "%2A").replace("%7E", "~")
            return res

        url = "http://dyvmsapi.aliyuncs.com/"
        out_id = tools.get_uuid1()
        nonce = tools.get_uuid1()
        timestamp = tools.dt_to_date_str(tools.get_utc_time(), fmt="%Y-%m-%dT%H:%M:%S.%fZ")

        params = {
            "VoiceCode": code,
            "OutId": out_id,
            "CalledNumber": to,
            "CalledShowNumber": from_,
            "Version": "2017-05-25",
            "Action": "SingleCallByVoice",
            "Format": "JSON",
            "RegionId": region_id,
            "Timestamp": timestamp,
            "SignatureMethod": "HMAC-SHA1",
            "SignatureType": "",
            "SignatureVersion": "1.0",
            "SignatureNonce": nonce,
            "AccessKeyId": access_key
        }
        query = "&".join(["{}={}".format(percent_encode(k), percent_encode(params[k])) for k in sorted(params.keys())])
        str_to_sign = "GET&%2F&" + percent_encode(query)
        print("data:", str_to_sign)
        h = hmac.new(bytes(secret_key + "&", "utf8"), bytes(str_to_sign, "utf8"), digestmod=hashlib.sha1)
        signature = base64.b64encode(h.digest()).decode()
        params["Signature"] = signature

        logger.info("url:", url, "params:", params, caller=cls)
        result = await AsyncHttpRequests.fetch("GET", url, params=params)
        logger.info("url:", url, "result:", result, caller=cls)
