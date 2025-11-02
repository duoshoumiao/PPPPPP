from ...util.linq import flow
from ...model.common import ExtraEquipChangeSlot, ExtraEquipChangeUnit, InventoryInfoPost
from ..modulebase import *
from ..config import *
from ...core.pcrclient import pcrclient
from ...model.error import *
from ...db.database import db
from ...model.enums import *
from collections import Counter

@name('强化EX装')
@default(True)
@booltype('ex_equip_enhance_view', '看消耗', True)
@inttype('ex_equip_enhance_max_num', '满强化个数', 5, list(range(-1, 51)))
@MultiChoiceConfig('ex_equip_enhance_up_kind', '强化种类', [], ['粉', '会战金', '普通金', '会战银'])
@description('仅使用强化PT强化至当前突破满星，不考虑突破。强化个数指同类满强化EX装超过阈值则不强化，-1表示不限制，看消耗指观察消耗资源情况，实际不执行强化')
class ex_equip_enhance_up(Module):
    async def do_task(self, client: pcrclient):
        use_ex_equip = {ex_slot.serial_id: [unit.id, frame, ex_slot.slot]
                        for unit in client.data.unit.values() 
                        for frame, ex_slots in enumerate([unit.ex_equip_slot, unit.cb_ex_equip_slot], start=1)
                        for ex_slot in ex_slots if ex_slot.serial_id != 0}

        ex_equip_enhance_up_kind = self.get_config('ex_equip_enhance_up_kind')
        ex_equip_enhance_max_nun = self.get_config('ex_equip_enhance_max_num')
        ex_equip_enhance_view = self.get_config('ex_equip_enhance_view')

        consider_ex_equips = flow(client.data.ex_equips.values()) \
                .where(lambda ex: 
                       '粉' in ex_equip_enhance_up_kind and db.get_ex_equip_rarity(ex.ex_equipment_id) == 4 \
                or '会战金' in ex_equip_enhance_up_kind and db.get_ex_equip_rarity(ex.ex_equipment_id) == 3 and db.is_clan_ex_equip((eInventoryType.ExtraEquip, ex.ex_equipment_id)) \
                or '普通金' in ex_equip_enhance_up_kind and db.get_ex_equip_rarity(ex.ex_equipment_id) == 3 and not db.is_clan_ex_equip((eInventoryType.ExtraEquip, ex.ex_equipment_id)) \
                or '会战银' in ex_equip_enhance_up_kind and db.get_ex_equip_rarity(ex.ex_equipment_id) == 2 and db.is_clan_ex_equip((eInventoryType.ExtraEquip, ex.ex_equipment_id))) \
                .to_list()

        consider_ex_equips.sort(key=lambda ex: (ex.rank, ex.ex_equipment_id), reverse=True)

        ex_equips_max_star_cnt = Counter()

        enhanceup_equip_cnt = 0
        consume_equip_pt = 0
        cost_mana = 0
        for equip in consider_ex_equips:
            max_star = db.get_ex_equip_max_star(equip.ex_equipment_id, equip.rank)
            cur_star = db.get_ex_equip_star_from_pt(equip.ex_equipment_id, equip.enhancement_pt)
            if cur_star >= max_star:
                ex_equips_max_star_cnt[equip.ex_equipment_id] += 1
                continue
            if ex_equip_enhance_max_nun != -1 and ex_equips_max_star_cnt[equip.ex_equipment_id] >= ex_equip_enhance_max_nun:
                continue
            demand_pt = db.get_ex_equip_enhance_pt(equip.ex_equipment_id, equip.enhancement_pt, max_star)
            if not ex_equip_enhance_view and client.data.get_inventory(db.ex_pt) < demand_pt:
                self._log(f"强化PT不足{demand_pt}，无法强化EX装")
                break

            demand_mana = db.get_ex_equip_enhance_mana(equip.ex_equipment_id, equip.enhancement_pt, max_star)
            if not ex_equip_enhance_view and not await client.prepare_mana(demand_mana):
                self._log(f"mana数不足{demand_mana}，无法强化EX装")
                break

            enhanceup_equip_cnt += 1
            consume_equip_pt += demand_pt
            cost_mana += demand_mana

            ex_equips_max_star_cnt[equip.ex_equipment_id] += 1

            unit_id, frame, slot = use_ex_equip.get(equip.serial_id, [0, 0, 0])
            if ex_equip_enhance_view:
                continue
            await client.equipment_enhance_ex(
                unit_id=unit_id,
                serial_id=equip.serial_id,
                frame=frame,
                slot=slot,
                before_enhancement_pt=equip.enhancement_pt,
                after_enhancement_pt=equip.enhancement_pt + demand_pt,
                consume_gold=demand_mana,
                from_view=2,
                item_list=[
                    InventoryInfoPost(type = db.ex_pt[0], id = db.ex_pt[1], count = demand_pt)
                ],
                consume_ex_serial_id_list=[],
            )

        if enhanceup_equip_cnt:
            if ex_equip_enhance_view:
                self._log(f"需消耗{consume_equip_pt}强化PT和{cost_mana} mana来强化{enhanceup_equip_cnt}个EX装")
                self._log(f"当前强化PT {client.data.get_inventory(db.ex_pt)}, mana {client.data.get_inventory(db.mana)}")
            else:
                self._log(f"消耗了{consume_equip_pt}强化PT和{cost_mana}mana，强化了{enhanceup_equip_cnt}个EX装")
        else:
            raise SkipError("没有可强化的EX装")

