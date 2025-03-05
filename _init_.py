import os
import random
import asyncio
import hoshino
import nonebot
from hoshino import Service, sucmd
from hoshino.util import FreqLimiter
from hoshino.config import SUPERUSERS
from .. import money, config
from .._R import get
from ..utilize import get_double_mean_money
from ..money import get_user_money, reduce_user_money, increase_user_money
from nonebot import on_command, on_request, get_bot
from hoshino.typing import CQEvent as Event, CommandSession, CQHttpError, NoticeSession
from nonebot.message import MessageSegment

sv = Service("狼人杀", manage_priv=5, visible=True, enable_on_default=True)

# 插件信息
__plugin_name__ = '狼人杀'
__plugin_usage__ = (
    '使用方法：\n'
    '开始狼人杀 - 创建一个狼人杀房间\n'
    '加入狼人杀 - 加入已创建的狼人杀房间\n'
    '退出狼人杀 - 退出狼人杀房间\n'
    '狼人杀状态 - 查看当前房间状态\n'
    '开始游戏 - (房主)开始游戏\n'
    '投票 [玩家序号] - 投票给指定玩家(白天放逐投票)\n'
    '狼人投票 [玩家序号] - 狼人晚上杀人投票，私聊机器人\n'
    '平安夜 - 女巫选择平安夜 (仅女巫夜晚私聊使用)\n'
    '解药 [玩家序号] - 女巫选择解药 (仅女巫夜晚私聊使用)\n'
    '毒药 [玩家序号] - 女巫选择毒药 (仅女巫夜晚私聊使用)\n'
    '查验 [玩家序号] - 预言家查验指定玩家 (仅预言家夜晚私聊使用)\n'
    '结束狼人杀 - (房主管理员)结束狼人杀'
)

# 游戏配置 (可以根据需要调整)
GAME_ROOM_GROUP = 1034405771  # 替换为游戏房间的群号
MIN_PLAYERS = 6  # 最少玩家数量
MAX_PLAYERS = 12  # 最大玩家数量
DEFAULT_ROLES = ['狼人', '狼人', '村民', '村民', '预言家', '女巫']  # 默认角色配置 (可以调整)

# 游戏状态
game_state = {}  # 使用字典存储游戏状态，键为群号

# 辅助函数
def is_game_room(bot, ev):
    """判断是否在游戏房间"""
    return ev.group_id == GAME_ROOM_GROUP

def is_game_running(group_id):
    """判断游戏是否正在运行"""
    return group_id in game_state and game_state[group_id]['is_running']

def get_player_nick(group_id, user_id):
    """获取玩家玩家序号"""
    return game_state[group_id]['players'][user_id]['player_num']

def get_player_uid(group_id, user_id):
    """获取玩家uid"""
    return game_state[group_id]['players'][user_id]['uid']

def get_alive_players(group_id):
    """获取所有存活玩家的ID列表"""
    return [user_id for user_id, player_info in game_state[group_id]['players'].items() if player_info['alive']]

def get_alive_players_count(group_id):
    """获取存活玩家的数量"""
    return len(get_alive_players(group_id))

def get_player_role(group_id, user_id):
    """获取玩家角色"""
    return game_state[group_id]['players'][user_id]['role']

def assign_roles(group_id):
    """分配角色"""
    players_count = len(game_state[group_id]['players'])
    roles = DEFAULT_ROLES[:players_count]  # 使用默认角色配置，并截取到玩家数量
    if players_count > len(DEFAULT_ROLES):
        # 如果玩家数量超过默认角色配置，则添加村民
        roles.extend(['村民'] * (players_count - len(DEFAULT_ROLES)))
    random.shuffle(roles)
    game_state[group_id]['roles'] = roles
    i = 0
    for user_id in game_state[group_id]['players']:
        game_state[group_id]['players'][user_id]['role'] = roles[i]
        game_state[group_id]['players'][user_id]['alive'] = True
        game_state[group_id]['players'][user_id]['voted'] = False
        i += 1

