from hoshino.service import Service
import aiohttp
import csv
import json
from datetime import datetime, timedelta

sv_event = Service('pcr-reminder-event', enable_on_default=False, help_='活动结束提醒', bundle='pcr订阅')
sv_gacha = Service('pcr-reminder-gacha', enable_on_default=False, help_='卡池结束提醒', bundle='pcr订阅')

db_root_url = "https://raw.githubusercontent.com/ZQZ44/redive_db_diff/master/"


def is_hour_before(item, today, hours):
    seconds_start = (hours - 1) * 3600
    seconds_end = hours * 3600
    if not item.tillEnd:
        item.tillEnd = (item.end_time - today).total_seconds()
    return seconds_end > item.tillEnd >= seconds_start


def is_last_day_with_hour(item, today, hour):
    if not item.endTime:
        item.endTime = parse_time(item.end_time)
    last_day = item.endTime + timedelta(days=-1)
    return last_day.day == today.day and last_day.month == today.month and today.hour == hour


def should_event_be_reminded_now(item, today):
    warn_hours = 3
    return is_hour_before(item, today, warn_hours)


def should_gacha_be_reminded_now(item, today):
    warn_hours = 2
    # hour in day: range(24)=[0...23]
    last_day_hour = 20
    return is_hour_before(item, today, warn_hours) or is_last_day_with_hour(item, today, last_day_hour)


# 活动一般晚上12点结束，1. 提前3小时提醒
@sv_event.scheduled_job('cron', hour='*', minute='2')
async def pcr_reminder_event():
    events = await find_event_reminds()
    if events and len(events) > 0:
        msg = '活动即将结束，记得清掉boss券兑换券'
        await sv_event.broadcast(msg, 'pcr-reminder-event', 0.2)


# 卡池一般上午11点结束， 1. 提前2小时提醒 2. 前一天的晚8点提醒
@sv_gacha.scheduled_job('cron', hour='*', minute='2')
async def pcr_reminder_gacha():
    gachas = await find_gacha_reminds()
    if gachas and len(gachas) > 0:
        msg = f'[CQ:at,qq=all] 以下卡池即将结束，请注意补井时间！\n' + print_gacha_info(gachas)
        await sv_gacha.broadcast(msg, 'pcr-reminder-gacha', 0.2)


@sv_gacha.on_prefix('列出当前卡池')
async def list_gacha(bot, ev):
    today = datetime.today()
    gachas = await fetch_csv("gacha_data.csv")
    gachas = [gacha for gacha in gachas if is_valid_gacha(gacha, today)]
    if gachas and len(gachas) > 0:
        await bot.send(ev, print_gacha_info(gachas))
    else:
        await bot.send(ev, '当前没有卡池')


@sv_gacha.on_prefix('列出所有卡池')
async def list_all_gacha(bot, ev):
    gachas = await fetch_csv("gacha_data.csv")
    if gachas and len(gachas) > 0:
        await bot.send(ev, print_gacha_info(gachas))
    else:
        await bot.send(ev, '当前没有卡池')


async def find_event_reminds():
    today = datetime.today()
    event_items = await fetch_csv("hatsune_schedule.csv")
    if event_items:
        return [item for item in event_items if
                is_valid_event(item, today) and should_event_be_reminded_now(item, today)]


async def find_gacha_reminds():
    today = datetime.today()
    gacha_items = await fetch_csv("gacha_data.csv")
    if gacha_items:
        return [item for item in gacha_items if
                is_valid_gacha(item, today) and should_gacha_be_reminded_now(item, today)]


def print_gacha_info(gachas):
    msg = ''
    for gacha in gachas:
        msg += "\n结束时间：" + gacha.end_time
        msg += "\n\t" + gacha.gacha_name
        msg += "\n\t" + gacha.description.replace('\\n', '\n\t')
    return msg


# 2099/01/01 11:00:00
def parse_time(t):
    return datetime.strptime(t, "%Y/%m/%d %H:%M:%S")


def is_valid_gacha(item, today):
    # 30000 为新角色卡池
    # 40000 为季节和周年庆典卡池
    # 50000 为FES卡池
    # 60000 为新手卡池
    # 70000 为三星必得卡池
    return is_valid_item(item, today) and "30000" <= item.gacha_id <= "70000" and item.end_time < "2099/01/01 11:00:00"


def is_valid_event(item, today):
    return is_valid_item(item, today)


def is_valid_item(item, today):
    if item:
        item.startTime = start_time = parse_time(item.start_time)
        item.endTime = end_time = parse_time(item.end_time)
        seconds_since_start = (today - start_time).total_seconds()
        seconds_till_end = (end_time - today).total_seconds()
        item.sinceStart = seconds_since_start
        item.tillEnd = seconds_till_end
        if seconds_since_start > 0 and seconds_till_end >= 0:
            return True


class CsvItem:
    def __init__(self, dictionary):
        for k, v in dictionary.items():
            setattr(self, k, v)

    def toJSON(self):
        return json.dumps(self, default=lambda o: o.__dict__,
                          sort_keys=True, indent=4)


async def fetch_csv(file_name):
    async with aiohttp.ClientSession() as session:
        async with session.get(db_root_url + file_name) as resp:
            data = await resp.text()
            records = csv.DictReader(data.split("\n"))
            items = [CsvItem(row) for row in records]
            return items

# loop = asyncio.get_event_loop()
# loop.run_until_complete(find_event_reminds())
