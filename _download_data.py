import asyncio

from autopcr.core.apiclient import apiclient
from autopcr.db.imagemgr import instance as imagemgr
from autopcr.db.database import db
from autopcr.db.dbstart import db_start
from autopcr.util.unit_recognizer import instance as unit_recognizer

async def main():
    await db_start()
    for unit in db.unlock_unit_condition:
        for star in [1, 3, 6]:
            await imagemgr.unit_icon(unit // 100, star)
    await unit_recognizer.update_dic()
    for ex_equip in db.ex_equipment_data:
        await imagemgr.ex_equip_icon(ex_equip)

if __name__ == "__main__":
    loop = asyncio.get_event_loop()
    loop.run_until_complete(main())
