import hmac
import hashlib
import base64
import aiohttp

from dydx3.constants import COLLATERAL_ASSET
from dydx3.constants import COLLATERAL_TOKEN_DECIMALS
from dydx3.constants import FACT_REGISTRY_CONTRACT
from dydx3.constants import NETWORK_ID_GOERLI
from dydx3.constants import TIME_IN_FORCE_GTT
from dydx3.constants import TOKEN_CONTRACTS
from dydx3.helpers.db import get_account_id
from dydx3.helpers.request_helpers import epoch_seconds_to_iso
from dydx3.helpers.request_helpers import generate_now_iso
from dydx3.helpers.request_helpers import generate_query_path
from dydx3.helpers.request_helpers import random_client_id
from dydx3.helpers.request_helpers import iso_to_epoch_seconds
from dydx3.helpers.request_helpers import json_stringify
from dydx3.helpers.request_helpers import remove_nones
from dydx3.helpers.requests import request
from dydx3.starkex.helpers import get_transfer_erc20_fact
from dydx3.starkex.helpers import nonce_from_client_id
from dydx3.starkex.order import SignableOrder
from dydx3.starkex.withdrawal import SignableWithdrawal
from dydx3.starkex.conditional_transfer import SignableConditionalTransfer
from dydx3.starkex.transfer import SignableTransfer


