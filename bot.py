import logging
import sqlite3
import asyncio
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, MessageHandler, filters, ContextTypes

# Logging setup
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)

# --- BOT CONFIGURATION ---
BOT_TOKEN = "8948870564:AAFH6lauqZ3zqOqiDWBGacG7l2zWFOBZzuQ"
ADMIN_ID = 5908090766
YOUR_UPI_ID = "9653511225@ptsbi"
QR_FILE_ID = "AgACAgUAAxkBAANDaiKf8tA0ZhYveRAOaI5BY6A5IcAAAkwQaxszyhlVoI_QfxUCFM0BAAMCAANtAAM7BA"

# Support Details
SUPPORT_NUMBER = "9653511225"
SUPPORT_TELEGRAM = "https://t.me/sk_script_provider"

# Default Prices Setup
DEFAULT_PRICES = {"1days": 50, "3days": 120, "7days": 250, "10days": 320, "15days": 450, "31days": 800}
DEFAULT_RESELLER_PRICES = {"1days": 40, "3days": 100, "7days": 220, "10days": 280, "15days": 400, "31days": 700}

def run_db_query(query, params=(), commit=False, fetchall=False, fetchone=False):
    conn = sqlite3.connect('keys_shop.db', timeout=10)
    cursor = conn.cursor()
    try:
        cursor.execute(query, params)
        if commit:
            conn.commit()
        if fetchall:
            return cursor.fetchall()
        if fetchone:
            return cursor.fetchone()
    except Exception as e:
        logging.error(f"Database Error on query [{query}]: {e}")
        raise e
    finally:
        conn.close()

def init_db():
    # 1. Sabse pehle basic tables create karenge bina kisi complex keys ke
    run_db_query('''CREATE TABLE IF NOT EXISTS keys_stock (
                        id INTEGER PRIMARY KEY AUTOINCREMENT, 
                        product TEXT, 
                        key_value TEXT UNIQUE, 
                        duration TEXT, 
                        status TEXT DEFAULT 'available')''', commit=True)
    
    run_db_query('''CREATE TABLE IF NOT EXISTS users_wallet (
                        user_id INTEGER PRIMARY KEY, 
                        balance INTEGER DEFAULT 0)''', commit=True)
    
    run_db_query('''CREATE TABLE IF NOT EXISTS product_prices (
                        product TEXT, 
                        duration TEXT, 
                        price INTEGER, 
                        PRIMARY KEY (product, duration))''', commit=True)
                        
    run_db_query('''CREATE TABLE IF NOT EXISTS products_list (
                        product TEXT PRIMARY KEY)''', commit=True)

    # 2. 🛠️ MASTER PATCH: Pehle check karenge aur naye columns force-insert karenge
    conn = sqlite3.connect('keys_shop.db')
    cursor = conn.cursor()
    
    # Check users_wallet table columns
    cursor.execute("PRAGMA table_info(users_wallet)")
    wallet_cols = [row[1] for row in cursor.fetchall()]
    if 'level' not in wallet_cols:
        try:
            cursor.execute("ALTER TABLE users_wallet ADD COLUMN level TEXT DEFAULT 'regular'")
            conn.commit()
        except Exception as e:
            logging.info(f"Wallet level column bypass: {e}")

    # Check product_prices table columns
    cursor.execute("PRAGMA table_info(product_prices)")
    price_cols = [row[1] for row in cursor.fetchall()]
    if 'reseller_price' not in price_cols:
        try:
            cursor.execute("ALTER TABLE product_prices ADD COLUMN reseller_price INTEGER DEFAULT 0")
            conn.commit()
        except Exception as e:
            logging.info(f"Prices reseller column bypass: {e}")
        
    conn.close()
                        
    # 3. Ab default data dalenge kyunki columns ki tasalli ho chuki hai
    initial_products = [
        "BR-MOD ROOT", "DRIP CLIENT APK MOD", "DRIP-CLIET ROOT", 
        "FLUORITE FF IOS", "G-BOX E-SIGN CERT", "HAXXCKER PRO ROOT", 
        "HG CHEAT APK MOD", "LK TEAM ROOT+PC", "PATO TEAM BLUE", 
        "PATO TEAM GREEN", "PATO TEAM ORANGE"
    ]
    for prod in initial_products:
        run_db_query('INSERT OR IGNORE INTO products_list (product) VALUES (?)', (prod,), commit=True)
        for dur, prc in DEFAULT_PRICES.items():
            resell_prc = DEFAULT_RESELLER_PRICES.get(dur, prc)
            # Safe ignore query with exact matching schema columns
            run_db_query('''INSERT OR IGNORE INTO product_prices (product, duration, price, reseller_price) 
                            VALUES (?, ?, ?, ?)''', (prod, dur, prc, resell_prc), commit=True)

