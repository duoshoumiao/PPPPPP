import os
import re
import json  
import random          # 新增  
import string          # 新增
import shutil
import traceback
import requests
from hoshino import Service, priv, get_bot
from hoshino.typing import CQEvent
from nonebot import on_command, CommandSession

sv = Service(
    '清日常创建', 
    enable_on_default=False,
    help_='发送"清日常创建"初始化日常配置（自动导入桌面账号文件）\n'  
          '或发送"清日常创建 账号 密码 用户名"设置账号密码及文件名\n'  
          '发送"清日常禁用 文件夹名1 [文件夹名2...]"禁用指定文件夹的日常任务\n'  
          '发送"清日常解禁 文件夹名1 [文件夹名2...]"解禁指定文件夹的日常任务\n'  
          '发送"清日常重置密码"将登录密码重置为随机密码'
)

def get_public_ip():
    """获取本机公网 IPv4，失败返回 None（绝不返回内网 IP 冒充公网地址）。

    优先复用 server.py 里的探测实现（含手工配置、多源并发、严格校验），
    这样两条指令给出的地址始终一致。
    """
    try:
        from .server import get_public_ip as _server_get_public_ip
        return _server_get_public_ip()
    except Exception:
        pass
    # 兜底：server 模块导入失败时，仍做一次严格探测
    try:
        services = [
            'https://ip.3322.net',
            'https://myip.ipip.net',
            'https://api.ip.sb/ip',
            'https://ipv4.icanhazip.com',
        ]
        for service in services:
            try:
                response = requests.get(service, timeout=5)
                if response.status_code == 200:
                    m = re.search(r'\b((?:\d{1,3}\.){3}\d{1,3})\b', response.text)
                    if not m:
                        continue
                    ip = m.group(1)
                    import ipaddress
                    addr = ipaddress.ip_address(ip)
                    if addr.version == 4 and addr.is_global:
                        return ip
            except Exception:
                continue
    except Exception:
        pass
    return None


def build_login_url():
    """构造登录地址。**保证返回非空字符串**，并在每一步打日志。"""
    # 1. 优先用 server.py 里探测/手工配置的地址
    try:
        from .server import address, address_ok
        sv.logger.info(f'[build_login_url] server.address_ok={address_ok!r}, server.address={address!r}')
        if address_ok and address:
            addr = str(address).strip()
            if re.match(r'^https?://', addr):
                return addr.rstrip('/') + '/login'
            sv.logger.warning(f'[build_login_url] server.address 不以 http(s):// 开头: {addr!r}')
    except Exception as e:
        sv.logger.warning(f'[build_login_url] 读取 server.address 失败: {e}')

    # 2. 自己探测公网 IP
    try:
        public_ip = get_public_ip()
        sv.logger.info(f'[build_login_url] get_public_ip() = {public_ip!r}')
        if public_ip:
            return f"http://{public_ip}:8040/daily/login"
    except Exception as e:
        sv.logger.warning(f'[build_login_url] get_public_ip 异常: {e}')

    # 3. 绝对兜底：返回一段可读的错误提示
    return ("❌ 未获取到公网IP，请联系管理员在 "
            "autopcr/cache/manual_address.txt 写入公网IP后重启机器人")


def build_login_line(login_url):
    """把 URL 直接拼进文本。QQ 官方 bot API 只支持纯文本 + 图片，
    不支持 json/share 卡片段，所以 URL 必须以纯文本形式出现在消息里。
    QQ 客户端会把 http://... 自动渲染成蓝色可点击链接。"""
    if not login_url or not isinstance(login_url, str) or not login_url.strip():
        return "🌐 清日常地址: （地址暂不可用，请联系管理员）"
    return f"🌐 清日常地址: {login_url.strip()}"


def update_json_file(file_path, username, password):
    """严格只更新username和password字段，其他内容原封不动"""
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()
        original_content = content
        if '"username"' in content:
            content = re.sub(
                r'("username"\s*:\s*")[^"]*(")',
                f'\\g<1>{username}\\g<2>',
                content
            )
        else:
            content = content.replace('{', f'{{\n    "username": "{username}",', 1)
        if '"password"' in content:
            content = re.sub(
                r'("password"\s*:\s*")[^"]*(")',
                f'\\g<1>{password}\\g<2>',
                content
            )
        else:
            content = content.replace('{', f'{{\n    "password": "{password}",', 1)
        try:
            json.loads(content)
        except json.JSONDecodeError as e:
            content = original_content
            raise Exception(f"更新后JSON格式无效，已恢复原文件: {str(e)}")
        with open(file_path, 'w', encoding='utf-8', newline='') as f:
            f.write(content)
    except Exception as e:
        raise Exception(f"更新JSON文件失败: {str(e)}")


