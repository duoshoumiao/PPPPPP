import os
import shutil
from hoshino import log, get_bot

logger = log.new_logger('clean_autopcr_cache')

# 定义要清理的目录路径
CACHE_POOL_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), 
                              '../../modules/autopcr/cache/pool')

def clean_cache_pool():
    """清理autopcr的pool缓存文件夹"""
    try:
        if os.path.exists(CACHE_POOL_PATH):
            # 判断是否为目录
            if os.path.isdir(CACHE_POOL_PATH):
                # 递归删除目录及其内容
                shutil.rmtree(CACHE_POOL_PATH)
                logger.info(f"成功删除缓存目录: {CACHE_POOL_PATH}")
                
                # 可选：删除后重新创建空目录
                os.makedirs(CACHE_POOL_PATH, exist_ok=True)
                logger.info(f"重新创建空缓存目录: {CACHE_POOL_PATH}")
            else:
                logger.warning(f"{CACHE_POOL_PATH} 不是一个目录，无法删除")
        else:
            logger.info(f"缓存目录不存在: {CACHE_POOL_PATH}")
            
    except Exception as e:
        logger.error(f"清理缓存目录时发生错误: {str(e)}")

# 在插件加载时执行清理操作
clean_cache_pool()

# 插件元信息
__plugin_name__ = '自动清理autopcr缓存'
__plugin_usage__ = '启动时自动删除autopcr模块下的cache/pool文件夹'
