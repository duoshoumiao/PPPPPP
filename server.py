from collections import Counter
from typing import Any, Callable, Coroutine, Dict, List, Tuple, Union

from .autopcr.module.accountmgr import BATCHINFO, AccountBatch, TaskResultInfo
from .autopcr.module.modulebase import eResultStatus
from .autopcr.util.draw_table import outp_b64
from .autopcr.http_server.httpserver import HttpServer
from .autopcr.db.database import db
from .autopcr.module.accountmgr import Account, AccountManager, instance as usermgr
from .autopcr.db.dbstart import db_start
from .autopcr.util.draw import instance as drawer
import asyncio, datetime

from io import BytesIO
from PIL import Image
import nonebot
from nonebot import on_startup
import hoshino
from hoshino import HoshinoBot, Service, priv
from hoshino.util import escape
from hoshino.typing import CQEvent
from quart_auth import QuartAuth
from quart_rate_limiter import RateLimiter
from quart_compress import Compress
import secrets
from .autopcr.util.pcr_data import get_id_from_name
import traceback
from .autopcr.util.logger import instance as logger
import os # 新增：用于获取进程端口信息
import re
import requests
import socket
from typing import Optional
import inspect  # 新增这一行
from hoshino import log  # 确保 log 模块已导入
logger = log.new_logger('auto_pcr')  # 初始化日志记录器
def get_public_ip() -> str:
    """获取服务器的公网IP（多重备选方案）"""
    # 备选公网IP查询API列表
    ip_apis = [
        "https://api.ipify.org?format=json",
        "https://ipinfo.io/json",
        "http://ip-api.com/json",
        "https://ifconfig.me/all.json",
    ]
    
    # 尝试所有可用的API
    for api_url in ip_apis:
        try:
            response = requests.get(api_url, timeout=5)
            if response.status_code == 200:
                data = response.json()
                # 不同API返回的字段可能不同
                if "ip" in data:
                    return data["ip"]
                elif "ip_addr" in data:
                    return data["ip_addr"]
        except:
            continue  # 如果当前API失败，尝试下一个
    
    # 如果所有API都失败，尝试最后的手段（可能返回内网IP）
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        local_ip = s.getsockname()[0]
        s.close()
        return local_ip  # 警告：可能是内网IP
    except Exception as e:
        raise ValueError(f"所有公网IP获取方法均失败，请手动填写！最后错误: {str(e)}")



def get_hoshino_port() -> int:
    """获取当前运行的HoshinoBot实际使用的端口号"""
    try:
        # 尝试从HoshinoBot配置文件中获取端口
        from hoshino.config import __bot__ as bot_config
        port = bot_config.PORT
        print(f"ℹ️ 从HoshinoBot配置中获取到端口: {port}")
        return port
    except ImportError:
        print("⚠️ 无法导入hoshino.config.__bot__，尝试从进程获取端口")
    except AttributeError:
        print("⚠️ 配置中没有PORT属性，尝试从进程获取端口")
    
    # 如果从配置文件获取失败，回退到原来的进程检测方法
    try:
        # 获取当前进程ID
        current_pid = os.getpid()
        
        # 查找可能是HoshinoBot的Python进程
        for proc in psutil.process_iter(['pid', 'name', 'cmdline', 'connections']):
            try:
                # 排除当前进程和非Python进程
                if proc.info['pid'] == current_pid or 'python' not in proc.info['name'].lower():
                    continue
                
                # 检查命令行参数是否包含hoshino相关字样
                cmdline = ' '.join(proc.info['cmdline'] or [])
                if 'hoshino' not in cmdline.lower():
                    continue
                
                # 获取该进程监听的端口
                for conn in proc.info['connections'] or []:
                    if conn.status == 'LISTEN' and conn.laddr:
                        return conn.laddr.port
                        
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue
                
    except Exception as e:
        print(f"⚠️ 无法从进程获取端口，使用默认8040。错误: {e}")
    
    return 8040  # 默认端口

def generate_address() -> str:
    """生成 address，格式 '公网IP:端口'"""
    try:
        public_ip = get_public_ip()
        # 检查是否是明显的私有IP
        if public_ip.startswith(("10.", "172.", "192.168.")) or public_ip == "127.0.0.1":
            raise ValueError(f"获取到内网IP: {public_ip}，请检查网络配置！")
        
        port = get_hoshino_port()
        print(f"ℹ️ 检测到运行中HoshinoBot使用的端口: {port}")  # 添加调试信息
        return f"{public_ip}:{port}"
    except ValueError as e:
        print(f"❌ 错误: {e}")
        return "请手动填写公网IP:端口"  # 获取失败时的占位文本

# ===== 自动获取 address =====
address = generate_address()
print(f"ℹ️ 当前address: {address}")

# 如果获取失败，建议手动填写
if "手动填写" in address:
    print("请手动修改下方address变量为你的公网IP和端口！")

useHttps = False  # 默认HTTP

server = HttpServer(qq_mod=True)
app = nonebot.get_bot().server_app
QuartAuth(app, cookie_secure=False)
RateLimiter(app)
Compress(app)
app.secret_key = secrets.token_urlsafe(16)  # cookie expires when reboot
app.register_blueprint(server.app)

prefix = '#'