def reset_votes(group_id):
    """重置投票记录"""
    game_state[group_id]['votes'] = {}
    for user_id in game_state[group_id]['players']:
        game_state[group_id]['players'][user_id]['voted'] = False

def check_game_over(group_id):
    """检查游戏是否结束"""
    alive_werewolves = 0
    alive_villagers = 0
    for user_id in get_alive_players(group_id):
        if get_player_role(group_id, user_id) == '狼人':
            alive_werewolves += 1
        else:
            alive_villagers += 1
    if alive_werewolves == 0:
        return '村民胜利！'
    if alive_villagers <= alive_werewolves:
        return '狼人胜利！'
    return None

def get_user_id_from_player_num(group_id, player_num):
    """通过玩家序号获取玩家 ID"""
    for user_id, player_info in game_state[group_id]['players'].items():
        if player_info['player_num'] == player_num:
            return user_id
    return None

@on_command('在吗')
async def zaima(session: CommandSession):
    bot = nonebot.get_bot()
    user = session.ev.user_id
    await bot.send_private_msg(user_id=user, message='嗨！')  #为测试指令，目的于检查玩家是否可以私聊机器人（如果无法私聊请让他加好友）

@sv.on_command('在不在')
async def zaibuzai(session: CommandSession):
    bot = nonebot.get_bot()
    user = session.event.user_id
    gid = session.event.group_id

    await bot.send_group_msg(group_id=gid, message=f'嗨！') #at_sender没有用！！#为另一个测试指令，检查机器人是否可以在群里发送信息



# 命令处理器
@sv.on_fullmatch('开始狼人杀')
async def start_werewolf(bot, ev):
    """开始狼人杀游戏"""
    group_id = ev.group_id
    user_id = ev.user_id
    if not is_game_room(bot, ev):
        await bot.send(ev, '请在游戏房间内使用此命令')
        return
    if is_game_running(group_id):
        await bot.send(ev, '游戏已经开始了！')
        return
    if group_id not in game_state:
        game_state[group_id] = {  # 初始化游戏状态
            'is_running': False,
            'room_owner': user_id,
            'players': {},
            'roles': [],
            'day': 0,
            'night': False,
            'votes': {},
            'witch_used_potion': False,
            'witch_used_poison': False,
            'last_night_dead': None,
            'next_player_num': 1
        }
        await bot.send(ev, f'狼人杀房间已创建！你是房主。使用 加入狼人杀 加入游戏。')
    else:
        await bot.send(ev, f'房间已创建，请使用 加入狼人杀 加入游戏。')

@sv.on_fullmatch('加入狼人杀')
async def join_werewolf(bot, ev):
    """加入狼人杀游戏"""
    group_id = ev.group_id
    user_id = ev.user_id
    if not is_game_room(bot, ev):
        await bot.send(ev, '请在游戏房间内使用此命令')
        return
    if group_id not in game_state or not game_state[group_id]['room_owner']:
        await bot.send(ev, '请先创建狼人杀房间！使用 开始狼人杀')
        return
    if is_game_running(group_id):
        await bot.send(ev, '游戏已经开始了，无法加入！')
        return
    if user_id in game_state[group_id]['players']:
        await bot.send(ev, '你已经加入游戏了！')
        return
    if len(game_state[group_id]['players']) >= MAX_PLAYERS:
        await bot.send(ev, f'人数已满({MAX_PLAYERS}人)，无法加入！')
        return
    player_num = game_state[group_id]['next_player_num']
    game_state[group_id]['players'][user_id] = {
        'player_num': player_num,
        'role': None,
        'alive': True,
        'voted': False
    }
    game_state[group_id]['next_player_num'] += 1
    await bot.send(ev, f'{player_num}号玩家加入了游戏！')

