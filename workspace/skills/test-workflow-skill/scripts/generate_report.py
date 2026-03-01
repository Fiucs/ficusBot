#!/usr/bin/env python3
"""
报告生成脚本 - 用于生成格式化的测试报告

类级注释:
- 功能: 生成Markdown格式的测试执行报告
- 核心方法: generate_summary(), generate_details(), generate_report()
- 配置项: 支持通过参数指定报告标题、输出路径和包含的章节
"""

import os
import sys
import json
import argparse
from datetime import datetime
from pathlib import Path


class ReportGenerator:
    """
    报告生成器类
    
    功能说明: 生成格式化的测试执行报告
    核心方法:
        - load_data(): 加载测试数据
        - generate_summary(): 生成执行摘要
        - generate_details(): 生成详细结果
        - generate_report(): 生成完整报告
        - save_report(): 保存报告到文件
    配置项:
        - title: 报告标题
        - output_path: 输出文件路径
        - include_sections: 包含的章节列表
    """
    
    def __init__(self, title="技能工作流测试报告", output_path=None, 
                 include_sections=None):
        """
        初始化报告生成器
        
        Args:
            title (str): 报告标题
            output_path (str): 输出文件路径
            include_sections (list): 包含的章节列表
        """
        self.title = title
        self.output_path = output_path
        self.include_sections = include_sections or [
            "summary", "details", "conclusion"
        ]
        self.data = {}
        self.report_sections = []
    
    def load_data(self, data_file=None, data_dict=None):
        """
        加载测试数据
        
        Args:
            data_file (str): 数据文件路径
            data_dict (dict): 数据字典
            
        Returns:
            bool: 加载是否成功
        """
        if data_dict is not None:
            self.data = data_dict
            return True
        
        if data_file is not None:
            try:
                with open(data_file, 'r', encoding='utf-8') as f:
                    self.data = json.load(f)
                return True
            except FileNotFoundError:
                print(f"警告: 数据文件未找到 {data_file}，使用示例数据")
                self.data = self._generate_sample_data()
                return True
            except json.JSONDecodeError as e:
                print(f"错误: JSON解析失败 - {str(e)}")
                return False
        
        # 如果没有提供数据，使用示例数据
        self.data = self._generate_sample_data()
        return True
    
    def _generate_sample_data(self):
        """
        生成示例数据
        
        Returns:
            dict: 示例测试数据
        """
        return {
            "execution_time": datetime.now().isoformat(),
            "steps": [
                {
                    "step_number": 1,
                    "step_name": "数据收集",
                    "status": "success",
                    "duration": 2.5,
                    "output": "成功收集环境信息和目录结构"
                },
                {
                    "step_number": 2,
                    "step_name": "数据处理",
                    "status": "success",
                    "duration": 1.8,
                    "output": "完成数据分析和转换"
                },
                {
                    "step_number": 3,
                    "step_name": "结果验证",
                    "status": "success",
                    "duration": 0.5,
                    "output": "所有验证项通过"
                },
                {
                    "step_number": 4,
                    "step_name": "报告生成",
                    "status": "success",
                    "duration": 0.3,
                    "output": "报告生成完成"
                }
            ]
        }
    
    def generate_summary(self):
        """
        生成执行摘要
        
        Returns:
            str: Markdown格式的摘要章节
        """
        steps = self.data.get("steps", [])
        total_steps = len(steps)
        successful_steps = sum(1 for s in steps if s.get("status") == "success")
        failed_steps = sum(1 for s in steps if s.get("status") == "failed")
        skipped_steps = sum(1 for s in steps if s.get("status") == "skipped")
        
        total_duration = sum(s.get("duration", 0) for s in steps)
        
        lines = [
            "## 执行摘要\n",
            f"- **执行时间**: {self.data.get('execution_time', datetime.now().isoformat())}",
            f"- **执行步骤**: {total_steps}",
            f"- **成功步骤**: {successful_steps}",
            f"- **失败步骤**: {failed_steps}",
            f"- **跳过步骤**: {skipped_steps}",
            f"- **总耗时**: {total_duration:.2f}秒\n"
        ]
        
        return "\n".join(lines)
    
    def generate_details(self):
        """
        生成详细结果
        
        Returns:
            str: Markdown格式的详细结果章节
        """
        steps = self.data.get("steps", [])
        
        lines = ["## 详细结果\n"]
        
        for step in steps:
            step_num = step.get("step_number", 0)
            step_name = step.get("step_name", "未知步骤")
            status = step.get("status", "unknown")
            duration = step.get("duration", 0)
            output = step.get("output", "无输出")
            
            # 状态图标
            status_icon = "✅" if status == "success" else "❌" if status == "failed" else "⏭️"
            
            lines.append(f"### 步骤{step_num}: {step_name}")
            lines.append(f"- **状态**: {status_icon} {status}")
            lines.append(f"- **耗时**: {duration:.2f}秒")
            lines.append(f"- **输出**: {output}\n")
        
        return "\n".join(lines)
    
    def generate_conclusion(self):
        """
        生成结论章节
        
        Returns:
            str: Markdown格式的结论章节
        """
        steps = self.data.get("steps", [])
        total_steps = len(steps)
        successful_steps = sum(1 for s in steps if s.get("status") == "success")
        
        success_rate = (successful_steps / total_steps * 100) if total_steps > 0 else 0
        
        if success_rate == 100:
            conclusion = "所有步骤执行成功，技能工作流运行正常。"
            recommendation = "可以继续使用此技能进行多步骤任务测试。"
        elif success_rate >= 80:
            conclusion = f"大部分步骤执行成功（{success_rate:.1f}%），技能工作流基本正常。"
            recommendation = "建议检查失败的步骤，排查潜在问题。"
        else:
            conclusion = f"多个步骤执行失败（成功率{success_rate:.1f}%），技能工作流存在问题。"
            recommendation = "建议全面检查技能配置和执行环境。"
        
        lines = [
            "## 结论\n",
            f"**总体评价**: {conclusion}",
            f"**建议**: {recommendation}\n"
        ]
        
        return "\n".join(lines)
    
    def generate_report(self):
        """
        生成完整报告
        
        Returns:
            str: 完整的Markdown报告
        """
        # 报告标题
        self.report_sections = [f"# {self.title}\n"]
        
        # 根据配置生成各章节
        if "summary" in self.include_sections:
            self.report_sections.append(self.generate_summary())
        
        if "details" in self.include_sections:
            self.report_sections.append(self.generate_details())
        
        if "conclusion" in self.include_sections:
            self.report_sections.append(self.generate_conclusion())
        
        return "\n".join(self.report_sections)
    
    def save_report(self, report_content=None):
        """
        保存报告到文件
        
        Args:
            report_content (str): 报告内容，如果为None则重新生成
            
        Returns:
            bool: 保存是否成功
        """
        if report_content is None:
            report_content = self.generate_report()
        
        if self.output_path:
            try:
                # 确保目录存在
                output_dir = Path(self.output_path).parent
                output_dir.mkdir(parents=True, exist_ok=True)
                
                with open(self.output_path, 'w', encoding='utf-8') as f:
                    f.write(report_content)
                print(f"报告已保存到: {self.output_path}")
                return True
            except Exception as e:
                print(f"保存报告失败: {str(e)}")
                return False
        else:
            print(report_content)
            return True


def main():
    """
    主函数
    """
    parser = argparse.ArgumentParser(description="报告生成脚本")
    parser.add_argument("--data", "-d", help="输入数据文件路径")
    parser.add_argument("--output", "-o", help="输出报告文件路径")
    parser.add_argument("--title", "-t", default="技能工作流测试报告", 
                        help="报告标题")
    parser.add_argument("--sections", "-s", nargs="+", 
                        choices=["summary", "details", "conclusion"],
                        default=["summary", "details", "conclusion"],
                        help="包含的章节")
    
    args = parser.parse_args()
    
    # 创建报告生成器
    generator = ReportGenerator(
        title=args.title,
        output_path=args.output,
        include_sections=args.sections
    )
    
    # 加载数据
    if not generator.load_data(data_file=args.data):
        return 1
    
    # 生成并保存报告
    report = generator.generate_report()
    generator.save_report(report)
    
    return 0


if __name__ == "__main__":
    sys.exit(main())