sv_help = f"""
- {prefix}配置日常 一切的开始
- {prefix}清日常 [昵称] 无昵称则默认账号
- {prefix}清日常所有 清该qq号下所有号的日常
指令格式： 命令 昵称 参数，下述省略昵称，<>表示必填，[]表示可选，|表示分割
- {prefix}日常记录 查看清日常状态
- {prefix}日常报告 [0|1|2|3] 最近四次清日常报告
- {prefix}定时日志 查看定时运行状态
- {prefix}查角色 [昵称] 查看角色练度
- {prefix}查缺角色 查看缺少的限定常驻角色
- {prefix}查ex装备 [会战] 查看ex装备库存
- {prefix}查探险编队 根据记忆碎片角色编队战力相当的队伍
- {prefix}查兑换角色碎片 [开换] 查询兑换特别角色的记忆碎片策略
- {prefix}查心碎 查询缺口心碎
- {prefix}查纯净碎片 查询缺口纯净碎片，国服六星+日服二专需求
- {prefix}查记忆碎片 [可刷取|大师币] 查询缺口记忆碎片，可按地图可刷取或大师币商店过滤
- {prefix}查装备 [<rank>] [fav] 查询缺口装备，rank为数字，只查询>=rank的角色缺口装备，fav表示只查询favorite的角色
- {prefix}刷图推荐 [<rank>] [fav] 查询缺口装备的刷图推荐，格式同上
- {prefix}公会支援 查询公会支援角色配置
- {prefix}卡池 查看当前卡池
- {prefix}半月刊
- {prefix}返钻
- {prefix}查属性练度
- {prefix}刷新box
- {prefix}查缺称号 查看缺少的称号
- {prefix}jjc透视 查前51名
- {prefix}pjjc透视 查前51名
- {prefix}jjc回刺 比如 #jjc回刺 19 2 就是打19 选择阵容2进攻
- {prefix}pjjc回刺 比如 #pjjc回刺 -1（或者不填） 就是打记录里第一条 
- {prefix}pjjc换防 将pjjc防守阵容随机错排
- {prefix}免费十连 <卡池id> 卡池id来自【{prefix}卡池】
- {prefix}来发十连 <卡池id> [抽到出] [单抽券|单抽] [编号小优先] [开抽] 赛博抽卡，谨慎使用。卡池id来自【{prefix}卡池】，[抽到出]表示抽到出货或达天井，默认十连，[单抽券]表示仅用厕纸，[单抽]表示宝石单抽，[标号小优先]指智能pickup时优先选择编号小的角色，[开抽]表示确认抽卡。已有up也可再次触发。
- {prefix}智能刷h图
- {prefix}智能刷外传
- {prefix}刷专二
- {prefix}强化ex装
- {prefix}合成ex装
- {prefix}领小屋体力
- {prefix}公会点赞
- {prefix}领每日体力
- {prefix}领取礼物箱
- {prefix}查公会深域进度
- {prefix}收菜  探险续航哦
- {prefix}一键编队 1 1 队名1 星级角色1 星级角色2 ... 星级角色5 队名2 星级角色1 星级角色2 END 设置多队编队，队伍不足5人以END结尾
- {prefix}导入编队 第几页 第几队  如 #导入编队 1 1  ，代表第一页第一队
- {prefix}识图   用于提取图中队伍
- {prefix}兑天井 卡池id 角色名 如 #兑天井 10283 火电  用 #卡池 获取ID  
- {prefix}拉角色练度 289 31 289 289 289 289 5 5 5 5 5 5 0 可可罗 佩可 凯露    代表 等级 品级 ub s1 s2 ex 左上 右上 左中 右中 左下 右下 专武 角色名
- {prefix}大富翁 [保留的骰子数量] [搬空商店为止|不止搬空商店] [到达次数]运行大富翁游戏，支持设置保留骰子数量和是否搬空商店后停止
  示例：{prefix}大富翁 30 不止搬空商店 0 | {prefix}大富翁所有 0 搬空商店为止  0（需要去批量运行里保存账号）
- {prefix}商店购买 [上期|当期] 购买大富翁商店物品，默认购买当期
  示例：{prefix}商店购买 上期 | {prefix}商店购买所有 当期 （需要去批量运行里保存账号）
- {prefix}查玩家 uid
""".strip()

if address is None:
    try:
        from hoshino.config import PUBLIC_ADDRESS

        address = PUBLIC_ADDRESS
    except:
        pass

if address is None:
    try:
        import socket

        address = socket.gethostbyname(socket.gethostname())
    except:
        pass

if address is None:
    address = "127.0.0.1"

address = ("https://" if useHttps else "http://") + address + "/daily/"

validate = ""

sv = Service(
    name="自动清日常",
    use_priv=priv.NORMAL,  # 使用权限
    manage_priv=priv.ADMIN,  # 管理权限
    visible=True,  # False隐藏
    enable_on_default=False,  # 是否默认启用
    bundle='pcr工具',  # 属于哪一类
    help_=sv_help  # 帮助文本
)

@on_startup
async def init():
    await db_start()
    from .autopcr.module.crons import queue_crons
    queue_crons()

class BotEvent:
    def __init__(self): ...
    async def finish(self, msg: str): ...
    async def send(self, msg: str): ...
    async def target_qq(self) -> str: ...
    async def group_id(self) -> str: ...
    async def send_qq(self) -> str: ...
    async def message(self) -> List[str]: ...
    async def image(self) -> List[str]: ...
    async def is_admin(self) -> bool: ...
    async def is_super_admin(self) -> bool: ...
    async def get_group_member_list(self) -> List: ...

class HoshinoEvent(BotEvent):
    def __init__(self, bot: HoshinoBot, ev: CQEvent):
        self.bot = bot
        self.ev = ev

        self.user_id = str(ev.user_id)

        self.at_sb = []
        self._message = []
        self._image = []
        for m in ev.message:
            if m.type == 'at' and m.data['qq'] != 'all':
                self.at_sb.append(str(m.data['qq']))
            elif m.type == 'text':
                self._message += m.data['text'].split()
            elif m.type == 'image':
                self._image.append(m.data['url'])

    async def get_group_member_list(self) -> List[Tuple[str, str]]: # (qq, nick_name)
        members = await self.bot.get_group_member_list(group_id=self.ev.group_id)
        ret = [(str(m['user_id']), m['card'] if m['card'] else m['nickname']) for m in members]
        ret = sorted(ret, key=lambda x: x[1])
        return ret

    async def target_qq(self):
        if len(self.at_sb) > 1:
            await self.finish("只能指定一个用户")

        return self.at_sb[0] if self.at_sb else str(self.user_id)
    
    async def send_qq(self):
        return self.user_id

    async def message(self):
        return self._message

    async def image(self):
        return self._image

    async def send(self, msg: str):
        msg = f"[CQ:reply,id={self.ev.message_id}]{msg}"
        await self.bot.send(self.ev, msg)

    async def finish(self, msg: str):
        await self.bot.finish(self.ev, msg)

    async def is_admin(self) -> bool:
        return priv.check_priv(self.ev, priv.ADMIN)

    async def is_super_admin(self) -> bool:
        return priv.check_priv(self.ev, priv.SU)

    async def group_id(self) -> str:
        return str(self.ev.group_id)

def wrap_hoshino_event(func):
    async def wrapper(bot: HoshinoBot, ev: CQEvent, *args, **kwargs):
        await func(HoshinoEvent(bot, ev), *args, **kwargs)
    wrapper.__name__ = func.__name__
    return wrapper

async def check_validate(botev: BotEvent, qq: str, cnt: int = 1):
    from .autopcr.http_server.validator import validate_dict
    for _ in range(360):
        if qq in validate_dict and validate_dict[qq]:
            validate = validate_dict[qq].pop()
            status = validate.status
            if status == "ok":
                del validate_dict[qq]
                cnt -= 1
                if not cnt: break
                continue

            url = validate.url
            url = address + url.lstrip("/daily/")
            
            msg=f"pcr账号登录需要验证码，请点击以下链接在120秒内完成认证:\n{url}"
            await botev.send(msg)

        else:
            await asyncio.sleep(1)

async def is_valid_qq(qq: str):
    qq = str(qq)
    groups = (await sv.get_enable_groups()).keys()
    bot = nonebot.get_bot()
    if qq.startswith("g"):
        gid = qq.lstrip('g')
        return gid.isdigit() and int(gid) in groups
    else:
        for group in groups:
            try:
                async for member in await bot.get_group_member_list(group_id=group):
                    if qq == str(member['user_id']):
                        return True
            except:
                for member in await bot.get_group_member_list(group_id=group):
                    if qq == str(member['user_id']):
                        return True
        return False