@name('合成EX装')
@default(True)
@inttype('ex_equip_rank_max_num', '满突破个数', 5, list(range(-1, 51)))
@MultiChoiceConfig('ex_equip_rank_up_kind', '合成种类', [], ['粉', '会战金', '普通金', '会战银'])
@description('合成忽略已装备和锁定的EX装，满突破个数指同类满突破EX装超过阈值则不突破，-1表示不限制')
class ex_equip_rank_up(Module):
    async def do_task(self, client: pcrclient):
        use_ex_equip = {ex_slot.serial_id: [unit.id, frame, ex_slot.slot]
                        for unit in client.data.unit.values() 
                        for frame, ex_slots in enumerate([unit.ex_equip_slot, unit.cb_ex_equip_slot], start=1)
                        for ex_slot in ex_slots if ex_slot.serial_id != 0}

        ex_equip_rank_up_kind = self.get_config('ex_equip_rank_up_kind')
        ex_equip_rank_max_num = self.get_config('ex_equip_rank_max_num')

        consider_ex_equips = flow(client.data.ex_equips.values()) \
                .where(lambda ex: ex.protection_flag != 2) \
                .where(lambda ex: 
                       '粉' in ex_equip_rank_up_kind and db.get_ex_equip_rarity(ex.ex_equipment_id) == 4 \
                or '会战金' in ex_equip_rank_up_kind and db.get_ex_equip_rarity(ex.ex_equipment_id) == 3 and db.is_clan_ex_equip((eInventoryType.ExtraEquip, ex.ex_equipment_id)) \
                or '普通金' in ex_equip_rank_up_kind and db.get_ex_equip_rarity(ex.ex_equipment_id) == 3 and not db.is_clan_ex_equip((eInventoryType.ExtraEquip, ex.ex_equipment_id)) \
                or '会战银' in ex_equip_rank_up_kind and db.get_ex_equip_rarity(ex.ex_equipment_id) == 2 and db.is_clan_ex_equip((eInventoryType.ExtraEquip, ex.ex_equipment_id))) \
                .to_list()

        zero_rank_ex = flow(consider_ex_equips) \
                    .where(lambda ex: ex.serial_id not in use_ex_equip and ex.rank == 0) \
                    .group_by(lambda ex: ex.ex_equipment_id) \
                    .to_dict(lambda ex: ex.key, lambda ex: ex.to_list())

        ex_equips_max_rank_cnt = Counter(flow(client.data.ex_equips.values()) \
                .where(lambda ex: ex.rank == db.get_ex_equip_max_rank(ex.ex_equipment_id)) \
                .group_by(lambda ex: ex.ex_equipment_id) \
                .to_dict(lambda ex: ex.key, lambda ex: ex.count()))

        rankup_equip_cnt = 0
        consume_equip_cnt = 0
        cost_mana = 0
        for equip in consider_ex_equips:
            if equip.serial_id not in client.data.ex_equips:
                continue
            max_rank = db.get_ex_equip_max_rank(equip.ex_equipment_id)
            if equip.rank >= max_rank:
                continue
            if ex_equip_rank_max_num != -1 and ex_equips_max_rank_cnt[equip.ex_equipment_id] >= ex_equip_rank_max_num:
                continue
            demand = max_rank - equip.rank
            use_series = flow(zero_rank_ex.get(equip.ex_equipment_id, [])) \
                .where(lambda ex: ex.serial_id != equip.serial_id 
                       and ex.serial_id in client.data.ex_equips 
                       and client.data.ex_equips[ex.serial_id].rank == 0) \
                .take(demand) \
                .select(lambda ex: ex.serial_id) \
                .to_list()

            if use_series:
                rankup_equip_cnt += 1
                consume_equip_cnt += len(use_series)
                final_rank = equip.rank + len(use_series)
                mana = db.get_ex_equip_rankup_cost(equip.ex_equipment_id, equip.rank, final_rank)
                cost_mana += mana
                if not await client.prepare_mana(mana):
                    self._log(f"mana数不足{mana}，无法合成EX装")
                    break
                unit_id, frame, slot = use_ex_equip.get(equip.serial_id, [0, 0, 0])
                await client.equipment_rankup_ex(
                    serial_id=equip.serial_id,
                    unit_id=unit_id,
                    frame=frame,
                    slot=slot,
                    before_rank=equip.rank,
                    after_rank=final_rank,
                    consume_gold=mana,
                    from_view=2,
                    item_list=[],
                    consume_ex_serial_id_list=use_series
                )
                if final_rank == max_rank:
                    ex_equips_max_rank_cnt[equip.ex_equipment_id] += 1


        if rankup_equip_cnt:
            self._log(f"消耗了{consume_equip_cnt}个零星EX装和{cost_mana}mana，合成了{rankup_equip_cnt}个EX装")
        else:
            raise SkipError("没有可合成的EX装")