def get_user_level_and_bal(user_id):
    row = run_db_query('SELECT balance, level FROM users_wallet WHERE user_id=?', (user_id,), fetchone=True)
    if not row:
        run_db_query('INSERT OR IGNORE INTO users_wallet (user_id, balance, level) VALUES (?, 0, "regular")', (user_id,), commit=True)
        return 0, "regular"
    return row[0], row[1]

def get_product_price(product, duration, level="regular"):
    prc_row = run_db_query('SELECT price, reseller_price FROM product_prices WHERE product=? AND duration=?', (product, duration), fetchone=True)
    if prc_row is not None:
        return prc_row[1] if level == "reseller" else prc_row[0]
    return DEFAULT_RESELLER_PRICES.get(duration, 40) if level == "reseller" else DEFAULT_PRICES.get(duration, 50)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    bal, level = get_user_level_and_bal(user_id)
    tier_text = "👤 Regular Customer" if level == "regular" else "💼 Reseller Account"
    
    keyboard = [
        [InlineKeyboardButton("🛒 Buy Cheats / Keys", callback_data="view_products")],
        [InlineKeyboardButton("📊 Check Availability", callback_data="check_stock")],
        [InlineKeyboardButton(f"💰 My Wallet (₹{bal}) / Add Fund", callback_data="my_wallet")],
        [InlineKeyboardButton("📞 Contact Support / Help", callback_data="get_help")]
    ]
    await update.message.reply_text(f"👋 Welcome to Premium Key Store Bot!\n🏷️ **Account Status:** {tier_text}\n\nOptions select karein:", reply_markup=InlineKeyboardMarkup(keyboard))