def check_final_args_be_empty(func):
    async def wrapper(botev: BotEvent, *args, **kwargs):
        msg = await botev.message()
        if msg:
            await botev.finish("未知的参数：【" + " ".join(msg) + "】")
        await func(botev, *args, **kwargs)
    wrapper.__name__ = func.__name__
    return wrapper

from dataclasses import dataclass
@dataclass
class ToolInfo:
    key: str
    config_parser: Callable[..., Coroutine[Any, Any, Any]]

tool_info: Dict[str, ToolInfo]= {}

def register_tool(name: str, key: str):
    def wrapper(func):
        tool_info[name] = ToolInfo(key=key, config_parser=func)
        async def inner(*args, **kwargs):
            await func(*args, **kwargs)

        inner.__name__ = func.__name__
        return inner
    return wrapper

def wrap_accountmgr(func):
    async def wrapper(botev: BotEvent, *args, **kwargs):
        target_qq = await botev.target_qq()
        sender_qq = await botev.send_qq()

        if sender_qq != target_qq and not await botev.is_admin():
            await botev.finish("只有管理员可以操作他人账号")

        if target_qq not in usermgr.qids():
            await botev.finish(f"未找到{target_qq}的账号，请在群里发送  清日常创建")

        async with usermgr.load(target_qq, readonly=True) as accmgr:
            await func(botev = botev, accmgr = accmgr, *args, **kwargs)

    wrapper.__name__ = func.__name__
    return wrapper

def wrap_account(func):
    async def wrapper(botev: BotEvent, accmgr: AccountManager, *args, **kwargs):
        msg = await botev.message()

        alias = msg[0] if msg else ""

        if alias == '所有':
            alias = BATCHINFO
            del msg[0]
        elif alias not in accmgr.accounts():
            alias = accmgr.default_account
        else:
            del msg[0]

        if alias != BATCHINFO and len(list(accmgr.accounts())) == 1:
            alias = list(accmgr.accounts())[0]

        if alias != BATCHINFO and alias not in accmgr.accounts():
            if alias:
                await botev.finish(f"未找到昵称为【{alias}】的账号")
            else:
                await botev.finish(f"存在多账号且未找到默认账号，请指定昵称")

        async with accmgr.load(alias) as acc:
            await func(botev = botev, acc = acc, *args, **kwargs)

    wrapper.__name__ = func.__name__
    return wrapper

def wrap_group(func):
    async def wrapper(botev: BotEvent, *args, **kwargs):
        msg = await botev.message()
        command = msg[0] if msg else ""

        if command.startswith("群"):
            if not await botev.is_admin():
                await botev.finish("仅管理员可以操作群帐号")
            async def new_qq():
                return "g" + str(await botev.group_id())
            botev.target_qq = new_qq
            msg[0] = msg[0].lstrip("群")

        await func(botev = botev, *args, **kwargs)

    wrapper.__name__ = func.__name__
    return wrapper

def wrap_tool(func):
    async def wrapper(botev: BotEvent, *args, **kwargs):
        msg = await botev.message()
        tool = msg[0] if msg else ""

        for tool_name in tool_info:
            if tool.startswith(tool_name):
                tool = tool_name
                msg[0] = msg[0].lstrip(tool_name)
                if not msg[0]:
                    del msg[0]
                break
        else:
            await botev.finish(f"未找到工具【{tool}，请发送#帮助】")

        tool = tool_info[tool]

        await func(botev = botev, tool = tool, *args, **kwargs)

    wrapper.__name__ = func.__name__
    return wrapper

def wrap_config(func):
    async def wrapper(botev: BotEvent, tool: ToolInfo, *args, **kwargs):
        config = await tool.config_parser(botev)
        await func(botev = botev, tool = tool, config = config, *args, **kwargs)

    wrapper.__name__ = func.__name__
    return wrapper

def require_super_admin(func):
    async def wrapper(botev: BotEvent, *args, **kwargs):
        if await botev.target_qq() != await botev.send_qq() and not await botev.is_super_admin():
            await botev.finish("仅超级管理员调用他人")
        else:
            return await func(botev = botev, *args, **kwargs)

    wrapper.__name__ = func.__name__
    return wrapper

@sv.on_fullmatch(["帮助自动清日常", f"{prefix}帮助"])
@wrap_hoshino_event
async def bangzhu_text(botev: BotEvent):
    msg = outp_b64(await drawer.draw_msgs(sv_help.split("\n")))
    await botev.finish(msg)

@sv.on_fullmatch(f"{prefix}清日常所有")
@wrap_hoshino_event
@wrap_accountmgr
async def clean_daily_all(botev: BotEvent, accmgr: AccountManager):
    loop = asyncio.get_event_loop()
    task = []
    alias = []
    is_admin_call = await botev.is_admin()
    async def clean_daily_pre(alias: str):
        async with accmgr.load(alias) as acc:
            return await acc.do_daily(is_admin_call)

    for acc in accmgr.accounts():
        alias.append(escape(acc))
        task.append(loop.create_task(clean_daily_pre(acc)))

    try:
        alias_str = ','.join(alias)
        await botev.send(f"开始为{alias_str}清理日常")
    except Exception as e:  
        logger.exception(e)

    loop = asyncio.get_event_loop()
    loop.create_task(check_validate(botev, accmgr.qid, len(alias)))

    resps: List[TaskResultInfo] = await asyncio.gather(*task, return_exceptions=True)
    header = ["昵称", "清日常结果", "状态"]
    content = []
    for i, daily_result in enumerate(resps):
        if not isinstance(daily_result, Exception):
            content.append([alias[i], daily_result.get_result().get_last_result().log, "#" + daily_result.status.value])
        else:
            content.append([alias[i], str(daily_result), "#" + eResultStatus.ERROR.value])
    img = await drawer.draw(header, content)

    msg = outp_b64(img)
    await botev.send(msg)

@sv.on_fullmatch(f"{prefix}查禁用")
@wrap_hoshino_event
async def query_clan_battle_forbidden(botev: BotEvent):
    if not await botev.is_admin():
        await botev.finish("仅管理员可以调用")

    content = ["会战期间仅管理员调用"]
    for qq in usermgr.qids():
        async with usermgr.load(qq, readonly=True) as accmgr:
            for alias in accmgr.accounts():
                async with accmgr.load(alias, readonly=True) as acc:
                    if acc.is_clan_battle_forbidden():
                        content.append(f"{acc.qq}  {acc.alias} ")
    img = outp_b64(await drawer.draw_msgs(content))
    await botev.finish(img)

