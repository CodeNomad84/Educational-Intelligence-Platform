# fastapi_core/data_pipeline.py
import pandas as pd
import numpy as np
from pathlib import Path
import re
from datetime import datetime

# ---------- مسیر فایل‌ها ----------
if Path("/data").exists():
    DATA_DIR = Path("/data/student-performance-attendance")
else:
    DATA_DIR = Path(__file__).parent.parent / "data" / "student-performance-attendance"


STUDENTS_CSV = DATA_DIR / "students.csv"
ATTENDANCE_CSV = DATA_DIR / "attendance.csv"
HOMEWORK_CSV = DATA_DIR / "homework.csv"
PERFORMANCE_CSV = DATA_DIR / "performance.csv"
COMMUNICATION_CSV = DATA_DIR / "teacher_parent_communication.csv"

# ---------- توابع کمکی ----------
def clean_percentage(val):
    """تبدیل '76' یا '90%' یا '100%' به عدد اعشاری (0.76, 0.9, 1.0)"""
    if pd.isna(val):
        return np.nan
    if isinstance(val, str):
        val = val.strip().replace('%', '').replace(' ', '')
    try:
        return round(float(val) / 100.0, 3)
    except:
        return np.nan

def safe_float(val):
    try:
        return float(val)
    except:
        return np.nan

def normalize_date(date_str):
    """یکسان‌سازی فرمت تاریخ (MM/DD/YYYY یا YYYY-MM-DD) به YYYY-MM-DD"""
    if pd.isna(date_str):
        return np.nan
    date_str = str(date_str).strip()
    for fmt in ['%m/%d/%Y', '%Y-%m-%d', '%d/%m/%Y']:
        try:
            return datetime.strptime(date_str, fmt).strftime('%Y-%m-%d')
        except:
            continue
    return np.nan

def parse_grade(grade_str):
    """استخراج عدد از 'Grade 3' یا 'Grade 12'"""
    if pd.isna(grade_str):
        return np.nan
    match = re.search(r'(\d+)', str(grade_str))
    if match:
        return int(match.group(1))
    return np.nan

def is_completed(status_val):
    """تشخیص انجام تکلیف بر اساس وضعیت (✅)"""
    if pd.isna(status_val):
        return False
    status_str = str(status_val).strip()
    # بررسی وجود ایموجی تیک یا کلمه‌های کلیدی
    return '✅' in status_str or 'completed' in status_str.lower() or 'done' in status_str.lower()

