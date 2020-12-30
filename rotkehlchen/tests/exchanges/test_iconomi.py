import warnings as test_warnings
from unittest.mock import patch

import pytest

from rotkehlchen.assets.asset import Asset
from rotkehlchen.constants.assets import A_BTC, A_ETH, A_EUR
from rotkehlchen.errors import DeserializationError, UnknownAsset, UnprocessableTradePair
from rotkehlchen.exchanges.data_structures import Trade
from rotkehlchen.exchanges.iconomi import Iconomi
from rotkehlchen.fval import FVal
from rotkehlchen.tests.utils.history import TEST_END_TS
from rotkehlchen.tests.utils.mock import MockResponse
from rotkehlchen.typing import AssetMovementCategory, Location, Timestamp, TradeType
from rotkehlchen.utils.misc import ts_now

ICONOMI_BALANCES_RESPONSE = """
{"currency":"USD","daaList":[{"name":"CARUS-AR","ticker":"CAR","balance":"100.0","value":"1000.0"},{"name":"Strategy 2","ticker":"SCND","balance":"80.00000000","value":"0"}],"assetList":[{"name":"Aragon","ticker":"ANT","balance":"1000","value":"200.0"},{"name":"Ethereum","ticker":"ETH","balance":"32","value":"10000.031241234"},{"name":"Augur","ticker":"REP","balance":"0.5314532451","value":"0.8349030710000"}]}
"""

ICONOMI_TRADES_RESPONSE = """
{"transactions":[{"transactionId":"8362abff-12fd-4f6e-a152-590295d89bd2","timestamp":1539713117,"status":"COMPLETED","exchangeRate":16.89955950,"paymentMethod":"WALLET","type":"sell_asset","kind":"trade","source_ticker":"REP","source_amount":1000.23,"target_ticker":"EUR","target_amount":1505.63000000,"fee_ticker":"EUR","fee_amount":0E-8},{"transactionId":"e8c2c522-e43a-4cd9-b73b-812903bc85ca","timestamp":1539713118,"status":"COMPLETED","exchangeRate":16.66495657,"paymentMethod":"WALLET","type":"buy_asset","kind":"trade","source_ticker":"EUR","source_amount":999.90000000,"target_ticker":"REP","target_amount":1234,"fee_ticker":"EUR","fee_amount":0E-8},{"transactionId":"eb3c23fb-8910-428a-ad06-e6e2acf8c3a1","timestamp":1539713119,"status":"COMPLETED","address":"X","type":"deposit","kind":"sepa","amount_ticker":"EUR","amount":1000.00000000,"fee_ticker":"EUR","fee_amount":0E-8}]}
"""

ICONOMI_TRADES_EMPTY_RESPONSE = """
{"transactions":[]}
"""

def test_name():
    exchange = Iconomi('a', b'a', object(), object())
    assert exchange.name == 'iconomi'


def test_iconomi_query_balances_unknown_asset(function_scope_iconomi):
    """Test that if a iconomi balance query returns unknown asset no exception
    is raised and a warning is generated. Same for unsupported assets"""
    iconomi = function_scope_iconomi

    def mock_unknown_asset_return(url, **kwargs):  # pylint: disable=unused-argument
        print("lol", url)
        return MockResponse(200, ICONOMI_BALANCES_RESPONSE)

    with patch.object(iconomi.session, 'get', side_effect=mock_unknown_asset_return):
        # Test that after querying the assets only ETH and BTC are there
        balances, msg = iconomi.query_balances()

    assert msg == ''
    assert len(balances) == 3
    assert balances[A_ETH]['amount'] == FVal('32.0')
    assert balances[Asset('REP')]['amount'] == FVal('0.5314532451')

    warnings = iconomi.msg_aggregator.consume_warnings()
    assert len(warnings) == 2
    assert 'unsupported ICONOMI strategy CAR' in warnings[0]
    assert 'unsupported ICONOMI strategy SCND' in warnings[1]


def test_query_trade_history(function_scope_iconomi):
    """Happy path test for iconomi trade history querying"""
    iconomi = function_scope_iconomi

    def mock_api_return(url, **kwargs):  # pylint: disable=unused-argument
        print("lol", url, kwargs)
        if 'pageNumber=0' in url:
            return MockResponse(200, ICONOMI_TRADES_RESPONSE)
        else:
            return MockResponse(200, ICONOMI_TRADES_EMPTY_RESPONSE)

    with patch.object(iconomi.session, 'get', side_effect=mock_api_return):
        trades = iconomi.query_trade_history(
            start_ts=0,
            end_ts=1565732120,
        )

    assert len(trades) == 2
    assert trades[0].timestamp == 1539713117
    assert trades[0].location == Location.ICONOMI
    assert trades[0].pair == 'REP_EUR'
    assert trades[0].trade_type == TradeType.SELL
    assert trades[0].amount == FVal('1000.23')
    assert trades[0].rate.is_close(FVal('1.50528378472'))
    assert trades[0].fee.is_close(FVal('0.0'))
    assert isinstance(trades[0].fee_currency, Asset)
    assert trades[0].fee_currency == A_EUR

    assert trades[1].timestamp == 1539713118
    assert trades[1].location == Location.ICONOMI
    assert trades[1].pair == 'REP_EUR'
    assert trades[1].trade_type == TradeType.BUY
    assert trades[1].amount == FVal('1234')
    assert trades[1].rate.is_close(FVal('0.8102917341977309562398703404'))
    assert trades[1].fee.is_close(FVal('0.0'))
    assert isinstance(trades[1].fee_currency, Asset)
    assert trades[1].fee_currency == A_EUR