@sv.on_fullmatch(f"{prefix}查群禁用")
@wrap_hoshino_event
async def query_group_clan_battle_forbidden(botev: BotEvent):
    if not await botev.is_admin():
        await botev.finish("仅管理员可以调用")

    content = []
    header = ["昵称", "QQ", "账号", "会战调用"]
    members = await botev.get_group_member_list()
    for qq, name in members:
        if qq in usermgr.qids():
            async with usermgr.load(qq, readonly=True) as accmgr:
                for alias in accmgr.accounts():
                    async with accmgr.load(alias, readonly=True) as acc:
                        msg = "仅限管理员" if acc.is_clan_battle_forbidden() else ""
                        content.append([name, qq, alias, msg])
        else:
            content.append([name, qq, "" ,""])
    img = outp_b64(await drawer.draw(header, content))
    await botev.finish(img)

@sv.on_fullmatch(f"{prefix}查内鬼")
@wrap_hoshino_event
async def find_ghost(botev: BotEvent):
    msg = []
    for qq in usermgr.qids():
        if not await is_valid_qq(qq):
            msg.append(qq)
    if not msg:
        msg.append("未找到内鬼")
    await botev.finish(" ".join(msg))

@sv.on_fullmatch(f"{prefix}清内鬼")
@wrap_hoshino_event
async def clean_ghost(botev: BotEvent):
    msg = []
    for qq in usermgr.qids():
        if not await is_valid_qq(qq):
            msg.append(qq)
    if not msg:
        msg.append("未找到内鬼")
    else:
        for qq in msg:
            usermgr.delete(qq)
        msg = [f"已清除{len(msg)}个内鬼:"] + msg
    await botev.finish(" ".join(msg))

@sv.on_prefix(f"{prefix}清日常")
@wrap_hoshino_event
@wrap_accountmgr
@wrap_account
@check_final_args_be_empty
async def clean_daily_from(botev: BotEvent, acc: Account):
    alias = escape(acc.alias)
    try:
        await botev.send(f"开始为{alias}清理日常")
    except Exception as e:  
        logger.exception(e)

    try:
        is_admin_call = await botev.is_admin()

        loop = asyncio.get_event_loop()
        loop.create_task(check_validate(botev, acc.qq))

        res = await acc.do_daily(is_admin_call)
        resp = res.get_result()
        img = await drawer.draw_tasks_result(resp)
        msg = f"{alias}"
        msg += outp_b64(img)
        await botev.send(msg)
    except Exception as e:
        await botev.send(f'{alias}: {e}')

@sv.on_prefix(f"{prefix}日常报告")
@wrap_hoshino_event
@wrap_accountmgr
@wrap_account
async def clean_daily_result(botev: BotEvent, acc: Account):
    result_id = 0
    msg = await botev.message()
    try:
        result_id = int(msg[0])
        del msg[0]
    except Exception as e:
        pass
    resp = await acc.get_daily_result_from_id(result_id)
    if not resp:
        await botev.finish("未找到日常报告")
    img = await drawer.draw_tasks_result(resp)
    await botev.finish(outp_b64(img))

@sv.on_prefix(f"{prefix}日常记录")
@wrap_hoshino_event
@wrap_accountmgr
async def clean_daily_time(botev: BotEvent, accmgr: AccountManager):
    content = []
    for alias in accmgr.accounts():
        async with accmgr.load(alias, readonly=True) as acc:
            content += [[acc.alias, daily_result.time, "#" + daily_result.status.value] for daily_result in acc.get_daily_result_list()]

    if not content:
        await botev.finish("暂无日常记录")
    header = ["昵称", "清日常时间", "状态"]
    img = outp_b64(await drawer.draw(header, content))
    await botev.finish(img)

@sv.on_prefix(f"{prefix}定时日志")
@wrap_hoshino_event
async def cron_log(botev: BotEvent):
    from .autopcr.module.crons import CRONLOG_PATH, CronLog
    with open(CRONLOG_PATH, 'r') as f:
        msg = [CronLog.from_json(line.strip()) for line in f.readlines()]
    args = await botev.message()
    cur = datetime.datetime.now()
    if is_args_exist(args, '错误'):
        msg = [log for log in msg if log.status == eResultStatus.ERROR]
    if is_args_exist(args, '警告'):
        msg = [log for log in msg if log.status == eResultStatus.WARNING]
    if is_args_exist(args, '成功'):
        msg = [log for log in msg if log.status == eResultStatus.SUCCESS]
    if is_args_exist(args, '昨日'):
        cur -= datetime.timedelta(days=1)
        msg = [log for log in msg if log.time.date() == cur.date()]
    if is_args_exist(args, '今日'):
        msg = [log for log in msg if log.time.date() == cur.date()]

    msg = msg[-40:]
    msg = msg[::-1]
    msg = [str(log) for log in msg]
    if not msg:
        msg.append("暂无定时日志")
    img = outp_b64(await drawer.draw_msgs(msg))
    await botev.finish(img)

@sv.on_prefix(f"{prefix}定时状态")
@wrap_hoshino_event
async def cron_status(botev: BotEvent):
    from .autopcr.module.crons import CRONLOG_PATH, CronLog, eCronOperation
    with open(CRONLOG_PATH, 'r') as f:
        logs = [CronLog.from_json(line.strip()) for line in f.readlines()]
    cur = datetime.datetime.now()
    msg = await botev.message()
    if is_args_exist(msg, '昨日'):
        cur -= datetime.timedelta(days=1)
    start_logs = [log for log in logs if log.operation == eCronOperation.START and log.time.date() == cur.date()]
    finish_logs = [log for log in logs if log.operation == eCronOperation.FINISH and log.time.date() == cur.date()]
    status = Counter([log.status for log in finish_logs])
    msg = [f'今日定时任务：启动{len(start_logs)}个，完成{len(finish_logs)}个'] 
    msg += [f"{k.value}: {v}" for k, v in status.items()]
    # notice = [log for log in logs if log.status != eResultStatus.SUCCESS]
    # if notice:
        # msg += [""]
        # msg += [str(log) for log in notice]
    img = outp_b64(await drawer.draw_msgs(msg))
    await botev.finish(img)

@sv.on_prefix(f"{prefix}定时统计")
@wrap_hoshino_event
async def cron_statistic(botev: BotEvent):
    cnt_clanbattle = Counter()
    cnt = Counter()
    for qq in usermgr.qids():
        async with usermgr.load(qq, readonly=True) as accmgr:
            for alias in accmgr.accounts():
                async with accmgr.load(alias, readonly=True) as acc:
                    for i in range(1,5):
                        suf = f"cron{i}"
                        if acc.data.config.get(suf, False):
                            time = acc.data.config.get(f"time_{suf}", "00:00")
                            if time.count(":") == 2:
                                time = ":".join(time.split(":")[:2])
                            cnt[time] += 1
                            if acc.data.config.get(f"clanbattle_run_{suf}", False):
                                cnt_clanbattle[time] += 1

    content = [[k, str(v), str(cnt_clanbattle[k])] for k, v in cnt.items()]
    content = sorted(content, key=lambda x: x[0])
    content.append(["总计", str(sum(cnt.values())), str(sum(cnt_clanbattle.values()))])
    header = ["时间", "定时任务数", "公会战任务数"]

    img = outp_b64(await drawer.draw(header, content))
    await botev.finish(img)