# ---------- تابع اصلی پاک‌سازی ----------
def load_and_clean_data():
    """بارگذاری و پاک‌سازی تمام فایل‌ها و برگرداندن دیتاست نهایی"""
    
    # 1. خواندن فایل دانش‌آموزان
    students = pd.read_csv(STUDENTS_CSV)
    students.columns = students.columns.str.strip()
    # نگاشت نام ستون‌ها
    students.rename(columns={
        'Student_ID': 'student_id',
        'Full_Name': 'full_name',
        'Grade_Level': 'grade_level',
        'Emergency_Contact': 'emergency_contact'
    }, inplace=True)
    students['student_id'] = students['student_id'].astype(str).str.strip()
    # استخراج پایه تحصیلی از 'Grade 3'
    students['grade'] = students['grade_level'].apply(parse_grade)
    # حذف ردیف‌هایی که پایه ندارند
    students = students.dropna(subset=['grade'])
    students['grade'] = students['grade'].astype(int)
    
    # 2. خواندن فایل حضور و غیاب
    attendance = pd.read_csv(ATTENDANCE_CSV)
    attendance.columns = attendance.columns.str.strip()
    attendance.rename(columns={
        'Student_ID': 'student_id',
        'Attendance_Status': 'status'
    }, inplace=True)
    attendance['student_id'] = attendance['student_id'].astype(str).str.strip()
    # یکسان‌سازی وضعیت (به حروف کوچک)
    attendance['status'] = attendance['status'].str.lower().str.strip()
    status_map = {
        'present': 'present',
        'absent': 'absent',
        'late': 'late',
        'excused': 'excused'
    }
    attendance['status'] = attendance['status'].map(status_map).fillna('absent')
    # تاریخ (برای استفاده‌ی بعدی، فعلاً فقط برای نمایش)
    attendance['date'] = attendance['Date'].apply(normalize_date)
    
    # 3. خواندن فایل تکالیف
    homework = pd.read_csv(HOMEWORK_CSV)
    homework.columns = homework.columns.str.strip()
    homework.rename(columns={
        'Student_ID': 'student_id',
        'Status': 'hw_status'
    }, inplace=True)
    homework['student_id'] = homework['student_id'].astype(str).str.strip()
    # تشخیص انجام تکلیف
    homework['completed'] = homework['hw_status'].apply(is_completed)
    
    # 4. خواندن فایل عملکرد امتحانی
    performance = pd.read_csv(PERFORMANCE_CSV)
    performance.columns = performance.columns.str.strip()
    performance.rename(columns={
        'Student_ID': 'student_id',
        'Exam_Score': 'exam_score',
        'Homework_Completion_%': 'completion_rate_raw'
    }, inplace=True)
    performance['student_id'] = performance['student_id'].astype(str).str.strip()
    # تبدیل نمرات به عدد (با محدودیت ۰ تا ۱۰۰)
    performance['exam_score'] = performance['exam_score'].apply(safe_float)
    performance.loc[performance['exam_score'] > 100, 'exam_score'] = 100
    performance.loc[performance['exam_score'] < 0, 'exam_score'] = 0
    # تبدیل درصد تکمیل (مثل 76 یا 100%)
    performance['completion_rate'] = performance['completion_rate_raw'].apply(clean_percentage)
    # پر کردن مقادیر NaN در نرخ تکمیل با میانگین
    mean_completion = performance['completion_rate'].mean()
    performance['completion_rate'] = performance['completion_rate'].fillna(mean_completion)
    
    # 5. خواندن فایل ارتباطات
    comm = pd.read_csv(COMMUNICATION_CSV)
    comm.columns = comm.columns.str.strip()
    comm.rename(columns={
        'Student_ID': 'student_id'
    }, inplace=True)
    comm['student_id'] = comm['student_id'].astype(str).str.strip()
    
    # ---------- استخراج ویژگی‌ها (Feature Engineering) ----------
    
    # 6. ویژگی‌های حضور و غیاب
    att_features = attendance.groupby('student_id').agg(
        total_absences=('status', lambda x: (x == 'absent').sum()),
        total_lates=('status', lambda x: (x == 'late').sum()),
        total_days=('status', 'count')
    ).reset_index()
    # نرخ حضور: 1 - (تعداد غیبت / کل روزها)
    att_features['attendance_rate'] = 1 - (att_features['total_absences'] / att_features['total_days'])
    att_features['attendance_rate'] = att_features['attendance_rate'].round(3)
    # پر کردن مقادیر NaN یا بی‌نهایت
    att_features['attendance_rate'] = att_features['attendance_rate'].fillna(1.0)
    
    # 7. ویژگی‌های تکالیف
    hw_features = homework.groupby('student_id').agg(
        total_homework=('hw_status', 'count'),
        completed_homework=('completed', 'sum')
    ).reset_index()
    # نرخ تکمیل تکالیف
    hw_features['avg_completion_rate'] = hw_features['completed_homework'] / hw_features['total_homework']
    hw_features['avg_completion_rate'] = hw_features['avg_completion_rate'].round(3).fillna(0)
    
    # 8. ویژگی‌های عملکرد امتحانی (میانگین نمرات)
    perf_features = performance.groupby('student_id').agg(
        avg_exam_score=('exam_score', 'mean')
    ).reset_index()
    perf_features['avg_exam_score'] = perf_features['avg_exam_score'].round(2)
    
    # 9. ویژگی‌های ارتباطات (تعداد پیام‌ها)
    comm_features = comm.groupby('student_id').agg(
        total_communications=('student_id', 'count')
    ).reset_index()
    
    # 10. ادغام همه‌ی ویژگی‌ها در یک دیتافریم
    # ابتدا از students شروع می‌کنیم
    merged = students[['student_id', 'grade']].copy()
    # اضافه کردن ویژگی‌ها با left join
    merged = merged.merge(att_features, on='student_id', how='left')
    merged = merged.merge(hw_features, on='student_id', how='left')
    merged = merged.merge(perf_features, on='student_id', how='left')
    merged = merged.merge(comm_features, on='student_id', how='left')
    
    # 11. پر کردن مقادیر گم‌شده (NaN) با مقادیر پیش‌فرض
    merged['attendance_rate'] = merged['attendance_rate'].fillna(1.0)
    merged['avg_completion_rate'] = merged['avg_completion_rate'].fillna(0.5)
    merged['avg_exam_score'] = merged['avg_exam_score'].fillna(10.0)
    merged['total_absences'] = merged['total_absences'].fillna(0)
    merged['total_lates'] = merged['total_lates'].fillna(0)
    merged['total_communications'] = merged['total_communications'].fillna(0)
    merged['completed_homework'] = merged['completed_homework'].fillna(0)
    merged['total_homework'] = merged['total_homework'].fillna(1)  # جلوگیری از تقسیم بر صفر
    
    # 12. ایجاد ویژگی هدف (Target) - ریسک افت تحصیلی
    # شرط: میانگین نمره کمتر از ۱۲ و غیبت بیشتر از ۵ جلسه
    merged['risk'] = ((merged['avg_exam_score'] < 12) & (merged['total_absences'] > 5)).astype(int)
    
    # 13. انتخاب ستون‌های نهایی برای آموزش
    features = [
        'grade', 'attendance_rate', 'avg_completion_rate', 
        'avg_exam_score', 'total_absences', 'total_lates',
        'total_communications', 'completed_homework'
    ]
    target = 'risk'
    
    final_df = merged[features + [target]].copy()
    
    # حذف ردیف‌های با داده‌های گم‌شده (در صورت وجود)
    final_df = final_df.dropna()
    
    print(f"✅ دیتاست نهایی با {len(final_df)} رکورد و {len(features)} ویژگی آماده شد.")
    print(f"📊 توزیع هدف (ریسک): {final_df['risk'].value_counts().to_dict()}")
    return final_df, features, target

# ---------- اجرای مستقیم برای تست ----------
if __name__ == "__main__":
    df, features, target = load_and_clean_data()
    print("\n📋 نمونه‌ای از داده‌های نهایی:")
    print(df.head())