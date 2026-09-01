# fastapi_core/train_nn_model.py
import torch
import torch.nn as nn
import torch.optim as optim
from torch.utils.data import DataLoader, TensorDataset
import pandas as pd
import numpy as np
from sklearn.model_selection import train_test_split
from sklearn.preprocessing import StandardScaler
import joblib
from pathlib import Path
from data_pipeline import load_and_clean_data

# ---------- تنظیمات ----------
MODEL_DIR = Path(__file__).parent / "models"
MODEL_DIR.mkdir(exist_ok=True)

# ---------- تعریف مدل ----------
class StudentRiskModel(nn.Module):
    def __init__(self, input_dim, hidden_layers=[128, 64, 32], dropout_rate=0.3):
        super(StudentRiskModel, self).__init__()
        layers = []
        prev_dim = input_dim
        for hidden_dim in hidden_layers:
            layers.append(nn.Linear(prev_dim, hidden_dim))
            layers.append(nn.ReLU())
            layers.append(nn.Dropout(dropout_rate))
            prev_dim = hidden_dim
        # لایه خروجی
        layers.append(nn.Linear(prev_dim, 1))
        layers.append(nn.Sigmoid())
        self.model = nn.Sequential(*layers)
    
    def forward(self, x):
        return self.model(x)

# ---------- تابع آموزش ----------
def train_model():
    # 1. بارگذاری داده‌های پاک‌شده
    df, features, target = load_and_clean_data()
    X = df[features].values
    y = df[target].values
    
    # 2. تقسیم داده‌ها
    X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2, random_state=42, stratify=y)
    
    # 3. استانداردسازی (Standardization)
    scaler = StandardScaler()
    X_train = scaler.fit_transform(X_train)
    X_test = scaler.transform(X_test)
    
    # ذخیره‌سازی scaler برای استفاده در FastAPI
    joblib.dump(scaler, MODEL_DIR / "scaler.joblib")
    
    # 4. تبدیل به تنسورهای PyTorch
    X_train_t = torch.tensor(X_train, dtype=torch.float32)
    y_train_t = torch.tensor(y_train, dtype=torch.float32).view(-1, 1)
    X_test_t = torch.tensor(X_test, dtype=torch.float32)
    y_test_t = torch.tensor(y_test, dtype=torch.float32).view(-1, 1)
    
    # 5. ایجاد DataLoader
    train_dataset = TensorDataset(X_train_t, y_train_t)
    test_dataset = TensorDataset(X_test_t, y_test_t)
    train_loader = DataLoader(train_dataset, batch_size=64, shuffle=True)
    test_loader = DataLoader(test_dataset, batch_size=64, shuffle=False)
    
    # 6. تعریف مدل
    input_dim = X_train.shape[1]
    model = StudentRiskModel(input_dim=input_dim)
    print(f"مدل با {input_dim} ویژگی ورودی ساخته شد.")
    
    # 7. تنظیمات آموزش
    criterion = nn.BCELoss()
    optimizer = optim.Adam(model.parameters(), lr=0.001)
    epochs = 50
    
    # 8. حلقه‌ی آموزش
    for epoch in range(epochs):
        model.train()
        train_loss = 0.0
        for batch_X, batch_y in train_loader:
            optimizer.zero_grad()
            outputs = model(batch_X)
            loss = criterion(outputs, batch_y)
            loss.backward()
            optimizer.step()
            train_loss += loss.item() * batch_X.size(0)
        
        train_loss /= len(train_loader.dataset)
        
        # ارزیابی در هر ۱۰ epochs
        if (epoch+1) % 10 == 0:
            model.eval()
            correct = 0
            total = 0
            with torch.no_grad():
                for batch_X, batch_y in test_loader:
                    outputs = model(batch_X)
                    predicted = (outputs > 0.5).float()
                    total += batch_y.size(0)
                    correct += (predicted == batch_y).sum().item()
            accuracy = correct / total
            print(f"Epoch {epoch+1}/{epochs}, Loss: {train_loss:.4f}, Accuracy: {accuracy:.4f}")
    
    # 9. ذخیره‌سازی مدل
    model_path = MODEL_DIR / "student_risk_model.pth"
    torch.save(model.state_dict(), model_path)
    print(f"مدل در {model_path} ذخیره شد.")
    
    return model, scaler

if __name__ == "__main__":
    train_model()