@sv.on_fullmatch('退出狼人杀')
async def leave_werewolf(bot, ev):
    """退出狼人杀游戏"""
    group_id = ev.group_id
    user_id = ev.user_id
    if not is_game_room(bot, ev):
        await bot.send(ev, '请在游戏房间内使用此命令')
        return
    if group_id not in game_state or user_id not in game_state[group_id]['players']:
        await bot.send(ev, '你还没有加入游戏！')
        return
    if is_game_running(group_id):
        await bot.send(ev, '游戏已经开始了，无法退出！')
        return
    player_num = game_state[group_id]['players'][user_id]['player_num']
    del game_state[group_id]['players'][user_id]
    await bot.send(ev, f'{player_num}号玩家退出了游戏！')
    if user_id == game_state[group_id]['room_owner']:
        # 房主退出，游戏结束
        del game_state[group_id]  # 直接删除游戏状态
        await bot.send(ev, '房主退出了游戏，游戏结束。')

@sv.on_fullmatch('狼人杀状态')
async def werewolf_status(bot, ev):
    """查看狼人杀状态"""
    group_id = ev.group_id
    if not is_game_room(bot, ev):
        await bot.send(ev, '请在游戏房间内使用此命令')
        return
    if group_id not in game_state or not game_state[group_id]['room_owner']:
        await bot.send(ev, '还没有创建狼人杀房间！使用 开始狼人杀')
        return
    msg = '当前狼人杀状态：\n'
    if is_game_running(group_id):
        msg += f'游戏正在进行中，当前是第 {game_state[group_id]["day"]} 天，{"夜晚" if game_state[group_id]["night"] else "白天"}\n'
    else:
        msg += '游戏尚未开始，等待玩家加入...\n'
    msg += '玩家列表：\n'
    for user_id, player_info in game_state[group_id]['players'].items():
        msg += f'- {player_info["player_num"]}号 (QQ: {user_id}) '  # 显示玩家序号和QQ号
        if is_game_running(group_id):
            # 只有房主能看所有身份
            if ev.user_id in SUPERUSERS:
                msg += f'({player_info["role"]}, {"存活" if player_info["alive"] else "死亡"})'
            else:
                msg += f'(身份未知, {"存活" if player_info["alive"] else "死亡"})'
        msg += '\n'
    await bot.send(ev, msg)

@sv.on_fullmatch('开始游戏')
async def start_game(bot, ev):
    """开始游戏"""
    group_id = ev.group_id
    user_id = ev.user_id
    if not is_game_room(bot, ev):
        await bot.send(ev, '请在游戏房间内使用此命令')
        return
    if group_id not in game_state or not game_state[group_id]['room_owner']:
        await bot.send(ev, '请先创建狼人杀房间！使用 开始狼人杀')
        return
    if is_game_running(group_id):
        await bot.send(ev, '游戏已经开始了！')
        return
    if user_id != game_state[group_id]['room_owner']:
        await bot.send(ev, '只有房主才能开始游戏！')
        return
    if len(game_state[group_id]['players']) < MIN_PLAYERS:
        await bot.send(ev, f'至少需要 {MIN_PLAYERS} 名玩家才能开始游戏！')
        return
    game_state[group_id]['is_running'] = True
    assign_roles(group_id)  # 分配角色
    game_state[group_id]['day'] = 1
    game_state[group_id]['night'] = True
    reset_votes(group_id)
    game_state[group_id]['witch_used_potion'] = False
    game_state[group_id]['witch_used_poison'] = False
    game_state[group_id]['last_night_dead'] = None
    await bot.send(ev, '游戏开始！')
    # 发送角色信息给每个玩家 (私聊)
    for user_id, player_info in game_state[group_id]['players'].items():
        role_name = player_info['role']
        try:
            await bot.send_private_msg(user_id=user_id, message=f'你的角色是：{role_name}！')
        except Exception as e:
            await bot.send(ev, f'无法私聊玩家 {user_id}，请确保已添加机器人好友。')
            hoshino.logger.error(f"私聊发送失败: {e}")
    await night_phase(bot, ev, group_id)  # 进入第一个夜晚
    
    

            