def update_secret_status(user_dirs, enable: bool):  
    """  
    批量更新secret文件的clan和disabled状态，并在禁用/解禁时备份或恢复 cron1~cron10 的开关状态。  
    """  
    result = {"success": [], "failed": []}  
    target_clan = "false" if enable else "true"  
    target_disabled = "false" if enable else "true"  
    hoshino_dir = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))  
    base_dir = os.path.join(hoshino_dir, 'modules', 'autopcr', 'cache', 'http_server')  
    cron_keys = [f'cron{i}' for i in range(1, 11)]  
  
    def replace_bool_field(content: str, key: str, value: str) -> str:  
        pattern = r'(\"%s\"\s*:\s*)(true|false)(?=\s*[,}\n])' % re.escape(key)  
        return re.sub(pattern, lambda m: m.group(1) + value, content)  
  
    for user_dir in user_dirs:  
        try:  
            secret_file = os.path.join(base_dir, user_dir, 'secret')  
            if not os.path.exists(secret_file):  
                result["failed"].append(f"{user_dir}: secret文件不存在")  
                continue  
            with open(secret_file, 'r', encoding='utf-8') as f:  
                content = f.read()  
            content = replace_bool_field(content, 'clan', target_clan)  
            content = replace_bool_field(content, 'disabled', target_disabled)  
            with open(secret_file, 'w', encoding='utf-8', newline='') as f:  
                f.write(content)  
            user_path = os.path.join(base_dir, user_dir)  
            if os.path.isdir(user_path):  
                for fn in os.listdir(user_path):  
                    if not fn.endswith('.json') or fn.endswith('.cron_backup.json'):  
                        continue  
                    account_file = os.path.join(user_path, fn)  
                    backup_file = account_file + '.cron_backup.json'  
                    try:  
                        with open(account_file, 'r', encoding='utf-8') as af:  
                            acontent = af.read()  
                        if not enable:  
                            if not os.path.exists(backup_file):  
                                cron_state = {}  
                                for key in cron_keys:  
                                    m = re.search(  
                                        r'(\"%s\"\s*:\s*)(true|false)(?=\s*[,}\n])' % re.escape(key),  
                                        acontent  
                                    )  
                                    if m:  
                                        cron_state[key] = (m.group(2) == 'true')  
                                with open(backup_file, 'w', encoding='utf-8') as bf:  
                                    json.dump(cron_state, bf, ensure_ascii=False, separators=(',', ':'))  
                            for key in cron_keys:  
                                acontent = re.sub(  
                                    r'(\"%s\"\s*:\s*)(true|false)(?=\s*[,}\n])' % re.escape(key),  
                                    lambda m: m.group(1) + 'false',  
                                    acontent  
                                )  
                        else:  
                            if not os.path.exists(backup_file):  
                                raise FileNotFoundError(f"{backup_file} 不存在，无法恢复 cron 状态")  
                            try:  
                                with open(backup_file, 'r', encoding='utf-8') as bf:  
                                    cron_state = json.load(bf)  
                                for key in cron_keys:  
                                    if key in cron_state:  
                                        raw = cron_state[key]  
                                        if isinstance(raw, str):  
                                            value = 'true' if raw.lower() == 'true' else 'false'  
                                        else:  
                                            value = 'true' if raw else 'false'  
                                        acontent = re.sub(  
                                            r'(\"%s\"\s*:\s*)(true|false)(?=\s*[,}\n])' % re.escape(key),  
                                            lambda m, v=value: m.group(1) + v,  
                                            acontent  
                                        )  
                            finally:  
                                if os.path.exists(backup_file):  
                                    os.remove(backup_file)  
                        with open(account_file, 'w', encoding='utf-8', newline='') as af:  
                            af.write(acontent)  
                    except Exception as ce:  
                        result["failed"].append(f"{user_dir}/{fn}: {str(ce)}")  
            result["success"].append(user_dir)  
        except Exception as e:  
            result["failed"].append(f"{user_dir}: {str(e)}")  
    return result


