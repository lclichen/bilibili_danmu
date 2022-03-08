import asyncio
import json
import random
import re
import sys,zlib
import xml.dom.minidom
from struct import *

import aiohttp
import requests

import config


class bilibiliClient():
    def __init__(self):

        self._getDanmuInfo_Url = 'http://api.live.bilibili.com/xlive/web-room/v1/index/getDanmuInfo?id='
        self._roomId = 0
        self._ChatHost = ''
        self._WssHost = ''
        self._ChatPort = 2243
        self._WsPort = 2244
        self._WssPort = 443



        self._CIDInfoUrl = 'http://live.bilibili.com/api/player?id=cid:'
        
        
        self._protocolversion = 2
        self._reader = 0
        self._writer = 0
        self.connected = False
        self._UserCount = 0
        

        self._roomId = input('请输入房间号：')# 23784093 测试用房间号
        self._roomId = int(self._roomId)

    async def connectServer(self):
        print ('正在进入房间……')
        s1 = requests.Session()
        r1 = s1.get(self._getDanmuInfo_Url + str(self._roomId))
        j1 = json.loads(r1.text)
        print(j1)
        host_num = 0
        host_0 = j1['data']['host_list'][host_num]
        self._ChatHost = host_0['host']
        self._ChatPort = host_0['port']
        self._WsPort = host_0['ws_port']
        self._WssPort = host_0['ws_port']
        self._token = j1['data']['token']
        self._WssHost = 'wss://'+self._ChatHost+':'+str(self._WssPort)+'/sub'

        reader, writer = await asyncio.open_connection(self._ChatHost, self._ChatPort,limit=2048)
        self._reader = reader
        self._writer = writer
        print ('链接弹幕中……')
        if (await self.SendJoinChannel(self._roomId) == True):
            self.connected = True
            print ('进入房间成功')
            print ('链接弹幕成功')
            await self.ReceiveMessageLoop()

    async def HeartbeatLoop(self):
        while self.connected == False:
            await asyncio.sleep(0.5)

        while self.connected == True:
            await self.SendSocketData(0, 16, self._protocolversion, 2, 1, "")#操作码2：心跳包#(封包总大小（头部大小+正文大小）,头部大小（一般为0x0010，16字节）,协议版本,操作码（封包类型）,sequence，每次发包时向上递增)
            await asyncio.sleep(30)


    async def SendJoinChannel(self, channelId):
        self._uid = (int)(100000000000000.0 + 200000000000000.0*random.random())
        body = '{"roomid":%s,"uid":%s}' % (channelId, self._uid)
        await self.SendSocketData(0, 16, self._protocolversion, 7, 1, body)#操作码7：认证包
        return True


    async def SendSocketData(self, packetlength, magic, ver, action, param, body):#操作码5：普通包（命令），3	心跳包回复（人气值），8	认证包回复
        bytearr = body.encode('utf-8')
        if packetlength == 0:
            packetlength = len(bytearr) + 16
        sendbytes = pack('!IHHII', packetlength, magic, ver, action, param)
        if len(bytearr) != 0:
            sendbytes = sendbytes + bytearr
        self._writer.write(sendbytes)
        await self._writer.drain()

    """
    头部格式：

    | 偏移量 | 长度 | 类型   | 含义                                                         |
    | ------ | ---- | ------ | ------------------------------------------------------------ |
    | 0      | 4    | uint32 | 封包总大小（头部大小+正文大小）                              |
    | 4      | 2    | uint16 | 头部大小（一般为0x0010，16字节）                             |
    | 6      | 2    | uint16 | 协议版本:
    0普通包正文不使用压缩 
    1心跳及认证包正文不使用压缩
    2普通包正文使用zlib压缩
    3普通包正文使用brotli压缩,解压为一个带头部的协议0普通包 |
    | 8      | 4    | uint32 | 操作码（封包类型）                                           |
    | 12     | 4    | uint32 | sequence，每次发包时向上递增                                 |

    *普通包可能包含多条命令，每个命令有一个头部，指示该条命令的长度等信息*
    """
    async def ReceiveMessageLoop(self):
        while self.connected == True:
            tmp = await self._reader.read(4)
            expr, = unpack('!I', tmp)
            tmp = await self._reader.read(2)
            tmp = await self._reader.read(2)
            protocol_version, = unpack('!H', tmp)
            tmp = await self._reader.read(4)
            num, = unpack('!I', tmp)
            tmp = await self._reader.read(4)
            num2 = expr - 16

            if num2 != 0:
                #print(num)
                if num==3:#心跳包回复（人气值）
                    tmp = await self._reader.read(4)
                    num3, = unpack('!I', tmp)
                    print ('房间人气为 %s' % num3)
                    self._UserCount = num3
                    continue
                elif num==5:#普通包（命令）
                    tmp = await self._reader.read(num2)
                    #print(protocol_version)
                    messages = []
                    try: #会出现zlib error，原因不明
                        if(protocol_version==2):
                            tmp = zlib.decompress(tmp)
                        #print('zlib success')
                        lss = tmp.split(b'\x00')
                        for i in range(len(lss)):
                            if len(lss[i])>16:
                                #print(lss[i])
                                messages.append(lss[i].decode('utf-8'))
                    except Exception:
                        print(sys.exc_info())
                        continue
                    for mss in messages:
                        self.parseDanMu(mss)
                    continue
                elif num==8:#认证包回复
                    tmp = await self._reader.read(num2)
                    continue
                else:
                    if num != 16:
                        tmp = await self._reader.read(num2)
                    else:
                        continue

    def parseDanMu(self, messages):
        try:
            dic = json.loads(messages)
        except: # 有些情况会 jsondecode 失败，未细究，可能平台导致
            return
        cmd = dic['cmd']
        # 1.弹幕类
        if cmd == 'DANMU_MSG':# 弹幕消息
            #print('RE:DANMU_MSG')
            commentText = dic['info'][1]
            commentUser = dic['info'][2][1]
            isAdmin = dic['info'][2][2] == '1'
            isVIP = dic['info'][2][3] == '1'
            if isAdmin:
                commentUser = '管理员 ' + commentUser
            if isVIP:
                commentUser = 'VIP ' + commentUser
            try:
                print (commentUser + ' say: ' + commentText)
            except:
                pass
            return
        if cmd == 'WELCOME_GUARD' and config.TURN_WELCOME == 1:#欢迎xxx老爷
            return
        if cmd == 'ENTRY_EFFECT' and config.TURN_WELCOME == 1:#欢迎舰长进入房间
            return
        if cmd == 'WELCOME' and config.TURN_WELCOME == 1:#欢迎xxx进入房间
            commentUser = dic['data']['uname']
            try:
                print ('欢迎 ' + commentUser + ' 进入房间！')
            except:
                pass
            return
        if cmd == 'SUPER_CHAT_MESSAGE_JPN':#二个都是SC留言
            return
        if cmd == 'SUPER_CHAT_MESSAGE':#二个都是SC留言
            return

        # 2.礼物类
        if cmd == 'SEND_GIFT' and config.TURN_GIFT == 1:# 投喂礼物
            GiftName = dic['data']['giftName']
            GiftUser = dic['data']['uname']
            Giftrcost = dic['data']['rcost']
            GiftNum = dic['data']['num']
            try:
                print(GiftUser + ' 送出了 ' + str(GiftNum) + ' 个 ' + GiftName)
            except:
                pass
            return
        if cmd == 'COMBO_SEND' and config.TURN_GIFT == 1:# 连击礼物
            return
        # 3.天选之人类
        if cmd == 'ANCHOR_LOT_START':# 天选之人开始完整信息
            
            return
        if cmd == 'ANCHOR_LOT_END':# 天选之人获奖id
            return
        if cmd == 'ANCHOR_LOT_AWARD':# 天选之人获奖完整信息
            return
        # 4.上船类
        if cmd == 'GUARD_BUY':# 上舰长
            return
        if cmd == 'USER_TOAST_MSG':# 续费了舰长
            return
        if cmd == 'NOTICE_MSG':# 在本房间续费了舰长
            return
        # 5.分区排行类
        if cmd == 'ACTIVITY_BANNER_UPDATE_V2':# 小时榜变动
            return
        # 6.关注数变化类
        if cmd == 'ROOM_REAL_TIME_MESSAGE_UPDATE':# 粉丝关注变动
            return
        with open('except_cmd.log','a+')as cmdlog:
            cmdlog.write(cmd)

        # 心跳回应：内容是一个 4 字节的 Big Endian 的 整数，表示房间人气
        
        return