@sv.on_fullmatch(f"{prefix}配置日常")
@wrap_hoshino_event
async def config_clear_daily(botev: BotEvent):
    await botev.finish(address + "login")


async def send_llonebot_forward(botev, alias: str, content: str):
    """
    LLOneBot专用合并转发函数（修正版，固定3段，每段34行）
    参数:
        botev: 事件对象
        alias: 显示名称
        content: 要发送的内容
    """
    try:
        # 1. 安全获取所有必要参数
        bot = getattr(botev, 'bot', None)
        if not bot:
            raise ValueError("无法获取bot实例")

        # 获取机器人ID（带默认值）
        bot_id = str(getattr(bot, 'self_id', '10000'))

        # 安全获取source_id（处理协程、方法和属性三种情况）
        async def safe_get_id(attr_name: str) -> int:
            attr = getattr(botev, attr_name, None)
            if attr is None:
                return None
            if inspect.iscoroutinefunction(attr):  # 协程函数
                try:
                    result = await attr()
                    return int(result)
                except Exception as e:
                    logger.error(f"获取{attr_name}失败(协程): {str(e)}")
                    return None
            elif callable(attr):  # 普通方法
                try:
                    return int(attr())
                except Exception as e:
                    logger.error(f"获取{attr_name}失败(方法): {str(e)}")
                    return None
            else:  # 普通属性
                try:
                    return int(attr)
                except Exception as e:
                    logger.error(f"获取{attr_name}失败(属性): {str(e)}")
                    return None

        # 优先尝试获取群号，失败则获取用户QQ号
        group_id = await safe_get_id('group_id')
        user_id = await safe_get_id('user_id')
        source_id = group_id or user_id
        if not source_id:
            raise ValueError("无法获取消息来源ID")

        message_type = "group" if group_id else "private"

        # 2. 分割内容为3段，每段34行
        lines = str(content).splitlines()
        total_lines = len(lines)
        chunk_size = 34  # 每段34行
        num_chunks = 3  # 分成3段

        # 计算实际分段（如果总行数不足，则按实际行数分割）
        messages = []
        for i in range(num_chunks):
            start = i * chunk_size
            end = (i + 1) * chunk_size if (i + 1) * chunk_size <= total_lines else total_lines
            chunk = lines[start:end]
            if not chunk:  # 如果最后一段是空的，跳过
                continue
            messages.append({
                "type": "node",
                "data": {
                    "name": str(alias),
                    "uin": bot_id,
                    "content": "\n".join(chunk).strip()
                }
            })

        # 3. 发送消息
        if message_type == "group":
            await bot.send_group_forward_msg(
                group_id=int(source_id),
                messages=messages
            )
        else:
            for msg in messages:
                await bot.send_private_msg(
                    user_id=int(source_id),
                    message=msg["data"]["content"]
                )
                await asyncio.sleep(0.5)  # 防止消息速率限制
                
    except Exception as e:
        logger.error(f"合并转发失败: {str(e)}")
        # 降级为普通消息发送
        try:
            # 直接发送原始内容，分成3段
            lines = str(content).splitlines()
            total_lines = len(lines)
            chunk_size = 34
            num_chunks = 3

            for i in range(num_chunks):
                start = i * chunk_size
                end = (i + 1) * chunk_size if (i + 1) * chunk_size <= total_lines else total_lines
                chunk = lines[start:end]
                if not chunk:
                    continue
                await botev.send("\n".join(chunk).strip())
                await asyncio.sleep(0.5)
        except Exception as fallback_error:
            logger.error(f"降级发送也失败: {str(fallback_error)}")

@sv.on_prefix(f"{prefix}")
@wrap_hoshino_event
@wrap_group
@wrap_tool
@wrap_accountmgr
@wrap_account
@wrap_config
@check_final_args_be_empty
async def tool_used(botev: CQEvent, tool, config: Dict[str, str], acc):
    """
    任务执行主函数
    参数:
        botev: CQEvent事件对象
        tool: 工具对象
        config: 配置字典
        acc: 账号对象
    """
    alias = getattr(acc, 'alias', '未知账号')
    try:
        # 原有逻辑（任务执行）
        loop = asyncio.get_event_loop()
        loop.create_task(check_validate(botev, getattr(acc, 'qq', '')))
        
        is_admin_call = await botev.is_admin()
        resp = await acc.do_from_key(config, getattr(tool, 'key', ''), is_admin_call)
        if isinstance(resp, List):
            resp = resp[0]
        resp = resp.get_result()

        # 仅对查公会深域进度工具生成图片
        if tool.key == "find_clan_talent_quest":
            # 生成深域进度图片
            img = await drawer.draw_task_result(resp)
            msg = f"{alias}"
            msg += outp_b64(img)
            await botev.send(msg)
        else:
            # 其他工具保持原有文本处理逻辑
            result_text = str(resp.log) if hasattr(resp, 'log') else str(resp)
            result_text = result_text.replace('\\n', '\n').replace('\n', '\n')
            await send_llonebot_forward(botev, alias, result_text)

    except Exception as e:
        error_msg = f"{alias} 任务执行失败（如果是指令+所有必须去网站-批量运行-BATCH_RUNNER 里保存队伍）：{str(e)[:500]}"
        try:
            await botev.send(error_msg)
        except:
            logger.error("发送错误消息失败")

@sv.on_fullmatch(f"{prefix}卡池")
@wrap_hoshino_event
async def gacha_current(botev: BotEvent):
    msg = '\n'.join(db.get_mirai_gacha())
    await botev.send("请稍等")
    await botev.finish(msg)

def is_args_exist(msg: List[str], key: str):
    if key in msg:
        msg.remove(key)
        return True
    return False

@register_tool("公会支援", 'get_clan_support_unit')
async def clan_support(botev: BotEvent):
    await botev.send("请稍等")
    return {}

@register_tool("查心碎", "get_need_xinsui")
async def find_xinsui(botev: BotEvent):
    return {}

@register_tool("jjc回刺", "jjc_back")
async def jjc_back(botev: BotEvent):
    msg = await botev.message()
    await botev.send("请稍等")
    opponent_jjc_rank = -1
    opponent_jjc_attack_team_id = 1
    try:
        opponent_jjc_rank = int(msg[0])
        del msg[0]
    except:
        pass
    try:
        opponent_jjc_attack_team_id = int(msg[0])
        del msg[0]
    except:
        pass
    config = {
        "opponent_jjc_rank": opponent_jjc_rank,
        "opponent_jjc_attack_team_id": opponent_jjc_attack_team_id,
    }
    return config
    
