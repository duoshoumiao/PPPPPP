import os
import secrets
from copy import deepcopy
from datetime import timedelta
from typing import Callable, Coroutine, Any
import json  
import time as _time
import asyncio
import quart
from quart import request, Blueprint, send_file, send_from_directory
from quart_auth import AuthUser, QuartAuth, Unauthorized, current_user, login_user, logout_user, login_required
from quart_compress import Compress
from quart_rate_limiter import RateLimiter, rate_limit, RateLimitExceeded

from .validator import validate_dict, ValidateInfo, validate_ok_dict, enable_manual_validator
from ..constants import CACHE_DIR, ALLOW_REGISTER, SUPERUSER
from ..module.accountmgr import Account, AccountManager, instance as usermgr, AccountException, UserData, \
    PermissionLimitedException, UserDisabledException, UserException
from ..util.draw import instance as drawer
from ..util.logger import instance as logger
from .command_relay import FinishSignal, RelayBotEvent, SPECIAL_HANDLERS   # ← 新增

APP_VERSION_MAJOR = 1
APP_VERSION_MINOR = 7

CACHE_HTTP_DIR = os.path.join(CACHE_DIR)

PATH = os.path.dirname(os.path.abspath(__file__))
static_path = os.path.join(PATH, 'ClientApp')

MESSAGES_PATH = os.path.join(CACHE_HTTP_DIR, 'messages.json')