@sv.on_prefix('投票')  # 白天投票，群聊指令
async def vote(bot, ev):
    """白天投票放逐玩家"""
    group_id = ev.group_id
    user_id = ev.user_id
    if not is_game_room(bot, ev):
        await bot.send(ev, '请在游戏房间内使用此命令')
        return
    if not is_game_running(group_id):
        await bot.send(ev, '游戏尚未开始！')
        return
    if game_state[group_id]['night']:
        await bot.send(ev, '请在白天进行投票！')
        return
    if user_id not in game_state[group_id]['players'] or not game_state[group_id]['players'][user_id]['alive']:
        await bot.send(ev, '你已经死亡，无法投票！')
        return
    if game_state[group_id]['players'][user_id]['voted']:
        await bot.send(ev, '你已经投过票了，不能再次投票！')
        return

    message = ev.message.extract_plain_text().strip()
    if not message.isdigit():
        await bot.send(ev, '请指定要投票的玩家序号 (例如: 投票 1)')
        return

    target_player_num = int(message)
    target_id = get_user_id_from_player_num(group_id, target_player_num)  # 通过序号获取用户ID
    if not target_id:
        await bot.send(ev, '无效的玩家序号！')
        return
    if not game_state[group_id]['players'][target_id]['alive']:
        await bot.send(ev, '该玩家已经死亡，不能投票！')
        return
    if target_id == user_id:
        await bot.send(ev, '不能投票给自己！')
        return

    game_state[group_id]['votes'][user_id] = target_id
    game_state[group_id]['players'][user_id]['voted'] = True
    target_nick = get_player_nick(group_id, target_id)
    await bot.send(ev, f'{ev.sender.nickname} 投票给了 {target_nick}！')

    # 检查是否所有人都投过票
    all_voted = True
    for u_id in get_alive_players(group_id):
        if not game_state[group_id]['players'][u_id]['voted']:
            all_voted = False
            break
    if all_voted:
        await process_day_votes(bot, ev, group_id)

@on_command('狼人投票', only_to_me=True)  # 狼人狼人投票，私聊指令
async def werewolf_vote(session: CommandSession):
    """狼人夜晚投票杀人"""
    bot = session.bot
    ev = session.event
    group_id = ev.group_id if ev.message_type == 'group' else session.ctx['group_id'] if 'group_id' in session.ctx else None #优先使用event中的group_id，如果没有（私聊），使用ctx中存储的group_id，如果ctx中也没有，则设为None
    user_id = ev.user_id

    if not group_id: #如果没有group_id，说明既不是群聊，ctx中也没有存，说明是第一次私聊，报错
        await bot.send(ev, '请先在群里开始游戏，再私聊我进行操作！')
        return

    if not is_game_running(group_id):
        await bot.send(ev, '游戏尚未开始！')
        return
    if not game_state[group_id]['night']:
        await bot.send(ev, '请在夜晚进行投票！')
        return
    if get_player_role(group_id, user_id) != '狼人':
        await bot.send(ev, '只有狼人才能投票！')
        return
    if user_id not in game_state[group_id]['players'] or not game_state[group_id]['players'][user_id]['alive']:
        await bot.send(ev, '你已经死亡，无法投票！')
        return
    message = ev.message.extract_plain_text().strip()
    if not message.isdigit():
        await bot.send(ev, '请指定要投票的玩家序号 (例如: 狼人投票 1)')
        return
    target_player_num = int(message)
    target_id = get_user_id_from_player_num(group_id, target_player_num)
    if not target_id:
        await bot.send(ev, '无效的玩家序号！')
        return
    if not game_state[group_id]['players'][target_id]['alive']:
        await bot.send(ev, '该玩家已经死亡，不能投票！')
        return
    if target_id == user_id:
        await bot.send(ev, '不能投票给自己！')
        return
    if 'wolf_votes' not in game_state[group_id]:
        game_state[group_id]['wolf_votes'] = {}
    game_state[group_id]['wolf_votes'][user_id] = target_id
    target_nick = get_player_nick(group_id, target_id)
    await bot.send(ev, f'你投票了 {target_nick}！')