@name('撤下会战EX装')
@default(True)
@description('')
class remove_cb_ex_equip(Module):
    async def do_task(self, client: pcrclient):
        ex_cnt = 0
        unit_cnt = 0
        forbidden = set(client.data.user_clan_battle_ex_equip_restriction.keys())
        no_remove_for_forbidden = 0
        for unit_id in client.data.unit:
            unit = client.data.unit[unit_id]
            exchange_list = []
            for ex_equip in unit.cb_ex_equip_slot:
                if ex_equip.serial_id != 0 and ex_equip.serial_id not in forbidden:
                    exchange_list.append(ExtraEquipChangeSlot(slot=ex_equip.slot, serial_id=0))
                    ex_cnt += 1
                elif ex_equip.serial_id in forbidden:
                    no_remove_for_forbidden += 1

            if exchange_list:
                unit_cnt += 1
                await client.unit_equip_ex([ExtraEquipChangeUnit(
                        unit_id=unit_id, 
                        ex_equip_slot = None,
                        cb_ex_equip_slot=exchange_list)])
        if ex_cnt:
            msg = f"（{no_remove_for_forbidden}个因会战CD未撤下）" if no_remove_for_forbidden else ""
            self._log(f"撤下了{unit_cnt}个角色的{ex_cnt}个会战EX装备{msg}")
        else:
            raise SkipError("所有会战EX装备均已撤下")


## add: 撤下普通ex装
@name('撤下普通EX装')
@default(True)
@description('')
class remove_normal_ex_equip(Module):
    async def do_task(self, client: pcrclient):
        ex_cnt = 0
        unit_cnt = 0
        for unit_id in client.data.unit:
            unit = client.data.unit[unit_id]
            exchange_list = []
            for ex_equip in unit.ex_equip_slot:
                if ex_equip.serial_id != 0:
                    exchange_list.append(ExtraEquipChangeSlot(slot=ex_equip.slot, serial_id=0))
                    ex_cnt += 1

            if exchange_list:
                unit_cnt += 1
                await client.unit_equip_ex([ExtraEquipChangeUnit(
                        unit_id=unit_id, 
                        ex_equip_slot=exchange_list,
                        cb_ex_equip_slot=None)])
        if ex_cnt:
            self._log(f"撤下了{unit_cnt}个角色的{ex_cnt}个普通EX装备")
        else:
            raise SkipError("所有普通EX装备均已撤下")

