import pickle
from django.http import HttpResponse
from django.shortcuts import render
from typing import Dict

from cl_v2 import rd
from cl_v2 import trader
from cl_v2 import kcharts
from cl_v2.my import trader_currency
from cl_v2.my import trader_hk_stock


def trader_view(request):
    """
    交易对象页面展示
    :param request:
    :return:
    """
    # 数字货币交易对象
    currency_trader = pickle.loads(rd.get_byte('trader_currency'))
    currency_result = trader.traders_result([currency_trader], lambda a: a).get_html_string(
        attributes={'class': 'table'})

    # 港股交易对象
    hk_stock_trader = pickle.loads(rd.get_byte('trader_hk_stock'))

    hk_stock_result = trader.traders_result([hk_stock_trader], lambda a: a).get_html_string(
        attributes={'class': 'table'})

    return render(request, 'trader_view.html', {
        'currency_trader': currency_trader,
        'currency_result': currency_result,
        'hk_stock_trader': hk_stock_trader,
        'hk_stock_result': hk_stock_result
    })


# 变量记录回测记录，避免每次请求都加载
__global_traders: Dict[str, Dict[str, trader.Trader]] = {}


def StrategyBackIndex(request):
    global __global_traders

    strategy_key = request.GET.get('strategy_key')
    show_mmd = request.GET.get('mmd')

    codes = []  # 记录运行的股票代码
    strategy_class = ''  # 记录运行的策略类
    result_table_html = ''  # 记录策略结果表格
    positions = {}  # 记录所有持仓历史记录

    if strategy_key is not None:
        if strategy_key not in __global_traders:
            p_obj = rd.strategy_get(strategy_key)
            __global_traders[strategy_key] = pickle.loads(p_obj)

        result_table_html = trader.traders_result(__global_traders[strategy_key].values(), lambda a: a).get_html_string(
                attributes={'class': 'table'})
        for td in __global_traders[strategy_key].values():
            strategy_class = td.strategy.__class__
            for code in td.positions_history:
                codes.append(code)
                for i in range(len(td.positions_history[code])):
                    p = td.positions_history[code][i]
                    if show_mmd is not None and show_mmd != p.mmd:
                        continue
                    positions[code + '-' + str(i)] = p
        codes = list(set(codes))

    strategy_list = rd.strategy_keys()

    return render(request, 'strategy_back_show.html', {
        'strategy_list': strategy_list,
        'strategy_key': strategy_key,
        'codes': codes, 'strategy_class': strategy_class,
        'result_table_html': result_table_html, 'positions': positions
    })


def StrategyBackKline(request):
    global __global_traders
    strategy_key = request.GET.get('strategy_key')
    key: str = request.GET.get('key')
    show_type = request.GET.get('show_type')
    frequency = request.GET.get('frequency')

    keys = key.split('-')
    code = keys[0]
    i = int(keys[1])
    cl_data = None
    for td in __global_traders[strategy_key].values():
        for _code in td.positions_history:
            if code != _code:
                continue
            pos = td.positions_history[_code][i]
            if show_type == 'open':
                cl_data = pos.open_cl_data[frequency]
            else:
                cl_data = pos.close_cl_data[frequency]
            break

    chart = kcharts.render_charts(code + ':' + frequency, cl_data)
    return HttpResponse(chart)
