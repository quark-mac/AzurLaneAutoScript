import re
from collections import defaultdict
from datetime import datetime
from typing import Dict

import numpy as np
from scipy.optimize import linprog
from yaml import safe_dump, safe_load

import module.config.server as server
from module.base.decorator import cached_property
from module.config.utils import server_time_offset
from module.daemon.daemon_base import DaemonBase
from module.island.data import *
from module.island_handler.technology_scanner import IslandTechnologyScanner
from module.logger import logger


def normalize_item_name(name):
    return str(name).strip()


def normalize_item_id(item_id):
    if isinstance(item_id, (int, np.integer)):
        normalized_id = int(item_id)
        if normalized_id in DIC_ISLAND_ITEM:
            return normalized_id
        raise ValueError(f'Unknown item id: {item_id}')

    item_text = normalize_item_name(item_id)
    if not item_text:
        raise ValueError('Empty item key')

    if item_text.isdigit():
        normalized_id = int(item_text)
        if normalized_id in DIC_ISLAND_ITEM:
            return normalized_id
        raise ValueError(f'Unknown item id: {item_text}')

    match = re.match(r'^(.*)\((\d+)\)$', item_text)
    if match:
        normalized_id = int(match.group(2))
        if normalized_id in DIC_ISLAND_ITEM:
            return normalized_id
        raise ValueError(f'Unknown item id: {item_text}')

    for normalized_id, item_data in DIC_ISLAND_ITEM.items():
        if item_data['name'][server.server] == item_text:
            return normalized_id

    raise ValueError(f'Unknown item key: {item_text}')


def normalize_item_keys(items=None):
    if not items:
        return {}
    normalized = {}
    for raw_item_id, raw_value in items.items():
        item_id = normalize_item_id(raw_item_id)
        normalized[item_id] = raw_value
    return normalized


def item_name(item_id):
    return DIC_ISLAND_ITEM[item_id]['name'][server.server]


def item_export_key(item_id, use_item_name=False):
    if use_item_name:
        return f'{item_name(item_id)} ({item_id})'
    return item_id


def item_mapping_to_yaml(items, use_item_name=False):
    payload = {
        item_export_key(item_id, use_item_name=use_item_name): value
        for item_id, value in sorted(items.items())
    }
    return safe_dump(payload, allow_unicode=True, sort_keys=False)


def load_item_mapping(yaml_text=None, config_name='Items'):
    if not yaml_text:
        return {}
    items = safe_load(yaml_text)
    if not items:
        return {}
    if not isinstance(items, dict):
        raise ValueError(f'{config_name} must be a YAML mapping')
    return items


def load_preserved_items(preserved_items_yaml=None):
    return load_item_mapping(preserved_items_yaml, config_name='PreservedItems')


def normalize_item_needs(items=None, default_period=1):
    if not items:
        return {}
    requirements = defaultdict(list)
    for raw_item_id, raw_value in items.items():
        item_id = normalize_item_id(raw_item_id)
        if isinstance(raw_value, (list, tuple)) or (isinstance(raw_value, dict) and 'deadlines' in raw_value):
            requirements[item_id].extend(item_need_input_to_requirements(raw_value, default_period=default_period))
            continue
        elif isinstance(raw_value, dict):
            total_need_count = raw_value.get('count', 0)
            rate_per_day = raw_value.get('rate_per_day', 0)
            if rate_per_day:
                period = float(total_need_count) / float(rate_per_day)
            else:
                period = raw_value.get('period', raw_value.get('days', default_period))
        else:
            total_need_count = raw_value
            period = default_period
        total_need_count = int(total_need_count)
        period = float(period)
        if total_need_count <= 0 or period <= 0:
            continue
        requirements[item_id].append((total_need_count, period))
    return {
        item_id: build_item_need_data(item_requirements)
        for item_id, item_requirements in requirements.items()
    }


def normalize_preserved_items(preserved_items=None):
    return normalize_item_needs(preserved_items, default_period=1)


def merge_item_needs(*item_needs):
    requirements = defaultdict(list)
    for needs in item_needs:
        for item_id, data in needs.items():
            requirements[item_id].extend(item_need_data_to_requirements(data))
    return {
        item_id: build_item_need_data(item_requirements)
        for item_id, item_requirements in requirements.items()
    }


def build_item_need_data(requirements):
    period_counts = defaultdict(int)
    for count, period in requirements:
        count = int(count)
        period = float(period)
        if count <= 0 or period <= 0:
            continue
        period_counts[period] += count

    deadlines = []
    total_need_count = 0
    rate_per_day = 0.0
    for period, count in sorted(period_counts.items()):
        total_need_count += count
        rate_per_day = max(rate_per_day, total_need_count / period)
        deadlines.append({
            'count': total_need_count,
            'period': period,
        })

    if not deadlines:
        return {
            'total_need_count': 0,
            'period': 1,
            'rate_per_day': 0.0,
        }

    return {
        'total_need_count': total_need_count,
        'period': deadlines[-1]['period'],
        'rate_per_day': rate_per_day,
        'deadlines': deadlines,
    }


def item_need_data_to_requirements(data):
    deadlines = data.get('deadlines')
    if not deadlines:
        return [(data['total_need_count'], data['period'])]

    requirements = []
    previous_count = 0
    for deadline in sorted(deadlines, key=lambda x: x['period']):
        count = int(deadline.get('count', deadline.get('total_need_count', 0)))
        period = float(deadline.get('period', deadline.get('days', data['period'])))
        marginal_count = count - previous_count
        if marginal_count > 0:
            requirements.append((marginal_count, period))
        previous_count = max(previous_count, count)
    return requirements


def item_need_input_to_requirements(data, default_period=1):
    if isinstance(data, dict):
        entries = data.get('deadlines', [])
    else:
        entries = data
    requirements = []
    for deadline in entries:
        if isinstance(deadline, dict):
            count = deadline.get('count', deadline.get('total_need_count', 0))
            period = deadline.get('period', deadline.get('days', default_period))
        else:
            count = deadline
            period = default_period
        count = int(count)
        period = float(period)
        if count > 0 and period > 0:
            requirements.append((count, period))
    return requirements


def parse_item_need_deadlines(item_need, default_period=1):
    if not item_need:
        return []
    if isinstance(item_need, dict) and item_need.get('deadlines') and (
        'total_need_count' in item_need or 'rate_per_day' in item_need
    ):
        return [
            (
                int(deadline.get('count', deadline.get('total_need_count', 0))),
                float(deadline.get('period', deadline.get('days', item_need['period']))),
            )
            for deadline in sorted(item_need['deadlines'], key=lambda x: x['period'])
            if int(deadline.get('count', deadline.get('total_need_count', 0))) > 0
        ]

    if isinstance(item_need, (list, tuple)) or (isinstance(item_need, dict) and 'deadlines' in item_need):
        data = build_item_need_data(item_need_input_to_requirements(item_need, default_period=default_period))
        return [
            (deadline['count'], deadline['period'])
            for deadline in data.get('deadlines', [])
        ]

    if isinstance(item_need, dict):
        total_need_count = item_need.get('count', item_need.get('total_need_count', 0))
        period = item_need.get('period', item_need.get('days', default_period))
        rate_per_day = item_need.get('rate_per_day', 0)
        if rate_per_day:
            period = float(total_need_count) / float(rate_per_day)
    else:
        total_need_count = item_need
        period = default_period
    total_need_count = int(total_need_count)
    period = float(period)
    if total_need_count <= 0 or period <= 0:
        return []
    return [(total_need_count, period)]


