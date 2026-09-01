# fastapi_core/train_model.py
import pandas as pd
import numpy as np
from sklearn.linear_model import LogisticRegression
from sklearn.model_selection import train_test_split
from sklearn.metrics import accuracy_score
import joblib
import os

def train_and_save_model():
    """
    تولید داده‌های ساختگی برای پیش‌بینی موفقیت تحصیلی
    ورودی‌ها: میانگین نمرات (0-20) و میزان غیبت (تعداد جلسات)
    خروجی: 1 = موفق / 0 = نیاز به تلاش بیشتر
    """
    # تولید ۲۰۰ نمونه داده‌ی تصادفی
    np.random.seed(42)
    n_samples = 200
    
    # میانگین نمرات بین ۰ تا ۲۰
    avg_score = np.random.uniform(5, 19.5, n_samples)
    # تعداد غیبت بین ۰ تا ۲۰ جلسه
    absences = np.random.randint(0, 20, n_samples)
    
    # قانون ساختگی برای تعیین برچسب (Label):
    # اگر نمره بالای ۱۲ بود و غیبت کمتر از ۵ بود -> موفق (۱)
    # در غیر این صورت -> نیاز به تلاش (۰)
    labels = ((avg_score > 12) & (absences < 5)).astype(int)
    
    # ساختن دیتافریم
    df = pd.DataFrame({
        'avg_score': avg_score,
        'absences': absences,
        'success': labels
    })
    
    # جداسازی ویژگی‌ها و هدف
    X = df[['avg_score', 'absences']]
    y = df['success']
    
    # تقسیم به آموزش و تست
    X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2, random_state=42)
    
    # آموزش مدل رگرسیون لجستیک
    model = LogisticRegression()
    model.fit(X_train, y_train)
    
    # ارزیابی
    y_pred = model.predict(X_test)
    accuracy = accuracy_score(y_test, y_pred)
    print(f"دقت مدل: {accuracy:.2f}")
    
    # ذخیره‌سازی مدل در فایل
    model_path = os.path.join(os.path.dirname(__file__), "student_model.joblib")
    joblib.dump(model, model_path)
    print(f"مدل در مسیر {model_path} ذخیره شد.")
    
    return model_path

if __name__ == "__main__":
    train_and_save_model()