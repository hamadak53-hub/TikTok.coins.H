import asyncio

from aiogram import Bot, Dispatcher, F
from aiogram.filters import Command, CommandStart
from aiogram.types import (
    Message,
    CallbackQuery,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
)

from config import BOT_TOKEN, ADMIN_IDS
from db import (
    init_db,
    add_order,
    latest_orders,
    confirm_payment,
    reject_payment,
)
from catalog import PRODUCTS


if not BOT_TOKEN:
    raise RuntimeError("Set BOT_TOKEN in .env")


bot = Bot(BOT_TOKEN)
dp = Dispatcher()

pending = {}

CASH_NUMBERS = [
    "01031921290",
    "01091924865",
]


def home():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(
            text="🪙 شحن العملات",
            callback_data="catalog"
        )],
        [InlineKeyboardButton(
            text="📞 الدعم",
            callback_data="support"
        )]
    ])


def payment_methods():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(
            text="📱 فودافون كاش",
            callback_data="pay:vodafone"
        )],
        [InlineKeyboardButton(
            text="💳 إنستا باي",
            callback_data="pay:instapay"
        )],
        [InlineKeyboardButton(
            text="🏦 تحويل بنكي",
            callback_data="pay:bank"
        )],
        [InlineKeyboardButton(
            text="🌐 بوابة دفع إلكترونية",
            callback_data="pay:gateway"
        )]
    ])


def receipt_buttons(order_id, user_id):
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(
                text="✅ تأكيد الدفع",
                callback_data=f"approve:{order_id}:{user_id}"
            ),
            InlineKeyboardButton(
                text="❌ رفض الدفع",
                callback_data=f"reject:{order_id}:{user_id}"
            )
        ]
    ])


@dp.message(CommandStart())
async def start(m: Message):
    pending.pop(m.from_user.id, None)

    await m.answer(
        "🖤 أهلاً بك في HAMO STORE\n"
        "متجر شحن عملات TikTok\n\n"
        "اختار الخدمة:",
        reply_markup=home()
    )


@dp.callback_query(F.data == "catalog")
async def catalog(c: CallbackQuery):

    rows = []

    for p in PRODUCTS.values():
        rows.append([
            InlineKeyboardButton(
                text=f'{p["coins"]:,} عملة — {p["price"]} جنيه',
                callback_data=f'buy:{p["code"]}'
            )
        ])

    await c.message.answer(
        "🪙 اختر باقة الشحن:",
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=rows
        )
    )

    await c.answer()


@dp.callback_query(F.data.startswith("buy:"))
async def buy(c: CallbackQuery):

    code = c.data.split(":", 1)[1]

    if code not in PRODUCTS:
        await c.answer(
            "الباقة غير متاحة",
            show_alert=True
        )
        return

    pending[c.from_user.id] = {
        "code": code,
        "step": "tiktok_id"
    }

    await c.message.answer(
        "🎮 أرسل TikTok ID أو اسم المستخدم المطلوب شحنه:"
    )

    await c.answer()


@dp.message(F.text)
async def get_text(m: Message):

    user_id = m.from_user.id
    data = pending.get(user_id)

    if not data:
        return

    if data["step"] == "tiktok_id":

        tiktok_id = m.text.strip().lstrip("@")

        if not 2 <= len(tiktok_id) <= 64:
            await m.answer("اسم الحساب غير صحيح. حاول مرة أخرى.")
            return

        data["tiktok_id"] = tiktok_id
        data["step"] = "payment"

        p = PRODUCTS[data["code"]]

        await m.answer(
            f"✅ تم تحديد الحساب: @{tiktok_id}\n\n"
            f"🪙 الباقة: {p['coins']:,} كوين\n"
            f"💰 السعر: {p['price']} جنيه\n\n"
            "اختر وسيلة الدفع:",
            reply_markup=payment_methods()
        )

        return


@dp.callback_query(F.data.startswith("pay:"))
async def choose_payment(c: CallbackQuery):

    user_id = c.from_user.id
    data = pending.get(user_id)

    if not data or data.get("step") != "payment":
        await c.answer("ابدأ طلب جديد من المتجر.", show_alert=True)
        return

    method = c.data.split(":")[1]

    if method in ("bank", "gateway"):
        await c.answer(
            "هذه الوسيلة قيد التجهيز. استخدم فودافون كاش أو إنستا باي حالياً.",
            show_alert=True
        )
        return

    if method == "vodafone":
        method_name = "فودافون كاش"

    elif method == "instapay":
        method_name = "إنستا باي"

    else:
        await c.answer("وسيلة الدفع غير متاحة", show_alert=True)
        return

    data["payment_method"] = method_name
    data["step"] = "receipt"

    numbers = "\n".join(
        f"📱 {number}" for number in CASH_NUMBERS
    )

    await c.message.answer(
        f"💳 وسيلة الدفع: {method_name}\n\n"
        f"حوّل المبلغ إلى أحد الرقمين:\n\n"
        f"{numbers}\n\n"
        "📸 بعد التحويل أرسل صورة الإيصال هنا.\n"
        "سيتم مراجعة التحويل من الإدارة قبل تنفيذ الشحن."
    )

    await c.answer()