def merge_task_target_preserved_items(preserved_items, task_target_items):
    return merge_item_needs(
        normalize_item_needs(preserved_items),
        normalize_item_needs(task_target_items, default_period=10),
    )


def get_preserved_level_load_rate(stock, min_stock, preserved_deadlines):
    effective_stock = max(stock - min_stock, 0)
    rate_per_day = 0
    target_stock = 0
    for preserved_stock, preserved_period in preserved_deadlines:
        deadline_rate = preserved_stock / preserved_period
        if deadline_rate > rate_per_day + 1e-9:
            rate_per_day = deadline_rate
            target_stock = preserved_stock
        elif abs(deadline_rate - rate_per_day) <= 1e-9:
            target_stock = max(target_stock, preserved_stock)
    if effective_stock >= target_stock:
        return 0
    return rate_per_day


def is_integer_value(value):
    if isinstance(value, (int, np.integer)):
        return True
    if isinstance(value, (float, np.floating)):
        return float(value).is_integer()
    return False


def ceil_div_or_ceil(numerator, denominator):
    if is_integer_value(numerator) and is_integer_value(denominator):
        numerator = int(numerator)
        denominator = int(denominator)
        return (numerator + denominator - 1) // denominator
    return ceil_with_epsilon(numerator / denominator)


def ceil_with_epsilon(amount, epsilon=1e-9):
    from math import ceil
    return int(ceil(float(amount) - epsilon))


def format_item_need_data(data, format_amount):
    deadlines = data.get('deadlines')
    if not deadlines:
        return f'{format_amount(data["total_need_count"])} in {format_amount(data["period"])} day(s)'
    return ', '.join(
        f'{format_amount(deadline["count"])} in {format_amount(deadline["period"])} day(s)'
        for deadline in deadlines
    )


def item_need_data_to_yaml_entry(data, round_up_int):
    deadlines = data.get('deadlines')
    if deadlines and len(deadlines) > 1:
        previous_count = 0
        entries = []
        for deadline in deadlines:
            count = round_up_int(deadline['count'])
            period = round_up_int(deadline['period'])
            entries.append({
                'count': count - previous_count,
                'period': period,
            })
            previous_count = count
        return entries
    return {
        'count': round_up_int(data['total_need_count']),
        'period': round_up_int(data['period']),
    }


def get_sub_dict(raw_dict: Dict[int, bool], keys: list) -> Dict[int, bool]:
    return {key: raw_dict.get(key, False) for key in keys}

def count_level(substatus: Dict[int, bool]):
    return sum(1 for status in substatus.values() if status)