def reset_secret_password(secret_file):
    """重置secret文件中的password字段为123456789，default_account字段为空字符串"""
    try:
        with open(secret_file, 'r', encoding='utf-8') as f:
            content = f.read()
        secret_data = json.loads(content)
        secret_data['password'] = '123456789'
        secret_data['default_account'] = ""
        with open(secret_file, 'w', encoding='utf-8') as f:
            json.dump(secret_data, f, ensure_ascii=False, separators=(',', ':'))
        return True
    except Exception as e:
        raise Exception(f"重置secret密码和默认账号清空失败: {str(e)}")


def generate_random_password(length=12):  
    chars = string.ascii_letters + string.digits  
    return ''.join(random.choices(chars, k=length))  


def reset_secret_password_random(secret_file):  
    try:  
        with open(secret_file, 'r', encoding='utf-8') as f:  
            content = f.read()  
        secret_data = json.loads(content)  
        new_password = generate_random_password()  
        secret_data['password'] = new_password  
        with open(secret_file, 'w', encoding='utf-8') as f:  
            json.dump(secret_data, f, ensure_ascii=True, separators=(',', ':'))  
        return new_password  
    except Exception as e:  
        raise Exception(f"重置secret随机密码失败: {str(e)}")


async def create_daily_config(user_id, username=None, password=None, filename=None):
    """返回 (文本, login_url)。文本里**直接嵌入 URL**（QQ 官方 bot API 只支持纯文本）。
    图片部分保留，但官方 API 拉不到 docimg 图片时会报 400，不影响文本送达。"""
    try:
        hoshino_dir = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
        base_dir = os.path.join(hoshino_dir, 'modules', 'autopcr', 'cache', 'http_server')
        user_dir = os.path.join(base_dir, user_id)
        secret_file = os.path.join(user_dir, 'secret')
        
        if os.name == 'nt':
            import winreg
            try:
                key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, r'Software\Microsoft\Windows\CurrentVersion\Explorer\Shell Folders')
                desktop_path = winreg.QueryValueEx(key, "Desktop")[0]
                winreg.CloseKey(key)
            except:
                desktop_path = os.path.join(os.path.expanduser('~'), 'Desktop')
        else:
            desktop_path = os.path.join(os.path.expanduser('~'), 'Desktop')
        
        src_json = os.path.join(desktop_path, '我的账号.json')
        json_filename = filename if filename else '我的账号.json'
        dst_json = os.path.join(user_dir, json_filename)
        
        os.makedirs(base_dir, exist_ok=True)
        os.makedirs(user_dir, exist_ok=True)
        
        file_msg = ""
        if not os.path.exists(secret_file):
            default_config = {
                "password": "123456789",
                "default_account": "",
                "clan": False,
                "admin": False,
                "disabled": False
            }
            with open(secret_file, 'w', encoding='utf-8') as f:
                json.dump(default_config, f, ensure_ascii=False, separators=(',', ':'))
            file_msg = "✅ 初始secret配置已创建（单行格式），密码已重置为123456789，默认账号已置空"
        else:  
            # 文件已存在（重复发送者）：URL 直接嵌在文本里
            login_url = build_login_url()
            login_line = build_login_line(login_url)
            return f'''【清日常配置已存在】
👤 用户ID: {user_id}
{login_line}
🔑 如需修改密码，请发送：清日常重置密码''', login_url
        
        if os.path.exists(src_json):
            try:
                if not os.path.exists(dst_json):
                    shutil.copy2(src_json, dst_json)
                    file_msg += "，✅ 桌面账号文件已复制"
                else:
                    file_msg += "，ℹ️ 目标文件夹已存在账号文件，未覆盖"
                if username and password:
                    try:
                        update_json_file(dst_json, username, password)
                        file_msg += "，账号密码已设置"
                    except Exception as e:
                        backup_json = f"{dst_json}.bak"
                        if os.path.exists(backup_json):
                            shutil.move(backup_json, dst_json)
                        file_msg += f"，⚠️ 账号文件更新失败: {str(e)}"
            except Exception as e:
                file_msg += f"，⚠️ 账号文件复制失败: {str(e)}"
        else:
            if username and password:
                account_data = {
                    "username": username,
                    "password": password
                }
                with open(dst_json, 'w', encoding='utf-8') as f:
                    json.dump(account_data, f, ensure_ascii=False, separators=(',', ':'))
                file_msg += "，✅ 账号密码已创建"
            else:
                file_msg += f"，⚠️ 未找到桌面上的账号文件，请手动放入：\n{user_dir}"
        
        login_url = build_login_url()
        login_line = build_login_line(login_url)

        # 注意：这里不再用任何 CQ 码包裹 URL，URL 直接以文本形式出现，
        # QQ 官方 bot 客户端会自动渲染成蓝色可点击链接。
        # 图片部分保留（如果官方 API 拉不到会报 400，但不影响文本 URL 送达）。
        return f'''【清日常配置创建完成】
👤 用户ID: {user_id}
{file_msg}
🔧🔧 使用说明：
1. 登录网站的账号为QQ号，初始密码为123456789，请及时修改[CQ:image,file=https://docimg7.docs.qq.com/image/AgAACIUgb5q_Vr3vGG5NIJHWpiWpcnHA.png?w=596&h=704]
2. 上去按指示点击圆点[CQ:image,file=https://docimg4.docs.qq.com/image/AgAACIUgb5qLsZ3QKA9Ntb683ojPeN-P.png?w=323&h=251]再点击配置填账号密码，[CQ:image,file=https://docimg5.docs.qq.com/image/AgAACIUgb5rXOV9adwdE6ai5YP1EccG_.png?w=667&h=554]再进入【日常】页面修改需求
3. [CQ:image,file=https://docimg3.docs.qq.com/image/AgAACIUgb5q18BAEbbFKL72SgBXRIu_R.png?w=452&h=174]平时可使用【#配置日常】召唤网站
{login_line}
''', login_url
        
    except Exception as e:
        error_msg = f'❌❌ 创建失败：{str(e)}\n{traceback.format_exc()}'
        sv.logger.error(error_msg)
        return f'❌❌ 创建失败：{str(e)}', None