@on_command('平安夜', only_to_me=True)
async def witch_night(session: CommandSession):
    """女巫选择平安夜"""
    bot = session.bot
    ev = session.event
    group_id = ev.group_id if ev.message_type == 'group' else session.ctx['group_id'] if 'group_id' in session.ctx else None
    user_id = ev.user_id

    if not group_id:
        await bot.send(ev, '请先在群里开始游戏，再私聊我进行操作！')
        return

    if not is_game_running(group_id):
        await bot.send(ev, '游戏尚未开始！')
        return
    if not game_state[group_id]['night']:
        await bot.send(ev, '请在夜晚使用此命令！')
        return
    if get_player_role(group_id, user_id) != '女巫':
        await bot.send(ev, '只有女巫才能使用此命令！')
        return
    if game_state[group_id]['witch_used_potion']:
        await bot.send(ev, '你已经使用过解药了！')
        return
    game_state[group_id]['witch_used_potion'] = True
    if game_state[group_id]['last_night_dead'] is None:
        await bot.send(ev, '昨晚没有人死亡，你无法使用解药！')
        await bot.send_group_msg(group_id=group_id, message='昨晚没有人死亡，女巫选择了不使用解药') # 发送回游戏群
        return
    game_state[group_id]['last_night_dead'] = None
    await bot.send(ev, '你选择了平安夜，昨晚死亡的玩家被你救活了！')
    await bot.send_group_msg(group_id=group_id, message='女巫选择了平安夜，昨晚死亡的玩家被救活了') # 发送回游戏群

@on_command('解药', only_to_me=True)
async def witch_save(session: CommandSession):
    """女巫使用解药"""
    bot = session.bot
    ev = session.event
    group_id = ev.group_id if ev.message_type == 'group' else session.ctx['group_id'] if 'group_id' in session.ctx else None
    user_id = ev.user_id

    if not group_id:
        await bot.send(ev, '请先在群里开始游戏，再私聊我进行操作！')
        return

    if not is_game_running(group_id):
        await bot.send(ev, '游戏尚未开始！')
        return
    if not game_state[group_id]['night']:
        await bot.send(ev, '请在夜晚使用此命令！')
        return
    if get_player_role(group_id, user_id) != '女巫':
        await bot.send(ev, '只有女巫才能使用此命令！')
        return
    if game_state[group_id]['witch_used_potion']:
        await bot.send(ev, '你已经使用过解药了！')
        return
    message = ev.message.extract_plain_text().strip()
    if not message.isdigit():
        await bot.send(ev, '请输入要救的玩家序号')
        return
    target_player_num = int(message)
    target_id = get_user_id_from_player_num(group_id, target_player_num)
    if not target_id:
        await bot.send(ev, '无效的玩家序号！')
        return
    if game_state[group_id]['players'][target_id]['alive']:
        await bot.send(ev, '该玩家还活着，不需要使用解药！')
        return
    if game_state[group_id]['last_night_dead'] != target_id:
        await bot.send(ev, '昨晚死亡的不是这个人！')
        return
    game_state[group_id]['witch_used_potion'] = True
    game_state[group_id]['players'][target_id]['alive'] = True
    game_state[group_id]['last_night_dead'] = None
    target_nick = get_player_nick(group_id, target_id)
    await bot.send(ev, f'你使用了灵药，救活了 {target_nick}！')
    await bot.send_group_msg(group_id=group_id, message=f'女巫使用了灵药，救活了 {target_nick}！') # 发送回游戏群