@register_tool("一键编队", "set_my_party")
async def set_my_party(botev: BotEvent):
    msg = await botev.message()
    await botev.send("请稍等")
    party_start_num = 1
    tab_start_num = 1
    try:
        tab_start_num = int(msg[0])
        del msg[0]
    except:
        pass
    try:
        party_start_num = int(msg[0])
        del msg[0]
    except:
        pass
    unknown_units = []
    token = []
    while True:
        if not msg:
            break
        if get_id_from_name(msg[0]) or msg[0].isdigit() and get_id_from_name(msg[0][1:]):
            title = "自定义编队"
        else:
            title = msg[0]
            del msg[0]
        units = []
        stars = []
        for _ in range(5):
            try:
                unit_name = msg[0]
                if msg[0] == "END":
                    del msg[0]
                    break

                unit = get_id_from_name(unit_name)
                if unit:
                    units.append(unit)
                    stars.append(6 if unit*100+1 in db.unit_to_pure_memory else 5)
                else:
                    if unit_name[0].isdigit():
                        star = int(unit_name[0])
                        unit = get_id_from_name(unit_name[1:])
                        if unit:
                            units.append(unit)
                            stars.append(star)
                        else:
                            unknown_units.append(unit_name)
                    else:
                        unknown_units.append(unit_name)
                del msg[0]
            except:
                pass
        token.append( (title, units, stars) )

    if unknown_units:
        await botev.finish(f"未知昵称{', '.join(unknown_units)}")
    if not token:
        await botev.finish("无法识别任何编队")
    set_my_party_text = "\n".join(
        f"{title}\n" + "\n".join(f"{unit * 100 + 1}\t{db.get_unit_name(unit*100+1)}\t1\t{star}" for unit, star in zip(units, stars))
        for title, units, stars in token)
    config = {
        "tab_start_num": tab_start_num,
        "party_start_num": party_start_num,
        "set_my_party_text": set_my_party_text,
    }
    return config
 
@register_tool("导入编队", "set_my_party")
async def set_my_party(botev: BotEvent):
    msg = await botev.message()
    await botev.send("请稍等")
    party_start_num = 1
    tab_start_num = 1
    try:
        tab_start_num = int(msg[0])
        del msg[0]
    except:
        pass
    try:
        party_start_num = int(msg[0])
        del msg[0]
    except:
        pass
    units = []
    unknown_units = []
    for _ in range(5):
        try:
            unit_name = msg[0]
            unit = get_id_from_name(unit_name)
            if unit:
                units.append(unit)
            else:
                unknown_units.append(unit_name)
            del msg[0]
        except:
            pass
    if unknown_units:
        await botev.finish(f"未知昵称{', '.join(unknown_units)}")
    config = {
        "tab_start_num": tab_start_num,
        "party_start_num": party_start_num,
    }
    return config


@sv.on_prefix(f"{prefix}识图")
@wrap_hoshino_event
async def ocr_team(botev: BotEvent):
    try:
        from hoshino.modules.priconne.arena import getBox, get_pic
    except ImportError:
        try:
            from hoshino.modules.priconne.arena.old_main import getBox, get_pic
        except ImportError:
            await botev.finish("未安装怎么拆截图版，无法使用识图")
            return

    img_urls = await botev.image()
    if not img_urls:
        await botev.finish("未识别到图片!")

    result = []
    for id, img_url in enumerate(img_urls):
        try:
            image = Image.open(BytesIO(await get_pic(img_url)))
        except Exception as e:
            await botev.send(f"图片{id+1}下载失败: {e}")
            continue
        box, s = await getBox(image)
        await botev.send(f"图片{id+1}识别结果: {s}")
        if not box:
            await botev.send(f"图片{id+1}未识别到任何队伍！")
            continue
        result += box

    if not result:
        await botev.finish("未识别到任何队伍！")

    msg = f"{prefix}一键编队 4 1\n" + "\n".join(
            f"队伍{id+1} {' '.join(db.get_unit_name(uid * 100 + 1) for uid in team)}{' END' if len(team) < 5 else ''}"
            for id, team in enumerate(result)
    )
    await botev.finish(msg)

@register_tool("pjjc回刺", "pjjc_back")
async def pjjc_back(botev: BotEvent):
    msg = await botev.message()
    await botev.send("请稍等")
    opponent_pjjc_rank = -1
    opponent_pjjc_attack_team_id = 1
    try:
        opponent_pjjc_rank = int(msg[0])
        del msg[0]
    except:
        pass
    try:
        opponent_pjjc_attack_team_id = int(msg[0])
        del msg[0]
    except:
        pass
    config = {
        "opponent_pjjc_rank": opponent_pjjc_rank,
        "opponent_pjjc_attack_team_id": opponent_pjjc_attack_team_id,
    }
    return config

@register_tool("jjc透视", "jjc_info")
async def jjc_info(botev: BotEvent):
    use_cache = True
    msg = await botev.message()
    await botev.send("请稍等")
    try:
        use_cache = not is_args_exist(msg, 'flush')
    except:
        pass
    config = {
        "jjc_info_cache": use_cache,
    }
    return config

@register_tool("pjjc透视", "pjjc_info")
async def pjjc_info(botev: BotEvent):
    use_cache = True
    msg = await botev.message()
    await botev.send("请稍等")
    try:
        use_cache = not is_args_exist(msg, 'flush')
    except:
        pass
    config = {
        "pjjc_info_cache": use_cache,
    }
    return config

@register_tool("查记忆碎片", "get_need_memory")
async def find_memory(botev: BotEvent):
    memory_demand_consider_unit = '所有'
    msg = await botev.message()
    await botev.send("请稍等")
    try:
        if is_args_exist(msg, '可刷取'):
            memory_demand_consider_unit = '地图可刷取'
        elif is_args_exist(msg, '大师币'):
            memory_demand_consider_unit = '大师币商店'
    except:
        pass
    config = {
        "memory_demand_consider_unit": memory_demand_consider_unit,
    }
    return config

@register_tool("查纯净碎片", "get_need_pure_memory")
async def find_pure_memory(botev: BotEvent):
    await botev.send("请稍等")
    return {}

@register_tool("返钻", "return_jewel")
async def return_jewel(botev: BotEvent):
    return {}

@register_tool(f"来发十连", "gacha_start")
@require_super_admin
async def shilian(botev: BotEvent):
    await botev.send("请稍等")
    cc_until_get = False
    pool_id = ""
    really_do = False
    single_ticket = False
    single = False
    small_first = False
    msg = await botev.message()
    try:
        pool_id = msg[0]
        del msg[0]
    except:
        pass

    try:
        cc_until_get = is_args_exist(msg, '抽到出')
    except:
        pass

    try:
        really_do = is_args_exist(msg, '开抽')
    except:
        pass

    try:
        single_ticket = is_args_exist(msg, '单抽券')
    except:
        pass

    try:
        single = is_args_exist(msg, '单抽')
    except:
        pass

    try:
        small_first = is_args_exist(msg, '编号小优先')
    except:
        pass

    current_gacha = {gacha.split(':')[0]: gacha for gacha in db.get_cur_gacha()}

    if pool_id not in current_gacha:
        await botev.finish(f"未找到该卡池{pool_id}")

    pool_id = current_gacha[pool_id]

    if single_ticket and single:
        await botev.finish("单抽券和单抽只能选一个")

    gacha_method = "十连"
    if single_ticket:
        gacha_method = "单抽券"
    elif single:
        gacha_method = "单抽"

    if not really_do:
        msg = f"卡池{pool_id}\n"
        if cc_until_get:
            msg += "抽到出\n"
        if small_first:
            msg += "编号小优先\n"
        msg += f"{gacha_method}\n"
        msg += "确认无误，消息末尾加上【开抽】即可开始抽卡"
        await botev.finish(msg)

    config = {
        "pool_id": pool_id,
        "cc_until_get": cc_until_get,
        "gacha_method": gacha_method,
        "gacha_start_auto_select_pickup_min_first": small_first,
    }
    return config

