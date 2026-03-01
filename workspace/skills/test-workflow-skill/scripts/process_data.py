#!/usr/bin/env python3
"""
数据处理脚本 - 用于处理和分析收集的测试数据

类级注释:
- 功能: 处理、分析和转换测试数据
- 核心方法: analyze_data(), transform_data(), calculate_statistics()
- 配置项: 支持通过参数指定输入数据和处理选项
"""

import os
import sys
import json
import argparse
from datetime import datetime
from pathlib import Path


class DataProcessor:
    """
    数据处理器类
    
    功能说明: 提供数据分析和转换功能
    核心方法:
        - load_data(): 加载输入数据
        - analyze(): 执行数据分析
        - transform(): 转换数据格式
        - save_result(): 保存处理结果
    配置项:
        - input_file: 输入文件路径
        - output_file: 输出文件路径
        - analysis_type: 分析类型 (summary/detailed)
    """
    
    def __init__(self, input_file=None, output_file=None, analysis_type="summary"):
        """
        初始化数据处理器
        
        Args:
            input_file (str): 输入数据文件路径
            output_file (str): 输出结果文件路径
            analysis_type (str): 分析类型，可选 summary 或 detailed
        """
        self.input_file = input_file
        self.output_file = output_file
        self.analysis_type = analysis_type
        self.data = None
        self.result = {}
    
    def load_data(self):
        """
        加载输入数据
        
        Returns:
            bool: 加载是否成功
        """
        if self.input_file is None:
            # 如果没有指定输入文件，使用示例数据
            self.data = self._generate_sample_data()
            return True
        
        try:
            with open(self.input_file, 'r', encoding='utf-8') as f:
                self.data = json.load(f)
            return True
        except FileNotFoundError:
            print(f"错误: 文件未找到 {self.input_file}")
            return False
        except json.JSONDecodeError as e:
            print(f"错误: JSON解析失败 - {str(e)}")
            return False
    
    def _generate_sample_data(self):
        """
        生成示例数据（用于测试）
        
        Returns:
            dict: 示例数据字典
        """
        return {
            "test_items": [
                {"id": 1, "name": "测试项1", "status": "pass", "duration": 1.2},
                {"id": 2, "name": "测试项2", "status": "pass", "duration": 0.8},
                {"id": 3, "name": "测试项3", "status": "fail", "duration": 2.5},
                {"id": 4, "name": "测试项4", "status": "pass", "duration": 1.0},
                {"id": 5, "name": "测试项5", "status": "skip", "duration": 0.0}
            ],
            "metadata": {
                "total": 5,
                "timestamp": datetime.now().isoformat()
            }
        }
    
    def analyze(self):
        """
        执行数据分析
        
        Returns:
            dict: 分析结果
        """
        if self.data is None:
            print("错误: 未加载数据")
            return None
        
        if self.analysis_type == "summary":
            return self._summary_analysis()
        elif self.analysis_type == "detailed":
            return self._detailed_analysis()
        else:
            print(f"错误: 未知的分析类型 {self.analysis_type}")
            return None
    
    def _summary_analysis(self):
        """
        执行摘要分析
        
        Returns:
            dict: 摘要分析结果
        """
        test_items = self.data.get("test_items", [])
        
        total = len(test_items)
        passed = sum(1 for item in test_items if item.get("status") == "pass")
        failed = sum(1 for item in test_items if item.get("status") == "fail")
        skipped = sum(1 for item in test_items if item.get("status") == "skip")
        
        total_duration = sum(item.get("duration", 0) for item in test_items)
        
        self.result = {
            "analysis_type": "summary",
            "analysis_time": datetime.now().isoformat(),
            "summary": {
                "total": total,
                "passed": passed,
                "failed": failed,
                "skipped": skipped,
                "pass_rate": f"{(passed/total*100):.1f}%" if total > 0 else "0%",
                "total_duration": f"{total_duration:.2f}s"
            }
        }
        
        return self.result
    
    def _detailed_analysis(self):
        """
        执行详细分析
        
        Returns:
            dict: 详细分析结果
        """
        summary = self._summary_analysis()
        
        test_items = self.data.get("test_items", [])
        
        # 添加详细的项目分析
        item_details = []
        for item in test_items:
            item_details.append({
                "id": item.get("id"),
                "name": item.get("name"),
                "status": item.get("status"),
                "duration": f"{item.get('duration', 0):.2f}s",
                "performance": "slow" if item.get("duration", 0) > 2.0 else "normal"
            })
        
        self.result["details"] = item_details
        
        return self.result
    
    def transform(self, output_format="json"):
        """
        转换数据格式
        
        Args:
            output_format (str): 输出格式，支持 json 或 markdown
            
        Returns:
            str: 转换后的数据字符串
        """
        if output_format == "json":
            return json.dumps(self.result, indent=2, ensure_ascii=False)
        elif output_format == "markdown":
            return self._to_markdown()
        else:
            return str(self.result)
    
    def _to_markdown(self):
        """
        转换为Markdown格式
        
        Returns:
            str: Markdown格式的结果
        """
        lines = ["# 数据分析报告\n"]
        
        summary = self.result.get("summary", {})
        lines.append("## 摘要\n")
        lines.append(f"- **总项目数**: {summary.get('total', 0)}")
        lines.append(f"- **通过**: {summary.get('passed', 0)}")
        lines.append(f"- **失败**: {summary.get('failed', 0)}")
        lines.append(f"- **跳过**: {summary.get('skipped', 0)}")
        lines.append(f"- **通过率**: {summary.get('pass_rate', 'N/A')}")
        lines.append(f"- **总耗时**: {summary.get('total_duration', 'N/A')}\n")
        
        if "details" in self.result:
            lines.append("## 详细结果\n")
            lines.append("| ID | 名称 | 状态 | 耗时 | 性能 |")
            lines.append("|---|---|---|---|---|")
            for item in self.result["details"]:
                lines.append(f"| {item['id']} | {item['name']} | {item['status']} | {item['duration']} | {item['performance']} |")
        
        return "\n".join(lines)
    
    def save_result(self, content=None):
        """
        保存处理结果
        
        Args:
            content (str): 要保存的内容，如果为None则使用self.result
            
        Returns:
            bool: 保存是否成功
        """
        if content is None:
            content = json.dumps(self.result, indent=2, ensure_ascii=False)
        
        if self.output_file:
            try:
                with open(self.output_file, 'w', encoding='utf-8') as f:
                    f.write(content)
                print(f"结果已保存到: {self.output_file}")
                return True
            except Exception as e:
                print(f"保存失败: {str(e)}")
                return False
        else:
            print(content)
            return True


def main():
    """
    主函数
    """
    parser = argparse.ArgumentParser(description="数据处理脚本")
    parser.add_argument("--input", "-i", help="输入文件路径")
    parser.add_argument("--output", "-o", help="输出文件路径")
    parser.add_argument("--type", "-t", choices=["summary", "detailed"], 
                        default="summary", help="分析类型")
    parser.add_argument("--format", "-f", choices=["json", "markdown"], 
                        default="json", help="输出格式")
    
    args = parser.parse_args()
    
    # 创建处理器实例
    processor = DataProcessor(
        input_file=args.input,
        output_file=args.output,
        analysis_type=args.type
    )
    
    # 执行处理流程
    if not processor.load_data():
        return 1
    
    result = processor.analyze()
    if result is None:
        return 1
    
    content = processor.transform(output_format=args.format)
    processor.save_result(content)
    
    return 0


if __name__ == "__main__":
    sys.exit(main())