class Private(object):

    def __init__(
        self,
        host,
        network_id,
        stark_private_key,
        default_address,
        api_timeout,
        api_key_credentials,
    ):
        self.host = host
        self.network_id = network_id
        self.stark_private_key = stark_private_key
        self.default_address = default_address
        self.api_timeout = api_timeout
        self.api_key_credentials = api_key_credentials
        self._session = None

    @property
    def session(self):
        """
        Lazily created the session
        """
        if self._session:
            return self._session
        headers = {
            'Accept': 'application/json',
            'Content-Type': 'application/json',
            'User-Agent': 'dydx/python',
        }
        self._session = aiohttp.ClientSession(headers=headers)
        return self._session

    async def close(self):
        if self._session:
            await self._session.close()

    # ============ Request Helpers ============

    async def _private_request(
        self,
        method,
        endpoint,
        data={},
    ):
        now_iso_string = generate_now_iso()
        request_path = '/'.join(['/v3', endpoint])
        signature = self.sign(
            request_path=request_path,
            method=method.upper(),
            iso_timestamp=now_iso_string,
            data=remove_nones(data),
        )
        headers = {
            'DYDX-SIGNATURE': signature,
            'DYDX-API-KEY': self.api_key_credentials['key'],
            'DYDX-TIMESTAMP': now_iso_string,
            'DYDX-PASSPHRASE': self.api_key_credentials['passphrase'],
        }
        return await request(
            self.host + request_path,
            method,
            session=self.session,
            headers=headers,
            data_values=data,
            api_timeout=self.api_timeout
        )

    async def _get(self, endpoint, params):
        return await self._private_request(
            'get',
            generate_query_path(endpoint, params),
        )

    async def _post(self, endpoint, data):
        return await self._private_request(
            'post',
            endpoint,
            data
        )

    async def _put(self, endpoint, data):
        return await self._private_request(
            'put',
            endpoint,
            data
        )

    async def _delete(self, endpoint, params):
        return await self._private_request(
            'delete',
            generate_query_path(endpoint, params),
        )

    # ============ Requests ============

    async def get_api_keys(
        self,
    ):
        '''
        Get API keys.

        :returns: Object containing an array of apiKeys

        :raises: DydxAPIError
        '''
        return await self._get(
            'api-keys',
            {},
        )

    async def get_registration(self):
        '''
        Get signature for registration

        :returns: str

        :raises: DydxAPIError
        '''

        return await self._get('registration', {})

    async def get_user(self):
        '''
        Get user information

        :returns: User

        :raises: DydxAPIError
        '''
        return await self._get('users', {})

    async def update_user(
        self,
        user_data={},
        email=None,
        username=None,
        is_sharing_username=None,
        is_sharing_address=None,
        country=None,
        language_code=None,
    ):
        '''
        Update user information

        :param user_data: optional
        :type user_data: dict

        :param email: optional
        :type email: str

        :param username: optional
        :type username: str

        :param is_sharing_username: optional
        :type is_sharing_username: str

        :param is_sharing_address: optional
        :type is_sharing_address: str

        :param country optional
        :type country: str (ISO 3166-1 Alpha-2)

        :param language_code optional
        :type language_code: str (ISO 639-1, including 'zh-CN')

        :returns: User

        :raises: DydxAPIError
        '''
        return await self._put(
            'users',
            {
                'email': email,
                'username': username,
                'isSharingUsername': is_sharing_username,
                'isSharingAddress': is_sharing_address,
                'userData': json_stringify(user_data),
                'country': country,
            },
        )

    async def create_account(
        self,
        stark_public_key,
        stark_public_key_y_coordinate,
    ):
        '''
        Make an account

        :param stark_public_key: required
        :type stark_public_key: str

        :param stark_public_key_y_coordinate: required
        :type stark_public_key_y_coordinate: str

        :returns: Account

        :raises: DydxAPIError
        '''
        return await self._post(
            'accounts',
            {
                'starkKey': stark_public_key,
                'starkKeyYCoordinate': stark_public_key_y_coordinate,
            }
        )

    async def get_account(
        self,
        ethereum_address=None,
    ):
        '''
        Get an account

        :param ethereum_address: optional
        :type ethereum_address: str

        :returns: Account

        :raises: DydxAPIError
        '''
        address = ethereum_address or self.default_address
        if address is None:
            raise ValueError('ethereum_address was not set')
        return await self._get(
            '/'.join(['accounts', get_account_id(address)]),
            {},
        )

    async def get_accounts(
        self,
    ):
        '''
        Get accounts

        :returns: Array of accounts for a user

        :raises: DydxAPIError
        '''
        return await self._get(
            'accounts',
            {},
        )

    async def get_positions(
        self,
        market=None,
        status=None,
        limit=None,
        created_before_or_at=None,
    ):
        '''
        Get positions

        :param market: optional
        :type market: str in list [
            "BTC-USD",
            "ETH-USD",
            "LINK-USD",
            ...
        ]

        :param status: optional
        :type status: str in list [
            "OPEN",
            "CLOSED",
            "LIQUIDATED",
        ]

        :param limit: optional
        :type limit: str

        :param created_before_or_at: optional
        :type created_before_or_at: ISO str

        :returns: Array of positions

        :raises: DydxAPIError
        '''
        return await self._get(
            'positions',
            {
                'market': market,
                'limit': limit,
                'status': status,
                'createdBeforeOrAt': created_before_or_at,
            },
        )

    async def get_orders(
        self,
        market=None,
        status=None,
        side=None,
        order_type=None,
        limit=None,
        created_before_or_at=None,
        returnLatestOrders=None,
    ):
        '''
        Get orders

        :param market: optional
        :type market: str in list [
            "BTC-USD",
            "ETH-USD",
            "LINK-USD",
            ...
        ]

        :param status: optional
        :type status: str in list [
            "PENDING",
            "OPEN",
            "FILLED",
            "CANCELED",
            "UNTRIGGERED",
        ]

        :param side: optional
        :type side: str in list [
            "BUY",
            "SELL",
        ]

        :param order_type: optional
        :type order_type: str in list [
            "LIMIT",
            "STOP",
            "TRAILING_STOP",
            "TAKE_PROFIT",
        ]

        :param limit: optional
        :type limit: str

        :param created_before_or_at: optional
        :type created_before_or_at: ISO str

        :param returnLatestOrders: optional
        :type returnLatestOrders: boolean

        :returns: Array of Orders

        :raises: DydxAPIError
        '''
        return await self._get(
            'orders',
            {
                'market': market,
                'status': status,
                'side': side,
                'type': order_type,
                'limit': limit,
                'createdBeforeOrAt': created_before_or_at,
                'returnLatestOrders': returnLatestOrders,
            },
        )

    async def get_active_orders(
        self,
        market,
        side=None,
        id=None,
    ):
        '''
        Get ActiveOrders
        :param market: required
        :type market: str in list [
            "BTC-USD",
            "ETH-USD",
            "LINK-USD",
            ...
        ]
        :param side: optional (required if id is passed in)
        :type side: str in list [
            "BUY",
            "SELL",
        ]
        param id: optional
        :type id: str
        :returns: Array of ActiveOrders
        :raises: DydxAPIError
        '''
        return await self._get(
            'active-orders',
            {
                'market': market,
                'side': side,
                'id': id,
            },
        )

    async def get_order_by_id(
        self,
        order_id,
    ):
        '''
        Get order by its id

        :param order_id: required
        :type order_id: str

        :returns: Order

        :raises: DydxAPIError
        '''
        return await self._get(
            '/'.join(['orders', order_id]),
            {},
        )

    async def get_order_by_client_id(
        self,
        client_id,
    ):
        '''
        Get order by its client_id

        :param client_id: required
        :type client_id: str

        :returns: Order

        :raises: DydxAPIError
        '''
        return await self._get(
            '/'.join(['orders/client', client_id]),
            {},
        )

    async def create_order(
        self,
        position_id,
        market,
        side,
        order_type,
        post_only,
        size,
        price,
        limit_fee,
        time_in_force=None,
        cancel_id=None,
        trigger_price=None,
        trailing_percent=None,
        client_id=None,
        expiration=None,
        expiration_epoch_seconds=None,
        signature=None,
        reduce_only=None
    ):
        '''
        Post an order

        :param position_id: required
        :type position_id: str or int

        :param market: required
        :type market: str in list [
            "BTC-USD",
            "ETH-USD",
            "LINK-USD",
            ...
        ]

        :param side: required
        :type side: str in list[
            "BUY",
            "SELL",
        ],

        :param order_type: required
        :type order_type: str in list [
            "LIMIT",
            "STOP",
            "TRAILING_STOP",
            "TAKE_PROFIT",
        ]

        :param post_only: required
        :type post_only: bool

        :param size: required
        :type size: str

        :param price: required
        :type price: str

        :param limit_fee: required
        :type limit_fee: str

        :param time_in_force: optional
        :type time_in_force: str in list [
            "GTT",
            "FOK",
            "IOC",
        ]

        :param cancel_id: optional
        :type cancel_id: str

        :param trigger_price: optional
        :type trigger_price: Decimal

        :param trailing_percent: optional
        :type trailing_percent: Decimal

        :param client_id: optional
        :type client_id: str

        :param expiration: optional
        :type expiration: ISO str

        :param expiration_epoch_seconds: optional
        :type expiration_epoch_seconds: int

        :param signature: optional
        type signature: str

        :param reduce_only: optional
        type reduce_only: bool

        :returns: Order

        :raises: DydxAPIError
        '''
        client_id = client_id or random_client_id()
        if bool(expiration) == bool(expiration_epoch_seconds):
            raise ValueError(
                'Exactly one of expiration and expiration_epoch_seconds must '
                'be specified',
            )
        expiration = expiration or epoch_seconds_to_iso(
            expiration_epoch_seconds,
        )
        expiration_epoch_seconds = (
            expiration_epoch_seconds or iso_to_epoch_seconds(expiration)
        )

        order_signature = signature
        if not order_signature:
            if not self.stark_private_key:
                raise Exception(
                    'No signature provided and client was not ' +
                    'initialized with stark_private_key'
                )
            order_to_sign = SignableOrder(
                network_id=self.network_id,
                position_id=position_id,
                client_id=client_id,
                market=market,
                side=side,
                human_size=size,
                human_price=price,
                limit_fee=limit_fee,
                expiration_epoch_seconds=expiration_epoch_seconds,
            )
            order_signature = order_to_sign.sign(self.stark_private_key)

        order = {
            'market': market,
            'side': side,
            'type': order_type,
            'timeInForce': time_in_force or TIME_IN_FORCE_GTT,
            'size': size,
            'price': price,
            'limitFee': limit_fee,
            'expiration': expiration,
            'cancelId': cancel_id,
            'triggerPrice': trigger_price,
            'trailingPercent': trailing_percent,
            'postOnly': post_only,
            'clientId': client_id,
            'signature': order_signature,
            'reduceOnly': reduce_only,
        }

        return await self._post(
            'orders',
            order,
        )

    async def cancel_order(
        self,
        order_id,
    ):
        '''
        Cancel an order

        :param order_id: required
        :type order_id: str

        :returns: Order

        :raises: DydxAPIError
        '''
        return await self._delete(
            '/'.join(['orders', order_id]),
            {},
        )

    async def cancel_all_orders(
        self,
        market=None,
    ):
        '''
        Cancel all orders

        :param market: optional
        :type market: str in list [
            "BTC-USD",
            "ETH-USD",
            "LINK-USD",
            ...
        ]

        :returns: Array of orders

        :raises: DydxAPIError
        '''
        params = {'market': market} if market else {}
        return await self._delete(
            'orders',
            params,
        )

    async def cancel_active_orders(
            self,
            market,
            side=None,
            id=None,
    ):
        '''
        Cancel ActiveOrders
        :param market: required
        :type market: str in list [
            "BTC-USD",
            "ETH-USD",
            "LINK-USD",
            ...
        ]
        :param side: optional (required if id is passed in)
        :type side: str in list [
            "BUY",
            "SELL",
        ]
        param id: optional
        :type id: str
        :returns: Array of ActiveOrders
        :raises: DydxAPIError
        '''
        return await self._delete(
            'active-orders',
            {
                'market': market,
                'side': side,
                'id': id,
            },
        )

    async def get_fills(
        self,
        market=None,
        order_id=None,
        limit=None,
        created_before_or_at=None,
    ):
        '''
        Get fills

        :param market: optional
        :type market: str in list [
            "BTC-USD",
            "ETH-USD",
            "LINK-USD",
            ...
        ]

        :param order_id: optional
        :type order_id: str

        :param limit: optional
        :type limit: str

        :param created_before_or_at: optional
        :type created_before_or_at: ISO str

        :returns: Array of fills

        :raises: DydxAPIError
        '''
        return await self._get(
            'fills',
            {
                'market': market,
                'orderId': order_id,
                'limit': limit,
                'createdBeforeOrAt': created_before_or_at,
            }
        )

    async def get_transfers(
        self,
        transfer_type=None,
        limit=None,
        created_before_or_at=None,
    ):
        '''
        Get transfers

        :param transfer_type: optional
        :type transfer_type: str in list [
            "DEPOSIT",
            "WITHDRAWAL",
            "FAST_WITHDRAWAL",
        ]

        :param limit: optional
        :type limit: str

        :param created_before_or_at: optional
        :type created_before_or_at: ISO str

        :returns: Array of transfers

        :raises: DydxAPIError
        '''
        return await self._get(
            'transfers',
            {
                'type': transfer_type,
                'limit': limit,
                'createdBeforeOrAt': created_before_or_at,
            },
        )

    async def create_withdrawal(
        self,
        position_id,
        amount,
        asset,
        to_address,
        client_id=None,
        expiration=None,
        expiration_epoch_seconds=None,
        signature=None,
    ):
        '''
        Post a withdrawal

        :param position_id: required
        :type position_id: int or str

        :param amount: required
        :type amount: str

        :param asset: required
        :type asset: str in list [
            "ETH",
            "LINK",
            "BTC",
            "USDC",
            "USDT",
            "USD",
            ...
        ]

        :param client_id: optional
        :type client_id: str

        :param expiration: optional
        :type expiration: ISO str

        :param expiration_epoch_seconds: optional
        :type expiration_epoch_seconds: int

        :param signature: optional
        :type signature: str

        :returns: Transfer

        :raises: DydxAPIError
        '''
        client_id = client_id or random_client_id()
        if bool(expiration) == bool(expiration_epoch_seconds):
            raise ValueError(
                'Exactly one of expiration and expiration_epoch_seconds must '
                'be specified',
            )
        expiration = expiration or epoch_seconds_to_iso(
            expiration_epoch_seconds,
        )
        expiration_epoch_seconds = (
            expiration_epoch_seconds or iso_to_epoch_seconds(expiration)
        )

        if not signature:
            if not self.stark_private_key:
                raise Exception(
                    'No signature provided and client was not' +
                    'initialized with stark_private_key'
                )
            withdrawal_to_sign = SignableWithdrawal(
                network_id=self.network_id,
                position_id=position_id,
                client_id=client_id,
                human_amount=amount,
                expiration_epoch_seconds=expiration_epoch_seconds,
            )
            signature = withdrawal_to_sign.sign(self.stark_private_key)

        params = {
            'amount': amount,
            'asset': asset,
            'expiration': expiration,
            'clientId': client_id,
            'signature': signature,
        }
        return await self._post('withdrawals', params)

    async def create_fast_withdrawal(
        self,
        position_id,
        credit_asset,
        credit_amount,
        debit_amount,
        to_address,
        lp_position_id,
        lp_stark_public_key,
        slippage_tolerance=None,
        client_id=None,
        expiration=None,
        expiration_epoch_seconds=None,
        signature=None,
    ):
        '''
        Post a fast withdrawal

        :param credit_asset: required
        :type credit_asset: str in list [
            "USDC",
            "USDT",
        ]

        :param position_id: required
        :type position_id: str or int

        :param credit_amount: required
        :type credit_amount: str or int

        :param debit_amount: required
        :type debit_amount: str or int

        :param to_address: required
        :type to_address: str

        :param lp_position_id: required
        :type lp_position_id: str or int

        :param lp_stark_public_key: required
        :type lp_stark_public_key: str

        :param slippage_tolerance: optional
        :type slippage_tolerance: str

        :param client_id: optional
        :type client_id: str

        :param expiration: optional
        :type expiration: ISO str

        :param expiration_epoch_seconds: optional
        :type expiration_epoch_seconds: int

        :param signature: optional
        :type signature: str

        :returns: Transfer

        :raises: DydxAPIError
        '''
        client_id = client_id or random_client_id()
        if bool(expiration) == bool(expiration_epoch_seconds):
            raise ValueError(
                'Exactly one of expiration and expiration_epoch_seconds must '
                'be specified',
            )
        expiration = expiration or epoch_seconds_to_iso(
            expiration_epoch_seconds,
        )
        expiration_epoch_seconds = (
            expiration_epoch_seconds or iso_to_epoch_seconds(expiration)
        )

        if not signature:
            if not self.stark_private_key:
                raise Exception(
                    'No signature provided and client was not' +
                    'initialized with stark_private_key'
                )
            fact = get_transfer_erc20_fact(
                recipient=to_address,
                token_decimals=COLLATERAL_TOKEN_DECIMALS,
                human_amount=credit_amount,
                token_address=(
                    TOKEN_CONTRACTS[COLLATERAL_ASSET][self.network_id]
                ),
                salt=nonce_from_client_id(client_id),
            )
            transfer_to_sign = SignableConditionalTransfer(
                network_id=self.network_id,
                sender_position_id=position_id,
                receiver_position_id=lp_position_id,
                receiver_public_key=lp_stark_public_key,
                fact_registry_address=FACT_REGISTRY_CONTRACT[self.network_id],
                fact=fact,
                human_amount=debit_amount,
                client_id=client_id,
                expiration_epoch_seconds=expiration_epoch_seconds,
            )
            signature = transfer_to_sign.sign(self.stark_private_key)

        params = {
            'creditAsset': credit_asset,
            'creditAmount': credit_amount,
            'debitAmount': debit_amount,
            'slippageTolerance': slippage_tolerance,
            # TODO: Signature verification should work regardless of case.
            'toAddress': to_address.lower(),
            'lpPositionId': lp_position_id,
            'expiration': expiration,
            'clientId': client_id,
            'signature': signature,
        }
        return await self._post('fast-withdrawals', params)

    async def get_funding_payments(
        self,
        market=None,
        limit=None,
        effective_before_or_at=None,
    ):
        '''
        Get funding payments

        :param market: optional
        :type market: str in list [
            "BTC-USD",
            "ETH-USD",
            "LINK-USD",
            ...
        ]

        :param limit: optional
        :type limit: str

        :param effective_before_or_at: optional
        :type effective_before_or_at: ISO str

        :returns: Array of funding payments

        :raises: DydxAPIError
        '''
        return await self._get(
            'funding',
            {
                'market': market,
                'limit': limit,
                'effectiveBeforeOrAt': effective_before_or_at,
            },
        )

    async def get_historical_pnl(
        self,
        created_before_or_at=None,
        created_on_or_after=None,
    ):
        '''
        Get historical pnl ticks

        :param created_before_or_at: optional
        :type created_before_or_at: ISO str

        :param created_on_or_after: optional
        :type created_on_or_after: ISO str

        :returns: Array of historical pnl ticks

        :raises: DydxAPIError
        '''
        return await self._get(
            'historical-pnl',
            {
                'createdBeforeOrAt': created_before_or_at,
                'createdOnOrAfter': created_on_or_after,
            },
        )

    async def send_verification_email(
        self,
    ):
        '''
        Send verification email

        :returns: Empty object

        :raises: DydxAPIError
        '''
        return await self._put(
            'emails/send-verification-email',
            {},
        )

    async def get_trading_rewards(
        self,
        epoch=None,
    ):
        '''
        Get trading rewards

        :param epoch: optional
        :type epoch: int

        :returns: TradingRewards

        :raises: DydxAPIError
        '''
        return await self._get(
            'rewards/weight',
            {
                'epoch': epoch,
            },
        )

    def get_liquidity_provider_rewards_v2(
        self,
        epoch=None,
    ):
        '''
        Get liquidity provider rewards

        :param epoch: optional
        :type epoch: int

        :returns: LiquidityProviderRewards

        :raises: DydxAPIError
        '''
        return self._get(
            'rewards/liquidity-provider',
            {
                'epoch': epoch,
            },
        )

    def get_liquidity_provider_rewards(
        self,
        epoch=None,
    ):
        '''
        (Deprecated, please use get_liquidity_provider_rewards_v2)
        Get liquidity rewards

        :param epoch: optional
        :type epoch: int

        :returns: LiquidityRewards

        :raises: DydxAPIError
        '''
        return self._get(
            'rewards/liquidity',
            {
                'epoch': epoch,
            },
        )

    async def get_retroactive_mining_rewards(
        self,
    ):
        '''
        Get retroactive mining rewards

        :returns: RetroactiveMiningRewards

        :raises: DydxAPIError
        '''
        return await self._get('rewards/retroactive-mining')

    async def request_testnet_tokens(
        self,
    ):
        '''
        Requests tokens on dYdX's staging server.
        NOTE: this will not work on Mainnet/Production.

        :returns: Transfer

        :raises: DydxAPIError
        '''
        if (self.network_id != 3):
            raise ValueError('network_id is not Ropsten')

        return await self._post('testnet/tokens', {})

    # ============ Signing ============

    def sign(
        self,
        request_path,
        method,
        iso_timestamp,
        data,
    ):
        message_string = (
            iso_timestamp +
            method +
            request_path +
            (json_stringify(data) if data else '')
        )

        hashed = hmac.new(
            base64.urlsafe_b64decode(
                (self.api_key_credentials['secret']).encode('utf-8'),
            ),
            msg=message_string.encode('utf-8'),
            digestmod=hashlib.sha256,
        )
        return base64.urlsafe_b64encode(hashed.digest()).decode()
