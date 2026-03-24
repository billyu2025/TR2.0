# PostgreSQL 数据库表定时更新配置指南

本指南说明如何在 PostgreSQL 数据库中设置定时更新 `TR_Report` 和 `TR_Report_Deduplication` 表。

## 📋 更新流程

1. **更新 TR_Report 表**：从 SQL Server 查询近3年数据，生成 `TR_Report` 表
2. **更新 TR_Report_Deduplication 表**：从 `TR_Report` 表按 `Order_No` 去重生成 `TR_Report_Deduplication` 表

## 🔧 方法 1：使用 Windows 任务计划程序（推荐）

### 步骤 1：创建批处理脚本

已创建 `update_tr_tables_postgres.bat` 脚本，该脚本会：
- 设置 PostgreSQL 环境变量
- 依次执行两个更新脚本
- 记录执行结果

### 步骤 2：配置 Windows 任务计划程序

1. **打开任务计划程序**
   - 按 `Win + R`，输入 `taskschd.msc`，回车

2. **创建基本任务**
   - 点击右侧"创建基本任务"
   - 名称：`TR PostgreSQL 数据库更新`
   - 描述：`每天自动更新 TR_Report 和 TR_Report_Deduplication 表`

3. **设置触发器**
   - 选择"每天"
   - 设置执行时间（例如：每天凌晨 2:00）

4. **设置操作**
   - 操作：启动程序
   - 程序或脚本：`C:\TR-master\TR UI\backend\update_tr_tables_postgres.bat`
   - 添加参数：`scheduled`（可选，用于静默运行）
   - 起始于：`C:\TR-master\TR UI\backend`

5. **完成配置**
   - 勾选"当单击完成时，打开此任务属性的对话框"
   - 在"常规"选项卡中：
     - 勾选"不管用户是否登录都要运行"
     - 勾选"使用最高权限运行"
   - 在"条件"选项卡中：
     - 取消勾选"只有在计算机使用交流电源时才启动此任务"（如果需要）
   - 在"设置"选项卡中：
     - 勾选"允许按需运行任务"
     - 勾选"如果请求的任务正在运行，则停止现有实例"

### 步骤 3：测试任务

1. 在任务计划程序中找到创建的任务
2. 右键点击 → "运行"
3. 检查日志文件确认执行成功：
   - `backend\logs\tr_report_3years_*.log`
   - `backend\logs\tr_report_deduplication_*.log`

## 🔧 方法 2：使用 Python 定时任务（可选）

如果需要更灵活的控制，可以创建一个 Python 定时任务脚本：

```python
# schedule_tr_update.py
import schedule
import time
import subprocess
import os
from datetime import datetime

def update_tr_tables():
    """执行 TR 表更新"""
    print(f"[{datetime.now()}] 开始更新 TR 表...")
    
    # 设置环境变量
    os.environ['DB_BACKEND'] = 'postgres'
    os.environ['POSTGRES_DSN'] = 'postgresql://postgres:postgres@127.0.0.1:5432/tr_db'
    
    # 执行更新脚本
    backend_dir = os.path.dirname(__file__)
    
    # 更新 TR_Report
    result1 = subprocess.run(['python', 'generate_tr_report_3years.py'], 
                            cwd=backend_dir, capture_output=True, text=True)
    if result1.returncode != 0:
        print(f"错误: TR_Report 更新失败\n{result1.stderr}")
        return
    
    # 更新 TR_Report_Deduplication
    result2 = subprocess.run(['python', 'update_tr_report_deduplication.py'], 
                            cwd=backend_dir, capture_output=True, text=True)
    if result2.returncode != 0:
        print(f"错误: TR_Report_Deduplication 更新失败\n{result2.stderr}")
        return
    
    print(f"[{datetime.now()}] TR 表更新完成")

# 设置定时任务（每天凌晨 2:00）
schedule.every().day.at("02:00").do(update_tr_tables)

# 运行调度器
print("TR 表定时更新任务已启动，每天 02:00 执行")
while True:
    schedule.run_pending()
    time.sleep(60)  # 每分钟检查一次
```

运行方式：
```bash
cd "C:\TR-master\TR UI\backend"
python schedule_tr_update.py
```

## 📝 注意事项

1. **环境变量**：确保 `POSTGRES_DSN` 环境变量正确设置
2. **数据库连接**：确保 PostgreSQL 服务正在运行
3. **SQL Server 连接**：确保可以访问 SQL Server（192.168.80.242）
4. **日志文件**：更新日志保存在 `backend\logs\` 目录下
5. **权限**：确保运行任务的用户有足够的权限访问数据库和文件系统

## 🔍 验证更新

更新完成后，可以通过以下方式验证：

1. **使用 DBeaver 或其他数据库工具**：
   ```sql
   SELECT COUNT(*) FROM "TR_Report";
   SELECT COUNT(*) FROM "TR_Report_Deduplication";
   SELECT MAX("Del_Date") FROM "TR_Report";
   ```

2. **查看日志文件**：
   - 检查 `backend\logs\tr_report_3years_*.log`
   - 检查 `backend\logs\tr_report_deduplication_*.log`

3. **在前端页面查看**：
   - 打开前端页面，查看订单列表是否包含最新数据

## 🛠️ 故障排除

如果更新失败，请检查：

1. **PostgreSQL 服务是否运行**
   ```bash
   # 检查服务状态
   sc query postgresql-x64-16
   ```

2. **环境变量是否正确**
   ```bash
   echo %POSTGRES_DSN%
   echo %DB_BACKEND%
   ```

3. **Python 脚本是否可以手动运行**
   ```bash
   cd "C:\TR-master\TR UI\backend"
   set DB_BACKEND=postgres
   set POSTGRES_DSN=postgresql://postgres:postgres@127.0.0.1:5432/tr_db
   python generate_tr_report_3years.py
   python update_tr_report_deduplication.py
   ```

4. **查看详细错误日志**
   - 检查 `backend\logs\` 目录下的最新日志文件
