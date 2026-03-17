"""
Agent Install Script Endpoint
为 agent.py 添加安装脚本端点的扩展模块
"""
import os
from pathlib import Path
from fastapi import HTTPException
from fastapi.responses import FileResponse


def add_install_endpoint(router):
    """添加安装脚本端点到路由器"""
    
    @router.get("/install.sh")
    async def get_agent_install_script():
        """
        Agent 安装脚本下载接口 (Agent Install Script Download)
        
        提供 VigilOps Agent 一键安装脚本，支持前端生成的安装命令。
        
        Returns:
            FileResponse: install-agent.sh 脚本文件
        Raises:
            HTTPException 404: 安装脚本文件不存在
        功能：
            - 作为 GitHub raw URL 的本地 fallback
            - 支持内网环境无法访问 GitHub 的场景
            - 提供与 GitHub 版本一致的安装脚本
        """
        # 查找安装脚本文件路径（相对于项目根目录）
        # 先尝试相对路径（开发环境），再尝试绝对路径（Docker环境）
        script_path = Path(__file__).parent.parent.parent.parent / "scripts" / "install-agent.sh"
        if not script_path.exists():
            script_path = Path("/scripts/install-agent.sh")
        
        if not script_path.exists():
            raise HTTPException(status_code=404, detail="Install script not found")
        
        return FileResponse(
            path=str(script_path),
            filename="install-agent.sh",
            media_type="text/plain",
            headers={
                "Cache-Control": "no-cache, no-store, must-revalidate",
                "Pragma": "no-cache",
                "Expires": "0"
            }
        )