@register_tool(f"查装备", "get_need_equip")
async def find_equip(botev: BotEvent):
    await botev.send("请稍等")
    like_unit_only = False
    start_rank = None
    msg = await botev.message()
    try:
        like_unit_only = is_args_exist(msg, 'fav')
    except:
        pass

    try:
        start_rank = int(msg[0])
        del msg[0]
    except:
        pass


    config = {
        "start_rank": start_rank,
        "like_unit_only": like_unit_only
    }
    return config

@register_tool(f"刷图推荐", "get_normal_quest_recommand")
async def quest_recommand(botev: BotEvent):
    await botev.send("请稍等")
    like_unit_only = False
    start_rank = None
    msg = await botev.message()
    try:
        like_unit_only = is_args_exist(msg, 'fav')
    except:
        pass
    try:
        start_rank = int(msg[0])
        del msg[0]
    except:
        pass

    config = {
        "start_rank": start_rank,
        "like_unit_only": like_unit_only
    }
    return config


@register_tool("pjjc换防", "pjjc_def_shuffle_team")
async def pjjc_def_shuffle_team(botev: BotEvent):
    await botev.send("请稍等")
    return {}

@register_tool("pjjc换攻", "pjjc_atk_shuffle_team")
async def pjjc_atk_shuffle_team(botev: BotEvent):
    await botev.send("请稍等")
    return {}
    
@register_tool("查玩家", "query_player_profile")
async def query_player_profile(botev: BotEvent):
    await botev.send("请稍等")
    msg = await botev.message()
    target_viewer_id = ""
    try:
        target_viewer_id = msg[0]
        del msg[0]
    except:
        await botev.finish("请输入玩家ID")
    
    if not target_viewer_id.isdigit():
        await botev.finish("玩家ID必须是数字")
    
    config = {
        "target_viewer_id": target_viewer_id
    }
    return config
    
@register_tool("查缺角色", "missing_unit")
async def find_missing_unit(botev: BotEvent):
    await botev.send("请稍等")
    return {}

@register_tool("查缺称号", "missing_emblem")
async def find_missing_emblem(botev: BotEvent):
    await botev.send("请稍等")
    return {}

@register_tool("合成ex装", "ex_equip_rank_up")
async def ex_equip_rank_up(botev: BotEvent):
    await botev.send("请稍等")
    return {}

@register_tool("强化ex装", "ex_equip_enhance_up")
async def ex_equip_enhance_up(botev: BotEvent):
    await botev.send("请稍等")
    return {}

@register_tool("查角色", "search_unit")
async def search_box(botev: BotEvent):
    await botev.send("请稍等")
    msg = await botev.message()
    unit = None
    unit_name = ""
    try:
        unit_name = msg[0]
        unit = get_id_from_name(unit_name)
        del msg[0]
    except:
        pass

    if unit:
        unit = unit * 100 + 1;
        return {
            "search_unit_id": unit
        }
    else:
        await botev.finish(f"未知昵称{unit_name}")

@register_tool("刷新box", "refresh_box")
async def refresh_box(botev: BotEvent):
    await botev.send("请稍等")
    return {}

@register_tool("查探险编队", "travel_team_view")
async def find_travel_team_view(botev: BotEvent):
    await botev.send("请稍等")
    return {}

@register_tool("查ex装备", "ex_equip_info")
async def ex_equip_info(botev: BotEvent):
    await botev.send("请稍等")
    ex_equip_info_cb_only = False
    msg = await botev.message()
    try:
        ex_equip_info_cb_only = is_args_exist(msg, '会战')
    except:
        pass
    config = {
        "ex_equip_info_cb_only": ex_equip_info_cb_only
    }
    return config

@register_tool("查兑换角色碎片", "redeem_unit_swap")
async def redeem_unit_swap(botev: BotEvent):
    await botev.send("请稍等")
    really_do = False
    msg = await botev.message()
    try:
        really_do = is_args_exist(msg, '开换')
    except:
        pass
    config = {
        "redeem_unit_swap_do": really_do
    }
    return config

@register_tool("查公会深域进度", "find_clan_talent_quest")
async def find_clan_talent_quest(botev: BotEvent):
    await botev.send("请稍等")
    return {}


@register_tool("兑天井", "gacha_exchange_chara")
async def gacha_exchange_chara(botev: BotEvent):
    await botev.send("请稍等")
    msg = await botev.message()
    gacha_id = ""
    unit_name = ""
    try:
        gacha_id = msg[0]
        del msg[0]
    except:
        pass
    try:
        unit_name = msg[0]
        del msg[0]
    except:
        pass

    current_gacha = {gacha.split(':')[0]: gacha for gacha in db.get_cur_gacha()}

    if gacha_id not in current_gacha:
        await botev.finish(f"未找到该卡池{gacha_id}")

    unit = get_id_from_name(unit_name)
    if not unit:
        await botev.finish(f"未知角色名{unit_name}")

    config = {
        "gacha_exchange_pool_id": current_gacha[gacha_id],
        "gacha_exchange_unit_id": unit * 100 + 1
    }
    return config

@register_tool("半月刊", "half_schedule")
async def half_schedule(botev: BotEvent):
    await botev.send("请稍等")
    return {}

@register_tool("免费十连", "free_gacha")
async def free_gacha(botev: BotEvent):
    await botev.send("请稍等")
    msg = await botev.message()
    gacha_id = 0
    try:
        gacha_id = int(msg[0])
        del msg[0]
    except:
        pass
    config = {
        "free_gacha_select_ids": [gacha_id],
        "today_end_gacha_no_do": False,
    }
    return config

# @register_tool("智能刷n图", "smart_normal_sweep")
# async def smart_normal_swee(botev: BotEvent):
    # await botev.send("请稍等")
    # msg = await botev.message()
    # config = {
        # "normal_sweep_strategy": "刷最缺",
        # "normal_sweep_quest_scope": "全部",
        # "normal_sweep_consider_unit": "所有",
        # "normal_sweep_consider_unit_fav": True,
        # "normal_sweep_equip_ok_to_full": True
    # }
    
    # try:
        # if is_args_exist(msg, '新开图'):
            # normal_sweep_quest_scope = '新开图'
        # elif is_args_exist(msg, '可扫荡'):
            # normal_sweep_quest_scope = '可扫荡'
    # except:
        # pass
    # config = {
        # "normal_sweep_quest_scope": normal_sweep_quest_scope,
        # "normal_sweep_consider_unit_fav": True,
        # "normal_sweep_equip_ok_to_full": True,
    # }
    # return config
    
