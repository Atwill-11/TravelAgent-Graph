"""本包包含用于生成智能体提示的函数。"""

import os
from datetime import datetime

from app.core.prompts.travels import (
    PLAN_MODEL_PROMPT, 
    SUBAGENT_PROMPT, 
    SUMMARY_PROMPT
)
from app.core.config import settings

def load_system_prompt(**kwargs):
    """从文件加载系统提示"""
    with open(os.path.join(os.path.dirname(__file__), "system.md"), "r", encoding="utf-8") as f:
        return f.read().format(
            agent_name=settings.PROJECT_NAME + " Agent",
            current_date_and_time=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            **kwargs,
        )
