# B 站直播弹幕姬 Python 版

Python 抓取 B 站直播弹幕。

基于[B站直播弹幕姬Python版](https://github.com/lyyyuna/bilibili_danmu)进行更新。

## 简单说明

B 站弹幕协议是会变的，目前至少改过一次。故不能保证向后兼容性。

我尽量保持更新（目前还仅仅是 TCP socket 版，待我学学 WebSockets 再增加 WebSockets 版啥的）

### 依赖

* Python 3.5-3.10
* pip3 install aiohttp requests

### 快速开始

在 config.py 中配置是否显示礼物、欢迎信息。

在命令行中，

    python3 main.py
    
根据提示输入房间号即可。

### 参考的API项目

[SocialSisterYi/bilibili-API-collect 直播信息流](https://github.com/SocialSisterYi/bilibili-API-collect/blob/master/live/message_stream.md)  

[lovelyyoshino/Bilibili-Live-API Bilibili 直播弹幕 WebSocket 协议](https://github.com/lovelyyoshino/Bilibili-Live-API/blob/master/API.WebSocket.md)

### CHANGE_LOG

2022/3/14：通过对直播间340、255的监听，应该没有遗漏的cmd标签了，具体解析内容准备以后推给易姐的repo