MESSAGEBOARD_SCRIPT = f'''  
<style>  
#msg-board-btn {{  
  position: fixed; bottom: 20px; right: 20px; z-index: 2147483647;  
  width: 50px; height: 50px; border-radius: 50%; border: none;  
  background: #1976d2; color: white; font-size: 24px; cursor: pointer;  
  box-shadow: 0 2px 8px rgba(0,0,0,0.3); display: none;  
  pointer-events: auto;
}}  
#msg-board-panel {{  
  position: fixed; bottom: 20px; right: 20px; z-index: 2147483647;  
  width: 315px; height: 450px; background: white; border-radius: 8px;  
  box-shadow: 0 4px 16px rgba(0,0,0,0.3); display: none; flex-direction: column;  
  font-family: sans-serif; color: #333;  
  pointer-events: auto;
}}  
#msg-board-header {{  
  padding: 12px 16px; background: #1976d2; color: white;  
  border-radius: 8px 8px 0 0; font-weight: bold; font-size: 16px;  
  display: flex; justify-content: space-between; align-items: center;  
}}  
#msg-board-minimize {{  
  background: none; border: none; color: white; font-size: 20px;  
  cursor: pointer; padding: 0 4px; line-height: 1;  
}}  
#msg-board-list {{  
  flex: 1; overflow-y: auto; padding: 8px 12px;  
}}  
.msg-item {{  
  margin-bottom: 10px; padding: 8px; background: #f5f5f5; border-radius: 6px;  
  font-size: 13px; word-break: break-all;  
}}  
.msg-item .msg-meta {{ color: #888; font-size: 11px; margin-bottom: 4px; }}  
.msg-item .msg-del {{  
  float: right; color: #e53935; cursor: pointer; font-size: 11px;  
  background: none; border: none; padding: 0;  
}}  
.msg-item img {{ max-width: 100%; border-radius: 4px; margin-top: 4px; cursor: pointer; }}  
#msg-board-preview {{  
  display: none; padding: 4px 8px; border-top: 1px solid #eee; position: relative;  
}}  
#msg-board-preview img {{ max-height: 60px; border-radius: 4px; }}  
#msg-board-preview-close {{  
  position: absolute; top: 2px; right: 8px; cursor: pointer;  
  background: rgba(0,0,0,0.5); color: white; border: none; border-radius: 50%;  
  width: 18px; height: 18px; font-size: 12px; line-height: 18px; text-align: center;  
}}  
#msg-board-input-area {{  
  display: flex; padding: 8px; border-top: 1px solid #eee; align-items: center;  
}}  
#msg-board-input {{  
  flex: 1; border: 1px solid #ccc; border-radius: 4px; padding: 6px 8px;  
  font-size: 13px; outline: none; background: white; color: #333;  
}}  
#msg-board-send {{  
  margin-left: 6px; border: none; background: #1976d2; color: white;  
  border-radius: 4px; padding: 6px 12px; cursor: pointer; font-size: 13px;  
}}  
#msg-board-img-btn {{  
  margin-left: 4px; border: none; background: none; cursor: pointer;  
  font-size: 18px; padding: 2px 4px; color: #1976d2;  
}}  
</style>  
  
<button id="msg-board-btn" title="留言板">💬</button>
<div id="msg-board-panel">  
  <div id="msg-board-header">  
    <span>留言板</span>  
    <button id="msg-board-minimize" title="缩小">&minus;</button>  
  </div>  
  <div id="msg-board-list"></div>  
  <div id="msg-board-preview">  
    <img id="msg-board-preview-img" />  
    <button id="msg-board-preview-close">&times;</button>  
  </div>  
  <div id="msg-board-input-area">  
    <button id="msg-board-img-btn" title="上传图片" style="background:none;border:none;font-size:18px;cursor:pointer;">🖼</button>  
    <button id="msg-board-ss-btn" title="截图" style="background:none;border:none;font-size:18px;cursor:pointer;">✂</button>  
    <input id="msg-board-input" placeholder="输入留言..." maxlength="500" />  
    <button id="msg-board-send">发送</button>   
    <input id="msg-board-file" type="file" accept="image/*" style="display:none" />  
  </div>  
</div>  
  
<script>  
(function() {{  
  var btn = document.getElementById('msg-board-btn');  
  var panel = document.getElementById('msg-board-panel');  
  var minBtn = document.getElementById('msg-board-minimize');  
  var list = document.getElementById('msg-board-list');  
  var input = document.getElementById('msg-board-input');  
  var sendBtn = document.getElementById('msg-board-send');  
  var imgBtn = document.getElementById('msg-board-img-btn');  
  var ssBtn = document.getElementById('msg-board-ss-btn');
  var fileInput = document.getElementById('msg-board-file');  
  var preview = document.getElementById('msg-board-preview');  
  var previewImg = document.getElementById('msg-board-preview-img');  
  var previewClose = document.getElementById('msg-board-preview-close');  
  var appVersion = '{APP_VERSION_MAJOR}.{APP_VERSION_MINOR}.0';  
  var loggedIn = false;  
  var minimized = false;  
  var isAdmin = false;  
  var timer = null;  
  var lastSeenId = localStorage.getItem('msg_board_last_seen') || '';
  var pendingImage = '';  
  
  
  function startPolling(interval) {{  
    if (timer) clearInterval(timer);  
    timer = setInterval(loadMessages, interval);  
  }}  
  
  minBtn.onclick = function() {{  
    minimized = true;  
    panel.style.display = 'none';  
    btn.style.display = 'block';  
  }};  
  
  btn.onclick = function() {{  
    panel.style.display = 'flex';  
    btn.style.display = 'none';  
    btn.textContent = '💬';  
    btn.style.fontSize = '24px';  
    btn.style.background = '#1976d2';  
    minimized = false;  
    loadMessages();  
  }};
  
  imgBtn.onclick = function() {{ fileInput.click(); }};  
  
  fileInput.onchange = function() {{  
    var file = fileInput.files[0];  
    if (!file) return;  
    if (file.size > 2 * 1024 * 1024) {{  
      alert('图片不能超过2MB');  
      fileInput.value = '';  
      return;  
    }}  
    var formData = new FormData();  
    formData.append('image', file);  
    fetch('/daily/api/messages/upload', {{  
      method: 'POST',  
      headers: {{ 'X-App-Version': appVersion }},  
      credentials: 'same-origin',  
      body: formData  
    }})  
    .then(function(r) {{  
      if (r.ok) return r.json();  
      return r.text().then(function(t) {{ throw new Error(t); }});  
    }})  
    .then(function(data) {{  
      pendingImage = data.filename;  
      previewImg.src = '/daily/api/messages/image/' + data.filename;  
      preview.style.display = 'block';  
    }})  
    .catch(function(e) {{ alert(e.message || '上传失败'); }});  
    fileInput.value = '';  
  }};  
  
  previewClose.onclick = function() {{  
    pendingImage = '';  
    preview.style.display = 'none';  
    previewImg.src = '';  
  }};  
  
  ssBtn.onclick = function() {{  
    if (!navigator.mediaDevices || !navigator.mediaDevices.getDisplayMedia) {{  
      alert('当前浏览器不支持截图功能，请使用 Ctrl+V 粘贴截图');  
      return;  
    }}  
    navigator.mediaDevices.getDisplayMedia({{ video: true }}).then(function(stream) {{  
      var video = document.createElement('video');  
      video.srcObject = stream;  
      video.onloadedmetadata = function() {{  
        video.play();  
        setTimeout(function() {{  
          var canvas = document.createElement('canvas');  
          canvas.width = video.videoWidth;  
          canvas.height = video.videoHeight;  
          canvas.getContext('2d').drawImage(video, 0, 0);  
          stream.getTracks().forEach(function(t) {{ t.stop(); }});  
          canvas.toBlob(function(blob) {{  
            if (!blob) return;  
            var formData = new FormData();  
            formData.append('image', blob, 'screenshot.png');  
            fetch('/daily/api/messages/upload', {{  
              method: 'POST',  
              headers: {{ 'X-App-Version': appVersion }},  
              credentials: 'same-origin',  
              body: formData  
            }})  
            .then(function(r) {{  
              if (r.ok) return r.json();  
              return r.text().then(function(t) {{ throw new Error(t); }});  
            }})  
            .then(function(data) {{  
              pendingImage = data.filename;  
              previewImg.src = '/daily/api/messages/image/' + data.filename;  
              preview.style.display = 'block';  
            }})  
            .catch(function(e) {{ alert(e.message || '上传失败'); }});  
          }}, 'image/png');  
        }}, 300);  
      }};  
    }}).catch(function(e) {{  
      if (e.name !== 'NotAllowedError') console.error(e);  
    }});  
  }};
  
  panel.addEventListener('paste', function(e) {{  
    var items = (e.clipboardData || e.originalEvent.clipboardData).items;  
    for (var i = 0; i < items.length; i++) {{  
      if (items[i].type.indexOf('image') !== -1) {{  
        e.preventDefault();  
        var blob = items[i].getAsFile();  
        var formData = new FormData();  
        formData.append('image', blob, 'paste.png');  
        fetch('/daily/api/messages/upload', {{  
          method: 'POST',  
          headers: {{ 'X-App-Version': appVersion }},  
          credentials: 'same-origin',  
          body: formData  
        }})  
        .then(function(r) {{  
          if (r.ok) return r.json();  
          return r.text().then(function(t) {{ throw new Error(t); }});  
        }})  
        .then(function(data) {{  
          pendingImage = data.filename;  
          previewImg.src = '/daily/api/messages/image/' + data.filename;  
          preview.style.display = 'block';  
        }})  
        .catch(function(e) {{ alert(e.message || '上传失败'); }});  
        break;  
      }}  
    }}  
  }});
  
  // 检测管理员身份  
  function checkRole() {{  
    fetch('/daily/api/role', {{  
      credentials: 'same-origin'  
    }})  
    .then(function(r) {{ if (r.ok) return r.json(); return null; }})  
    .then(function(data) {{  
      if (data) isAdmin = data.admin || data.super_user;  
    }})  
    .catch(function() {{}});  
  }}  
  
  function loadMessages() {{  
    fetch('/daily/api/messages', {{  
      headers: {{ 'X-App-Version': appVersion }},  
      credentials: 'same-origin'  
    }})  
    .then(function(r) {{  
      if (r.status === 401) {{  
        if (loggedIn) {{  
          panel.style.display = 'none';  
          btn.style.display = 'none';  
          loggedIn = false;  
          minimized = false;  
          isAdmin = false;  
          startPolling(2000);  
        }}  
        return null;  
      }}  
      return r.json();  
    }})  
    .then(function(msgs) {{  
      if (!msgs) return;  
      if (!loggedIn) {{  
        loggedIn = true;  
        btn.style.display = 'block';  
        startPolling(3000);  
        checkRole();  
      }}  
      var wasAtBottom = list.scrollHeight - list.scrollTop - list.clientHeight < 30;  
      list.innerHTML = ''; 
      msgs.forEach(function(m) {{  
        var div = document.createElement('div');  
        div.className = 'msg-item';  
        var html = '<div class="msg-meta">' + m.qq + ' &middot; ' + m.time;  
        if (isAdmin) {{  
          html += ' <button class="msg-del" data-id="' + m.id + '">&times; 删除</button>';  
        }}  
        html += '</div>';  
        if (m.content) html += '<div>' + m.content + '</div>';  
        if (m.image) html += '<img src="/daily/api/messages/image/' + m.image + '" onclick="window.open(this.src)" />';  
        div.innerHTML = html;  
        list.appendChild(div);  
      }});  
      // 绑定删除按钮事件  
      list.querySelectorAll('.msg-del').forEach(function(delBtn) {{  
        delBtn.onclick = function() {{  
          if (!confirm('确定删除这条留言？')) return;  
          var msgId = this.getAttribute('data-id');  
          fetch('/daily/api/messages/' + msgId, {{  
            method: 'DELETE',  
            headers: {{ 'X-App-Version': appVersion }},  
            credentials: 'same-origin'  
          }})  
          .then(function(r) {{  
            if (r.ok) loadMessages();  
            else r.text().then(function(t) {{ alert(t); }});  
          }})  
          .catch(function(e) {{ console.error(e); }});  
        }};  
      }});  
      if (wasAtBottom) list.scrollTop = list.scrollHeight;
      // 新消息红点逻辑  
      if (msgs.length > 0) {{  
        var latestId = msgs[msgs.length - 1].id;  
        if (panel.style.display === 'flex') {{  
          lastSeenId = latestId;  
          localStorage.setItem('msg_board_last_seen', latestId);  
          btn.textContent = '💬';  
          btn.style.fontSize = '24px';  
          btn.style.background = '#1976d2';  
        }} else if (latestId !== lastSeenId) {{  
          btn.textContent = '新消息';  
          btn.style.fontSize = '12px';  
          btn.style.background = '#e53935';  
        }}  
      }} else {{  
        btn.textContent = '💬';  
        btn.style.fontSize = '24px';  
        btn.style.background = '#1976d2';  
      }}
    }})  
    .catch(function(e) {{ console.error(e); }});  
  }}  
  
  sendBtn.onclick = function() {{  
    var content = input.value.trim();  
    if (!content && !pendingImage) return;  
    var body = {{ content: content }};  
    if (pendingImage) body.image = pendingImage;  
    fetch('/daily/api/messages', {{  
      method: 'POST',  
      headers: {{ 'Content-Type': 'application/json', 'X-App-Version': appVersion }},  
      credentials: 'same-origin',  
      body: JSON.stringify(body)  
    }})  
    .then(function(r) {{  
      if (r.ok) {{  
        input.value = '';  
        pendingImage = '';  
        preview.style.display = 'none';  
        previewImg.src = '';  
        loadMessages();  
      }}  
      else r.text().then(function(t) {{ alert(t); }});  
    }})  
    .catch(function(e) {{ console.error(e); }});  
  }};  
  
  input.addEventListener('keydown', function(e) {{  
    if (e.key === 'Enter') sendBtn.click();  
  }});  
  
  loadMessages();  
  startPolling(2000);  
}})();  
</script>  
'''

