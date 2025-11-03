import os
import re
import json
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
          '或发送"清日常创建 账号 密码 用户名"设置账号密码及文件名'
)

def get_public_ip():
    try:
        services = [
            'https://api.ipify.org',
            'https://ident.me',
            'https://ifconfig.me/ip'
        ]
        for service in services:
            try:
                response = requests.get(service, timeout=5)
                if response.status_code == 200:
                    return response.text.strip()
            except:
                continue
        return None
    except Exception:
        return None

def update_json_file(file_path, username, password):
    """严格只更新username和password字段，其他内容原封不动"""
    try:
        # 1. 读取原始文件内容（完全保留所有字符）
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()
        
        # 2. 备份原始内容
        original_content = content
        
        # 3. 处理username字段
        if '"username"' in content:
            # 如果已有username字段，只替换值部分
            content = re.sub(
                r'("username"\s*:\s*")[^"]*(")',
                f'\\g<1>{username}\\g<2>',
                content
            )
        else:
            # 如果没有username字段，在第一个{后添加
            content = content.replace('{', f'{{\n    "username": "{username}",', 1)
        
        # 4. 处理password字段
        if '"password"' in content:
            content = re.sub(
                r'("password"\s*:\s*")[^"]*(")',
                f'\\g<1>{password}\\g<2>',
                content
            )
        else:
            # 如果没有password字段，在第一个{后添加
            content = content.replace('{', f'{{\n    "password": "{password}",', 1)
        
        # 5. 验证JSON格式是否有效
        try:
            json.loads(content)
        except json.JSONDecodeError as e:
            # 如果格式错误，恢复原始内容
            content = original_content
            raise Exception(f"更新后JSON格式无效，已恢复原文件: {str(e)}")
        
        # 6. 写入文件（完全保留原始编码和换行符）
        with open(file_path, 'w', encoding='utf-8', newline='') as f:
            f.write(content)
            
    except Exception as e:
        raise Exception(f"更新JSON文件失败: {str(e)}")

async def create_daily_config(user_id, username=None, password=None, filename=None):
    try:
        hoshino_dir = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
        base_dir = os.path.join(hoshino_dir, 'modules', 'autopcr', 'cache', 'http_server')
        user_dir = os.path.join(base_dir, user_id)
        secret_file = os.path.join(user_dir, 'secret')
        
        desktop_path = os.path.join(os.path.expanduser('~'), 'Desktop')
        src_json = os.path.join(desktop_path, '我的账号.json')
        
        # 确定JSON文件名，有提供则使用，否则用默认
        json_filename = filename if filename else '我的账号.json'
        
        default_config = {
            "password": "123456789",
            "default_account": "",
            "clan": False,
            "admin": False,
            "disabled": False
        }
        
        # 确保基础目录存在
        os.makedirs(base_dir, exist_ok=True)
        
        # 判断用户目录是否已存在
        dir_exists = os.path.exists(user_dir)
        
        # 无论目录是否存在，都创建/覆盖secret文件
        os.makedirs(user_dir, exist_ok=True)  # 确保用户目录存在
        with open(secret_file, 'w', encoding='utf-8') as f:
            json.dump(default_config, f, ensure_ascii=False, indent=4)
        
        file_msg = ""
        # 只有目录不存在时，才处理账号文件导入
        if not dir_exists:
            if os.path.exists(src_json):
                dst_json = os.path.join(user_dir, json_filename)
                
                # 复制文件
                shutil.copy2(src_json, dst_json)
                
                if username and password:
                    try:
                        update_json_file(dst_json, username, password)
                        file_msg = "✅ 账号密码已设置"
                    except Exception as e:
                        # 恢复备份（如果有）
                        backup_json = f"{dst_json}.bak"
                        if os.path.exists(backup_json):
                            shutil.move(backup_json, dst_json)
                        file_msg = f"⚠️ 账号文件存在但更新失败（已恢复原文件）: {str(e)}"
            else:
                if username and password:
                    account_data = {
                        "username": username,
                        "password": password
                    }
                    dst_json = os.path.join(user_dir, json_filename)
                    with open(dst_json, 'w', encoding='utf-8') as f:
                        json.dump(account_data, f, ensure_ascii=False, indent=4)
                    file_msg = "✅ 账号密码已创建"
                else:
                    file_msg = "⚠️ 未找到桌面上的账号文件，请手动放入以下文件夹：\n" + user_dir
        else:
            file_msg = "✅ 目录已存在，仅重置登录密码"
        
        public_ip = get_public_ip()
        login_url = f"http://{public_ip}:8040/daily/login" if public_ip else "无法获取公网IP，请手动配置"
        
        return f'''【清日常配置创建完成】
{file_msg}
🔧🔧 使用说明：
1. 登录网站的账号为QQ号，初始密码为123456789，请及时修改
2. 上去按指示点击圆点[CQ:image,file=https://docimg6.docs.qq.com/image/AgAACIUgb5osrIDjZllIBJ-ZIlyD7UtV.png?w=301&h=327]再点击配置填账号密码，再进入【日常】页面修改需求
3. 平时可使用【#配置日常】召唤网站

🌐🌐 访问地址: {login_url}
'''
        
    except Exception as e:
        error_msg = f'❌❌ 创建失败：{str(e)}\n{traceback.format_exc()}'
        sv.logger.error(error_msg)
        return f'❌❌ 创建失败：{str(e)}'

@sv.on_prefix('清日常创建')
async def create_daily_file(bot, ev: CQEvent):
    user_id = str(ev.user_id)
    args = ev.message.extract_plain_text().strip().split()
    
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
    
    result = await create_daily_config(user_id, username, password, filename)
    await bot.send(ev, result)

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
    
    result = await create_daily_config(user_id, username, password, filename)
    await session.send(result)