async def set_user_level(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID: return
    try:
        raw_text = update.message.text.replace('/setlevel', '').strip()
        parts = [p.strip() for p in raw_text.split('|')]
        if len(parts) != 2:
            await update.message.reply_text("❌ Format: `/setlevel USER_ID | level` \nExample: `/setlevel 12345678 | reseller`")
            return
        u_id, lvl = int(parts[0]), parts[1].lower()
        if lvl not in ['regular', 'reseller']:
            await update.message.reply_text("❌ Level sirf 'regular' ya 'reseller' ho sakta hai.")
            return
            
        run_db_query('INSERT INTO users_wallet (user_id, balance, level) VALUES (?, 0, ?) ON CONFLICT(user_id) DO UPDATE SET level=?', (u_id, lvl, lvl), commit=True)
        await update.message.reply_text(f"✅ User `{u_id}` ka status successfully **{lvl.upper()}** set kar diya gaya hai!")
        try:
            await context.bot.send_message(chat_id=u_id, text=f"🎉 Status Alert! Admin ne aapka account level badal kar **{lvl.upper()}** kar diya hai. Ab aapko saste rates milenge!")
        except: pass
    except Exception as e:
        await update.message.reply_text(f"❌ Error: {str(e)}")

async def add_product(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID: return
    product_name = update.message.text.replace('/addproduct', '').strip()
    if not product_name:
        await update.message.reply_text("❌ Format: `/addproduct NAME`")
        return
    run_db_query('INSERT OR IGNORE INTO products_list (product) VALUES (?)', (product_name,), commit=True)
    for dur, prc in DEFAULT_PRICES.items():
        resell_prc = DEFAULT_RESELLER_PRICES.get(dur, prc)
        run_db_query('INSERT OR IGNORE INTO product_prices (product, duration, price, reseller_price) VALUES (?, ?, ?, ?)', (product_name, dur, prc, resell_prc), commit=True)
    await update.message.reply_text(f"✅ Product Added: `{product_name}`")

async def del_product(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID: return
    prod_name = update.message.text.replace('/delproduct', '').strip()
    if not prod_name:
        await update.message.reply_text("❌ Format: `/delproduct PRODUCT_NAME`")
        return
    run_db_query("DELETE FROM products_list WHERE product=?", (prod_name,), commit=True)
    run_db_query("DELETE FROM keys_stock WHERE product=?", (prod_name,), commit=True)
    run_db_query("DELETE FROM product_prices WHERE product=?", (prod_name,), commit=True)
    await update.message.reply_text(f"🗑️ **Product Deleted:** `{prod_name}`")

async def del_key(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID: return
    key_val = update.message.text.replace('/delkey', '').strip()
    if not key_val:
        await update.message.reply_text("❌ Format: `/delkey KEY_VALUE`")
        return
    run_db_query("DELETE FROM keys_stock WHERE key_value=?", (key_val,), commit=True)
    await update.message.reply_text(f"🗑️ **Key Database Se Permanent Delete Ho Gayi Hai:** `{key_val}`")

async def view_stock(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID: return
    rows = run_db_query("SELECT product, key_value, duration, status FROM keys_stock ORDER BY product, status", fetchall=True)
    if not rows:
        await update.message.reply_text("📊 Database Stock Khali Hai!")
        return
    report = "📋 **LIVE STOCK REPORT** 📋\n"
    current_prod = ""
    for row in rows:
        prod, key, duration, status = row[0], row[1], row[2], row[3]
        if prod != current_prod:
            report += f"\n📦 **{prod}**\n"
            current_prod = prod
        icon = "🟢 [Avail]" if status == "available" else "🔴 [Sold]"
        report += f" ├ ⏳ {duration} ➜ `{key}` {icon}\n"
        if len(report) > 3500:
            await update.message.reply_text(report, parse_mode="Markdown")
            report = ""
    if report:
        await update.message.reply_text(report, parse_mode="Markdown")

async def set_price(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID: return
    try:
        raw_text = update.message.text.replace('/setprice', '').strip()
        parts = [p.strip() for p in raw_text.split('|')]
        if len(parts) != 4:
            await update.message.reply_text("❌ Format: `/setprice PRODUCT | VALIDITY | USER_PRICE | RESELLER_PRICE`")
            return
        product, duration, new_price, new_reseller_price = parts[0], parts[1], int(parts[2]), int(parts[3])
        run_db_query('''INSERT INTO product_prices (product, duration, price, reseller_price) VALUES (?, ?, ?, ?)
                          ON CONFLICT(product, duration) DO UPDATE SET price=excluded.price, reseller_price=excluded.reseller_price''', 
                     (product, duration, new_price, new_reseller_price), commit=True)
        await update.message.reply_text(f"✅ Price Fixed:\n📦 `{product}` ({duration})\n👤 Regular User: ₹{new_price}\n💼 Reseller: ₹{new_reseller_price}")
    except Exception as e:
        await update.message.reply_text(f"❌ Error: {str(e)}")

async def add_key(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID: return
    raw_text = update.message.text.replace('/addkey', '').strip()
    parts = [x.strip() for x in raw_text.split('|')]
    if len(parts) != 3:
        await update.message.reply_text("❌ Format Sahi Nahi Hai!")
        return
    product, key_string, duration = parts[0], parts[1], parts[2]
    
    rows = run_db_query('SELECT product FROM products_list', fetchall=True)
    all_prods = [r[0] for r in rows] if rows else []
    if product not in all_prods:
        await update.message.reply_text(f"❌ Product `{product}` list me nahi hai! Pehle `/addproduct {product}` karein.")
        return
        
    keys_to_add = [k.strip() for k in key_string.split('//') if k.strip()] if '//' in key_string else [key_string]
    success_count = 0
    duplicate_keys_list = []
    
    for individual_key in keys_to_add:
        exist_check = run_db_query("SELECT status FROM keys_stock WHERE key_value=?", (individual_key,), fetchone=True)
        
        if exist_check:
            if exist_check[0] == 'sold':
                run_db_query("DELETE FROM keys_stock WHERE key_value=?", (individual_key,), commit=True)
                run_db_query('INSERT INTO keys_stock (product, key_value, duration) VALUES (?, ?, ?)', (product, individual_key, duration), commit=True)
                success_count += 1
            else:
                duplicate_keys_list.append(f"{individual_key} (Available)")
        else:
            try:
                run_db_query('INSERT INTO keys_stock (product, key_value, duration) VALUES (?, ?, ?)', (product, individual_key, duration), commit=True)
                success_count += 1
            except:
                duplicate_keys_list.append(individual_key)
                
    reply = f"📊 **Process Result for {product}:**\n\n✅ Added: {success_count} keys.\n"
    if duplicate_keys_list:
        reply += f"\n❌ **Blocked (Already Active in Stock):**\n" + "\n".join([f"👉 `{d}`" for d in duplicate_keys_list])
    await update.message.reply_text(reply)

async def approve_fund(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID: return
    try:
        raw_text = update.message.text.replace('/approve', '').strip()
        target_user, amount = [t.strip() for t in raw_text.split('|')]
        target_user, amount = int(target_user), int(amount)
        run_db_query('UPDATE users_wallet SET balance = balance + ? WHERE user_id = ?', (amount, target_user), commit=True)
        row = run_db_query('SELECT balance FROM users_wallet WHERE user_id = ?', (target_user,), fetchone=True)
        new_bal = row[0] if row else amount
        await update.message.reply_text("✅ Fund Approved!")
        await context.bot.send_message(chat_id=target_user, text=f"🎉 Fund Added: ₹{amount}\nBalance: ₹{new_bal}")
    except Exception as e:
        await update.message.reply_text(f"❌ Error in approval: {e}")

async def handle_screenshot(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    photo_id = update.message.photo[-1].file_id
    await update.message.reply_text("📨 Screenshot Received! Wait for verification.")
    await context.bot.send_photo(chat_id=ADMIN_ID, photo=photo_id, caption=f"💰 **New Screenshot!**\nUser: `{user_id}`\n`/approve {user_id} | AMOUNT`")

async def button_click(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data, user_id = query.data, query.from_user.id
    bal, level = get_user_level_and_bal(user_id)
    
    rows = run_db_query('SELECT product FROM products_list', fetchall=True)
    all_products_list = [r[0] for r in rows] if rows else []

    if data in ["view_products", "check_stock"]:
        keyboard = []
        for prod in all_products_list:
            stk_row = run_db_query("SELECT COUNT(*) FROM keys_stock WHERE product=? AND status='available'", (prod,), fetchone=True)
            stock = stk_row[0] if stk_row else 0
            if data == "view_products" and stock == 0: continue
            btn_txt = f"📦 {prod} [{stock} Left]" if stock > 0 else f"❌ {prod} [Out of Stock]"
            act = f"viewprod_{prod}" if data == "check_stock" else f"buy_{prod}"
            keyboard.append([InlineKeyboardButton(btn_txt, callback_data=act)])
        keyboard.append([InlineKeyboardButton("🔙 Main Menu", callback_data="back_to_start")])
        await query.edit_message_text(text="🎯 **Product List**", reply_markup=InlineKeyboardMarkup(keyboard))

    elif data == "back_to_start":
        keyboard = [
            [InlineKeyboardButton("🛒 Buy Cheats / Keys", callback_data="view_products")],
            [InlineKeyboardButton("📊 Check Availability", callback_data="check_stock")],
            [InlineKeyboardButton(f"💰 My Wallet (₹{bal}) / Add Fund", callback_data="my_wallet")],
            [InlineKeyboardButton("📞 Contact Support / Help", callback_data="get_help")]
        ]
        await query.message.delete()
        await context.bot.send_message(chat_id=user_id, text="👋 Welcome to Premium Key Store Bot!", reply_markup=InlineKeyboardMarkup(keyboard))

    elif data == "get_help":
        help_text = f"📞 **Support & Help**\n\n💬 **Telegram Official ID:** [Sukhwant Singh]({SUPPORT_TELEGRAM})\n📞 **Phone Number:** `{SUPPORT_NUMBER}`"
        await query.edit_message_text(text=help_text, reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Main Menu", callback_data="back_to_start")]]), parse_mode="Markdown", disable_web_page_preview=True)

    elif data == "my_wallet":
        w_text = f"💰 **Wallet Balance: ₹{bal}**\n\n📸 QR Scan karke screenshot bhejein.\n\nUPI ID: `{YOUR_UPI_ID}`"
        await query.message.delete()
        await context.bot.send_photo(chat_id=user_id, photo=QR_FILE_ID, caption=w_text, reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Main Menu", callback_data="back_to_start")]]))

    elif data.startswith("viewprod_"):
        prod = data.replace("viewprod_", "")
        dur_rows = run_db_query("SELECT DISTINCT duration FROM keys_stock WHERE product=? AND status='available'", (prod,), fetchall=True)
        durations = [r[0] for r in dur_rows] if dur_rows else ["1days", "3days", "7days", "10days", "15days", "31days"]
        stock_text = f"📊 **Stock Info for {prod}**\n\n"
        for dur in sorted(durations):
            stk_cnt = run_db_query("SELECT COUNT(*) FROM keys_stock WHERE product=? AND duration=? AND status='available'", (prod, dur), fetchone=True)
            cnt = stk_cnt[0] if stk_cnt else 0
            cost = get_product_price(prod, dur, level)
            stock_text += f"│ ⏳ {dur}: ₹{cost} ({cnt} Keys Available)\n"
        await query.edit_message_text(text=stock_text, reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🛒 Buy", callback_data=f"buy_{prod}")], [InlineKeyboardButton("🔙 Back", callback_data="check_stock")]]))

    elif data.startswith("buy_"):
        prod = data.replace("buy_", "")
        dur_rows = run_db_query("SELECT DISTINCT duration FROM keys_stock WHERE product=? AND status='available'", (prod,), fetchall=True)
        durations = [r[0] for r in dur_rows] if dur_rows else []
        if not durations:
            await query.edit_message_text(text="❌ Out of stock!", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back", callback_data="view_products")]]))
            return
        keyboard = []
        for d in sorted(durations):
            cost = get_product_price(prod, d, level)
            keyboard.append([InlineKeyboardButton(f"📆 {d} (₹{cost})", callback_data=f"conf_{prod}_{d}")])
        keyboard.append([InlineKeyboardButton("🔙 Back", callback_data="view_products")])
        await query.edit_message_text(text=f"🎁 **{prod}** validity select karein:", reply_markup=InlineKeyboardMarkup(keyboard))

    elif data.startswith("conf_"):
        _, prod, duration = data.split('_')
        cost = get_product_price(prod, duration, level)
        
        key_row = run_db_query("SELECT id, key_value FROM keys_stock WHERE product=? AND duration=? AND status='available' LIMIT 1", (prod, duration), fetchone=True)
        if not key_row:
            await context.bot.send_message(chat_id=user_id, text="❌ Yeh validity abhi out of stock ho gayi hai!")
            return
        if bal < cost:
            await context.bot.send_message(chat_id=user_id, text=f"❌ Insufficient Balance! Is plan ki cost aapke liye ₹{cost} hai, aapka balance ₹{bal} hai. Pehle wallet fill karein.")
            return
            
        key_id, key_val = key_row[0], key_row[1]
        run_db_query("UPDATE users_wallet SET balance = balance - ? WHERE user_id = ?", (cost, user_id), commit=True)
        run_db_query("UPDATE keys_stock SET status='sold' WHERE id=?", (key_id,), commit=True)
        
        await context.bot.send_message(chat_id=user_id, text=f"✅ **Purchase Success!**\n\n📦 Product: {prod}\n⏳ Validity: {duration}\n💰 Cost: ₹{cost}\n\n🔑 Key: `{key_val}`\n\n👉 APK is channel se lo:\nhttps://t.me/SKGMSTORE")
        await context.bot.send_message(chat_id=ADMIN_ID, text=f"🔔 Sale Alert! User `{user_id}` (Tier: {level}) bought `{prod}` ({duration}) for ₹{cost}")

def main():
    init_db()
    app = Application.builder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("setlevel", set_user_level))
    app.add_handler(CommandHandler("approve", approve_fund))
    app.add_handler(CommandHandler("addkey", add_key))
    app.add_handler(CommandHandler("setprice", set_price))
    app.add_handler(CommandHandler("addproduct", add_product))
    app.add_handler(CommandHandler("delproduct", del_product))
    app.add_handler(CommandHandler("delkey", del_key))
    app.add_handler(CommandHandler("viewstock", view_stock))
    app.add_handler(MessageHandler(filters.PHOTO, handle_screenshot))
    app.add_handler(CallbackQueryHandler(button_click))
    app.run_polling(drop_pending_updates=True)

if __name__ == '__main__':
    main()