@on_command('毒药', only_to_me=True)
async def witch_poison(session: CommandSession):
    """女巫使用毒药"""
    bot = session.bot
    ev = session.event
    group_id = ev.group_id if ev.message_type == 'group' else session.ctx['group_id'] if 'group_id' in session.ctx else None
    user_id = ev.user_id

    if not group_id:
        await bot.send(ev, '请先在群里开始游戏，再私聊我进行操作！')
        return

    if not is_game_running(group_id):
        await bot.send(ev, '游戏尚未开始！')
        return
    if not game_state[group_id]['night']:
        await bot.send(ev, '请在夜晚使用此命令！')
        return
    if get_player_role(group_id, user_id) != '女巫':
        await bot.send(ev, '只有女巫才能使用此命令！')
        return
    if game_state[group_id]['witch_used_poison']:
        await bot.send(ev, '你已经使用过毒药了！')
        return
    message = ev.message.extract_plain_text().strip()
    if not message.isdigit():
        await bot.send(ev, '请输入要毒的玩家序号')
        return
    target_player_num = int(message)
    target_id = get_user_id_from_player_num(group_id, target_player_num)
    if not target_id:
        await bot.send(ev, '无效的玩家序号！')
        return
    if not game_state[group_id]['players'][target_id]['alive']:
        await bot.send(ev, '该玩家已经死亡，不能使用毒药！')
        return
    game_state[group_id]['witch_used_poison'] = True
    game_state[group_id]['players'][target_id]['alive'] = False
    target_nick = get_player_nick(group_id, target_id)
    await bot.send(ev, f'你使用了毒药，毒死了 {target_nick}！')
    await bot.send_group_msg(group_id=group_id, message=f'女巫使用了毒药，毒死了 {target_nick}！') # 发送回游戏群

@on_command('查验', only_to_me=True)
async def seer_check(session: CommandSession):
    """预言家查验"""
    bot = session.bot
    ev = session.event
    group_id = ev.group_id if ev.message_type == 'group' else session.ctx['group_id'] if 'group_id' in session.ctx else None
    user_id = ev.user_id

    if not group_id:
        await bot.send(ev, '请先在群里开始游戏，再私聊我进行操作！')
        return

    if not is_game_running(group_id):
        await bot.send(ev, '游戏尚未开始！')
        return
    if not game_state[group_id]['night']:
        await bot.send(ev, '请在夜晚使用此命令！')
        return
    if get_player_role(group_id, user_id) != '预言家':
        await bot.send(ev, '只有预言家才能使用此命令！')
        return
    message = ev.message.extract_plain_text().strip()
    if not message.isdigit():
        await bot.send(ev, '请输入要查验的玩家序号')
        return
    target_player_num = int(message)
    target_id = get_user_id_from_player_num(group_id, target_player_num)
    if not target_id:
        await bot.send(ev, '无效的玩家序号！')
        return
    if not game_state[group_id]['players'][target_id]['alive']:
        await bot.send(ev, '该玩家已经死亡，无法查验！')
        return
    target_role = get_player_role(group_id, target_id)
    is_werewolf = target_role == '狼人'
    result = '是狼人' if is_werewolf else '不是狼人'
    target_nick = get_player_nick(group_id, target_id)
    await bot.send(ev, f'{target_nick} {result}！')
    await bot.send_group_msg(group_id=group_id, message='预言家进行了查验') # 发送回游戏群

@sv.on_fullmatch('结束狼人杀')
async def end_werewolf(bot, ev):
    """结束狼人杀游戏"""
    group_id = ev.group_id
    user_id = ev.user_id
    if not is_game_room(bot, ev):
        await bot.send(ev, '请在游戏房间内使用此命令')
        return
    if group_id not in game_state or not game_state[group_id]['is_running']:
        await bot.send(ev, '当前没有进行中的游戏！')
        return
    # 检查是否有权限结束游戏
    if user_id == game_state[group_id]['room_owner'] or user_id in SUPERUSERS:
        await end_game(bot, ev)  # 修复：只传递 bot 和 ev
        await bot.send(ev, '游戏已结束。')
    else:
        await bot.send(ev, '只有房主或管理员才能结束游戏！')

