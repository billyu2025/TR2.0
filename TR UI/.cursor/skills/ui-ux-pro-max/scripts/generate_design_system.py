#!/usr/bin/env python3
"""
UI UX Pro Max - Design System Generator
简化版设计系统生成器，用于 TR Report System
"""

import json
import sys
import argparse
from typing import Dict, List, Any

# 设计系统模板
DESIGN_SYSTEMS = {
    "enterprise": {
        "name": "Enterprise Dashboard",
        "colors": {
            "primary": "#2c3e50",
            "primaryLight": "#34495e",
            "primaryDark": "#1a252f",
            "secondary": "#667eea",
            "success": "#27ae60",
            "warning": "#f39c12",
            "error": "#e74c3c",
            "info": "#3498db",
            "background": "#f5f7fa",
            "surface": "#ffffff",
            "textPrimary": "#2c3e50",
            "textSecondary": "#7f8c8d",
            "border": "#e1e8ed"
        },
        "typography": {
            "fontFamily": "-apple-system, BlinkMacSystemFont, 'Segoe UI', 'Roboto', 'Helvetica Neue', Arial, sans-serif",
            "fontSizes": {
                "xs": "12px",
                "sm": "14px",
                "base": "16px",
                "lg": "18px",
                "xl": "20px",
                "2xl": "24px",
                "3xl": "28px",
                "4xl": "32px"
            },
            "fontWeights": {
                "normal": 400,
                "medium": 500,
                "semibold": 600,
                "bold": 700
            },
            "lineHeights": {
                "tight": 1.25,
                "normal": 1.5,
                "relaxed": 1.75
            }
        },
        "spacing": {
            "base": 8,
            "scale": [4, 8, 12, 16, 24, 32, 48, 64]
        },
        "borderRadius": {
            "sm": "4px",
            "md": "6px",
            "lg": "8px",
            "xl": "12px",
            "full": "9999px"
        },
        "shadows": {
            "sm": "0 1px 2px rgba(0, 0, 0, 0.05)",
            "md": "0 2px 8px rgba(0, 0, 0, 0.06)",
            "lg": "0 8px 16px rgba(0, 0, 0, 0.12)",
            "xl": "0 20px 60px rgba(0, 0, 0, 0.3)"
        }
    }
}

def generate_design_system(project_name: str = "TR Report System", style: str = "enterprise") -> Dict[str, Any]:
    """生成设计系统"""
    base_system = DESIGN_SYSTEMS.get(style, DESIGN_SYSTEMS["enterprise"])
    
    design_system = {
        "project": project_name,
        "style": style,
        **base_system
    }
    
    return design_system

def format_as_css_variables(design_system: Dict[str, Any]) -> str:
    """将设计系统格式化为 CSS 变量"""
    css = ":root {\n"
    
    # 颜色变量
    css += "  /* Colors */\n"
    for key, value in design_system["colors"].items():
        css += f"  --color-{key}: {value};\n"
    
    # 间距变量
    css += "\n  /* Spacing */\n"
    base = design_system["spacing"]["base"]
    for i, size in enumerate(design_system["spacing"]["scale"]):
        css += f"  --spacing-{i+1}: {size}px;\n"
    
    # 字体大小
    css += "\n  /* Typography - Font Sizes */\n"
    for key, value in design_system["typography"]["fontSizes"].items():
        css += f"  --font-size-{key}: {value};\n"
    
    # 字体粗细
    css += "\n  /* Typography - Font Weights */\n"
    for key, value in design_system["typography"]["fontWeights"].items():
        css += f"  --font-weight-{key}: {value};\n"
    
    # 圆角
    css += "\n  /* Border Radius */\n"
    for key, value in design_system["borderRadius"].items():
        css += f"  --radius-{key}: {value};\n"
    
    # 阴影
    css += "\n  /* Shadows */\n"
    for key, value in design_system["shadows"].items():
        css += f"  --shadow-{key}: {value};\n"
    
    css += "}\n"
    return css

def format_as_markdown(design_system: Dict[str, Any]) -> str:
    """将设计系统格式化为 Markdown"""
    md = f"# Design System: {design_system['project']}\n\n"
    md += f"**Style:** {design_system['style']}\n\n"
    
    md += "## Colors\n\n"
    for key, value in design_system["colors"].items():
        md += f"- `{key}`: `{value}`\n"
    
    md += "\n## Typography\n\n"
    md += f"- **Font Family:** `{design_system['typography']['fontFamily']}`\n\n"
    md += "### Font Sizes\n"
    for key, value in design_system["typography"]["fontSizes"].items():
        md += f"- `{key}`: `{value}`\n"
    
    md += "\n## Spacing\n\n"
    md += f"- **Base Unit:** {design_system['spacing']['base']}px\n"
    md += "- **Scale:** " + ", ".join([f"{s}px" for s in design_system["spacing"]["scale"]]) + "\n"
    
    return md

def main():
    parser = argparse.ArgumentParser(description="Generate design system for TR Report System")
    parser.add_argument("-p", "--project", default="TR Report System", help="Project name")
    parser.add_argument("-s", "--style", default="enterprise", help="Design style")
    parser.add_argument("-f", "--format", choices=["json", "css", "markdown"], default="markdown", help="Output format")
    parser.add_argument("--persist", action="store_true", help="Save to design-system/MASTER.md")
    
    args = parser.parse_args()
    
    # 生成设计系统
    design_system = generate_design_system(args.project, args.style)
    
    # 格式化输出
    if args.format == "json":
        output = json.dumps(design_system, indent=2)
    elif args.format == "css":
        output = format_as_css_variables(design_system)
    else:
        output = format_as_markdown(design_system)
    
    # 保存或输出
    if args.persist:
        import os
        os.makedirs("design-system", exist_ok=True)
        filepath = "design-system/MASTER.md"
        with open(filepath, "w", encoding="utf-8") as f:
            f.write(output)
        print(f"Design system saved to {filepath}")
    else:
        print(output)

if __name__ == "__main__":
    main()
