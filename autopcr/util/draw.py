import os, io, re  
from typing import Dict, List  
from PIL import Image, ImageFont, ImageDraw  
from ..constants import DATA_DIR, CACHE_DIR  
from .draw_table import grid2img, json2img  
from pathlib import Path  
  
class Drawer():  
  
    font_path = os.path.join(DATA_DIR, "微软雅黑.ttf")  
    font=ImageFont.truetype(font_path, size=30)  
  
    def dark_color(self):  
        return {  
            'bg': '#222529',  
            'odd_row_cell_bg': '#3A3A3C',  
            'even_row_cell_bg': '#2C2C2E',  
            'header_bg': '#1C1C1E',  
            'font': '#DFE2E6',  
            'rowline': 'white',  
            'colline': 'white',  
            '成功': '#255035',  
            '跳过': '#35778D',  
            '警告': '#FF8C00',  
            '中止': '#937526',  
            '错误': '#79282C',  
            '致命': '#8B0000',  
        }  
  
    def light_color(self):  
        return {  
            'bg': 'white',  
            'odd_row_cell_bg': '#EEEEEE',  
            'even_row_cell_bg': 'white',  
            'header_bg': '#C8C8C9',  
            'font': 'black',  
            'rowline': 'black',  
            'colline': 'black',  
            '成功': '#E1FFB5',  
            '跳过': '#C8D6FA',  
            '警告': '#FFD700',  
            '中止': 'yellow',  
            '错误': 'red',  
            '致命': '#8B0000',  
        }  
  
    def color(self):  
        from datetime import datetime  
        now = datetime.now()  
        is_night = not(now.hour < 18 and now.hour > 7)  
        if is_night:  
            return self.dark_color()  
        else:  
            return self.light_color()  
  
    async def draw(self, header: List[str], content: List[List[str]]) -> Image.Image:  
        img = grid2img(content, header, colors=self.color(), font=self.font, stock=True)  
        return img  
  
    async def draw_json(self, titles: List[str], records: List[Dict]) -> Image.Image:  
        img = json2img(records, titles, colors=self.color(), font=self.font, stock=True)  
        return img  
  
    async def draw_tasks_result(self, data: "TaskResult") -> Image.Image:  
        content = []  
        header = ["序号", "名字","配置","状态","结果"]  
        result = data.result  
        cnt = 0  
        for key in data.order:  
            value = result[key]  
            if value.log == "功能未启用":  
                continue  
            cnt += 1  
            content.append([str(cnt), value.name.strip(), value.config.strip(), "#"+value.status.value, value.log.strip()])  
        img = await self.draw(header, content)  
        return img  
  
    async def draw_task_result(self, data: "ModuleResult") -> Image.Image:  
        # 检测是否包含EX装备图标标记  
        if '[ex:' in data.log:  
            return await self.draw_ex_equip_result(data)  
        if data.table and data.table.data and len(data.table.data) > 1:  
            return await self.draw_task_table(data)  
        content = [["配置", data.config.strip()], ["状态", f"#{data.status.value}"], ["结果", data.log.strip()]]  
        header = ["名字", data.name.strip()]  
        img = await self.draw(header, content)  
        return img  
  
    async def draw_ex_equip_result(self, data: "ModuleResult") -> Image.Image:  
        """渲染带EX装备图标的预览图"""  
        from ..db.imagemgr import instance as imgmgr  
  
        colors = self.color()  
        font = self.font  
  
        ICON_SIZE = 144  
        LINE_HEIGHT = max(ICON_SIZE + 8, 44)  
        HEADER_LINE_HEIGHT = 40  
        LEFT_MARGIN = 12  
        ICON_TEXT_GAP = 8  
        TOP_MARGIN = 10  
        RIGHT_MARGIN = 20  
  
        # 解析log，提取 [ex:XXXXXXX] 标记  
        log_text = data.log.strip()  
        raw_lines = log_text.split('\n')  
  
        ex_pattern = re.compile(r'^\[ex:(\d+)\](.*)')  
  
        parsed_lines = []  # list of (equip_id 或 None, 显示文本)  
        for line in raw_lines:  
            m = ex_pattern.match(line)  
            if m:  
                equip_id = int(m.group(1))  
                text = m.group(2)  
                parsed_lines.append((equip_id, text))  
            else:  
                parsed_lines.append((None, line))  
  
        # 加载图标（使用 imagemgr，会自动下载缓存）  
        icon_cache = {}  
        for equip_id, _ in parsed_lines:  
            if equip_id and equip_id not in icon_cache:  
                try:  
                    icon = await imgmgr.ex_equip_icon(equip_id)  
                    if icon:  
                        icon_cache[equip_id] = icon  
                except Exception:  
                    pass  
  
        # 头部信息（config 可能有多行，逐行拆分）  
        header_texts = [f"【{data.name.strip()}】"]  
        for line in data.config.strip().split('\n'):  
            line = line.strip()  
            if line:  
                header_texts.append(line)
  
        # 计算画布尺寸  
        dummy_img = Image.new('RGB', (1, 1))  
        dummy_draw = ImageDraw.Draw(dummy_img)  
  
        max_width = 0  
        for text in header_texts:  
            bbox = dummy_draw.textbbox((0, 0), text, font=font)  
            max_width = max(max_width, bbox[2] - bbox[0])  
  
        for equip_id, text in parsed_lines:  
            bbox = dummy_draw.textbbox((0, 0), text, font=font)  
            tw = bbox[2] - bbox[0]  
            line_width = LEFT_MARGIN + ICON_SIZE + ICON_TEXT_GAP + tw + RIGHT_MARGIN  
            max_width = max(max_width, line_width)  
  
        canvas_width = int(max_width + LEFT_MARGIN + RIGHT_MARGIN)  
        canvas_height = int(  
            TOP_MARGIN +  
            len(header_texts) * HEADER_LINE_HEIGHT +  
            10 +  
            len(parsed_lines) * LINE_HEIGHT +  
            TOP_MARGIN  
        )  
  
        bg_color = colors['bg']  
        font_color = colors['font']  
  
        canvas = Image.new('RGB', (canvas_width, canvas_height), bg_color)  
        draw = ImageDraw.Draw(canvas)  
  
        # 绘制头部  
        y = TOP_MARGIN  
        for text in header_texts:  
            draw.text((LEFT_MARGIN, y), text, font=font, fill=font_color)  
            y += HEADER_LINE_HEIGHT  
  
        # 分隔线  
        y += 5  
        draw.line([(LEFT_MARGIN, y), (canvas_width - RIGHT_MARGIN, y)], fill=font_color)  
        y += 5  
  
        # 绘制日志行（带图标）  
        for equip_id, text in parsed_lines:  
            icon_img = icon_cache.get(equip_id) if equip_id else None  
  
            if icon_img:  
                resized = icon_img.copy().resize(  
                    (ICON_SIZE, ICON_SIZE),  
                    Image.LANCZOS if hasattr(Image, 'LANCZOS') else Image.ANTIALIAS  
                )  
                icon_y = y + (LINE_HEIGHT - ICON_SIZE) // 2  
                if resized.mode == 'RGBA':  
                    canvas.paste(resized, (LEFT_MARGIN, icon_y), resized)  
                else:  
                    canvas.paste(resized, (LEFT_MARGIN, icon_y))  
                text_x = LEFT_MARGIN + ICON_SIZE + ICON_TEXT_GAP  
            else:  
                # 没有图标的行，文本也从同一位置开始（保持对齐）  
                text_x = LEFT_MARGIN + ICON_SIZE + ICON_TEXT_GAP  
  
            bbox = draw.textbbox((0, 0), text, font=font)  
            text_h = bbox[3] - bbox[1]  
            text_y = y + (LINE_HEIGHT - text_h) // 2  
            draw.text((text_x, text_y), text, font=font, fill=font_color)  
            y += LINE_HEIGHT  
  
        return canvas  
  
    async def draw_task_table(self, data: "ModuleResult") -> Image.Image:  
        content = data.table.data  
        header = data.table.header  
        img = await self.draw_json(header, content)  
        return img  
  
    async def draw_msgs(self, msgs: List[str]) -> Image.Image:  
        content = [[msg] for msg in msgs]  
        img = await self.draw(["结果"], content)  
        return img  
  
    async def horizon_concatenate(self, images_path: List[str]):  
        images = [Image.open(i) for i in images_path]  
        widths, heights = zip(*(i.size  for i in images))  
  
        max_height = max(heights)  
        total_widths = sum(widths)  
  
        new_image = Image.new('RGB', (total_widths, max_height))  
  
        x_offset = 0  
        for img in images:  
            new_image.paste(img, (x_offset, 0))  
            x_offset += img.size[0]  
  
        return new_image  
      
    async def img2bytesio(self, img: Image.Image, format: str = 'JPEG') -> io.BytesIO:  
        img_byte_arr = io.BytesIO()  
        img.save(img_byte_arr, format=format)  
        img_byte_arr.seek(0)  
        return img_byte_arr  
  
instance = Drawer()