class IslandProductionPlanner(DaemonBase):
    NET_ACCUMULATING_EPSILON = 1e-3
    EXCHANGE_REQUIRES_MANUAL_OPERATION = True
    SLOT_TO_GROUP = {
        9001: 'field', 9002: 'field', 9003: 'field', 9004: 'field',
        9011: 'mine', 9012: 'mine', 9013: 'mine', 9014: 'mine',
        9021: 'wood', 9022: 'wood', 9023: 'wood', 9024: 'wood',
        9031: 'ranch_chicken', 9032: 'ranch_pig', 9033: 'ranch_cow', 9034: 'ranch_sheep',
        9041: 'cafe', 9042: 'cafe',
        9061: 'koi', 9062: 'koi',
        9071: 'bear', 9072: 'bear',
        9081: 'eatery', 9082: 'eatery',
        9091: 'grill', 9092: 'grill',
        9101: 'orchard', 9102: 'orchard', 9103: 'orchard', 9104: 'orchard',
        9111: 'nursery', 9112: 'nursery',
        9201: 'manufacturing_lumber', 9202: 'manufacturing_lumber',
        9203: 'manufacturing_machinery', 9204: 'manufacturing_machinery',
        9205: 'manufacturing_electronic', 9206: 'manufacturing_electronic',
        9207: 'manufacturing_crafts', 9208: 'manufacturing_crafts',
        9211: 'fishery', 9212: 'fishery', 9213: 'fishery',
    }
    GROUP_TO_PLACE = {
        'field': 101,
        'ranch_chicken': 102,
        'ranch_pig': 102,
        'ranch_cow': 102,
        'ranch_sheep': 102,
        'fishery': 201,
        'mine': 401,
        'wood': 402,
        'orchard': 501,
        'nursery': 502,
        'koi': 601,
        'bear': 602,
        'eatery': 603,
        'grill': 604,
        'manufacturing_lumber': 703,
        'manufacturing_machinery': 704,
        'manufacturing_electronic': 705,
        'manufacturing_crafts': 706,
        'cafe': 901,
    }
    GROUP_TO_SLOTS = {
        'field': [9001, 9002, 9003, 9004],
        'mine': [9011, 9012, 9013, 9014],
        'wood': [9021, 9022, 9023, 9024],
        'ranch_chicken': [9031],
        'ranch_pig': [9032],
        'ranch_cow': [9033],
        'ranch_sheep': [9034],
        'cafe': [9041, 9042],
        'koi': [9061, 9062],
        'bear': [9071, 9072],
        'eatery': [9081, 9082],
        'grill': [9091, 9092],
        'orchard': [9101, 9102, 9103, 9104],
        'nursery': [9111, 9112],
        'manufacturing_lumber': [9201, 9202],
        'manufacturing_machinery': [9203, 9204],
        'manufacturing_electronic': [9205, 9206],
        'manufacturing_crafts': [9207, 9208],
        'fishery': [9211, 9212, 9213],
    }
    RESTAURANT_MENU_CONFIG = {
        601: "IslandBusiness.IslandRestaurant.KoiMenu",
        602: "IslandBusiness.IslandRestaurant.BearMenu",
        603: "IslandBusiness.IslandRestaurant.EateryMenu",
        604: "IslandBusiness.IslandRestaurant.GrillMenu",
        901: "IslandBusiness.IslandRestaurant.CafeMenu",
    }
    RECIPE_PRODUCT_IDS = {
        next(iter(recipe['commission_product']))
        for recipe in DIC_ISLAND_RECIPE.values()
        if recipe['commission_product']
    }
    EXCHANGE_PRODUCT_IDS = {
        item_id
        for recipe in DIC_ISLAND_EXCHANGE_RECIPE.values()
        for item_id in recipe['items']
    }
    DISH_ITEM_TO_SLOT = {
        item_id: slot
        for slot, menu in DIC_ISLAND_RESTAURANT_MENU_TO_RECIPE.items()
        for item_id in menu
    }

    @cached_property
    def current_activity_list(self):
        time = datetime.now() + server_time_offset()
        for season, content in DIC_ISLAND_SEASON.items():
            start_time = datetime.strptime(content['start_time'][server.server], "%Y-%m-%d %H:%M:%S")
            end_time = datetime.strptime(content['end_time'][server.server], "%Y-%m-%d %H:%M:%S")
            if start_time <= time < end_time:
                return content['activity']

    def analyze_technology_status(self, technology_status: Dict[int, bool]):
        self.recipe_available = {}
        self.wild_gather_available = {}
        for activity_id in self.current_activity_list:
            if DIC_ISLAND_ACTIVITY[activity_id]['type'] == 5003:
                for gather_id in DIC_ISLAND_ACTIVITY[activity_id]['config_data']:
                    self.wild_gather_available[gather_id] = True
            if DIC_ISLAND_ACTIVITY[activity_id]['type'] == 5004:
                for recipe_id in DIC_ISLAND_ACTIVITY[activity_id]['config_data']:
                    self.recipe_available[recipe_id] = True

        self.slot_available = {
            # Fields
            9001: technology_status.get(310101, False),
            9002: technology_status.get(310102, False),
            9003: technology_status.get(310103, False),
            9004: technology_status.get(310104, False),
            # Mine
            9011: technology_status.get(220101, False),
            9012: technology_status.get(220102, False),
            9013: technology_status.get(220103, False),
            9014: technology_status.get(220104, False),
            # Woods
            9021: technology_status.get(210101, False),
            9022: technology_status.get(210102, False),
            9023: technology_status.get(210103, False),
            9024: technology_status.get(210104, False),
            # Ranch
            9031: True,
            9032: technology_status.get(420301, False),
            9033: technology_status.get(430301, False),
            9034: technology_status.get(440301, False),
            # Cafe
            9041: True,
            9042: technology_status.get(620101, False),
            # Koi
            9061: True,
            9062: technology_status.get(510101, False),
            # Bear
            9071: technology_status.get(520001, False),
            9072: technology_status.get(520101, False),
            # Eatery
            9081: technology_status.get(530001, False),
            9082: technology_status.get(530101, False),
            # Grill
            9091: technology_status.get(540001, False),
            9092: technology_status.get(540101, False),
            # Orchard
            9101: technology_status.get(330101, False),
            9102: technology_status.get(330102, False),
            9103: technology_status.get(330103, False),
            9104: technology_status.get(330104, False),
            # Nursery
            9111: technology_status.get(320101, False),
            9112: technology_status.get(320102, False),
            # Lumber
            9201: True,
            9202: technology_status.get(630101, False),
            # Machinery
            9203: technology_status.get(640001, False),
            9204: technology_status.get(640101, False),
            # Electronic
            9205: technology_status.get(650001, False),
            9206: technology_status.get(650101, False),
            # Crafts
            9207: technology_status.get(660001, False),
            9208: technology_status.get(660101, False),
            # Fish
            9211: True,
            9212: technology_status.get(460101, False),
            9213: technology_status.get(460102, False)
        }
        self.recipe_group = {}
        self.available_slot_recipes = set()
        for slot, slot_data in DIC_ISLAND_SLOT.items():
            if not self.slot_available.get(slot, False):
                continue
            group = self.SLOT_TO_GROUP.get(slot)
            if group is None:
                continue
            for recipe_id in slot_data.get('formula', []):
                self.available_slot_recipes.add(recipe_id)
                self.recipe_group.setdefault(recipe_id, group)
            for recipe_id in slot_data.get('activity_formula', []):
                self.available_slot_recipes.add(recipe_id)
                self.recipe_group.setdefault(recipe_id, group)
        self.recipe_available.update({
            # Farm
            101002: technology_status.get(500212, False),  # 玉米 <- 玉米种植技术
            101003: technology_status.get(310201, False),  # 牧草 <- 牧草种植技术
            101004: technology_status.get(500211, False),  # 咖啡豆 <- 咖啡树种植技术
            101005: technology_status.get(310202, False),  # 大米 <- 旱稻种植技术
            101006: technology_status.get(500215, False),  # 白菜 <- 白菜种植技术
            101007: technology_status.get(500214, False),  # 土豆 <- 土豆种植技术
            101008: technology_status.get(500213, False),  # 大豆 <- 大豆种植技术
            # Mining
            401004: technology_status.get(220201, False),  # 铝矿 <- 铝矿勘探技术
            401005: technology_status.get(220202, False),  # 铁矿 <- 铁矿勘探技术
            401006: technology_status.get(220203, False),  # 硫矿 <- 硫矿勘探技术
            401007: technology_status.get(220204, False),  # 银矿 <- 银矿勘探技术
            # Woods
            402002: technology_status.get(210201, False),  # 实用之木 <- 实用之木生产技术
            402003: technology_status.get(210202, False),  # 精选之木 <- 精选之木生产技术
            402004: technology_status.get(210203, False),  # 典雅之木 <- 典雅之木生产技术
            # Orchard
            501001: technology_status.get(500231, False),  # 苹果 <- 苹果树种植技术
            501002: technology_status.get(500232, False),  # 柑橘 <- 柑橘树种植技术
            501003: technology_status.get(500233, False),  # 香蕉 <- 香蕉树种植技术
            501004: technology_status.get(500234, False),  # 芒果 <- 芒果树种植技术
            501005: technology_status.get(500235, False),  # 柠檬 <- 柠檬树种植技术
            501006: technology_status.get(500236, False),  # 牛油果 <- 牛油果树种植技术
            501007: technology_status.get(330201, False),  # 橡胶 <- 橡胶树种植技术
            # Nursery
            502002: technology_status.get(320201, False),  # 草莓 <- 草莓种植技术
            502003: technology_status.get(320202, False),  # 棉花 <- 棉花种植技术
            502004: technology_status.get(320203, False),  # 茶叶 <- 茶树种植技术
            502005: technology_status.get(320205, False),  # 薰衣草 <- 薰衣草种植技术
            502006: technology_status.get(320204, False),  # 胡萝卜 <- 胡萝卜种植技术
            502007: technology_status.get(320206, False),  # 洋葱 <- 洋葱种植技术
            # Food
            601002: technology_status.get(510201, False),  # 肉末烧豆腐
            601003: technology_status.get(510202, False),  # 蛋包饭
            601004: technology_status.get(510203, False),  # 白菜豆腐汤
            601005: technology_status.get(510204, False),  # 蔬菜沙拉
            601006: technology_status.get(460201, False),  # 炸鱼薯条
            601007: technology_status.get(460202, False),  # 洋葱蒸鱼
            601008: technology_status.get(460206, False),  # 佛跳墙
            602002: technology_status.get(520201, False),  # 香蕉芒果汁
            602003: technology_status.get(520202, False),  # 蜂蜜柠檬水
            602004: technology_status.get(520205, False),  # 草莓蜜沁
            602005: technology_status.get(520204, False),  # 薰衣草茶
            602006: technology_status.get(520203, False),  # 草莓蜂蜜冰沙
            603002: technology_status.get(530205, False),  # 苹果派
            603003: technology_status.get(530206, False),  # 香橙派
            603004: technology_status.get(530202, False),  # 芒果糯米饭
            603005: technology_status.get(530203, False),  # 香蕉可丽饼
            603006: technology_status.get(530204, False),  # 草莓夏洛特
            603007: technology_status.get(460205, False),  # 海鲜饭
            604002: technology_status.get(540201, False),  # 禽肉土豆拼盘
            604004: technology_status.get(540202, False),  # 爆炒禽肉
            604005: technology_status.get(540204, False),  # 胡萝卜厚蛋烧
            604006: technology_status.get(540205, False),  # 汉堡肉饭
            604007: technology_status.get(460203, False),  # 柠檬虾
            604008: technology_status.get(460204, False),  # 爆炒小龙虾
            901003: technology_status.get(550201, False),  # 芝士
            901004: technology_status.get(550202, False),  # 拿铁
            901005: technology_status.get(550203, False),  # 柑橘咖啡
            901006: technology_status.get(550204, False),  # 草莓奶绿
            # Food combination (all uses 500001)
            601101: technology_status.get(500001, False),
            601102: technology_status.get(500001, False),
            602101: technology_status.get(500001, False),
            602102: technology_status.get(500001, False),
            602103: technology_status.get(500001, False),
            603101: technology_status.get(500001, False),
            603102: technology_status.get(500001, False),
            603103: technology_status.get(500001, False),
            604101: technology_status.get(500001, False),
            604102: technology_status.get(500001, False),
            901101: technology_status.get(500001, False),
            901102: technology_status.get(500001, False),
            901103: technology_status.get(500001, False),
            # Manufacturing
            701002: technology_status.get(660201, False),  # 皮革
            701003: technology_status.get(660202, False),  # 绳索
            701004: technology_status.get(660203, False),  # 手套
            701005: technology_status.get(660204, False),  # 香囊
            701006: technology_status.get(660205, False),  # 鞋靴
            701007: technology_status.get(660206, False),  # 绷带
            701009: technology_status.get(640202, False),  # 电缆
            701010: technology_status.get(640201, False),  # 铁钉
            701011: technology_status.get(640203, False),  # 硫酸
            701012: technology_status.get(640204, False),  # 火药
            701013: technology_status.get(640205, False),  # 刀叉餐具
            701015: technology_status.get(630201, False),  # 记事本
            701016: technology_status.get(630202, False),  # 桌椅
            701017: technology_status.get(630203, False),  # 精选木桶
            701018: technology_status.get(630204, False),  # 文件柜
            701020: technology_status.get(650201, False),  # 钟表
            701021: technology_status.get(650202, False),  # 蓄电池
            701022: technology_status.get(650203, False),  # 净水滤芯
            701023: technology_status.get(630205, False),  # 装饰画
        })
        for recipe_id in DIC_ISLAND_RECIPE:
            if recipe_id < 9900000:
                self.recipe_available.setdefault(recipe_id, True)
            else:
                self.recipe_available.setdefault(recipe_id, False)
        for recipe_id in self.available_slot_recipes:
            if recipe_id >= 9900000:
                self.recipe_available[recipe_id] = True

        self.mining_additional = technology_status.get(220401, False)
        self.wood_additional = technology_status.get(210401, False)
        self.ranch_additional = technology_status.get(400001, False)
        self.ranch_level = {
            9031: count_level(get_sub_dict(technology_status, [410301, 410302, 410303, 410304, 410305])),
            9032: count_level(get_sub_dict(technology_status, [420302, 420303, 420304])),
            9033: count_level(get_sub_dict(technology_status, [430302, 430303, 430304])),
            9034: count_level(get_sub_dict(technology_status, [440302, 440303, 440304]))
        }
        self.wild_gather_available.update({
            5: technology_status.get(450301, False),
            6: technology_status.get(450302, False),
        })
        for id, item in DIC_ISLAND_WILD_GATHER.items():
            if id < 10:
                self.wild_gather_available.setdefault(id, True)
            else:
                self.wild_gather_available.setdefault(id, False)

        self.place_efficiency_bonus = {
            101: self.config.cross_get("IslandProductionPlanner.IslandProductionPlanner.FieldsEfficiency"),
            401: 0.05 if technology_status.get(220601, False) else 0,
            402: 0.05 if technology_status.get(210601, False) else 0,
            501: self.config.cross_get("IslandProductionPlanner.IslandProductionPlanner.OrchardEfficiency"),
            502: self.config.cross_get("IslandProductionPlanner.IslandProductionPlanner.NurseryEfficiency"),
        }

    @staticmethod
    def get_initial_capacity_from_grade(grade):
        if grade == 'bronze':
            return 5
        elif grade in ['silver', 'gold', 'diamond']:
            return 6
        else:
            raise ValueError(f"Invalid grade: {grade}")

    def has_waitress(self, config_key, waitress_name):
        value = self.config.cross_get(config_key)
        if not isinstance(value, str):
            return False
        return waitress_name in value.split('+')

    @cached_property
    def restaurant_capacity(self):
        capacity = {
            601: self.get_initial_capacity_from_grade(self.config.cross_get("IslandBusiness.IslandRestaurant.KoiGrade")),
            602: self.get_initial_capacity_from_grade(self.config.cross_get("IslandBusiness.IslandRestaurant.BearGrade")),
            603: self.get_initial_capacity_from_grade(self.config.cross_get("IslandBusiness.IslandRestaurant.EateryGrade")),
            604: self.get_initial_capacity_from_grade(self.config.cross_get("IslandBusiness.IslandRestaurant.GrillGrade")),
            901: self.get_initial_capacity_from_grade(self.config.cross_get("IslandBusiness.IslandRestaurant.CafeGrade")),
        }
        if self.has_waitress("IslandBusiness.IslandRestaurant.KoiWaitress", 'Chao_Ho'):
            capacity[601] += 1
        if self.has_waitress("IslandBusiness.IslandRestaurant.BearWaitress", 'Cheshire'):
            capacity[602] += 1
        if self.has_waitress("IslandBusiness.IslandRestaurant.EateryWaitress", 'Helena'):
            capacity[603] += 1
        if self.has_waitress("IslandBusiness.IslandRestaurant.GrillWaitress", 'August_von_Parseval'):
            capacity[604] += 1
        if self.has_waitress("IslandBusiness.IslandRestaurant.CafeWaitress", 'Cheshire'):
            capacity[901] += 1
        return capacity

    @staticmethod
    def get_quantity_from_grade(grade):
        if grade in ['bronze', 'silver']:
            return 2
        elif grade == 'gold':
            return 3
        elif grade == 'diamond':
            return 4
        else:
            raise ValueError(f"Invalid grade: {grade}")

    @cached_property
    def restaurant_quantity(self):
        quantity = {
            601: self.get_quantity_from_grade(self.config.cross_get("IslandBusiness.IslandRestaurant.KoiGrade")),
            602: self.get_quantity_from_grade(self.config.cross_get("IslandBusiness.IslandRestaurant.BearGrade")),
            603: self.get_quantity_from_grade(self.config.cross_get("IslandBusiness.IslandRestaurant.EateryGrade")),
            604: self.get_quantity_from_grade(self.config.cross_get("IslandBusiness.IslandRestaurant.GrillGrade")),
            901: self.get_quantity_from_grade(self.config.cross_get("IslandBusiness.IslandRestaurant.CafeGrade")),
        }
        return quantity

    @cached_property
    def restaurant_sales_bonus(self):
        bonus = {key: 0 for key in [601, 602, 603, 604, 901]}
        if self.has_waitress("IslandBusiness.IslandRestaurant.KoiWaitress", 'Chao_Ho'):
            bonus[601] += 0.1
        if self.has_waitress("IslandBusiness.IslandRestaurant.BearWaitress", 'Cheshire'):
            bonus[602] += 0.05
        if self.has_waitress("IslandBusiness.IslandRestaurant.EateryWaitress", 'Helena'):
            bonus[603] += 0.1
        if self.has_waitress("IslandBusiness.IslandRestaurant.EateryWaitress", 'Prinz_Eugen'):
            bonus[603] += 0.1
        if self.has_waitress("IslandBusiness.IslandRestaurant.GrillWaitress", 'Prinz_Eugen'):
            bonus[604] += 0.1
        if self.has_waitress("IslandBusiness.IslandRestaurant.GrillWaitress", 'August_von_Parseval'):
            bonus[604] += 0.1
        if self.has_waitress("IslandBusiness.IslandRestaurant.CafeWaitress", 'Cheshire'):
            bonus[901] += 0.05
        return bonus

    def _reset_lp_result(self):
        self.lp_status = None
        self.lp_success = False
        self.lp_message = ''
        self._clear_solution_state()

    def _clear_solution_state(self):
        self.production_plan = {}
        self.shop_plan = {}
        self.exchange_plan = {}
        self.sell_plan = {}
        self.net_items = {}
        self.net_accumulating_items = {}
        self.product_min_stock_items = {}
        self.accumulating_rate_per_day = {}
        self.inventory_levels_yaml_text = ''
        self.accumulating_rate_yaml_text = ''
        self.preserved_items_yaml_text = ''
        self.group_usage_summary = {}
        self.total_pt = 0
        self.daily_profit = 0
        self.daily_coin_cost = 0
        self.daily_coin_revenue = 0
        self.wild_gather_plan = {}
        self.mining_supply_plan = {}
        self.logging_supply_plan = {}
        self.demand_items = {}
        self.preserved_items = {}
        self.task_target_items = {}

    @staticmethod
    def _format_amount(amount):
        rounded = round(amount)
        if abs(amount - rounded) <= 1e-6:
            return str(int(rounded))
        return f'{amount:.3f}'.rstrip('0').rstrip('.')

    @staticmethod
    def _round_output_amount(amount):
        return float(round(float(amount) + 1e-10, 3))

    @staticmethod
    def _round_up_int(amount):
        return ceil_with_epsilon(amount)

    def _get_natural_accumulating_amount(self, item_id, amount):
        if DIC_ISLAND_ITEM[item_id].get('pt_num', 0) <= 0:
            return 0
        reserved_rate = self.demand_items.get(item_id, {}).get('rate_per_day', 0)
        accumulating_amount = amount - reserved_rate
        if accumulating_amount <= self.NET_ACCUMULATING_EPSILON:
            return 0
        return accumulating_amount

    def _redirect_exchange_accumulating_items(self):
        if not self.EXCHANGE_REQUIRES_MANUAL_OPERATION or not self.exchange_plan:
            return

        exchange_inputs = defaultdict(float)
        exchange_outputs = defaultdict(float)
        for exchange_id, amount in self.exchange_plan.items():
            recipe = DIC_ISLAND_EXCHANGE_RECIPE[exchange_id]
            for item_id, input_amount in recipe['resource_consume'].items():
                exchange_inputs[item_id] += input_amount * amount
            for item_id, output_amount in recipe['items'].items():
                exchange_outputs[item_id] += output_amount * amount

        for item_id, amount in exchange_outputs.items():
            current = self.net_accumulating_items.get(item_id, 0)
            if current <= self.NET_ACCUMULATING_EPSILON:
                continue
            remaining = current - min(current, amount)
            if remaining > self.NET_ACCUMULATING_EPSILON:
                self.net_accumulating_items[item_id] = remaining
            else:
                self.net_accumulating_items.pop(item_id, None)

        for item_id, amount in exchange_inputs.items():
            if amount <= self.NET_ACCUMULATING_EPSILON:
                continue
            self.net_accumulating_items[item_id] = self.net_accumulating_items.get(item_id, 0) + amount

    def _item_name(self, item_id):
        return item_name(item_id)

    def _recipe_name(self, recipe_id):
        return DIC_ISLAND_RECIPE[recipe_id]['name'][server.server]

    def _shop_name(self, shop_id):
        return DIC_ISLAND_SHOP_RECIPE[shop_id]['name'][server.server]

    def _exchange_name(self, exchange_id):
        recipe = DIC_ISLAND_EXCHANGE_RECIPE[exchange_id]
        output_id = next(iter(recipe['items']))
        return self._item_name(output_id)

    def _slot_group_name(self, group):
        place_id = self.GROUP_TO_PLACE.get(group)
        if place_id is None:
            return group
        name = DIC_ISLAND_PRODUCTION_PLACE[place_id]['name'][server.server]
        slots = self.GROUP_TO_SLOTS.get(group, [])
        if slots:
            slot_text = ','.join(str(slot) for slot in slots)
            return f'{name} ({slot_text})'
        return name

    def _slot_group_sort_key(self, key):
        if isinstance(key, int):
            return key
        slots = self.GROUP_TO_SLOTS.get(key, [])
        if slots:
            return min(slots)
        return 999999

    def _build_production_problem(self, demand_items=None):
        if demand_items is None:
            demand_items = {}
        daily_workload = 24 * 60 * 60 * 10

        group_slots = defaultdict(list)
        for slot, available in self.slot_available.items():
            group = self.SLOT_TO_GROUP.get(slot)
            if available and group is not None:
                group_slots[group].append(slot)
        group_capacity = {
            group: len(slots) * daily_workload if not group.startswith('ranch_') else daily_workload
            for group, slots in group_slots.items()
        }
        group_efficiency = {
            'field': 1 + self.place_efficiency_bonus.get(101, 0),
            'mine': 1 + self.place_efficiency_bonus.get(401, 0),
            'wood': 1 + self.place_efficiency_bonus.get(402, 0),
            'orchard': 1 + self.place_efficiency_bonus.get(501, 0),
            'nursery': 1 + self.place_efficiency_bonus.get(502, 0),
            'ranch_chicken': 1,
            'ranch_pig': 1,
            'ranch_cow': 1,
            'ranch_sheep': 1,
            'cafe': 1,
            'koi': 1,
            'bear': 1,
            'eatery': 1,
            'grill': 1,
            'manufacturing_lumber': 1,
            'manufacturing_machinery': 1,
            'manufacturing_electronic': 1,
            'manufacturing_crafts': 1,
            'fishery': 1,
        }

        recipe_group = getattr(self, 'recipe_group', {})
        activities = []

        for recipe_id, recipe in DIC_ISLAND_RECIPE.items():
            if not self.recipe_available.get(recipe_id, False):
                continue
            group = recipe_group.get(recipe_id)
            if group is None or group not in group_capacity:
                continue
            inputs = dict(recipe['commission_cost'])
            outputs = dict(recipe['commission_product'])
            if group.startswith('ranch_'):
                multiplier = 1 + {
                    'ranch_chicken': self.ranch_level[9031],
                    'ranch_pig': self.ranch_level[9032],
                    'ranch_cow': self.ranch_level[9033],
                    'ranch_sheep': self.ranch_level[9034],
                }[group]
                inputs = {item_id: amount * multiplier for item_id, amount in inputs.items()}
                outputs = {item_id: amount * multiplier for item_id, amount in outputs.items()}
                if self.ranch_additional:
                    for item_id, amount in recipe['second_product_display'].items():
                        outputs[item_id] = outputs.get(item_id, 0) + amount * multiplier
            activities.append({
                'kind': 'recipe',
                'id': recipe_id,
                'group': group,
                'workload': recipe['workload'] / group_efficiency[group],
                'inputs': inputs,
                'outputs': outputs,
            })

        for shop_id, recipe in DIC_ISLAND_SHOP_RECIPE.items():
            activities.append({
                'kind': 'shop',
                'id': shop_id,
                'group': None,
                'workload': 0,
                'inputs': dict(recipe['resource_consume']),
                'outputs': dict(recipe['items']),
            })
        for exchange_id, recipe in DIC_ISLAND_EXCHANGE_RECIPE.items():
            activities.append({
                'kind': 'exchange',
                'id': exchange_id,
                'group': None,
                'workload': 0,
                'inputs': dict(recipe['resource_consume']),
                'outputs': dict(recipe['items']),
            })

        initial_supply = defaultdict(float)
        wild_gather_plan = {}
        for gather_id, gather in DIC_ISLAND_WILD_GATHER.items():
            if self.wild_gather_available.get(gather_id, False):
                wild_gather_plan[gather_id] = dict(gather['product'])
                for item_id, amount in gather['product'].items():
                    initial_supply[item_id] += amount
        mining_multiplier = 2 if self.mining_additional else 1
        mining_supply_plan = defaultdict(float)
        for product in DIC_ISLAND_PRODUCTION_MINING.values():
            for item_id, amount in product.items():
                mining_supply_plan[item_id] += amount * mining_multiplier
                initial_supply[item_id] += amount * mining_multiplier
        wood_multiplier = 2 if self.wood_additional else 1
        logging_supply_plan = defaultdict(float)
        for product in DIC_ISLAND_PRODUCTION_LOGGING.values():
            for item_id, amount in product.items():
                logging_supply_plan[item_id] += amount * wood_multiplier
                initial_supply[item_id] += amount * wood_multiplier

        sell_slots = {
            601: DIC_ISLAND_RESTAURANT_MENU_TO_RECIPE[601],
            602: DIC_ISLAND_RESTAURANT_MENU_TO_RECIPE[602],
            603: DIC_ISLAND_RESTAURANT_MENU_TO_RECIPE[603],
            604: DIC_ISLAND_RESTAURANT_MENU_TO_RECIPE[604],
            901: DIC_ISLAND_RESTAURANT_MENU_TO_RECIPE[901],
        }
        sale_entries = []
        for slot, menu in sell_slots.items():
            for item_id in menu:
                sale_entries.append((slot, item_id))

        item_ids = {1}
        for activity in activities:
            item_ids.update(activity['inputs'])
            item_ids.update(activity['outputs'])
        item_ids.update(initial_supply)
        item_ids.update(demand_items)
        item_ids.update(item_id for _, item_id in sale_entries)
        item_ids = sorted(item_ids)

        activity_count = len(activities)
        sale_count = len(sale_entries)
        item_count = len(item_ids)
        total_vars = activity_count + sale_count + item_count
        item_index = {item_id: idx for idx, item_id in enumerate(item_ids)}
        end_offset = activity_count + sale_count

        c = np.zeros(total_vars)
        for item_id, idx in item_index.items():
            c[end_offset + idx] = -DIC_ISLAND_ITEM.get(item_id, {}).get('pt_num', 0)

        a_eq = np.zeros((item_count, total_vars))
        b_eq = np.zeros(item_count)
        for col, activity in enumerate(activities):
            for item_id, amount in activity['outputs'].items():
                a_eq[item_index[item_id], col] += amount
            for item_id, amount in activity['inputs'].items():
                a_eq[item_index[item_id], col] -= amount
        for sale_col, (slot, item_id) in enumerate(sale_entries, start=activity_count):
            a_eq[item_index[item_id], sale_col] -= 1
            revenue = DIC_ISLAND_ITEM[item_id]['order_price'] * (1 + self.restaurant_sales_bonus[slot])
            a_eq[item_index[1], sale_col] += revenue
        for item_id, idx in item_index.items():
            a_eq[idx, end_offset + idx] -= 1
            b_eq[idx] = -initial_supply.get(item_id, 0)

        a_ub = []
        b_ub = []
        for group, capacity in group_capacity.items():
            row = np.zeros(total_vars)
            for col, activity in enumerate(activities):
                if activity['group'] == group and activity['workload'] > 0:
                    row[col] = activity['workload']
            if row.any():
                a_ub.append(row)
                b_ub.append(capacity)

        for slot, menu in sell_slots.items():
            slot_sales = [idx for idx, entry in enumerate(sale_entries) if entry[0] == slot]
            if slot_sales:
                row = np.zeros(total_vars)
                for idx in slot_sales:
                    row[activity_count + idx] = 1
                a_ub.append(row)
                b_ub.append(self.restaurant_quantity[slot] * self.restaurant_capacity[slot])
                for idx in slot_sales:
                    cap_row = np.zeros(total_vars)
                    cap_row[activity_count + idx] = 1
                    a_ub.append(cap_row)
                    b_ub.append(self.restaurant_capacity[slot])

        profit_row = np.zeros(total_vars)
        profit_row[end_offset + item_index[1]] = -1
        a_ub.append(profit_row)
        b_ub.append(-self.daily_profit_lower_limit)

        for item_id, demand_data in demand_items.items():
            demand_row = np.zeros(total_vars)
            demand_row[end_offset + item_index[item_id]] = -1
            a_ub.append(demand_row)
            b_ub.append(-demand_data['rate_per_day'])

        return {
            'daily_workload': daily_workload,
            'group_slots': group_slots,
            'activities': activities,
            'sale_entries': sale_entries,
            'item_index': item_index,
            'end_offset': end_offset,
            'wild_gather_plan': wild_gather_plan,
            'mining_supply_plan': dict(mining_supply_plan),
            'logging_supply_plan': dict(logging_supply_plan),
            'demand_items': demand_items,
            'preserved_items': getattr(self, 'preserved_items', {}),
            'task_target_items': getattr(self, 'task_target_items', {}),
            'c': c,
            'A_ub': np.array(a_ub) if a_ub else None,
            'b_ub': np.array(b_ub) if b_ub else None,
            'A_eq': a_eq,
            'b_eq': b_eq,
            'bounds': [(0, None)] * total_vars,
        }

    def _apply_production_lp_result(self, result, problem):
        self.lp_status = result.status
        self.lp_success = result.success
        self.lp_message = result.message
        self._clear_solution_state()
        self.wild_gather_plan = problem['wild_gather_plan']
        self.mining_supply_plan = problem['mining_supply_plan']
        self.logging_supply_plan = problem['logging_supply_plan']
        self.demand_items = problem['demand_items']
        self.preserved_items = problem['preserved_items']
        self.task_target_items = problem['task_target_items']
        if not result.success:
            return

        activities = problem['activities']
        sale_entries = problem['sale_entries']
        item_index = problem['item_index']
        end_offset = problem['end_offset']
        group_slots = problem['group_slots']
        daily_workload = problem['daily_workload']
        activity_count = len(activities)
        solution = result.x

        for col, activity in enumerate(activities):
            amount = solution[col]
            if amount <= 1e-6:
                continue
            target = {
                'recipe': self.production_plan,
                'shop': self.shop_plan,
                'exchange': self.exchange_plan,
            }[activity['kind']]
            target[activity['id']] = amount

        for idx, (slot, item_id) in enumerate(sale_entries, start=activity_count):
            amount = solution[idx]
            if amount > 1e-6:
                self.sell_plan[(slot, item_id)] = amount
                self.daily_coin_revenue += DIC_ISLAND_ITEM[item_id]['order_price'] * (1 + self.restaurant_sales_bonus[slot]) * amount

        for item_id, idx in item_index.items():
            amount = solution[end_offset + idx]
            if amount > 1e-6:
                self.net_items[item_id] = amount
                accumulating_amount = self._get_natural_accumulating_amount(item_id, amount)
                if accumulating_amount > 0:
                    self.net_accumulating_items[item_id] = accumulating_amount
        self._redirect_exchange_accumulating_items()
        self.total_pt = sum(
            DIC_ISLAND_ITEM[item_id].get('pt_num', 0) * amount
            for item_id, amount in self.net_accumulating_items.items()
        )
        self.daily_profit = self.net_items.get(1, 0)
        for col, activity in enumerate(activities):
            amount = solution[col]
            if amount <= 1e-6:
                continue
            coin_cost = activity['inputs'].get(1, 0)
            if coin_cost > 0:
                self.daily_coin_cost += coin_cost * amount
        self.product_min_stock_items = self._calculate_product_min_stock_items(
            solution=solution,
            activities=activities,
            sale_entries=sale_entries,
            activity_count=activity_count,
        )
        self.accumulating_rate_per_day = {
            item_id: self._round_output_amount(amount)
            for item_id, amount in sorted(self.net_accumulating_items.items())
            if self._round_output_amount(amount) > 0
        }

        grouped_recipe_plan = defaultdict(list)
        for activity in activities:
            if activity['kind'] == 'recipe':
                amount = self.production_plan.get(activity['id'], 0)
                if amount > 1e-6:
                    grouped_recipe_plan[activity['group']].append((activity['id'], amount, activity['workload']))
        for group, entries in grouped_recipe_plan.items():
            total_workload = sum(amount * workload for _, amount, workload in entries)
            slot_count = len(group_slots.get(group, []))
            if slot_count <= 0:
                continue
            self.group_usage_summary[group] = {
                'total_workload': total_workload,
                'slot_count': slot_count,
                'hours_per_slot': total_workload / 36000 / slot_count,
                'total_hours': total_workload / 36000,
                'recipes': {
                    recipe_id: {
                        'batches': amount,
                        'hours_total': amount * workload / 36000,
                    }
                    for recipe_id, amount, workload in entries
                }
            }

    def _calculate_product_min_stock_items(self, solution, activities, sale_entries, activity_count):
        daily_product_demand = defaultdict(float)
        sold_recipe_product_capacity = {}

        for col, activity in enumerate(activities):
            amount = solution[col]
            if amount <= self.NET_ACCUMULATING_EPSILON:
                continue
            for item_id, input_amount in activity['inputs'].items():
                if item_id in self.RECIPE_PRODUCT_IDS or (
                    self.EXCHANGE_REQUIRES_MANUAL_OPERATION and item_id in self.EXCHANGE_PRODUCT_IDS
                ):
                    daily_product_demand[item_id] += input_amount * amount

        for idx, (slot, item_id) in enumerate(sale_entries, start=activity_count):
            amount = solution[idx]
            if amount <= self.NET_ACCUMULATING_EPSILON:
                continue
            if item_id in self.RECIPE_PRODUCT_IDS:
                daily_product_demand[item_id] += amount
                sold_recipe_product_capacity[item_id] = max(
                    sold_recipe_product_capacity.get(item_id, 0),
                    self.restaurant_capacity[slot],
                )

        for item_id, capacity in sold_recipe_product_capacity.items():
            daily_product_demand[item_id] = max(daily_product_demand[item_id], capacity)

        min_stock_items = {}
        for item_id, amount in sorted(daily_product_demand.items()):
            if amount <= self.NET_ACCUMULATING_EPSILON:
                continue
            min_stock = ceil_with_epsilon(amount * (1 + self.min_stock_safety_margin))
            dish_slot = self.DISH_ITEM_TO_SLOT.get(item_id)
            if dish_slot is not None:
                min_stock = max(min_stock, self.restaurant_capacity[dish_slot])
            min_stock_items[item_id] = min_stock
        return min_stock_items

    def format_solved_production_plan(self):
        lines = [
            f'LP success: {self.lp_success}',
            f'LP status: {self.lp_status}',
            f'LP message: {self.lp_message}',
            f'Total PT: {self._format_amount(self.total_pt)}',
            f'Daily coin revenue: {self._format_amount(self.daily_coin_revenue)}',
            f'Daily coin cost: {self._format_amount(self.daily_coin_cost)}',
            f'Daily profit: {self._format_amount(self.daily_profit)}',
            '',
            '[production]',
        ]
        if self.production_plan:
            for recipe_id, amount in sorted(self.production_plan.items()):
                lines.append(f'{self._recipe_name(recipe_id)} ({recipe_id}): {self._format_amount(amount)} batches')
        else:
            lines.append('-')

        lines.append('')
        lines.append('[wild_gather/mining/logging]')
        has_passive = False
        for gather_id, product in sorted(self.wild_gather_plan.items()):
            has_passive = True
            product_text = ', '.join(
                f'{self._item_name(item_id)}({item_id}) x{self._format_amount(amount)}'
                for item_id, amount in product.items()
            )
            lines.append(f'wild_gather {gather_id}: {product_text}')
        if self.mining_supply_plan:
            has_passive = True
            product_text = ', '.join(
                f'{self._item_name(item_id)}({item_id}) x{self._format_amount(amount)}'
                for item_id, amount in sorted(self.mining_supply_plan.items())
            )
            lines.append(f'mining: {product_text}')
        if self.logging_supply_plan:
            has_passive = True
            product_text = ', '.join(
                f'{self._item_name(item_id)}({item_id}) x{self._format_amount(amount)}'
                for item_id, amount in sorted(self.logging_supply_plan.items())
            )
            lines.append(f'logging: {product_text}')
        if not has_passive:
            lines.append('-')

        lines.append('')
        lines.append('[exchange/buy]')
        has_trade = False
        for shop_id, amount in sorted(self.shop_plan.items()):
            has_trade = True
            lines.append(f'buy {self._shop_name(shop_id)} ({shop_id}): {self._format_amount(amount)}')
        for exchange_id, amount in sorted(self.exchange_plan.items()):
            has_trade = True
            lines.append(f'exchange {self._exchange_name(exchange_id)} ({exchange_id}): {self._format_amount(amount)}')
        if not has_trade:
            lines.append('-')

        lines.append('')
        lines.append('[sell]')
        if self.sell_plan:
            for (slot, item_id), amount in sorted(self.sell_plan.items()):
                lines.append(
                    f'slot {slot} {self._item_name(item_id)} ({item_id}): {self._format_amount(amount)}'
                )
        else:
            lines.append('-')

        lines.append('')
        lines.append('[slot_usage_by_type]')
        if self.group_usage_summary:
            for group, data in sorted(self.group_usage_summary.items(), key=lambda item: self._slot_group_sort_key(item[0])):
                lines.append(
                    f'{self._slot_group_name(group)}: {self._format_amount(data["total_hours"])}h total, '
                    f'{self._format_amount(data["hours_per_slot"])}h/24h per slot x{data["slot_count"]}'
                )
                for recipe_id, recipe_data in sorted(data['recipes'].items()):
                    lines.append(
                        f'  {self._recipe_name(recipe_id)} ({recipe_id}): '
                        f'{self._format_amount(recipe_data["batches"])} batches, '
                        f'{self._format_amount(recipe_data["hours_total"])}h total'
                    )
        else:
            lines.append('-')

        lines.append('')
        lines.append('[demand_items]')
        if self.demand_items:
            for item_id, data in sorted(self.demand_items.items()):
                need_text = format_item_need_data(data, self._format_amount)
                lines.append(
                    f'{self._item_name(item_id)} ({item_id}): '
                    f'{need_text}, '
                    f'{self._format_amount(data["rate_per_day"])} per day'
                )
        else:
            lines.append('-')

        lines.append('')
        lines.append('[preserved_items]')
        if self.preserved_items:
            for item_id, amount in sorted(self.preserved_items.items()):
                lines.append(f'{self._item_name(item_id)} ({item_id}): {self._format_amount(amount)}')
        else:
            lines.append('-')

        lines.append('')
        lines.append('[min_stock_products]')
        if self.product_min_stock_items:
            for item_id, amount in sorted(self.product_min_stock_items.items()):
                lines.append(f'{self._item_name(item_id)} ({item_id}): {self._format_amount(amount)}')
        else:
            lines.append('-')

        lines.append('')
        lines.append('[net_accumulating_items]')
        if self.accumulating_rate_per_day:
            for item_id, amount in sorted(self.accumulating_rate_per_day.items()):
                lines.append(f'{self._item_name(item_id)} ({item_id}): {self._format_amount(amount)}')
        else:
            lines.append('-')
        return '\n'.join(lines)

    def print_solved_production_plan(self):
        for line in self.format_solved_production_plan().split('\n'):
            logger.info(line)

    def _get_min_stock_export_entry(self, item_id):
        return self.product_min_stock_items.get(item_id, 0)

    def inventory_levels_to_yaml(self, use_item_name=False):
        item_ids = sorted(self.product_min_stock_items)
        return item_mapping_to_yaml(
            {
                item_id: self._get_min_stock_export_entry(item_id)
                for item_id in item_ids
            },
            use_item_name=use_item_name,
        )

    def accumulating_rate_to_yaml(self, use_item_name=False):
        return item_mapping_to_yaml(self.accumulating_rate_per_day, use_item_name=use_item_name)

    def preserved_items_to_yaml(self, use_item_name=False):
        return item_mapping_to_yaml(self.preserved_items, use_item_name=use_item_name)

    def restaurant_menus_to_yaml(self):
        menus = {slot: {} for slot in self.RESTAURANT_MENU_CONFIG}
        for (slot, item_id), amount in sorted(self.sell_plan.items()):
            if amount <= self.NET_ACCUMULATING_EPSILON:
                continue
            menus[slot][item_id] = self._round_output_amount(amount)
        return {
            slot: item_mapping_to_yaml(menu, use_item_name=True)
            for slot, menu in menus.items()
        }

    def solve_production_plan(self, preserved_items=None, task_target_items=None):
        self.daily_profit_lower_limit = self.config.cross_get("IslandProductionPlanner.IslandProductionPlanner.DailyProfitLowerLimit", 0)
        self.min_stock_safety_margin = max(
            float(self.config.cross_get("IslandProductionPlanner.IslandProductionPlanner.MinStockSafetyMargin", 0)),
            0,
        )
        if preserved_items is None:
            preserved_items = load_preserved_items(
                self.config.cross_get("IslandProduction.IslandProduction.PreservedItems", "")
            )
        if task_target_items is None:
            task_target_items = load_item_mapping(
                self.config.cross_get("IslandSeasonTask.IslandSeasonTask.TaskTarget", "{}"),
                config_name='TaskTarget',
            )
        self.preserved_items = normalize_item_keys(preserved_items)
        self.task_target_items = normalize_item_needs(task_target_items, default_period=10)
        demand_items = self.task_target_items
        problem = self._build_production_problem(demand_items=demand_items)
        self._reset_lp_result()
        result = None
        solver_attempts = [
            ('interior-point', {'tol': 1e-9}),
            ('revised simplex', {'tol': 1e-9}),
        ]
        for method, options in solver_attempts:
            result = linprog(
                problem['c'],
                A_ub=problem['A_ub'],
                b_ub=problem['b_ub'],
                A_eq=problem['A_eq'],
                b_eq=problem['b_eq'],
                bounds=problem['bounds'],
                method=method,
                options=options,
            )
            if result.success:
                break
        self._apply_production_lp_result(result, problem)

    def run(self, tech_status_yaml=None, preserved_items_yaml=None, task_target_items=None, export=True, use_item_name_in_export=True):
        if tech_status_yaml is not None:
            technology_status = safe_load(tech_status_yaml) if tech_status_yaml else None
        else:
            technology_status = self.config.cross_get("IslandProductionPlanner.Storage.Storage.IslandTechnologyStatus", None)
            if technology_status is None or self.config.cross_get("IslandProductionPlanner.IslandProductionPlanner.RescanIslandTechnology", False):
                technology_status = IslandTechnologyScanner(self.config).get_technology_status()
            else:
                technology_status = {int(k): v for k, v in technology_status.items()}
        if preserved_items_yaml is None:
            preserved_items = load_preserved_items(
                self.config.cross_get("IslandProduction.IslandProduction.PreservedItems", "")
            )
        else:
            preserved_items = load_preserved_items(preserved_items_yaml)
        if task_target_items is None:
            task_target_items = load_item_mapping(
                self.config.cross_get("IslandSeasonTask.IslandSeasonTask.TaskTarget", "{}"),
                config_name='TaskTarget',
            )
        self.analyze_technology_status(technology_status)
        self.solve_production_plan(preserved_items=preserved_items, task_target_items=task_target_items)
        self.print_solved_production_plan()
        if export:
            inventory_levels_yaml_text = self.inventory_levels_to_yaml(use_item_name=use_item_name_in_export)
            accumulating_rate_yaml_text = self.accumulating_rate_to_yaml(use_item_name=use_item_name_in_export)
            preserved_items_yaml_text = self.preserved_items_to_yaml(use_item_name=use_item_name_in_export)
            restaurant_menu_yaml_texts = self.restaurant_menus_to_yaml()
            self.inventory_levels_yaml_text = inventory_levels_yaml_text
            self.accumulating_rate_yaml_text = accumulating_rate_yaml_text
            self.preserved_items_yaml_text = preserved_items_yaml_text
            with self.config.multi_set():
                self.config.cross_set("IslandProductionPlanner.Storage.Storage.IslandTechnologyStatus", technology_status)
                self.config.cross_set("IslandProduction.IslandProduction.MinStockItems", inventory_levels_yaml_text)
                self.config.cross_set("IslandProduction.IslandProduction.AccumulatingItems", accumulating_rate_yaml_text)
                self.config.cross_set("IslandProduction.IslandProduction.PreservedItems", preserved_items_yaml_text)
                for slot, config_key in self.RESTAURANT_MENU_CONFIG.items():
                    self.config.cross_set(config_key, restaurant_menu_yaml_texts[slot])
                self.config.cross_set("IslandProductionPlanner.IslandProductionPlanner.RescanIslandTechnology", False)