# 游戏流程函数
async def night_phase(bot, ev, group_id):
    """夜晚阶段"""
    game_state[group_id]['night'] = True
    game_state[group_id]['day'] += 1
    await bot.send(ev, f'第 {game_state[group_id]["day"]} 天夜晚降临了，请大家闭眼。')

    # 狼人行动
    await werewolf_action(bot, ev, group_id)

    # 女巫行动
    await witch_action(bot, ev, group_id)

    # 预言家行动
    await seer_action(bot, ev, group_id)

    await bot.send(ev, '天亮了，请大家睁眼。')
    await day_phase(bot, ev, group_id)

async def werewolf_action(bot, ev, group_id):
    """狼人行动"""
    await bot.send(ev, '狼人请睁眼，请选择要杀死的玩家（请私聊机器人 狼人投票 [玩家序号]）。')
    werewolf_ids = [user_id for user_id, player_info in game_state[group_id]['players'].items() if
                    player_info['role'] == '狼人' and player_info['alive']]
    for werewolf_id in werewolf_ids:
        try:
            await bot.send_private_msg(user_id=werewolf_id, message='请选择要杀死的玩家，使用 狼人投票 [玩家序号]')
        except Exception as e:
            await bot.send(ev, f'无法私聊玩家 {werewolf_id}，请确保已添加机器人好友。')
            hoshino.logger.error(f"私聊发送失败: {e}")
    await asyncio.sleep(60)  # 留给狼人60秒时间

    # 统计狼人投票结果 (选择票数最高的玩家)
    if 'wolf_votes' in game_state[group_id]:
        wolf_votes = {}
        for user_id in game_state[group_id]['wolf_votes']:
            target_id = game_state[group_id]['wolf_votes'][user_id]
            if target_id in wolf_votes:
                wolf_votes[target_id] += 1
            else:
                wolf_votes[target_id] = 1

        if wolf_votes:
            killed_player = max(wolf_votes, key=wolf_votes.get)  # 找到票数最高的玩家
            game_state[group_id]['last_night_dead'] = killed_player  # 记录昨晚死亡的玩家，供女巫使用
            game_state[group_id]['players'][killed_player]['alive'] = False  # 标记死亡
            killed_nick = get_player_nick(group_id, killed_player)
            await bot.send(ev, f'昨晚，{killed_nick} 被狼人杀死了！')
        else:
            game_state[group_id]['last_night_dead'] = None
            await bot.send(ev, '昨晚是平安夜。')
    else:
        game_state[group_id]['last_night_dead'] = None
        await bot.send(ev, '昨晚是平安夜。')

    # 清空狼人投票
    if 'wolf_votes' in game_state[group_id]:
        game_state[group_id]['wolf_votes'] = {}

    await bot.send(ev, '狼人请闭眼。')

async def witch_action(bot, ev, group_id):
    """女巫行动"""
    witch_id = next((user_id for user_id, player_info in game_state[group_id]['players'].items() if
                    player_info['role'] == '女巫' and player_info['alive']), None)
    if witch_id:
        await bot.send(ev, '女巫请睁眼，你有一瓶解药和一瓶毒药。')
        if game_state[group_id]['last_night_dead'] is not None:
            dead_player_nick = get_player_nick(group_id, game_state[group_id]['last_night_dead'])
            try:
                await bot.send_private_msg(user_id=witch_id,
                                         message=f'昨晚，{dead_player_nick} 被狼人杀死了，你要使用解药吗？(使用 解药 [玩家序号] 或 平安夜)')
            except Exception as e:
                await bot.send(ev, f'无法私聊玩家 {witch_id}，请确保已添加机器人好友。')
                hoshino.logger.error(f"私聊发送失败: {e}")
        else:
            try:
                await bot.send_private_msg(user_id=witch_id, message='昨晚是平安夜，你要使用毒药吗？(使用 毒药 [玩家序号])')
            except Exception as e:
                await bot.send(ev, f'无法私聊玩家 {witch_id}，请确保已添加机器人好友。')
                hoshino.logger.error(f"私聊发送失败: {e}")
        if not game_state[group_id]['witch_used_poison']:
            try:
                await bot.send_private_msg(user_id=witch_id, message='你要使用毒药吗？(使用 毒药 [玩家序号])')
            except Exception as e:
                await bot.send(ev, f'无法私聊玩家 {witch_id}，请确保已添加机器人好友。')
                hoshino.logger.error(f"私聊发送失败: {e}")
        await asyncio.sleep(60)  # 留给女巫60秒时间


