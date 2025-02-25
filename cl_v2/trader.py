from dataclasses import dataclass
from typing import Dict

import prettytable as pt
import copy

from . import cl
from . import fun
from . import kcharts


@dataclass
class POSITION:
    """
    持仓对象
    """
    code: str
    mmd: str
    type: str = None
    balance: float = 0
    price: float = 0
    amount: float = 0
    loss_price: float = None
    open_date: str = None
    open_datetime: str = None
    close_datetime: str = None
    profit_rate: float = 0
    max_profit_rate: float = 0
    max_loss_rate: float = 0
    open_msg: str = ''
    close_msg: str = ''
    info: Dict = None
    # 以下信息，只有在回测的时候才会记录
    open_cl_data = None
    close_cl_data = None


class Trader(object):
    """
    回测交易（可继承支持实盘）
    """

    def __init__(self, name, is_stock=True, is_futures=False, mmds=None, log=None, is_test=True):
        """
        交易者初始化
        :param name: 交易者名称
        :param is_stock: 是否是股票交易（决定当日是否可以卖出）
        :param is_futures: 是否是期货交易（决定是否可以做空）
        :param mmds: 可交易的买卖点
        :param log: 日志展示方法
        :param is_test: 是否回测测试（回测的话会记录一些运行信息）
        """

        # 当前名称
        self.name = name
        self.is_stock = is_stock
        self.is_futures = is_futures
        self.allow_mmds = mmds
        self.is_test = is_test

        # 是否打印日志
        self.log = log
        self.log_history = []

        # 盯盘对象
        self.strategy = None

        # 存储代码最后的价格
        self.prices = {}

        # 存储缠论数据
        self.cl_datas:Dict[str, cl.CL] = {}

        # 代码当前运行时间
        self.todays = {}

        # 当前持仓信息
        self.positions = {}
        self.positions_history = {}

        # 代码订单信息
        self.orders = {}

        # 统计结果数据
        self.results = {
            '1buy': {'win_num': 0, 'loss_num': 0, 'win_balance': 0, 'loss_balance': 0},
            '2buy': {'win_num': 0, 'loss_num': 0, 'win_balance': 0, 'loss_balance': 0},
            'l2buy': {'win_num': 0, 'loss_num': 0, 'win_balance': 0, 'loss_balance': 0},
            '3buy': {'win_num': 0, 'loss_num': 0, 'win_balance': 0, 'loss_balance': 0},
            'l3buy': {'win_num': 0, 'loss_num': 0, 'win_balance': 0, 'loss_balance': 0},
            '1sell': {'win_num': 0, 'loss_num': 0, 'win_balance': 0, 'loss_balance': 0},
            '2sell': {'win_num': 0, 'loss_num': 0, 'win_balance': 0, 'loss_balance': 0},
            'l2sell': {'win_num': 0, 'loss_num': 0, 'win_balance': 0, 'loss_balance': 0},
            '3sell': {'win_num': 0, 'loss_num': 0, 'win_balance': 0, 'loss_balance': 0},
            'l3sell': {'win_num': 0, 'loss_num': 0, 'win_balance': 0, 'loss_balance': 0},
        }

    def set_strategy(self, strategy):
        """
        设置策略对象
        :param strategy:
        :return:
        """
        self.strategy = strategy

    # 运行的唯一入口
    def run(self, code, cl_datas: Dict[str, cl.CL]):
        self.cl_datas[code] = cl_datas

        # 存储当前代码最后价格/时间
        frequencys = list(cl_datas.keys())
        self.prices[code] = float(cl_datas[frequencys[-1]].klines[-1].c)
        self.todays[code] = cl_datas[frequencys[-1]].klines[-1].date

        high_price = float(cl_datas[frequencys[-1]].klines[-1].h)
        low_price = float(cl_datas[frequencys[-1]].klines[-1].l)
        self._position_record(code, high_price, low_price)

        # 优先检查持仓情况
        if code in self.positions:
            for mmd in self.positions[code]:
                pos = self.positions[code][mmd]
                opt = self.strategy.stare(mmd, pos, list(cl_datas.values()))
                if opt:
                    self.execute(code, opt)

        # 再执行检查机会方法
        opts = self.strategy.look(list(cl_datas.values()))
        if opts:
            for opt in opts:
                self.execute(code, opt)

        return True

    # 运行结束，统一清仓
    def end(self):
        for code in self.positions:
            for mmd in self.positions[code]:
                pos = self.positions[code][mmd]
                if pos.balance > 0:
                    self.execute(code, {'opt': 'sell', 'mmd': mmd, 'msg': '退出'})
        return True

    # 结果显示Kline结果
    def show_kline(self, code, show_frequency='d'):
        cd = self.cl_datas[code][show_frequency]
        orders = fun.convert_stock_order_by_frequency(self.orders[code], show_frequency) if code in self.orders else []
        render = kcharts.render_charts('%s' % code, cd, orders=orders)
        return render

    # 查询代码买卖点的持仓信息
    def query_code_mmd_pos(self, code: str, mmd: str) -> POSITION:
        if code in self.positions:
            if mmd in self.positions[code]:
                return self.positions[code][mmd]
            else:
                self.positions[code][mmd] = POSITION(code=code, mmd=mmd)
        else:
            self.positions[code] = {mmd: POSITION(code=code, mmd=mmd)}
        return self.positions[code][mmd]

    def reset_pos(self, code: str, mmd: str):
        # 增加进入历史
        self.positions[code][mmd].close_datetime = self.todays[code].strftime('%Y-%m-%d %H:%M:%S')
        if code not in self.positions_history:
            self.positions_history[code] = []
        self.positions_history[code].append(self.positions[code][mmd])

        self.positions[code][mmd] = POSITION(code=code, mmd=mmd)
        return

    def _position_record(self, code: str, high_price: float, low_price: float):
        """
        持仓记录更新
        :param code:
        :param high_price:
        :param low_price:
        :return:
        """
        if code not in self.positions:
            return
        for pos in self.positions[code].values():
            if pos.balance == 0:
                continue
            if pos.type == '做多':
                profit_rate = round((high_price - pos.price) / pos.price * 100, 4)
                pos.max_profit_rate = max(pos.max_profit_rate, profit_rate)
                pos.max_loss_rate = min(pos.max_loss_rate, profit_rate)
            if pos.type == '做空':
                profit_rate = round((pos.price - low_price) / pos.price * 100, 4)
                pos.max_profit_rate = max(pos.max_profit_rate, profit_rate)
                pos.max_loss_rate = min(pos.max_loss_rate, profit_rate)
        return

    # 做多买入
    def open_buy(self, code, opt):
        use_balance = 100000
        amount = round((use_balance / self.prices[code]) * 0.99, 4)
        return {'price': self.prices[code], 'amount': amount}

    # 做空卖出
    def open_sell(self, code, opt):
        use_balance = 100000
        amount = round((use_balance / self.prices[code]) * 0.99, 4)
        return {'price': self.prices[code], 'amount': amount}

    # 做多平仓
    def close_buy(self, code, pos: POSITION, opt):
        return {'price': self.prices[code], 'amount': pos.amount}

    # 做空平仓
    def close_sell(self, code, pos: POSITION, opt):
        return {'price': self.prices[code], 'amount': pos.amount}

    # 打印日志信息
    def _print_log(self, msg):
        self.log_history.append(msg)
        if self.log:
            self.log(msg)
        return

    # 执行操作
    def execute(self, code, opt):
        opt_mmd = opt['mmd']
        # 检查是否在允许做的买卖点上
        if self.allow_mmds is not None and opt_mmd not in self.allow_mmds:
            return True

        pos = self.query_code_mmd_pos(code, opt_mmd)
        res = None
        # 买点，买入，开仓做多
        if 'buy' in opt_mmd and opt['opt'] == 'buy':
            if pos.balance > 0:
                return False
            res = self.open_buy(code, opt)
            if res is False:
                return False
            pos.type = '做多'
            pos.price = res['price']
            pos.amount = res['amount']
            pos.balance = res['price'] * res['amount']
            pos.loss_price = opt['loss_price']
            pos.open_date = self.todays[code].strftime('%Y-%m-%d')
            pos.open_datetime = self.todays[code].strftime('%Y-%m-%d %H:%M:%S')
            pos.open_msg = opt['msg']
            pos.info = opt['info']
            if self.is_test:
                pos.open_cl_data = copy.deepcopy(self.cl_datas[code])

            self._print_log('[%s - %s] // %s 做多买入（%s - %s），原因： %s' % (
                code, self.todays[code], opt_mmd, res['price'], res['amount'], opt['msg']))

        # 卖点，买入，开仓做空（期货）
        if self.is_futures and 'sell' in opt_mmd and opt['opt'] == 'buy':
            if pos.balance > 0:
                return False
            res = self.open_sell(code, opt)
            if res is False:
                return False
            pos.type = '做空'
            pos.price = res['price']
            pos.amount = res['amount']
            pos.balance = res['price'] * res['amount']
            pos.loss_price = opt['loss_price']
            pos.open_date = self.todays[code].strftime('%Y-%m-%d')
            pos.open_datetime = self.todays[code].strftime('%Y-%m-%d %H:%M:%S')
            pos.open_msg = opt['msg']
            pos.info = opt['info']
            if self.is_test:
                pos.open_cl_data = copy.deepcopy(self.cl_datas[code])

            self._print_log('[%s - %s] // %s 做空卖出（%s - %s），原因： %s' % (
                code, self.todays[code], opt_mmd, res['price'], res['amount'], opt['msg']))

        # 卖点，卖出，平仓做空（期货）
        if self.is_futures and 'sell' in opt_mmd and opt['opt'] == 'sell':
            if pos.balance == 0:
                return False
            if self.is_stock and pos.open_date == self.todays[code].strftime('%Y-%m-%d'):
                # 股票交易，当日不能卖出
                return False
            res = self.close_sell(code, pos, opt)
            if res is False:
                return False
            sell_balance = res['price'] * res['amount']
            hold_balance = pos.balance

            profit = hold_balance - sell_balance
            if profit > 0:
                # 盈利
                self.results[opt_mmd]['win_num'] += 1
                self.results[opt_mmd]['win_balance'] += profit
            else:
                # 亏损
                self.results[opt_mmd]['loss_num'] += 1
                self.results[opt_mmd]['loss_balance'] += abs(profit)

            profit_rate = round((profit / hold_balance) * 100, 2)
            pos.profit_rate = profit_rate
            pos.close_msg = opt['msg']
            if self.is_test:
                pos.close_cl_data = copy.deepcopy(self.cl_datas[code])

            self._print_log('[%s - %s] // %s 平仓做空（%s - %s） 盈亏：%s (%.2f%%)，原因： %s' % (
                code, self.todays[code], opt_mmd, res['price'], res['amount'], profit, profit_rate, opt['msg']))

            # 清空持仓
            self.reset_pos(code, opt_mmd)

        # 买点，卖出，平仓做多
        if 'buy' in opt_mmd and opt['opt'] == 'sell':
            if pos.balance == 0:
                return False
            if self.is_stock and pos.open_date == self.todays[code].strftime('%Y-%m-%d'):
                # 股票交易，当日不能卖出
                return False
            res = self.close_buy(code, pos, opt)
            if res is False:
                return False
            sell_balance = res['price'] * res['amount']
            hold_balance = pos.balance
            profit = sell_balance - hold_balance
            if profit > 0:
                # 盈利
                self.results[opt_mmd]['win_num'] += 1
                self.results[opt_mmd]['win_balance'] += profit
            else:
                # 亏损
                self.results[opt_mmd]['loss_num'] += 1
                self.results[opt_mmd]['loss_balance'] += abs(profit)

            profit_rate = round((profit / hold_balance) * 100, 2)
            pos.profit_rate = profit_rate
            pos.close_msg = opt['msg']
            if self.is_test:
                pos.close_cl_data = copy.deepcopy(self.cl_datas[code])

            self._print_log('[%s - %s] // %s 平仓做多（%s - %s） 盈亏：%s  (%.2f%%)，原因： %s' % (
                code, self.todays[code], opt_mmd, res['price'], res['amount'], profit, profit_rate, opt['msg']))

            # 清空持仓
            self.reset_pos(code, opt_mmd)

        if res:
            # 记录订单信息
            if code not in self.orders:
                self.orders[code] = []
            self.orders[code].append({
                'datetime': self.todays[code],
                'type': opt['opt'],
                'price': res['price'],
                'amount': res['amount'],
                'info': opt['msg'],
            })
            return True

        return False


