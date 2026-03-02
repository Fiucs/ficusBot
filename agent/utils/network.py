#!/usr/bin/env python
# -*- coding:utf-8 -*-
# @FileName  :network.py
# @Time      :2026/03/02
# @Author    :Ficus

"""
网络工具模块

功能说明:
    - 获取本机局域网 IP 地址
    - 获取所有网络接口信息

核心方法:
    - get_local_ip: 获取本机局域网 IP
    - get_all_ips: 获取所有网络接口 IP
"""

import socket
from typing import List, Optional


def get_local_ip() -> Optional[str]:
    """
    获取本机局域网 IP 地址。
    
    优先返回私有 IP 地址（192.168.x.x, 10.x.x.x, 172.16-31.x.x）。
    
    返回:
        Optional[str]: 局域网 IP 地址，获取失败返回 None
    
    使用示例:
        ip = get_local_ip()
        print(f"局域网 IP: {ip}")  # 例如: 192.168.1.100
    """
    def is_private_ip(ip: str) -> bool:
        """检查是否为私有 IP"""
        if ip.startswith("192.168."):
            return True
        if ip.startswith("10."):
            return True
        if ip.startswith("172."):
            parts = ip.split(".")
            if len(parts) >= 2:
                second = int(parts[1])
                if 16 <= second <= 31:
                    return True
        return False
    
    try:
        # 方法1：获取所有接口 IP，优先返回私有 IP
        hostname = socket.gethostname()
        addr_infos = socket.getaddrinfo(hostname, None)
        
        private_ips = []
        other_ips = []
        
        for addr_info in addr_infos:
            ip = addr_info[4][0]
            # 跳过 IPv6 和回环地址
            if ":" in ip or ip.startswith("127."):
                continue
            if is_private_ip(ip):
                private_ips.append(ip)
            elif not ip.startswith("169.254."):  # 跳过链路本地地址
                other_ips.append(ip)
        
        # 优先返回私有 IP
        if private_ips:
            return private_ips[0]
        if other_ips:
            return other_ips[0]
        
        # 方法2：通过 UDP 连接获取
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        local_ip = s.getsockname()[0]
        s.close()
        return local_ip
        
    except Exception:
        return None


def get_all_ips() -> List[str]:
    """
    获取本机所有网络接口的 IP 地址。
    
    返回:
        List[str]: IP 地址列表
    
    使用示例:
        ips = get_all_ips()
        for ip in ips:
            print(f"IP: {ip}")
    """
    ips = []
    try:
        hostname = socket.gethostname()
        addr_infos = socket.getaddrinfo(hostname, None)
        
        for addr_info in addr_infos:
            ip = addr_info[4][0]
            if ip not in ips and not ip.startswith("127."):
                ips.append(ip)
    except Exception:
        pass
    
    # 如果上面方法失败，尝试使用 get_local_ip
    if not ips:
        local_ip = get_local_ip()
        if local_ip:
            ips.append(local_ip)
    
    return ips


def format_url(host: str, port: int, path: str = "") -> str:
    """
    格式化 URL。
    
    参数:
        host: 主机地址
        port: 端口号
        path: 路径（可选）
    
    返回:
        str: 格式化后的 URL
    
    使用示例:
        url = format_url("0.0.0.0", 8080, "/docs")
        # 返回: http://0.0.0.0:8080/docs
    """
    if path and not path.startswith("/"):
        path = "/" + path
    return f"http://{host}:{port}{path}"