@dp.message(F.photo)
async def receive_receipt(m: Message):

    user_id = m.from_user.id
    data = pending.get(user_id)

    if not data or data.get("step") != "receipt":
        return

    p = PRODUCTS[data["code"]]
    receipt_id = m.photo[-1].file_id

    try:
        order_id = await add_order(
            user_id,
            m.from_user.username,
            data["tiktok_id"],
            p,
            data["payment_method"],
            receipt_id
        )

        pending.pop(user_id, None)

        await m.answer(
            f"✅ تم استلام إيصالك بنجاح.\n\n"
            f"رقم الطلب: #{order_id}\n"
            f"الباقة: {p['coins']} كوين\n"
            f"السعر: {p['price']} جنيه\n"
            f"الحالة: بانتظار مراجعة الدفع."
        )

        caption = (
            f"🧾 طلب دفع جديد #{order_id}\n\n"
            f"العميل: {user_id}\n"
            f"اسم المستخدم: @{m.from_user.username or 'غير متوفر'}\n"
            f"TikTok: @{data['tiktok_id']}\n"
            f"الباقة: {p['coins']} Coins\n"
            f"المبلغ: {p['price']} جنيه\n"
            f"الدفع: {data['payment_method']}\n"
            f"الحالة: بانتظار المراجعة"
        )

        for admin_id in ADMIN_IDS:
            await bot.send_photo(
                admin_id,
                receipt_id,
                caption=caption,
                reply_markup=receipt_buttons(order_id, user_id)
            )

    except Exception as e:
        print("Receipt error:", e)
        await m.answer(
            "حدث خطأ أثناء تسجيل الطلب. حاول مرة أخرى أو تواصل مع الدعم."
        )


@dp.callback_query(F.data.startswith("approve:"))
async def approve(c: CallbackQuery):

    if c.from_user.id not in ADMIN_IDS:
        await c.answer("غير مسموح لك.", show_alert=True)
        return

    _, order_id, user_id = c.data.split(":")

    try:
        await confirm_payment(int(order_id))

        await bot.send_message(
            int(user_id),
            f"✅ تم تأكيد دفع طلبك #{order_id}.\n"
            "طلبك الآن بانتظار تنفيذ الشحن."
        )

        await c.message.edit_reply_markup(reply_markup=None)

        await c.answer("تم تأكيد الدفع.")

    except Exception as e:
        print("Approve error:", e)
        await c.answer("تعذر تأكيد الطلب.", show_alert=True)


@dp.callback_query(F.data.startswith("reject:"))
async def reject(c: CallbackQuery):

    if c.from_user.id not in ADMIN_IDS:
        await c.answer("غير مسموح لك.", show_alert=True)
        return

    _, order_id, user_id = c.data.split(":")

    try:
        await reject_payment(int(order_id))

        await bot.send_message(
            int(user_id),
            f"❌ لم يتم قبول إيصال الدفع للطلب #{order_id}.\n"
            "يرجى التواصل مع الإدارة."
        )

        await c.message.edit_reply_markup(reply_markup=None)

        await c.answer("تم رفض الدفع.")

    except Exception as e:
        print("Reject error:", e)
        await c.answer("تعذر رفض الطلب.", show_alert=True)


@dp.message(Command("admin"))
async def admin(m: Message):

    if m.from_user.id not in ADMIN_IDS:
        return

    rows = await latest_orders()

    if not rows:
        await m.answer("لا توجد طلبات.")
        return

    result = []

    for r in rows:
        result.append(
            f"#{r[0]} | العميل: {r[1]}\n"
            f"TikTok: @{r[2]}\n"
            f"العملات: {r[3]}\n"
            f"السعر: {r[4]} جنيه\n"
            f"الحالة: {r[5]}"
        )

    await m.answer("\n\n".join(result))


@dp.callback_query(F.data == "support")
async def support(c: CallbackQuery):

    await c.message.answer(
        "📞 دعم HAMO STORE\n\n"
        "أرسل رسالتك هنا وسيتم التواصل مع الإدارة."
    )

    await c.answer()


async def main():

    await init_db()

    print("HAMO STORE is running...")

    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
    