class HttpServer:
    def __init__(self, host = '0.0.0.0', port = 2, qq_mod = False):

        self.web = Blueprint('web', __name__, static_folder=static_path)

        # version check & rate limit
        self.api_limit = Blueprint('api_limit', __name__, url_prefix = "/")
        self.api = Blueprint('api', __name__, url_prefix = "/api")

        self.app = Blueprint('app', __name__, url_prefix = "/daily")

        self.quart = quart.Quart(__name__)
        QuartAuth(self.quart, cookie_secure=False)
        RateLimiter(self.quart)
        Compress(self.quart)
        self.quart.secret_key = secrets.token_urlsafe(16)

        self.app.register_blueprint(self.web)
        self.app.register_blueprint(self.api)
        self.api.register_blueprint(self.api_limit)

        self.host = host
        self.port = port
        self.validate_server = {}
        self.configure_routes()
        self.qq_mod = qq_mod
        self._auto_def_tasks = {}  # ← 新增：管理自动换防任务，key=qq

        self.app.after_request(self.log_request_info)

        enable_manual_validator()

    def log_request_info(self, response):
        logger.info(
            f"{request.method} {request.url} - {response.status_code} - {request.remote_addr}"
        )
        return response

    @staticmethod
    def wrapaccount(readonly = False):
        def wrapper(func: Callable[..., Coroutine[Any, Any, Any]]):
            async def inner(accountmgr: AccountManager, acc: str, *args, **kwargs):
                if acc:
                    async with accountmgr.load(acc, readonly) as mgr:
                        return await func(mgr, *args, **kwargs)
                else: 
                    return "Please specify an account", 400
            inner.__name__ = func.__name__
            return inner
        return wrapper

    @staticmethod
    def wrapaccountmgr(readonly = False):
        def wrapper(func: Callable[..., Coroutine[Any, Any, Any]]):
            async def inner(*args, **kwargs):
                qid: str = current_user.auth_id
                async with usermgr.load(qid, readonly) as mgr:
                    return await func(accountmgr = mgr, *args, **kwargs)
            inner.__name__ = func.__name__
            return inner
        return wrapper

    @staticmethod
    def login_required():
        def wrapper(func: Callable[..., Coroutine[Any, Any, Any]]):
            async def inner(*args, **kwargs):
                if not await current_user.is_authenticated:
                    raise Unauthorized()
                else:
                    async with usermgr.load(current_user.auth_id, True) as mgr:
                        disabled = mgr.secret.disabled
                if not disabled:
                    return await func(*args, **kwargs)
                else:
                    raise UserDisabledException()
            inner.__name__ = func.__name__
            return inner
        return wrapper

    @staticmethod
    def admin_required():
        def wrapper(func: Callable[..., Coroutine[Any, Any, Any]]):
            async def inner(*args, **kwargs):
                if SUPERUSER == current_user.auth_id:
                    admin = True
                else:
                    async with usermgr.load(current_user.auth_id, True) as mgr:
                        admin = mgr.secret.admin
                if admin:
                    return await func(*args, **kwargs)
                else:
                    raise PermissionLimitedException()
            inner.__name__ = func.__name__
            return inner
        return wrapper

    def configure_routes(self):

        @self.api_limit.before_request
        async def check_app_version():
            version = request.headers.get('X-App-Version', "0.0.0")
            try:
                major, minor, patch = map(int, version.split("."))
                if major != APP_VERSION_MAJOR or minor != APP_VERSION_MINOR:
                    return f"后端期望前端版本为{APP_VERSION_MAJOR}.{APP_VERSION_MINOR}，请更新", 400
                else:
                    return None
            except Exception:
                return "无法解析前端版本号，请更新", 400

        @self.api_limit.errorhandler(RateLimitExceeded)
        async def handle_rate_limit_exceeded_error(error):
            return "您冲得太快了，休息一下吧", 429

        @self.api.errorhandler(Unauthorized)
        async def redirect_to_login(*_: Exception):
            return "未登录，请登录", 401

        @self.api.errorhandler(PermissionLimitedException)
        async def limited(*_: Exception):
            return "无权使用此接口", 403

        @self.api.errorhandler(UserDisabledException)
        async def disabled(*_: Exception):
            return "已到期，请联系管理员", 403

        @self.api.errorhandler(UserException)
        async def handle_user_exception(e):
            logger.exception(e)
            return str(e), 400

        @self.api.errorhandler(ValueError)
        async def handle_value_error(e):
            logger.exception(e)
            return str(e), 400

        @self.api.errorhandler(AccountException)
        async def handle_account_exception(e):
            logger.exception(e)
            return str(e), 400

        @self.api.errorhandler(Exception)
        async def handle_general_exception(e):
            logger.exception(e)
            return "服务器发生错误", 500

        @self.api.route('/clan_forbid', methods = ["GET"])
        @HttpServer.login_required()
        @HttpServer.admin_required()
        async def get_clan_forbid():
            accs = usermgr.get_clan_battle_forbidden()
            return '\n'.join(accs), 200

        @self.api.route('/clan_forbid', methods = ["PUT"])
        @HttpServer.login_required()
        @HttpServer.admin_required()
        async def put_clan_forbid():
            data = (await request.get_json())['accs'].split('\n')
            usermgr.set_clan_battle_forbidden(data)
            return f'设置成功，禁止了{len(data)}个账号', 200

        @self.api.route('/role', methods = ["GET"])
        @HttpServer.login_required()
        @HttpServer.wrapaccountmgr(readonly = True)
        async def get_role(accountmgr: AccountManager):
            return await accountmgr.generate_role(), 200

        @self.api.route('/running_status', methods = ["GET"])
        @HttpServer.login_required()
        async def get_running_status():
            from ..core.clientpool import instance as clientpool
            sema, farm_sema = clientpool.sema_status()
            ret = []
            for i, (running, waiting, max_count) in enumerate([sema, farm_sema]):
                ret.append({
                    'name': f"运行状态{i}",
                    'running': running,
                    'waiting': waiting,
                    'max_running': max_count,
                })
            return {'statuses': ret}, 200

        @self.api.route('/account', methods = ['GET'])
        @HttpServer.login_required()
        @HttpServer.wrapaccountmgr(readonly = True)
        async def get_info(accountmgr: AccountManager):
            return await accountmgr.generate_info(), 200

        @self.api.route('/account', methods = ["PUT"])
        @HttpServer.login_required()
        @HttpServer.wrapaccountmgr()
        async def put_info(accountmgr: AccountManager):
            data = await request.get_json()
            default_accont = data.get('default_account', '')
            if default_accont:
                accountmgr.set_default_account(default_accont)
            password = data.get('password', '')
            if password:
                accountmgr.set_password(password)
            return "保存成功", 200

        @self.api.route('/account', methods = ["POST"])
        @HttpServer.login_required()
        @HttpServer.wrapaccountmgr()
        async def create_account(accountmgr: AccountManager):
            data = await request.get_json()
            acc = data.get("alias", "")
            accountmgr.create_account(acc.strip())
            return "创建账号成功", 200

        @self.api.route('/account/import', methods = ["POST"])
        @HttpServer.login_required()
        @HttpServer.wrapaccountmgr()
        async def create_accounts(accountmgr: AccountManager):
            file = await request.files
            if 'file' not in file:
                return "请选择文件", 400
            file = file['file']
            if file.filename.split('.')[-1] != 'tsv':
                return "文件格式错误", 400
            data = file.read().decode()
            ok, msg = await accountmgr.create_accounts_from_tsv(data)
            return msg, 200 if ok else 400

        @self.api.route('/', methods = ["DELETE"])
        @HttpServer.login_required()
        @HttpServer.wrapaccountmgr()
        async def delete_qq(accountmgr: AccountManager):
            accountmgr.delete_mgr()
            logout_user()
            return "删除QQ成功", 200

        @self.api.route('/account', methods = ["DELETE"])
        @HttpServer.login_required()
        @HttpServer.wrapaccountmgr()
        async def delete_account(accountmgr: AccountManager):
            accountmgr.delete_all_accounts()
            return "删除账号成功", 200

        @self.api.route('/account/sync', methods = ["POST"])
        @HttpServer.login_required()
        @HttpServer.wrapaccountmgr()
        async def sync_account_config(accountmgr: AccountManager):
            data = await request.get_json()
            acc = data.get("alias", "")
            if acc not in accountmgr.accounts():
                return "账号不存在", 400
            async with accountmgr.load(acc) as mgr:
                for ano in accountmgr.accounts():
                    if ano != acc:
                        async with accountmgr.load(ano) as other:
                            other.data.config = mgr.data.config
            return "配置同步成功", 200

        @self.api.route('/account/<string:acc>', methods = ['GET'])
        @HttpServer.login_required()
        @HttpServer.wrapaccountmgr(readonly = True)
        @HttpServer.wrapaccount(readonly=True)
        async def get_account(account: Account):
            return account.generate_info(), 200

        @self.api.route('/account/<string:acc>', methods = ["PUT", "DELETE"])
        @HttpServer.login_required()
        @HttpServer.wrapaccountmgr()
        @HttpServer.wrapaccount()
        async def update_account(account: Account):
            if request.method == "PUT":
                data = await request.get_json()
                if 'username' in data:
                    account.data.username = data['username']
                if 'password' in data and data['password'] != '*' * 8:
                    account.data.password = data['password']
                if 'channel' in data:
                    account.data.channel = data['channel']
                if 'batch_accounts' in data:
                    account.data.batch_accounts = data['batch_accounts']
                return "保存账户信息成功", 200
            elif request.method == "DELETE":
                account.delete()
                return "删除账户信息成功", 200
            else:
                return "", 404

        # ==================== 指令中继 ====================  
        @self.api.route('/account/<string:acc>/command', methods=['POST'])  
        @HttpServer.login_required()  
        @HttpServer.wrapaccountmgr(readonly=True)  
        @HttpServer.wrapaccount()  
        async def command_relay(mgr: Account):  
            from ...server import tool_info  # 延迟导入避免循环依赖  
  
            data = await request.get_json()  
            command = data.get("command", "").strip()  
            if not command:  
                return {"status": "error", "message": "指令为空"}, 200  
  
            # 去掉前缀 #  
            if command.startswith("#"):  
                command = command[1:]  
  
            qq = current_user.auth_id  
            accmgr = mgr._parent  # AccountManager  
  
            # ① 先匹配特殊指令（不在 register_tool 中的）
            for prefix_name, handler in SPECIAL_HANDLERS.items():
                if command.startswith(prefix_name):
                    remaining = command[len(prefix_name):].strip()
                    parts = remaining.split() if remaining else []
                    try:  
                        result = await handler(mgr, parts)  
                        if isinstance(result, dict):  
                            return {  
                                "status": "ok",  
                                "result": {  
                                    "name": result.get("text", ""),  
                                    "log": result.get("text", ""),  
                                    "status": "",  
                                    "image": result.get("image")  
                                }  
                            }, 200  
                        else:  
                            return {"status": "finish", "message": result}, 200
                    except Exception as e:
                        return {"status": "error", "message": f"执行失败: {e}"}, 200

            # ② 再匹配 register_tool 注册的指令
            matched_tool = None
            remaining = ""
            for tool_name, tool in tool_info.items():
                if command.startswith(tool_name):
                    matched_tool = tool
                    remaining = command[len(tool_name):].strip()
                    break

            if not matched_tool:
                return {"status": "error", "message": f"未找到指令: {command.split()[0]}"}, 200

            # 构造伪 BotEvent，解析参数
            parts = remaining.split() if remaining else []
            # 保留原始remaining内容（包括换行符），不要用空格重新连接
            raw_remaining = remaining
            relay_event = RelayBotEvent(qq, parts, raw_remaining)  
  
            try:  
                config = await matched_tool.config_parser(relay_event)  
                if config is None:  
                    config = {}  
            except FinishSignal as e:  
                return {"status": "finish", "message": str(e.msg)}, 200  
            except Exception as e:  
                return {"status": "error", "message": f"参数解析失败: {e}"}, 200  
  
            # 执行指令  
            try:  
                merged = deepcopy(mgr.config)  
                if isinstance(config, dict):  
                    merged.update(config)  
                clan = mgr._parent.secret.clan  
  
                resp = await asyncio.wait_for(  
                    mgr.do_from_key(merged, matched_tool.key, clan),  
                    timeout=300  
                )  
  
                result = resp.get_result()  
                status_str = ""  
                if hasattr(result, 'status'):  
                    status_str = result.status.value if hasattr(result.status, 'value') else str(result.status)  
                  
                image_b64 = None  
                log_text = getattr(result, 'log', '') or ""  
                if '[ex:' in log_text:  
                    try:  
                        import base64, io  
                        img = await drawer.draw_task_result(result)  
                        buf = io.BytesIO()  
                        img.save(buf, format='PNG')  
                        image_b64 = base64.b64encode(buf.getvalue()).decode()  
                    except Exception as e:  
                        logger.error(f"渲染EX装备图片失败: {e}")  
                  
                return {  
                    "status": "ok",  
                    "result": {  
                        "name": getattr(result, 'name', '') or matched_tool.name,  
                        "log": log_text,  
                        "status": status_str,  
                        "image": image_b64  
                    }  
                }, 200  
  
            except FinishSignal as e:  
                return {"status": "finish", "message": str(e.msg)}, 200  
            except asyncio.TimeoutError:  
                return {"status": "error", "message": "执行超时（5分钟）"}, 200  
            except Exception as e:  
                return {"status": "error", "message": f"执行失败: {e}"}, 200
        
        @self.api.route('/account/<string:acc>/<string:modules_key>', methods = ['GET'])
        @HttpServer.login_required()
        @HttpServer.wrapaccountmgr(readonly = True)
        @HttpServer.wrapaccount(readonly= True)
        async def get_modules_config(mgr: Account, modules_key: str):
            return mgr.generate_modules_info(modules_key)

        @self.api.route('/account/<string:acc>/config', methods = ['PUT'])
        @HttpServer.login_required()
        @HttpServer.wrapaccountmgr(readonly = True)
        @HttpServer.wrapaccount()
        async def put_config(mgr: Account):
            data = await request.get_json()
            mgr.data.config.update(data)
            return "配置保存成功", 200

        @self.api.route('/account/<string:acc>/do_daily', methods = ['POST'])  
        @HttpServer.login_required()  
        @HttpServer.wrapaccountmgr(readonly=True)  
        @HttpServer.wrapaccount()  
        async def do_daily(mgr: Account):  
            try:  
                await asyncio.wait_for(mgr.do_daily(mgr._parent.secret.clan), timeout=600)  # 10 min timeout  
            except asyncio.TimeoutError:  
                return "清日常超时，请稍后重试", 504  
            return mgr.generate_result_info(), 200

        @self.api.route('/account/<string:acc>/pjjc_auto_def/start', methods=['POST'])  
        @HttpServer.login_required()  
        async def pjjc_auto_def_start(acc: str):  
            import random  
            import itertools  
            from datetime import datetime as dt  
  
            qq = current_user.auth_id  
  
            if qq in self._auto_def_tasks:  
                return {"status": "error", "message": "已有正在运行的自动换防任务，请先终止"}, 409  
  
            messages = []  
            stop_event = asyncio.Event()  
  
            self._auto_def_tasks[qq] = {  
                "stop_event": stop_event,  
                "acc": acc,  
                "task": None,  
                "messages": messages,  
                "shuffle_count": 0  
            }  
  
            async def auto_def_loop():  
                shuffle_count = 0  
                check_interval = 2  
                try:  
                    from ..core.pcrclient import eLoginStatus  
                    from ..model.common import DeckListData  
                    from ..model.enums import ePartyType  
  
                    # 在后台任务内部自行加载账号，保持上下文在整个循环期间打开  
                    async with usermgr.load(qq, readonly=True) as accountmgr:  
                        async with accountmgr.load(acc) as mgr:  
                            alias = mgr.alias  
                            client = mgr.client  
  
                            # 更新 acc 字段为实际别名  
                            if qq in self._auto_def_tasks:  
                                self._auto_def_tasks[qq]["acc"] = alias  
  
                            await client.activate()  
                            if client.logged == eLoginStatus.NOT_LOGGED or not client.data.ready:  
                                await client.login()  
  
                            history_resp = await client.get_grand_arena_history()  
                            known_log_ids = set()  
                            if history_resp.grand_arena_history_list:  
                                for h in history_resp.grand_arena_history_list:  
                                    known_log_ids.add(h.log_id)  
  
                            messages.append(f"{alias} pjjc自动换防已开启，每{check_interval}秒检测被刺记录")  
  
                            async def do_shuffle():  
                                info = await client.get_grand_arena_info()  
                                limit_info = info.update_deck_times_limit  
                                if limit_info.round_times == limit_info.round_max_limited_times:  
                                    return None, f"已达到换防次数上限{limit_info.round_max_limited_times}，自动换防终止"  
                                if limit_info.daily_times == limit_info.daily_max_limited_times:  
                                    return None, f"已达到每日换防次数上限{limit_info.daily_max_limited_times}，自动换防终止"  
  
                                limit_msg = ""  
                                team_cnt = 3  
                                teams = [list(x) for x in itertools.permutations(range(team_cnt))]  
                                teams = [x for x in teams if all(x[i] != i for i in range(team_cnt))]  
                                ids = random.choice(teams)  
  
                                deck_list = []  
                                for i in range(team_cnt):  
                                    deck_number_src = getattr(ePartyType, f"GRAND_ARENA_DEF_{i + 1}")  
                                    units = client.data.deck_list[deck_number_src]  
                                    units_id = [getattr(units, f"unit_id_{j + 1}") for j in range(5)]  
                                    deck = DeckListData()  
                                    deck.deck_number = getattr(ePartyType, f"GRAND_ARENA_DEF_{ids[i] + 1}")  
                                    deck.unit_list = units_id  
                                    deck_list.append(deck)  
  
                                deck_list.sort(key=lambda x: x.deck_number)  
                                await client.deck_update_list(deck_list)  
  
                                shuffle_msg = '\n'.join([f"队伍{i+1} -> 位置{ids[i]+1}" for i in range(team_cnt)])  
                                result_msg = (  
                                    f"{shuffle_msg}\n"  
                                    f"本轮换防次数{limit_info.round_times + 1}/{limit_info.round_max_limited_times}\n"  
                                    f"今日换防次数{limit_info.daily_times + 1}/{limit_info.daily_max_limited_times}"  
                                )  
                                return ids, result_msg  
  
                            while True:  
                                try:  
                                    await asyncio.wait_for(stop_event.wait(), timeout=check_interval)  
                                    messages.append(f"{alias} 收到终止信号，自动换防已停止，共执行换防{shuffle_count}次")  
                                    client.deactivate()  
                                    return  
                                except asyncio.TimeoutError:  
                                    pass  
  
                                try:  
                                    history_resp = await client.get_grand_arena_history()  
                                    if history_resp.grand_arena_history_list:  
                                        new_attacks = []  
                                        for h in history_resp.grand_arena_history_list:  
                                            if h.log_id not in known_log_ids:  
                                                known_log_ids.add(h.log_id)  
                                                if not h.is_challenge:  
                                                    opponent = h.opponent_user  
                                                    attack_time = dt.fromtimestamp(h.versus_time)  
                                                    new_attacks.append(f"{opponent.user_name}({opponent.viewer_id}) {attack_time}")  
  
                                        if new_attacks:  
                                            attack_msg = "\n".join(new_attacks)  
                                            try:  
                                                result = await do_shuffle()  
                                                if result[0] is None:  
                                                    messages.append(f"检测到被刺：{attack_msg}\n{result[1]}")  
                                                    break  
                                                shuffle_count += 1  
                                                if qq in self._auto_def_tasks:  
                                                    self._auto_def_tasks[qq]["shuffle_count"] = shuffle_count  
                                                  
                                                messages.append(  
                                                    f"检测到被刺：{attack_msg}\n"  
                                                    f"已执行第{shuffle_count}次换防\n{result[1]}\n"  
                                                    f"正在下线并重新上线..."  
                                                )  
                                                  
                                                # 换防后下线  
                                                client.deactivate()  
                                                  
                                                # 重新上线  
                                                await client.activate()  
                                                if client.logged == eLoginStatus.NOT_LOGGED or not client.data.ready:  
                                                    await client.login()  
                                                  
                                                # 重建历史记录基线  
                                                known_log_ids.clear()  
                                                history_resp2 = await client.get_grand_arena_history()  
                                                if history_resp2.grand_arena_history_list:  
                                                    for h2 in history_resp2.grand_arena_history_list:  
                                                        known_log_ids.add(h2.log_id)  
                                                  
                                                messages.append(f"已重新上线，继续检测被刺")  
                                                
                                            except Exception as e:  
                                                messages.append(f"换防出错: {str(e)[:200]}，尝试下线并重新上线...")  
                                                try:  
                                                    client.deactivate()  
                                                    await client.activate()  
                                                    if client.logged == eLoginStatus.NOT_LOGGED or not client.data.ready:  
                                                        await client.login()  
                                                    known_log_ids.clear()  
                                                    history_resp_err = await client.get_grand_arena_history()  
                                                    if history_resp_err.grand_arena_history_list:  
                                                        for h_err in history_resp_err.grand_arena_history_list:  
                                                            known_log_ids.add(h_err.log_id)  
                                                except:  
                                                    messages.append("重新登录失败，自动换防终止")  
                                                    break
  
                                except Exception as e:  
                                    messages.append(f"检查被刺出错: {str(e)[:200]}，尝试下线并重新上线...")  
                                    try:  
                                        client.deactivate()  
                                        await client.activate()  
                                        if client.logged == eLoginStatus.NOT_LOGGED or not client.data.ready:  
                                            await client.login()  
                                        known_log_ids.clear()  
                                        history_resp_err = await client.get_grand_arena_history()  
                                        if history_resp_err.grand_arena_history_list:  
                                            for h_err in history_resp_err.grand_arena_history_list:  
                                                known_log_ids.add(h_err.log_id)  
                                    except:  
                                        messages.append("重新登录失败，自动换防终止")  
                                        break
  
                            client.deactivate()  
                            messages.append(f"{alias} pjjc自动换防已结束，共执行换防{shuffle_count}次")  
  
                except Exception as e:  
                    messages.append(f"自动换防异常终止: {str(e)[:300]}")  
                finally:  
                    self._auto_def_tasks.pop(qq, None)  
  
            task = asyncio.get_event_loop().create_task(auto_def_loop())  
            self._auto_def_tasks[qq]["task"] = task  
  
            return {"status": "ok", "message": f"自动换防已启动，账号: {acc}"}, 200  
  
        @self.api.route('/pjjc_auto_def/stop', methods=['POST'])  
        @HttpServer.login_required()  
        async def pjjc_auto_def_stop():  
            qq = current_user.auth_id  
            if qq in self._auto_def_tasks:  
                self._auto_def_tasks[qq]["stop_event"].set()  
                return {"status": "ok", "message": "已发送终止信号"}, 200  
            else:  
                return {"status": "error", "message": "当前没有正在运行的自动换防任务"}, 404  
  
        @self.api.route('/pjjc_auto_def/status', methods=['GET'])  
        @HttpServer.login_required()  
        async def pjjc_auto_def_status():  
            qq = current_user.auth_id  
            if qq in self._auto_def_tasks:  
                info = self._auto_def_tasks[qq]  
                return {  
                    "running": True,  
                    "acc": info["acc"],  
                    "shuffle_count": info.get("shuffle_count", 0),  
                    "messages": info["messages"]  
                }, 200  
            else:  
                return {"running": False, "messages": []}, 200 
        
        @self.api.route('/account/<string:acc>/daily_result', methods = ['GET'])
        @HttpServer.login_required()
        @HttpServer.wrapaccountmgr(readonly = True)
        @HttpServer.wrapaccount(readonly= True)
        async def daily_result_list(mgr: Account):
            resp = mgr.get_daily_result_list()
            resp = [r.response('/daily/api/account/{}' + '/daily_result/' + str(r.key)) for r in resp]
            return resp, 200

        @self.api.route('/account/<string:acc>/daily_result/<string:key>', methods = ['GET'])
        @HttpServer.login_required()
        @HttpServer.wrapaccountmgr(readonly = True)
        @HttpServer.wrapaccount(readonly= True)
        async def daily_result(mgr: Account, key: str):
            resp_text = request.args.get('text', 'false').lower()
            resp = await mgr.get_daily_result_from_key(key)
            if not resp:
                return "无结果", 404
            if resp_text == 'false':
                img = await drawer.draw_tasks_result(resp)
                bytesio = await drawer.img2bytesio(img, 'webp')
                return await send_file(bytesio, mimetype='image/webp')
            else:
                return resp.to_json(), 200

        @self.api.route('/account/<string:acc>/do_single', methods = ['POST'])
        @HttpServer.login_required()
        @HttpServer.wrapaccountmgr(readonly=True)
        @HttpServer.wrapaccount()
        async def do_single(mgr: Account):
            data = await request.get_json()
            order = data.get("order", "")
            await mgr.do_from_key(deepcopy(mgr.config), order, mgr._parent.secret.clan)
            resp = mgr.get_single_result_list(order)
            resp = [r.response('/daily/api/account/{}' + f'/single_result/{order}/{r.key}') for r in resp]
            return resp, 200

        @self.api.route('/account/<string:acc>/single_result/<string:order>', methods = ['GET'])
        @HttpServer.login_required()
        @HttpServer.wrapaccountmgr(readonly = True)
        @HttpServer.wrapaccount(readonly= True)
        async def single_result_list(mgr: Account, order: str):
            resp = mgr.get_single_result_list(order)
            resp = [r.response('/daily/api/account/{}' + f'/single_result/{order}/{r.key}') for r in resp]
            return resp, 200

        @self.api.route('/account/<string:acc>/single_result/<string:order>/<string:key>', methods = ['GET'])
        @HttpServer.login_required()
        @HttpServer.wrapaccountmgr(readonly = True)
        @HttpServer.wrapaccount(readonly= True)
        async def single_result(mgr: Account, order: str, key: str):
            resp_text = request.args.get('text', 'false').lower()
            resp = await mgr.get_single_result_from_key(order, key)
            if not resp:
                return "无结果", 404

            if resp_text == 'false':
                img = await drawer.draw_task_result(resp)
                bytesio = await drawer.img2bytesio(img, 'webp')
                return await send_file(bytesio, mimetype='image/webp')
            else:
                return resp.to_json(), 200

        @self.api.route('/user', methods = ['GET'])
        @HttpServer.login_required()
        @HttpServer.admin_required()
        async def get_users():
            qids = sorted(list(usermgr.qids()))
            results = []
            for qid in qids:
                async with usermgr.load(qid, readonly=True) as mgr:
                    result = {
                        "qq": qid,
                        "admin": mgr.is_admin(),
                        "clan": mgr.secret.clan,
                        "disabled": mgr.secret.disabled,
                        "account_count": mgr.account_count(),
                    }
                results.append(result)
            return results, 200

        @self.api.route('/user/<string:qid>', methods = ['POST'])
        @HttpServer.login_required()
        @HttpServer.admin_required()
        async def create_user(qid: str):
            data = await request.get_data()
            userdata = UserData.from_json(data)
            if userdata.admin and current_user.auth_id != SUPERUSER:
                # 仅超管可创建管理员
                raise PermissionLimitedException()
            async with usermgr.create(qid, userdata.admin) as mgr:
                mgr.secret = userdata
            return "创建用户成功", 200

        @self.api.route('/user/<string:qid>', methods = ['PUT'])
        @HttpServer.login_required()
        @HttpServer.admin_required()
        async def set_user(qid: str):
            data = await request.get_json()
            async with usermgr.load(qid) as mgr:
                if mgr.is_admin() and current_user.auth_id != SUPERUSER:
                    # 仅超管可更改管理员
                    raise PermissionLimitedException()
                if 'admin' in data:
                    if current_user.auth_id != SUPERUSER:
                        # 仅超管可添加管理员
                        raise PermissionLimitedException()
                    if current_user.auth_id == qid and not data['admin']:
                        return "无法取消自己的管理权限", 403
                    mgr.secret.admin = data['admin']
                if 'disabled' in data:
                    if current_user.auth_id == qid and data['disabled']:
                        return "无法禁用自己", 403
                    mgr.secret.disabled = data['disabled']
                if 'password' in data:
                    mgr.secret.password = data['password']
                if 'clan' in data:
                    mgr.secret.clan = data['clan']
            return "更新用户信息成功", 200

        @self.api.route('/user/<string:qid>', methods = ['DELETE'])
        @HttpServer.login_required()
        @HttpServer.admin_required()
        async def delete_user(qid: str):
            if qid == current_user.auth_id:
                return "无法删除自己", 403
            if qid == SUPERUSER:
                return "不可删除超级管理员", 403
            usermgr.delete(qid)
            return "删除用户成功", 200

        @self.api.route('/query_validate', methods = ['GET'])
        @HttpServer.login_required()
        @HttpServer.wrapaccountmgr(readonly = True)
        async def query_validate(accountmgr: AccountManager):
            if "text/event-stream" not in request.accept_mimetypes:
                return "", 400

            server_id = secrets.token_urlsafe(8)
            self.validate_server[accountmgr.qid] = server_id

            async def send_events(qid, server_id):
                for _ in range(30):
                    if self.validate_server[qid] != server_id:
                        break
                    if qid in validate_dict and validate_dict[qid]:
                        ret = validate_dict[qid].pop().to_json()
                        id = secrets.token_urlsafe(8)
                        yield f'''id: {id}
retry: 1000
data: {ret}\n\n'''
                    else:
                        await asyncio.sleep(1)

            response = await quart.make_response(
                send_events(accountmgr.qid, server_id),
                {
                    'Content-Type': 'text/event-stream',
                    'Cache-Control': 'no-cache',
                    'Transfer-Encoding': 'chunked',
                },
            )
            response.timeout = None
            return response

        @self.api.route('/validate', methods = ['POST'])
        async def validate(): # TODO think to check login or not
            data = await request.get_json()
            if 'id' not in data:
                return "incorrect", 403
            id = data['id']
            validate_ok_dict[id] = ValidateInfo.from_dict(data)
            return "", 200

        @self.api_limit.route('/login/qq', methods = ['POST'])
        @rate_limit(1, timedelta(seconds=1))
        @rate_limit(3, timedelta(minutes=1))
        async def login_qq():
            data = await request.get_json()
            qq = data.get('qq', "")
            password = data.get('password', "")

            if not qq or not password:
                return "请输入QQ和密码", 400
            if not usermgr.validate_password(str(qq), str(password)):
                return "无效的QQ或密码", 400
            if not usermgr.check_enabled(str(qq)):
                return "已到期，请联系管理员", 403
            login_user(AuthUser(qq))
            return "欢迎回来，" + qq, 200

        @self.api_limit.route('/register', methods = ['POST'])
        @rate_limit(1, timedelta(minutes=1))
        async def register():
            if not ALLOW_REGISTER:
                return "请在群里发送 清日常创建", 400

            data = await request.get_json()
            qq = data.get('qq', "")
            password = data.get('password', "")
            if not qq or not password:
                return "请输入QQ和密码", 400
            if self.qq_mod:
                from ...server import is_valid_qq
                if not await is_valid_qq(qq):
                    return "无效的QQ", 400
            usermgr.create(str(qq), str(password))
            login_user(AuthUser(qq))
            return "欢迎回来，" + qq, 200
            

        @self.api_limit.route('/create_daily', methods = ['POST'])  
        @rate_limit(1, timedelta(minutes=1))  
        async def create_daily():  
            data = await request.get_json()  
            qq = data.get('qq', "")  
            password = data.get('password', "")  
            if not qq or not password:  
                return "请输入QQ和密码", 400  
            try:  
                usermgr.create(str(qq), str(password))  
            except Exception as e:  
                return str(e), 400
            login_user(AuthUser(qq))  
            return "欢迎回来，" + qq, 200
        
        @self.api.route('/logout', methods = ['POST'])
        @login_required
        @HttpServer.wrapaccountmgr(readonly = True)
        @rate_limit(1, timedelta(seconds=1))
        async def logout(accountmgr: AccountManager):
            logout_user()
            return "再见, " + accountmgr.qid, 200

        # ===== 指令中继 =====  
        @self.api.route('/account/<string:acc>/command', methods=['POST'])  
        @HttpServer.login_required()  
        @HttpServer.wrapaccountmgr(readonly=True)  
        @HttpServer.wrapaccount()  
        async def relay_command(mgr: Account):  
            from ...server import tool_info  # 延迟导入避免循环依赖  
  
            data = await request.get_json()  
            command: str = (data.get("command", "") or "").strip()  
            if not command:  
                return {"status": "error", "message": "请输入指令"}, 200  
            if command.startswith("#"):  
                command = command[1:]  
  
            qq = current_user.auth_id
            parts = command.split()
            if not parts:
                return {"status": "error", "message": "指令为空"}, 200

            first = parts[0]
            matched_tool = None
            matched_tool_name = None  # 记录匹配的指令名
            for tool_name in sorted(tool_info.keys(), key=len, reverse=True):
                if first.startswith(tool_name):
                    matched_tool = tool_info[tool_name]
                    matched_tool_name = tool_name  # 记录匹配的指令名
                    remainder = first[len(tool_name):]
                    if remainder:
                        parts[0] = remainder
                    else:
                        parts.pop(0)
                    break

            if not matched_tool:
                return {"status": "error", "message": f"未找到指令「{first}」"}, 200

            # 保留原始指令内容（包括换行符），不要用空格重新连接
            raw_remaining = command[len(matched_tool_name):].strip()
            relay_event = RelayBotEvent(qq, parts, raw_remaining)  
  
            try:  
                config = await matched_tool.config_parser(relay_event)  
                if config is None:  
                    config = {}  
            except FinishSignal as e:  
                return {"status": "finish", "message": str(e.msg)}, 200  
            except Exception as e:  
                return {"status": "error", "message": f"参数解析失败: {e}"}, 200  
  
            try:  
                merged = deepcopy(mgr.config)  
                if isinstance(config, dict):  
                    merged.update(config)  
                clan = mgr._parent.secret.clan  
  
                resp = await asyncio.wait_for(  
                    mgr.do_from_key(merged, matched_tool.key, clan),  
                    timeout=300  
                )  
  
                result = resp.get_result()  
                status_str = ""  
                if hasattr(result, 'status'):  
                    status_str = result.status.value if hasattr(result.status, 'value') else str(result.status)  
  
                # 检测 [ex:] 标记，渲染为图片  
                image_b64 = None  
                log_text = getattr(result, 'log', '') or ""  
                if '[ex:' in log_text:  
                    try:  
                        import base64, io  
                        img = await drawer.draw_task_result(result)  
                        buf = io.BytesIO()  
                        img.save(buf, format='PNG')  
                        image_b64 = base64.b64encode(buf.getvalue()).decode()  
                    except Exception as e:  
                        logger.error(f"渲染EX装备图片失败: {e}")  
  
                return {  
                    "status": "ok",  
                    "result": {  
                        "name": getattr(result, 'name', '') or matched_tool.name,  
                        "log": log_text,  
                        "status": status_str,  
                        "image": image_b64  
                    }  
                }, 200  
  
            except FinishSignal as e:  
                return {"status": "finish", "message": str(e.msg)}, 200  
            except asyncio.TimeoutError:  
                return {"status": "error", "message": "执行超时（5分钟）"}, 200  
            except Exception as e:  
                return {"status": "error", "message": f"执行失败: {e}"}, 200  
  
        
        # frontend  
        @self.web.route("/", defaults={"path": ""})  
        @self.web.route("/<path:path>")  
        async def index(path):  
            if os.path.exists(os.path.join(str(self.web.static_folder), path)):  
                return await send_from_directory(str(self.web.static_folder), path, mimetype=("text/javascript" if path.endswith(".js") else None))  
            else:  
                # 读取 index.html 并注入留言板脚本  
                index_path = os.path.join(str(self.web.static_folder), 'index.html')  
                with open(index_path, 'r', encoding='utf-8') as f:  
                    html = f.read()  
                html = html.replace('</body>', MESSAGEBOARD_SCRIPT + '</body>')  
                return html, 200, {'Content-Type': 'text/html; charset=utf-8'}

        def run_forever(self, loop):
            self.quart.register_blueprint(self.app)
            self.quart.run(host=self.host, port=self.port, loop=loop)
            
            
            
            
            
        def _load_messages():  
            if os.path.exists(MESSAGES_PATH):  
                with open(MESSAGES_PATH, 'r', encoding='utf-8') as f:  
                    messages = json.load(f)  
                # 过滤掉超过7天的留言  
                now = _time.time()  
                filtered = []  
                for m in messages:  
                    try:  
                        t = _time.mktime(_time.strptime(m['time'], '%Y-%m-%d %H:%M:%S'))  
                        if now - t < 7 * 86400:  
                            filtered.append(m)  
                    except Exception:  
                        filtered.append(m)  # 解析失败的保留  
                if len(filtered) != len(messages):  
                    _save_messages(filtered)  # 有过期的就顺便清理掉文件  
                return filtered  
            return [] 
          
        def _save_messages(messages):  
            os.makedirs(os.path.dirname(MESSAGES_PATH), exist_ok=True)  
            with open(MESSAGES_PATH, 'w', encoding='utf-8') as f:  
                json.dump(messages, f, ensure_ascii=False)    
            
        @self.api.route('/messages', methods=['GET'])  
        @HttpServer.login_required()  
        async def get_messages():  
            messages = _load_messages()  
            return messages, 200        
            
        @self.api.route('/messages', methods=['POST'])  
        @login_required  
        @rate_limit(1, timedelta(seconds=3))  
        async def post_message():  
            data = await request.get_json()  
            content = data.get('content', '').strip()  
            image = data.get('image', '').strip()  
            if not content and not image:  
                return "留言内容不能为空", 400  
            if len(content) > 500:  
                return "留言内容不能超过500字", 400  
            # 验证图片文件名是否合法  
            if image:  
                if '/' in image or '\\' in image or '..' in image:  
                    return "无效的图片文件名", 400  
                if not os.path.exists(os.path.join(IMG_DIR, image)):  
                    return "图片不存在", 400  
            messages = _load_messages()  
            msg = {  
                'id': secrets.token_urlsafe(8),  
                'qq': current_user.auth_id,  
                'content': content,  
                'time': _time.strftime('%Y-%m-%d %H:%M:%S')  
            }  
            if image:  
                msg['image'] = image  
            messages.append(msg)  
            if len(messages) > 100:  
                messages = messages[-100:]  
            _save_messages(messages)  
            return msg, 200  
            
        @self.api.route('/messages/<string:msg_id>', methods=['DELETE'])  
        @HttpServer.login_required()  
        @HttpServer.admin_required()  
        async def delete_message(msg_id: str):  
            messages = _load_messages()  
            for m in messages:  
                if m['id'] == msg_id and m.get('image'):  
                    imgpath = os.path.join(IMG_DIR, m['image'])  
                    if os.path.exists(imgpath):  
                        os.remove(imgpath)  
            messages = [m for m in messages if m['id'] != msg_id]  
            _save_messages(messages)  
            return "删除成功", 200

        IMG_DIR = os.path.join(CACHE_DIR, 'msg_images')  
  
        @self.api.route('/messages/upload', methods=['POST'])  
        @login_required  
        @rate_limit(1, timedelta(seconds=3))  
        async def upload_msg_image():  
            files = await request.files  
            img = files.get('image')  
            if not img:  
                return "没有上传图片", 400  
            # 限制 2MB  
            data = img.read()  
            if len(data) > 2 * 1024 * 1024:  
                return "图片不能超过2MB", 400  
            # 只允许常见图片格式  
            ext = os.path.splitext(img.filename)[1].lower()  
            if ext not in ('.jpg', '.jpeg', '.png', '.gif', '.webp'):  
                return "不支持的图片格式", 400  
            os.makedirs(IMG_DIR, exist_ok=True)  
            filename = secrets.token_urlsafe(12) + ext  
            filepath = os.path.join(IMG_DIR, filename)  
            with open(filepath, 'wb') as f:  
                f.write(data)  
            return {"filename": filename}, 200
           
        @self.api.route('/messages/image/<string:filename>', methods=['GET'])  
        @login_required  
        async def get_msg_image(filename: str):  
            # 防止路径穿越  
            if '/' in filename or '\\' in filename or '..' in filename:  
                return "无效文件名", 400  
            filepath = os.path.join(IMG_DIR, filename)  
            if not os.path.exists(filepath):  
                return "图片不存在", 404  
            return await send_file(filepath)       

                    