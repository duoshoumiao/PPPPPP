import asyncio, json, sys  
from pathlib import Path  
sys.path.insert(0, str(Path(__file__).parent))  
from autopcr.db.dbstart import db_start  
from autopcr.db.database import db  
from autopcr.model.enums import eInventoryType  
  
ATTR_KEYS = ["hp","atk","magic_str","def","magic_def","physical_critical",  
             "magic_critical","wave_hp_recovery","wave_energy_recovery","dodge",  
             "physical_penetrate","magic_penetrate","life_steal",  
             "hp_recovery_rate","energy_recovery_rate","energy_reduce_rate","accuracy"]  
  
async def main():  
    await db_start()  
    out = {  
        # unit_id -> [槽1类别, 槽2类别, 槽3类别]  
        "unit_slots": {str(uid): [s.slot_category_1, s.slot_category_2, s.slot_category_3]  
                       for uid, s in db.unit_ex_equipment_slot.items()},  
        # rarity -> {star: total_point}，用于 enhancement_pt 反推星数  
        "star_pt": {str(r): {str(star): d.total_point  
                             for star, d in lv.items()}  
                    for r, lv in db.ex_equipment_enhance_data.items()},  
        "equips": {}  
    }  
    for ex_id, e in db.ex_equipment_data.items():  
        max_rank = db.get_ex_equip_max_rank(ex_id)  
        max_star = db.get_ex_equip_max_star(ex_id, max_rank)  
        attrs = {}  
        for k in ATTR_KEYS:  
            d = getattr(e, f"default_{k}", 0) or 0  
            m = getattr(e, f"max_{k}", 0) or 0  
            if d or m:  
                attrs[k] = [d, m]  
        name = db.inventory_name.get((eInventoryType.ExtraEquip, ex_id), str(ex_id))  
        out["equips"][str(ex_id)] = {  
            "name": name, "category": e.category, "rarity": e.rarity,  
            "cb": e.clan_battle_equip_flag, "max_star": max_star, "attrs": attrs  
        }  
    Path("ex_meta.json").write_text(json.dumps(out, ensure_ascii=False), encoding="utf-8")  
    print(f"导出 {len(out['equips'])} 件EX, {len(out['unit_slots'])} 个角色槽位")  
  
asyncio.get_event_loop().run_until_complete(main())