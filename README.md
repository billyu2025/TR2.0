# PDF自动化生成工具

基于Excel数据自动生成PDF报告的Python工具。

## 功能特性

- 📊 自动读取Excel数据
- 📈 生成多种类型的图表（折线图、柱状图、直方图、散点图）
- 📋 创建数据表格
- 🎨 美观的PDF布局和样式
- 🌏 支持中文字体显示

## 安装依赖

```bash
pip install -r requirements.txt
```

## 使用方法

### 基本使用

1. 将你的Excel文件命名为 `data.xlsx` 并放在项目目录下
2. 运行脚本：
   ```bash
   python pdf_generator.py
   ```
3. 生成的PDF文件将保存为 `数据分析报告.pdf`

### 自定义使用

```python
from pdf_generator import PDFGenerator

# 创建生成器实例
generator = PDFGenerator("your_data.xlsx")

# 加载数据
generator.load_data()

# 生成PDF（可自定义选项）
generator.generate_pdf(
    output_path="自定义报告.pdf",
    include_charts=True,  # 是否包含图表
    include_table=True    # 是否包含数据表格
)
```

## 输出内容

生成的PDF包含：

1. **标题页** - 报告标题
2. **数据概览** - 数据基本统计信息
3. **数据表格** - 前20行数据的表格展示
4. **数据图表** - 数值列的图表展示（折线图）

## 自定义图表

你可以创建特定类型的图表：

```python
# 创建折线图
chart = generator.create_chart('line', '列名', '图表标题')

# 创建柱状图
chart = generator.create_chart('bar', '列名', '图表标题')

# 创建直方图
chart = generator.create_chart('hist', '列名', '图表标题')

# 创建散点图
chart = generator.create_chart('scatter', None, '散点图')
```

## 注意事项

- 确保Excel文件格式正确
- 数值列会自动生成图表
- 图表支持中文显示
- PDF使用A4纸张大小

## 下一步

请告诉我你希望PDF的具体格式要求，我可以进一步定制：
- 页面布局和样式
- 特定的图表类型
- 数据筛选和分组
- 自定义标题和内容
- 公司logo或水印等