# 群聊 - 清日常创建
@sv.on_prefix('清日常创建')
async def create_daily_file(bot, ev: CQEvent):
    user_id = str(ev.user_id)
    args = ev.message.extract_plain_text().strip().split()
    filename = None
    if len(args) >= 1:
        filename = args[0] + '.json' if not args[0].endswith('.json') else args[0]
    result, login_url = await create_daily_config(user_id, username=None, password=None, filename=filename)
    sv.logger.info(f'[清日常创建] user_id={user_id!r} login_url={login_url!r}')
    # 直接发送：URL 已嵌入文本，官方 bot 客户端自动渲染为可点击链接
    await bot.send(ev, result)


# 群聊 - 清日常重置密码  
@sv.on_prefix('清日常重置密码')  
async def reset_daily_password(bot, ev: CQEvent):  
    user_id = str(ev.user_id)  
    hoshino_dir = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))  
    base_dir = os.path.join(hoshino_dir, 'modules', 'autopcr', 'cache', 'http_server')  
    user_dir = os.path.join(base_dir, user_id)  
    secret_file = os.path.join(user_dir, 'secret')  
    if not os.path.exists(secret_file):  
        await bot.send(ev, "❌ 未找到你的清日常配置，请先发送“清日常创建”")  
        return  
    try:  
        new_pwd = reset_secret_password_random(secret_file)  
        await bot.send(ev, f"✅ 密码已重置为随机密码：{new_pwd}\n请尽快用它登录网站并修改。")  
    except Exception as e:  
        await bot.send(ev, f"❌ 重置失败：{str(e)}")


# 群聊 - 清日常禁用
@sv.on_prefix('清日常禁用')
async def disable_daily(bot, ev: CQEvent):
    args = ev.message.extract_plain_text().strip().split()
    if not args:
        await bot.send(ev, "❌ 请指定要禁用的文件夹名，支持批量：\n格式：清日常禁用 文件夹名1 [文件夹名2...]")
        return
    result = update_secret_status(args, enable=False)
    msg = "【清日常禁用结果】\n"
    if result["success"]:
        msg += f"✅ 成功禁用：{', '.join(result['success'])}\n"
    if result["failed"]:
        msg += f"❌ 禁用失败：\n" + "\n".join([f"  - {item}" for item in result["failed"]])
    await bot.send(ev, msg)


