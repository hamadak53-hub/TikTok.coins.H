import asyncio
from aiogram import Bot, Dispatcher, F
from aiogram.filters import Command, CommandStart
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton, LabeledPrice, PreCheckoutQuery
from config import BOT_TOKEN, ADMIN_IDS
from db import init_db, add_order, latest_orders
from catalog import PRODUCTS

if not BOT_TOKEN:
    raise RuntimeError("Set BOT_TOKEN in .env")

bot = Bot(BOT_TOKEN)
dp = Dispatcher()
pending = {}

def home():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🪙 شحن العملات", callback_data="catalog")],
        [InlineKeyboardButton(text="📞 الدعم", callback_data="support")]
    ])

@dp.message(CommandStart())
async def start(m: Message):
    await m.answer("🖤 أهلاً بك في HAMO STORE\nمتجر شحن عملات TikTok\nاختار الخدمة:", reply_markup=home())

@dp.callback_query(F.data == "catalog")
async def catalog(c: CallbackQuery):
    rows = [[InlineKeyboardButton(text=f'{p["coins"]:,} عملة — {p["stars"]} ⭐', callback_data=f'buy:{p["code"]}')] for p in PRODUCTS.values()]
    await c.message.answer("اختر الباقة — الدفع داخل البوت عبر Telegram Stars:", reply_markup=InlineKeyboardMarkup(inline_keyboard=rows))
    await c.answer()

@dp.callback_query(F.data.startswith("buy:"))
async def buy(c: CallbackQuery):
    code = c.data.split(":", 1)[1]
    if code not in PRODUCTS:
        await c.answer("الباقة غير متاحة", show_alert=True)
        return
    pending[c.from_user.id] = code
    await c.message.answer("أرسل TikTok ID أو اسم المستخدم المطلوب شحنه:")
    await c.answer()

@dp.message(F.text)
async def get_id(m: Message):
    code = pending.get(m.from_user.id)
    if not code:
        return
    tiktok_id = m.text.strip().lstrip("@")
    if not 2 <= len(tiktok_id) <= 64:
        await m.answer("اسم الحساب غير صحيح. حاول مرة أخرى.")
        return
    p = PRODUCTS[code]
    await bot.send_invoice(
        chat_id=m.chat.id, title=f'HAMO STORE - {p["coins"]} TikTok Coins',
        description=f'TikTok Coins for @{tiktok_id}',
        payload=f'{m.from_user.id}|{code}|{tiktok_id}',
        currency="XTR", prices=[LabeledPrice(label=f'{p["coins"]} Coins', amount=p["stars"])],
        provider_token=""
    )
    pending.pop(m.from_user.id, None)

@dp.pre_checkout_query()
async def checkout(q: PreCheckoutQuery):
    await q.answer(ok=True)

@dp.message(F.successful_payment)
async def paid(m: Message):
    sp = m.successful_payment
    try:
        uid, code, tiktok_id = sp.invoice_payload.split("|", 2)
        p = PRODUCTS[code]
        oid = await add_order(int(uid), m.from_user.username, tiktok_id, p, sp.telegram_payment_charge_id)
        await m.answer(f"✅ تم استلام الدفع. رقم الطلب #{oid}\nالحالة: بانتظار تنفيذ الشحن.")
        for aid in ADMIN_IDS:
            await bot.send_message(aid, f"طلب مدفوع #{oid}\nالعميل: {uid}\nTikTok: @{tiktok_id}\nالباقة: {p['coins']} Coins\nالحالة: paid_waiting_supplier")
    except Exception:
        await m.answer("تعذر تسجيل الطلب آليًا. تواصل مع الدعم واحتفظ بإيصال الدفع.")

@dp.message(Command("admin"))
async def admin(m: Message):
    if m.from_user.id not in ADMIN_IDS:
        return
    rows = await latest_orders()
    await m.answer("\n".join([f"#{r[0]} | user {r[1]} | @{r[2]} | {r[3]} coins | {r[5]}" for r in rows]) or "لا توجد طلبات.")

@dp.callback_query(F.data == "support")
async def support(c: CallbackQuery):
    await c.message.answer("للدعم، تواصل مع إدارة HAMO STORE.")
    await c.answer()

async def main():
    await init_db()
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
