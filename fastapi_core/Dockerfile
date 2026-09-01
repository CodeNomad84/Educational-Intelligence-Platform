# استفاده از ایمیج سبک پایتون
FROM python:3.10-slim

# جلوگیری از تولید فایل‌های .pyc و بافر شدن خروجی
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

# پوشه کاری داخل container
WORKDIR /app

# نصب torch (نسخه CPU) با timeout بالا از منبع رسمی PyTorch
RUN pip install --default-timeout=3000 --retries=5 --no-cache-dir torch --index-url https://download.pytorch.org/whl/cpu

# اول فقط requirements را کپی می‌کنیم (برای کش بهتر)
COPY requirements.txt .
RUN pip install --default-timeout=3000 --retries=5 --no-cache-dir -r requirements.txt


# سپس بقیه کدها
COPY . .

# پورتی که سرویس روی آن گوش می‌دهد
EXPOSE 8001

# دستور اجرا
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8001", "--reload"]