@register_tool("智能刷h图", "smart_hard_sweep")
async def smart_hard_sweep(botev: BotEvent):
    await botev.send("请稍等")
    return {}

@register_tool("领取礼物箱", "present_receive")
async def present_receive(botev: BotEvent):
    await botev.send("请稍等")
    return {}

@register_tool("智能刷外传", "smart_shiori_sweep")
async def smart_shiori_sweep(botev: BotEvent):
    await botev.send("请稍等")
    return {}  

@register_tool("刷专二", "mirai_very_hard_sweep")
async def mirai_very_hard_sweep(botev: BotEvent):
    await botev.send("请稍等")
    return {}    

@register_tool("领小屋体力", "room_accept_all")
async def room_accept_all(botev: BotEvent):
    await botev.send("请稍等")
    return {}  

@register_tool("公会点赞", "clan_like")
async def clan_like(botev: BotEvent):
    await botev.send("请稍等")
    return {}  

@register_tool("领每日体力", "mission_receive_first")
async def mission_receive_first(botev: BotEvent):
    await botev.send("请稍等")
    return {}  

@register_tool("收菜", "travel_quest_sweep")
async def travel_quest_sweep(botev: BotEvent):
    await botev.send("请稍等")
    return {}
    
@register_tool("查属性练度", "get_talent_info")
async def get_talent_info(botev: BotEvent):
    await botev.send("请稍等")
    return {}

@register_tool("查刀数", "clan_battle_knive")
async def clan_battle_knive(botev: BotEvent):
    await botev.send("请稍等")
    return {}

@register_tool("拉角色练度", "unit_promote")
async def unit_promote(botev: BotEvent):
    await botev.send("请稍等")
    msg = await botev.message()
    config = {
        "unit_promote_level_when_fail_to_equip_or_skill": False,
        "unit_promote_rank_when_fail_to_unique_equip": False,
        "unit_promote_rank_use_raw_ore": False,
        "unit_promote_level": 1,
        "unit_promote_rank": 1,
        "unit_promote_skill_ub": 1,
        "unit_promote_skill_s1": 1,
        "unit_promote_skill_s2": 1,
        "unit_promote_skill_ex": 1,
        "unit_promote_unique_equip1_level": 0,
        "unit_promote_equip_0": -1,
        "unit_promote_equip_1": -1,
        "unit_promote_equip_2": -1,
        "unit_promote_equip_3": -1,
        "unit_promote_equip_4": -1,
        "unit_promote_equip_5": -1,
        "unit_promote_units": []
    }
    try:
        config["unit_promote_level"] = int(msg[0])
        del msg[0]
    except:
        pass
    try:
        config["unit_promote_rank"] = int(msg[0])
        del msg[0]
    except:
        pass
    try:
        config["unit_promote_skill_ub"] = int(msg[0])
        del msg[0]
    except:
        pass
    try:
        config["unit_promote_skill_s1"] = int(msg[0])
        del msg[0]
    except:
        pass
    try:
        config["unit_promote_skill_s2"] = int(msg[0])
        del msg[0]
    except:
        pass
    try:
        config["unit_promote_skill_ex"] = int(msg[0])
        del msg[0]
    except:
        pass

    # 解析6个装备星级（左上到右下）
    equip_slots = ["unit_promote_equip_0", "unit_promote_equip_1", 
                   "unit_promote_equip_2", "unit_promote_equip_3", 
                   "unit_promote_equip_4", "unit_promote_equip_5"]
    for slot in equip_slots:
        try:
            val = int(msg[0])
            if val in [-1, 0, 1, 2, 3, 4, 5]:  # 装备星级有效范围
                config[slot] = val
            del msg[0]
        except:
            pass

    # 专武等级
    try:
        config["unit_promote_unique_equip1_level"] = int(msg[0])
        del msg[0]
    except:
        pass

    # 角色列表（参考search_unit的角色昵称处理方式）
    unknown_units = []
    while msg:
        try:
            unit_name = msg[0]
            unit = get_id_from_name(unit_name)
            if unit:
                config["unit_promote_units"].append(unit * 100 + 1)  # 转换为角色ID
            else:
                unknown_units.append(unit_name)
            del msg[0]
        except:
            break

    # 错误处理
    if unknown_units:
        await botev.finish(f"未知昵称{', '.join(unknown_units)}")
    if not config["unit_promote_units"]:
        await botev.finish("未指定任何角色")

    return config

@register_tool("大富翁", "caravan_play")
async def caravan_play(botev: BotEvent):
    msg = await botev.message()
    # 发送任务正在进行提示
    await botev.send("好的，马上进行大富翁任务")
    # 默认配置：保留0个骰子，搬空商店为止，到达终点次数0
    config = {
        "caravan_play_dice_hold_num": 0,
        "caravan_play_until_shop_empty": True,
        "caravan_play_goal_num": 0
    }
    
    try:
        # 解析参数（按顺序：保留骰子数量 -> 商店设置 -> 到达终点次数）
        # 解析保留骰子数量
        if msg and msg[0].isdigit():
            config["caravan_play_dice_hold_num"] = int(msg[0])
            msg.pop(0)
        
        # 解析是否搬空商店
        if msg and msg[0] in ["搬空商店为止", "不止搬空商店"]:
            config["caravan_play_until_shop_empty"] = (msg[0] == "搬空商店为止")
            msg.pop(0)
        
        # 解析到达终点次数（第三个参数）
        if msg and msg[0].isdigit():
            config["caravan_play_goal_num"] = int(msg[0])
            msg.pop(0)
    
    except Exception as e:
        logger.warning(f"解析大富翁参数出错: {e}")
    
    # 检查未识别参数
    if msg:
        await botev.finish(f"未知的参数：【{' '.join(msg)}】")
    
    return config


@register_tool("商店购买", "caravan_shop_buy")
async def caravan_shop_buy(botev: BotEvent):
    msg = await botev.message()
    # 发送任务正在进行提示
    await botev.send("购买中，请稍等")
    # 默认配置：购买当期商店
    config = {
        "caravan_shop_last_season": False
    }
    
    try:
        # 解析购买上期/当期商店（直接提取关键词）
        if is_args_exist(msg, "上期"):
            config["caravan_shop_last_season"] = True
        elif is_args_exist(msg, "当期"):
            config["caravan_shop_last_season"] = False
    except Exception as e:
        logger.warning(f"解析大富翁商店购买参数出错: {e}")
    
    # 检查未识别参数
    if msg:
        await botev.finish(f"未知的参数：【{' '.join(msg)}】")
    
    return config
    
# @register_tool("获取导入", "get_library_import_data")
# async def get_library_import(botev: BotEvent):
    # return {}