# add: 计算已有角色最佳3星ex装备
# 每个角色有三个槽，通过unit_ex_equipment_slot、ex_equipment_data可以找到每个槽能够使用的多个装备，通过calc_unit_power计算装上ex装备增加的战力倒序，获取最佳3星ex，以及次佳与最佳的差值。目前的calc_unit_attribute只能获取到未添加ex装备的战力，如果装上ex装备，需要在白板unit_attribute上加上"ex_equipment_data"的对应max_xxx值（如果是100的倍数需要加上百分之几，如200就加2%，如果不是就直接加上原数字）。装备显示成名称。

@name('计算最佳3星EX装备')
@default(False)
@description('计算已有角色每个槽位的最佳3星EX装备推荐')
@booltype('auto_equip', '自动装备', False)
class calc_best_3star_ex_equip(Module):
    async def do_task(self, client: pcrclient):
        auto_equip: bool = self.get_config('auto_equip')
        results = []
        total_best_power_increase = 0  # 统计所有最佳装备的战力提升总和
        all_slot_data = {}  # 存储每个角色每个槽位的所有装备选择: {(unit_id, slot): [(ex_id, power), ...]}
        
        for unit_id in client.data.unit:
            unit = client.data.unit[unit_id]
            unit_name = db.get_unit_name(unit_id)
            
            # 获取角色当前战力（基础战力，参考successful example）
            base_power = client.data.get_unit_power(unit_id)
            
            # 获取角色基础属性（用于计算增强后的战力）
            base_attr = db.calc_unit_attribute(unit, client.data.read_story_ids)
            
            # 计算每个槽位的最佳EX装备（只处理普通EX槽位1-3）
            for slot in range(3):  # 只处理槽位1-3，槽位4-6是会战EX
                slot_recommendations = []
                
                # 获取该槽位可用的EX装备
                available_ex_equips = []
                if unit_id in db.unit_ex_equipment_slot:
                    slot_data = db.unit_ex_equipment_slot[unit_id]
                    # 获取槽位的种类号
                    category = None
                    if slot == 0:  # 槽位1
                        category = slot_data.slot_category_1
                    elif slot == 1:  # 槽位2
                        category = slot_data.slot_category_2
                    elif slot == 2:  # 槽位3
                        category = slot_data.slot_category_3
                    
                    # 在ex_equipment_data中查找匹配该种类的所有装备ID
                    if category is not None:
                        available_ex_equips = [ex_id for ex_id, ex_data in db.ex_equipment_data.items() 
                                             if ex_data.category == category]
                
                if not available_ex_equips:
                    continue
                    
                for ex_equip_id in available_ex_equips:
                    # 只考虑3星品质的EX装备
                    if db.get_ex_equip_rarity(ex_equip_id) != 3:
                        continue
                        
                    # 获取EX装备数据
                    ex_data = db.ex_equipment_data[ex_equip_id]
                    
                    # 计算装备该EX装备后的属性
                    enhanced_attr = {
                        'hp': base_attr.hp,
                        'atk': base_attr.atk,
                        'def_': base_attr.def_,
                        'magic_str': base_attr.magic_str,
                        'magic_def': base_attr.magic_def,
                        'physical_critical': base_attr.physical_critical,
                        'magic_critical': base_attr.magic_critical,
                        'dodge': base_attr.dodge,
                        'accuracy': base_attr.accuracy,
                        'energy_recovery_rate': base_attr.energy_recovery_rate,
                        'hp_recovery_rate': base_attr.hp_recovery_rate,
                        'energy_reduce_rate': base_attr.energy_reduce_rate
                    }
                    
                    # 根据注释说明，添加EX装备属性
                    for attr_name in ['max_hp', 'max_atk', 'max_def', 'max_magic_str', 
                                     'max_magic_def', 'max_physical_critical', 'max_magic_critical',
                                     'max_dodge', 'max_accuracy', 'max_energy_recovery_rate',
                                     'max_hp_recovery_rate', 'max_energy_reduce_rate']:
                        ex_value = getattr(ex_data, attr_name, 0)
                        if ex_value > 0:
                            # 转换属性名：max_hp -> hp, max_def -> def_
                            base_attr_name = attr_name.replace('max_', '')
                            if base_attr_name == 'def':
                                base_attr_name = 'def_'
                            
                            base_value = enhanced_attr.get(base_attr_name, 0)
                            if ex_value % 100 == 0 and ex_value >= 100:
                                # 百分比属性
                                enhanced_attr[base_attr_name] = float(base_value) * (1 + ex_value / 10000)
                            else:
                                # 固定数值属性
                                enhanced_attr[base_attr_name] = float(base_value) + ex_value
                    
                    # 计算装备后的战力 (属性值与系数相乘求和)
                    coefficient = db.unit_status_coefficient[1]
                    
                    # 使用_coefficient形式的属性名，并转换为float避免Decimal类型冲突
                    coeff_hp = float(coefficient.hp_coefficient)
                    coeff_atk = float(coefficient.atk_coefficient)
                    coeff_def = float(coefficient.def_coefficient)
                    coeff_magic_str = float(coefficient.magic_str_coefficient)
                    coeff_magic_def = float(coefficient.magic_def_coefficient)
                    coeff_physical_critical = float(coefficient.physical_critical_coefficient)
                    coeff_magic_critical = float(coefficient.magic_critical_coefficient)
                    coeff_dodge = float(coefficient.dodge_coefficient)
                    coeff_accuracy = float(coefficient.accuracy_coefficient)
                    coeff_energy_recovery_rate = float(coefficient.energy_recovery_rate_coefficient)
                    coeff_hp_recovery_rate = float(coefficient.hp_recovery_rate_coefficient)
                    coeff_energy_reduce_rate = float(coefficient.energy_reduce_rate_coefficient)
                    aaa = float(base_attr.hp) * coeff_hp
                    # 计算基础战力
                    base_attr_power = (
                        float(base_attr.hp) * coeff_hp +
                        float(base_attr.atk) * coeff_atk +
                        float(base_attr.def_) * coeff_def +
                        float(base_attr.magic_str) * coeff_magic_str +
                        float(base_attr.magic_def) * coeff_magic_def +
                        float(base_attr.physical_critical) * coeff_physical_critical +
                        float(base_attr.magic_critical) * coeff_magic_critical +
                        float(base_attr.dodge) * coeff_dodge +
                        float(base_attr.accuracy) * coeff_accuracy +
                        float(base_attr.energy_recovery_rate) * coeff_energy_recovery_rate +
                        float(base_attr.hp_recovery_rate) * coeff_hp_recovery_rate +
                        float(base_attr.energy_reduce_rate) * coeff_energy_reduce_rate
                    )
                    
                    # 计算增强后战力
                    power_with_ex = (
                        float(enhanced_attr['hp']) * coeff_hp +
                        float(enhanced_attr['atk']) * coeff_atk +
                        float(enhanced_attr['def_']) * coeff_def +
                        float(enhanced_attr['magic_str']) * coeff_magic_str +
                        float(enhanced_attr['magic_def']) * coeff_magic_def +
                        float(enhanced_attr['physical_critical']) * coeff_physical_critical +
                        float(enhanced_attr['magic_critical']) * coeff_magic_critical +
                        float(enhanced_attr['dodge']) * coeff_dodge +
                        float(enhanced_attr['accuracy']) * coeff_accuracy +
                        float(enhanced_attr['energy_recovery_rate']) * coeff_energy_recovery_rate +
                        float(enhanced_attr['hp_recovery_rate']) * coeff_hp_recovery_rate +
                        float(enhanced_attr['energy_reduce_rate']) * coeff_energy_reduce_rate
                    )
                    
                    power_increase = power_with_ex - base_attr_power
                    
                    ex_name = ex_data.name
                    slot_recommendations.append((ex_equip_id, ex_name, int(power_increase)))
                
                # 按战力增加值排序
                slot_recommendations.sort(key=lambda x: x[2], reverse=True)
                
                # 存储该槽位的所有装备选择
                if slot_recommendations:
                    all_slot_data[(unit_id, slot + 1)] = [(ex_id, power) for ex_id, ex_name, power in slot_recommendations]
                
                if len(slot_recommendations) >= 3:
                    top3 = slot_recommendations[:3]
                    best_power = top3[0][2]  # 最佳装备的战力
                    
                    result_text = f"{unit_name} 槽位{slot+1}: "
                    for i, (ex_id, ex_name, power) in enumerate(top3):
                        rank_name = ["最佳", "次佳", "第三"][i]
                        power_diff = power - best_power  # 相对于最佳的差值
                        if power_diff == 0:
                            result_text += f"{rank_name}={ex_name}(0)"
                        else:
                            result_text += f"{rank_name}={ex_name}({power_diff})"
                        if i < len(top3) - 1:
                            result_text += ", "
                    results.append(result_text)
                    # 累加最佳装备的战力提升
                    total_best_power_increase += best_power
                elif len(slot_recommendations) == 2:
                    best, second = slot_recommendations[:2]
                    power_diff = second[2] - best[2]
                    results.append(f"{unit_name} 槽位{slot+1}: 最佳={best[1]}(0), 次佳={second[1]}({power_diff})")
                    # 累加最佳装备的战力提升
                    total_best_power_increase += best[2]
                elif len(slot_recommendations) == 1:
                    best = slot_recommendations[0]
                    results.append(f"{unit_name} 槽位{slot+1}: 最佳={best[1]}(0)")
                    # 累加最佳装备的战力提升
                    total_best_power_increase += best[2]
        
        if results:
            if auto_equip:
                # 执行自动装备操作
                await self._auto_equip_best_ex(client, all_slot_data)
            else:
                # 只显示推荐结果
                self._log("3星EX装备推荐结果:")
                for result in results:
                    self._log(result)
                self._log(f"所有最佳装备战力提升总计: +{total_best_power_increase}")
        else:
            raise SkipError("没有找到可推荐的3星EX装备")
    
    async def _auto_equip_best_ex(self, client: pcrclient, all_slot_data):
        """自动装备最佳3星EX装备"""
        equipped_units = 0
        equipped_count = 0
        
        # 统计四种装备类型的数量
        max_enhanced_best = 0      # 满强化最优
        max_enhanced_secondary = 0 # 满强化次优
        rank2_unlocked_best = 0    # 未强化但解锁rank2的最优
        rank_locked_best = 0       # 未解锁rank的最优
        
        # 获取当前未使用的EX装备
        use_ex_equip = set(ex_slot.serial_id
                          for unit in client.data.unit.values() 
                          for ex_slot in unit.ex_equip_slot if ex_slot.serial_id != 0)
        
        # 按EX装备ID分组可用装备
        ex_equip_by_ex_id = {}
        for ex in client.data.ex_equips.values():
            if ex.serial_id not in use_ex_equip:
                if ex.ex_equipment_id not in ex_equip_by_ex_id:
                    ex_equip_by_ex_id[ex.ex_equipment_id] = []
                ex_equip_by_ex_id[ex.ex_equipment_id].append(ex)
        
        # 为每个EX装备ID按优先级排序：首先enhancement_pt越高越优先，其次rank越高越优先
        for ex_id in ex_equip_by_ex_id:
            ex_equip_by_ex_id[ex_id].sort(key=lambda x: (-x.enhancement_pt, -x.rank))
        
        # 按战力从高到低排序处理槽位
        sorted_combinations = []
        for (unit_id, slot), options in all_slot_data.items():
            # 只处理普通EX装备槽位1-3
            if slot > 3:
                continue
            max_power = max(option[1] for option in options)
            sorted_combinations.append((unit_id, slot, options, max_power))
        
        sorted_combinations.sort(key=lambda x: x[3], reverse=True)
        
        # 处理每个角色槽位组合
        equipped_units_set = set()
        for unit_id, slot, options, max_power in sorted_combinations:
            unit_name = db.get_unit_name(unit_id)
            
            # 智能选择：从该槽位的所有选项中选择最佳装备
            # 获取最高战力的装备ID作为默认选择
            best_option = max(options, key=lambda x: x[1])
            final_ex_id = best_option[0]
            
            if len(options) > 1:
                # 检查当前最优装备的强化情况
                current_best_enhancement = 0
                if final_ex_id in ex_equip_by_ex_id and ex_equip_by_ex_id[final_ex_id]:
                    current_best_enhancement = max(ex.enhancement_pt for ex in ex_equip_by_ex_id[final_ex_id] 
                                                  if db.ex_equipment_data[ex.ex_equipment_id].rarity == 3)
                
                # 如果最优装备未强化，检查其他选项
                if current_best_enhancement == 0:
                    for alt_ex_id, alt_power in options:
                        if alt_ex_id != final_ex_id and (max_power - alt_power) <= 100:
                            # 检查替代装备的强化情况
                            if alt_ex_id in ex_equip_by_ex_id and ex_equip_by_ex_id[alt_ex_id]:
                                alt_enhancement = max(ex.enhancement_pt for ex in ex_equip_by_ex_id[alt_ex_id] 
                                                    if db.ex_equipment_data[ex.ex_equipment_id].rarity == 3)
                                if alt_enhancement == 6000:  # 满强化
                                    final_ex_id = alt_ex_id
                                    break
            
            # 检查是否有可用的装备
            if final_ex_id not in ex_equip_by_ex_id or not ex_equip_by_ex_id[final_ex_id]:
                continue
                
            # 获取当前槽位的装备
            unit = client.data.unit[unit_id]
            current_ex_slot = unit.ex_equip_slot[slot - 1]
            
            # 如果已经装备了相同的装备ID，跳过
            if current_ex_slot.serial_id != 0:
                current_ex = client.data.ex_equips[current_ex_slot.serial_id]
                if current_ex.ex_equipment_id == final_ex_id:
                    continue
            
            # 选择最佳可用装备（优先强化满的，其次未强化的）
            target_ex = None
            for ex in ex_equip_by_ex_id[final_ex_id]:
                # 检查是否为3星装备
                if db.ex_equipment_data[ex.ex_equipment_id].rarity == 3:
                    target_ex = ex
                    break
            
            if not target_ex:
                continue
            
            # 执行装备操作
            try:
                exchange_list = [ExtraEquipChangeSlot(slot=slot, serial_id=target_ex.serial_id)]
                await client.unit_equip_ex([ExtraEquipChangeUnit(
                    unit_id=unit_id, 
                    ex_equip_slot=exchange_list,
                    cb_ex_equip_slot=None
                )])
                
                # 从可用列表中移除已使用的装备
                ex_equip_by_ex_id[final_ex_id].remove(target_ex)
                if not ex_equip_by_ex_id[final_ex_id]:
                    del ex_equip_by_ex_id[final_ex_id]
                
                equipped_count += 1
                equipped_units_set.add(unit_id)
                
                # 统计装备类型
                original_best_ex_id = best_option[0]  # 原始最优装备ID
                is_best = (final_ex_id == original_best_ex_id)  # 是否为原始最优装备
                enhancement = target_ex.enhancement_pt
                rank = target_ex.rank
                
                if enhancement == 6000:  # 满强化
                    if is_best:
                        max_enhanced_best += 1
                    else:
                        max_enhanced_secondary += 1
                elif enhancement == 0:  # 未强化
                    if rank >= 2:  # 解锁rank2
                        rank2_unlocked_best += 1
                    else:  # 未解锁rank
                        rank_locked_best += 1
                
            except Exception as e:
                ex_name = db.ex_equipment_data[final_ex_id].name
                self._warn(f"为{unit_name}装备{ex_name}失败: {e}")
        
        equipped_units = len(equipped_units_set)
        self._log(f"自动装备完成：为{equipped_units}个角色装备了{equipped_count}个最佳3星EX装备")
        self._log(f"装备详情：满强化最优{max_enhanced_best}个，满强化次优{max_enhanced_secondary}个，"
                 f"未强化但解锁rank2的最优{rank2_unlocked_best}个，未解锁rank的最优{rank_locked_best}个")