# 所有交易者中的结果进行汇总并统计，之后格式化输出
def traders_result(traders, _pfun=None):
    if _pfun is None:
        _pfun = print

    tb = pt.PrettyTable()
    tb.field_names = ["买卖点", "成功", "失败", '胜率', "盈利", '亏损', '净利润', '回吐比例', '平均盈利', '平均亏损', '盈亏比']

    results = {
        '1buy': {'win_num': 0, 'loss_num': 0, 'win_balance': 0, 'loss_balance': 0},
        '2buy': {'win_num': 0, 'loss_num': 0, 'win_balance': 0, 'loss_balance': 0},
        'l2buy': {'win_num': 0, 'loss_num': 0, 'win_balance': 0, 'loss_balance': 0},
        '3buy': {'win_num': 0, 'loss_num': 0, 'win_balance': 0, 'loss_balance': 0},
        'l3buy': {'win_num': 0, 'loss_num': 0, 'win_balance': 0, 'loss_balance': 0},
        '1sell': {'win_num': 0, 'loss_num': 0, 'win_balance': 0, 'loss_balance': 0},
        '2sell': {'win_num': 0, 'loss_num': 0, 'win_balance': 0, 'loss_balance': 0},
        'l2sell': {'win_num': 0, 'loss_num': 0, 'win_balance': 0, 'loss_balance': 0},
        '3sell': {'win_num': 0, 'loss_num': 0, 'win_balance': 0, 'loss_balance': 0},
        'l3sell': {'win_num': 0, 'loss_num': 0, 'win_balance': 0, 'loss_balance': 0},
    }
    for t in traders:
        for mmd in results.keys():
            results[mmd]['win_num'] += t.results[mmd]['win_num']
            results[mmd]['loss_num'] += t.results[mmd]['loss_num']
            results[mmd]['win_balance'] += t.results[mmd]['win_balance']
            results[mmd]['loss_balance'] += t.results[mmd]['loss_balance']

    mmds = {
        '1buy': '一类买点', '2buy': '二类买点', 'l2buy': '类二类买点', '3buy': '三类买点', 'l3buy': '类三类买点',
        '1sell': '一类卖点', '2sell': '二类卖点', 'l2sell': '类二类卖点', '3sell': '三类卖点', 'l3sell': '类三类卖点',
    }
    for k in results.keys():
        mmd = mmds[k]
        win_num = results[k]['win_num']
        loss_num = results[k]['loss_num']
        shenglv = 0 if win_num == 0 and loss_num == 0 else win_num / (win_num + loss_num) * 100
        win_balance = results[k]['win_balance']
        loss_balance = results[k]['loss_balance']
        net_balance = win_balance - loss_balance
        back_rate = 0 if win_balance == 0 else loss_balance / win_balance * 100
        win_mean_balance = 0 if win_num == 0 else win_balance / win_num
        loss_mean_balance = 0 if loss_num == 0 else loss_balance / loss_num
        ykb = 0 if loss_mean_balance == 0 or win_mean_balance == 0 else win_mean_balance / loss_mean_balance

        tb.add_row([mmd, win_num, loss_num, str(round(shenglv, 2)) + '%', round(win_balance, 2), round(loss_balance, 2),
                    round(net_balance, 2), round(back_rate, 2), round(win_mean_balance, 2), round(loss_mean_balance, 2),
                    round(ykb, 4)])
    return _pfun(tb)
