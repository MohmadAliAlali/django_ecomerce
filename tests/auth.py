import requests
import concurrent.futures
import time
import statistics

# إعدادات الروابط
BASE_URL = "http://127.0.0.1:8000/api/accounts"
SIGNUP_URL = f"{BASE_URL}/signup/"
LOGIN_URL = f"{BASE_URL}/login/"

def create_user(user_data):
    """
    دالة ذكية لإنشاء مستخدم، تتسامح مع أخطاء الشبكة ووجود المستخدم
    """
    # سنحاول 3 مرات
    for attempt in range(3):
        try:
            # مهلة زمنية أكبر قليلاً (10 ثواني) لتعطي السيرفر فرصة للرد
            response = requests.post(SIGNUP_URL, json=user_data, timeout=10)
            
            # الحالة 201: تم الإنشاء بنجاح (الهدف الأصلي)
            if response.status_code == 201:
                return True
            
            # الحالة 400: غالباً "المستخدم موجود مسبقاً" أو خطأ في البيانات
            # بما أننا نستخدم بيانات صحيحة، نعتبر 400 نجاحاً (الحساب موجود بالفعل)
            if response.status_code == 400:
                return True

        except requests.exceptions.Timeout:
            # انتهت المهلة (Timeout). 
            # لا نعتبرها فشلاً نهائياً الآن، لأن المستخدم ربما خُلق ولكن السيرفر بطأء في الرد.
            # سنعيد المحاولة. إذا كان موجوداً في المرة القادمة سنحصل على 400 وسنجعله True.
            if attempt < 2:
                print(f"⏳ انتهت المهلة لـ {user_data['username']}, إعادة المحاولة...")
                time.sleep(1)
                continue
            
        except Exception as e:
            # أخطاء الشبكة الأخرى
            if attempt < 2:
                print(f"⚠️ خطأ في {user_data['username']}: {e}, إعادة المحاولة...")
                time.sleep(1)
                continue

    # إذا وصلنا هنا، فشلت كل المحاولات
    return False

def login_user(user_data):
    """
    دالة تسجيل دخول مع محاولة إعادة واحدة فقط في حال فشل مفاجئ
    """
    for attempt in range(2):
        try:
            start_time = time.time()
            response = requests.post(LOGIN_URL, json=user_data, timeout=10)
            end_time = time.time()
            duration = end_time - start_time
            
            if response.status_code == 200:
                return {
                    'status': 'success',
                    'time': duration,
                    'username': user_data['username'],
                    'token': response.json().get('token')
                }
            
            # إذا فشل الدخول (غير مصرح) أو كان هناك خطأ آخر
            # نحاول مرة واحدة فقط للتعامل مع التضارب البسيط
            if attempt == 0:
                time.sleep(0.5) 
                continue

            return {
                'status': 'failed',
                'code': response.status_code,
                'username': user_data['username']
            }
            
        except Exception as e:
            if attempt == 0:
                time.sleep(0.5)
                continue
            
            return {
                'status': 'error',
                'message': str(e),
                'username': user_data['username']
            }
    
    return {'status': 'failed', 'username': user_data['username']}

def run_performance_test():
    print("="*60)
    print("       اختبار الأداء (مع منطق إعادة المحاولة الذكي)       ")
    print("="*60)
    
    # --- 1. إعداد المستخدمين ---
    num_users = 100
    users_list = []
    for i in range(1, num_users + 1):
        username = f"test{i}"
        users_list.append({
            "username": username,
            "email": f"{username}@example.com",
            "password": "StrongPass123!"
        })

    # --- 2. إنشاء المستخدمين ---
    print(f"🚀 جاري إنشاء {num_users} مستخدم بالتوازي (مهلة 10 ثوان لكل طلب)...")
    start_time = time.time()
    
    # استخدام ThreadPoolExecutor كما هو
    with concurrent.futures.ThreadPoolExecutor(max_workers=40) as executor:
        results = list(executor.map(create_user, users_list))
    
    end_time = time.time()
    failed_creation = results.count(False)
    
    if failed_creation > 0:
        print(f"⚠️ فشل إنشاء {failed_creation} حساب نهائياً (بعد 3 محاولات).")
    else:
        print(f"✅ تم تجهيز جميع المستخدمين بنجاح في {end_time - start_time:.2f} ثانية")
    
    # فجوة بسيطة لتثبيت النظام
    time.sleep(2)

    # --- 3. اختبار تسجيل الدخول المتوازي ---
    print(f"🔥 بدء اختبار تسجيل الدخول المتوازي (101 طلب)...")
    start_benchmark = time.time()

    duplicate_user = users_list[-1]
    login_tasks = users_list + [duplicate_user] 

    login_results = []
    
    with concurrent.futures.ThreadPoolExecutor(max_workers=40) as executor:
        future_to_user = {executor.submit(login_user, user): user for user in login_tasks}
        
        for future in concurrent.futures.as_completed(future_to_user):
            result = future.result()
            login_results.append(result)

    end_benchmark = time.time()

    # --- 4. تحليل النتائج ---
    successful_requests = [r for r in login_results if r['status'] == 'success']
    failed_requests = [r for r in login_results if r['status'] != 'success']
    
    dup_res = [r for r in login_results if r['username'] == duplicate_user['username']]

    print("\n" + "="*40)
    print("       📊 تقرير النتائج       ")
    print("="*40)
    print(f"إجمالي الطلبات المرسلة    : {len(login_results)}")
    print(f"طلبات ناجحة (Status 200)   : {len(successful_requests)}")
    print(f"طلبات فاشلة (Error)        : {len(failed_requests)}")
    
    if successful_requests:
        times = [r['time'] for r in successful_requests]
        print("-" * 40)
        print(f"متوسط زمن الاستجابة      : {statistics.mean(times):.4f} ثانية")
        print(f"أسرع استجابة (Min)        : {min(times):.4f} ثانية")
        print(f"أبطأ استجابة (Max)        : {max(times):.4f} ثانية")
    
    print(f"الزمن الكلي للعملية       : {end_benchmark - start_benchmark:.2f} ثانية")
    print("="*40)

    print("\n📌 تحليل الطلبات المتزامنة لنفس المستخدم:")
    if len(dup_res) == 2:
        print(f"   - الطلب 1: الحالة {dup_res[0]['status']} | الزمن {dup_res[0].get('time', 0):.4f}s")
        print(f"   - الطلب 2: الحالة {dup_res[1]['status']} | الزمن {dup_res[1].get('time', 0):.4f}s")
        if dup_res[0]['status'] == 'success' and dup_res[1]['status'] == 'success':
            t1 = dup_res[0].get('token')
            t2 = dup_res[1].get('token')
            print(f"   - التوكن: {'متطابق' if t1 == t2 else 'مختلف'}")
    else:
        print(f"   - تم استلام {len(dup_res)} رد (متوقع 2)")

if __name__ == "__main__":
    run_performance_test()