# 群聊 - 清日常解禁
@sv.on_prefix('清日常解禁')
async def enable_daily(bot, ev: CQEvent):
    args = ev.message.extract_plain_text().strip().split()
    if not args:
        await bot.send(ev, "❌ 请指定要解禁的文件夹名，支持批量：\n格式：清日常解禁 文件夹名1 [文件夹名2...]")
        return
    result = update_secret_status(args, enable=True)
    msg = "【清日常解禁结果】\n"
    if result["success"]:
        msg += f"✅ 成功解禁：{', '.join(result['success'])}\n"
    if result["failed"]:
        msg += f"❌ 解禁失败：\n" + "\n".join([f"  - {item}" for item in result["failed"]])
    await bot.send(ev, msg)


# 私聊 - 清日常创建
# @on_command('清日常创建', aliases=('创建清日常', '初始化清日常'), permission=priv.NORMAL)
async def private_create_daily(session: CommandSession):
    user_id = str(session.event.user_id)
    args = session.current_arg_text.strip().split()
    username = None
    password = None
    filename = None
    if len(args) >= 3:
        username = args[0]
        password = args[1]
        filename = args[2] + '.json' if not args[2].endswith('.json') else args[2]
    elif len(args) == 2:
        username = args[0]
        password = args[1]
    elif len(args) == 1:
        await session.send('请输入完整的账号和密码，格式：清日常创建 账号 密码 [用户名]')
        return
    result, login_url = await create_daily_config(user_id, username, password, filename)
    sv.logger.info(f'[清日常创建/私聊] user_id={user_id!r} login_url={login_url!r}')
    await session.send(result)


# 私聊 - 清日常禁用
@on_command('清日常禁用', aliases=('禁用清日常',), permission=priv.NORMAL)
async def private_disable_daily(session: CommandSession):
    args = session.current_arg_text.strip().split()
    if not args:
        await session.send("❌ 请指定要禁用的文件夹名，支持批量：\n格式：清日常禁用 文件夹名1 [文件夹名2...]")
        return
    result = update_secret_status(args, enable=False)
    msg = "【清日常禁用结果】\n"
    if result["success"]:
        msg += f"✅ 成功禁用：{', '.join(result['success'])}\n"
    if result["failed"]:
        msg += f"❌ 禁用失败：\n" + "\n".join([f"  - {item}" for item in result["failed"]])
    await session.send(msg)


# 私聊 - 清日常解禁
@on_command('清日常解禁', aliases=('解禁清日常',), permission=priv.NORMAL)
async def private_enable_daily(session: CommandSession):
    args = session.current_arg_text.strip().split()
    if not args:
        await session.send("❌ 请指定要解禁的文件夹名，支持批量：\n格式：清日常解禁 文件夹名1 [文件夹名2...]")
        return
    result = update_secret_status(args, enable=True)
    msg = "【清日常解禁结果】\n"
    if result["success"]:
        msg += f"✅ 成功解禁：{', '.join(result['success'])}\n"
    if result["failed"]:
        msg += f"❌ 解禁失败：\n" + "\n".join([f"  - {item}" for item in result["failed"]])
    await session.send(msg)


# 私聊 - 清日常重置密码  
@on_command('清日常重置密码', aliases=('重置清日常密码',), permission=priv.NORMAL)  
async def private_reset_daily_password(session: CommandSession):  
    user_id = str(session.event.user_id)  
    hoshino_dir = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))  
    base_dir = os.path.join(hoshino_dir, 'modules', 'autopcr', 'cache', 'http_server')  
    user_dir = os.path.join(base_dir, user_id)  
    secret_file = os.path.join(user_dir, 'secret')  
    if not os.path.exists(secret_file):  
        await session.send("❌ 未找到你的清日常配置，请先发送“清日常创建”")  
        return  
    try:  
        new_pwd = reset_secret_password_random(secret_file)  
        await session.send(f"✅ 密码已重置为随机密码：{new_pwd}\n请尽快用它登录网站并修改。")  
    except Exception as e:  
        await session.send(f"❌ 重置失败：{str(e)}")