async def seer_action(bot, ev, group_id):
    """预言家行动"""
    seer_id = next((user_id for user_id, player_info in game_state[group_id]['players'].items() if
                    player_info['role'] == '预言家' and player_info['alive']), None)
    if seer_id:
        await bot.send(ev, '预言家请睁眼，你要查验谁？(使用 查验 [玩家序号])')
        try:
            await bot.send_private_msg(user_id=seer_id, message='你要查验谁？(使用 查验 [玩家序号])')
        except Exception as e:
            await bot.send(ev, f'无法私聊玩家 {seer_id}，请确保已添加机器人好友。')
            hoshino.logger.error(f"私聊发送失败: {e}")
        await asyncio.sleep(60)  # 留给预言家60秒时间
        await bot.send(ev, '预言家请闭眼。')

async def day_phase(bot, ev, group_id):
    """白天阶段"""
    group_id = ev.group_id
    game_state[group_id]['night'] = False
    await bot.send(ev, f'现在是第 {game_state[group_id]["day"]} 天白天，请大家自由发言(120s)。')
    if game_state[group_id]['last_night_dead']:
        dead_player_nick = get_player_nick(group_id, game_state[group_id]['last_night_dead'])
        await bot.send(ev, f'昨晚，{dead_player_nick} 死亡了。')
    await asyncio.sleep(120)  # 留给玩家120秒讨论时间
    reset_votes(group_id) #重置白天投票
    await bot.send(ev, '发言结束，请大家投票放逐一名玩家。(使用 投票 [玩家序号])')

async def process_day_votes(bot, ev, group_id):
    """处理白天投票结果"""
    vote_counts = {}
    for voter_id, target_id in game_state[group_id]['votes'].items():
        if target_id in vote_counts:
            vote_counts[target_id] += 1
        else:
            vote_counts[target_id] = 1

    if vote_counts:
        most_voted_player = max(vote_counts, key=vote_counts.get)  # 找到票数最高的玩家
        if vote_counts[most_voted_player] > 0: # 确认有投票
            game_state[group_id]['players'][most_voted_player]['alive'] = False  # 标记死亡
            most_voted_nick = get_player_nick(group_id, most_voted_player)
            await bot.send(ev, f'{most_voted_nick} 被放逐了！')
        else:
            await bot.send(ev, '没有人被放逐。')
    else:
        await bot.send(ev, '没有人被放逐。')

    game_over_result = check_game_over(group_id)
    if game_over_result:
        await bot.send(ev, game_over_result)
        await end_game(bot, ev, group_id)
    else:
        await night_phase(bot, ev, group_id)

async def end_game(bot, ev):  # 修复：只接受 bot 和 ev
    """结束游戏"""
    group_id = ev.group_id  # 从 ev 中获取 group_id
    if group_id in game_state:
        del game_state[group_id]  # 清除游戏状态
    await bot.send(ev, '游戏结束！')

# 帮助命令
@sv.on_fullmatch('狼人杀帮助')
async def werewolf_help(bot, ev):
    await bot.send(ev, __plugin_usage__)
