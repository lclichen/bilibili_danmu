import asyncio
import json
import random
import re
import sys,zlib,os
import xml.dom.minidom
from struct import *

import aiohttp
import requests

import config


class bilibiliClient():
    def __init__(self):

        self._getRoomInfoOld_Url = 'http://api.live.bilibili.com/room/v1/Room/getRoomInfoOld?mid='
        self._getRoomInit_Url = 'http://api.live.bilibili.com/room/v1/Room/room_init?id='
        self._userId = 0
        self._shortId = 0
        self._roomId = 0

        self._getDanmuInfo_Url = 'http://api.live.bilibili.com/xlive/web-room/v1/index/getDanmuInfo?id='
        
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
        self._ursw = 2#input('请选择输入(1或2)，1 用户ID ;2 房间号')
        self._ursw = int(self._ursw)
        if self._ursw == 1:
            self._userId = input('请输入用户ID：')

            self._userId = int(self._userId)

        elif self._ursw == 2:
            self._shortId = 255 #input('请输入房间号：')# 255 430 测试用房间号
            
            self._shortId = int(self._shortId)

    async def connectServer(self):
        print ('正在进入房间……')
        s1 = requests.Session()
        if self._ursw == 1:
            r0 = s1.get(self._getRoomInfoOld_Url+str(self._userId))
            j0 = json.loads(r0.text)
            if(j0['code']==0):
                self._roomId = j0['data']['roomid']
        elif self._ursw == 2:
            r0 = s1.get(self._getRoomInit_Url+str(self._shortId))
            j0 = json.loads(r0.text)
            if(j0['code']==0):
                self._roomId = j0['data']['room_id']
        
        print(self._roomId)
        if not os.path.isdir('logs/'+str(self._roomId)):
            os.mkdir('logs/'+str(self._roomId))

        r1 = s1.get(self._getDanmuInfo_Url + str(self._roomId))
        j1 = json.loads(r1.text)
        print(j1)
        host_num = 2
        host_0 = j1['data']['host_list'][host_num]
        self._ChatHost = host_0['host']
        self._ChatPort = host_0['port']
        self._WsPort = host_0['ws_port']
        self._WssPort = host_0['ws_port']
        self._token = j1['data']['token']
        self._WssHost = 'wss://'+self._ChatHost+'/sub'

        reader, writer = await asyncio.open_connection(self._ChatHost, self._ChatPort)
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
        self._uid = 5583907#(int)(100000000000000.0 + 200000000000000.0*random.random())
        body = '{"roomid":%s,"uid":%s}' % (channelId, self._uid)# ,"key":%s,"protover":%d # , self._token, 2
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
                    try: #不加协议判断的话会出现zlib error，可能是由于空包不会进行压缩。
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
        except: 
            print('解析出错，跳过')
            return
        cmd = dic['cmd']
        # 1.弹幕类
        if cmd == 'DANMU_MSG':# 弹幕消息
            #固有表情弹幕
            #{"cmd": "DANMU_MSG", 
            # "info": [
                # [0, 1, 25, 5566168, 1647222923249, 1647222824, 0, "3aa48643", 0, 0, 0, "", 1, {"bulge_display": 0, "emoticon_unique": "official_124", "height": 60, "in_player_area": 1, "is_dynamic": 1, "url": "http://i0.hdslb.com/bfs/live/a98e35996545509188fe4d24bd1a56518ea5af48.png", "width": 183}, "{}", {"mode": 0, "show_player_type": 0, "extra": "{\"send_from_me\":false,\"mode\":0,\"color\":5566168,\"dm_type\":1,\"font_size\":25,\"player_mode\":1,\"show_player_type\":0,\"content\":\"2333\",\"user_hash\":\"983860803\",\"emoticon_unique\":\"official_124\",\"bulge_display\":0,\"direction\":0,\"pk_direction\":0,\"quartet_direction\":0,\"yeah_space_type\":\"\",\"yeah_space_url\":\"\",\"jump_to_url\":\"\",\"space_type\":\"\",\"space_url\":\"\"}"}], 
                # "2333", 
                # [79646219, "斯列恩马-穆夏", 0, 0, 0, 10000, 1, ""], 
                # [], 
                # [16, 0, 6406234, ">50000", 0], 
                # ["", ""], 
                # 0, 
                # 0, 
                # null, 
                # {"ts": 1647222923, "ct": "2AB16870"}, 
                # 0, 
                # 0, 
                # null, 
                # null, 
                # 0, 
                # 7]
            # }
            #文字弹幕
            #{"cmd": "DANMU_MSG", 
            # "info": [
                #0 [0, 4, 25, 14893055, 1647222920227, -1831693494, 0, "a83f197f", 0, 0, 5, "#1453BAFF,#4C2263A2,#3353BAFF", 0, "{}", "{}", {"mode": 0, "show_player_type": 0, "extra": "{\"send_from_me\":false,\"mode\":0,\"color\":14893055,\"dm_type\":0,\"font_size\":25,\"player_mode\":4,\"show_player_type\":0,\"content\":\"恩恩，无锡酱排骨好吃\",\"user_hash\":\"2822707583\",\"emoticon_unique\":\"\",\"bulge_display\":0,\"direction\":0,\"pk_direction\":0,\"quartet_direction\":0,\"yeah_space_type\":\"\",\"yeah_space_url\":\"\",\"jump_to_url\":\"\",\"space_type\":\"\",\"space_url\":\"\"}"}], 
                #1 "恩恩，无锡酱排骨好吃", 
                #2 [38386893, "孤殇00", 0, 0, 0, 10000, 1, "#00D1F1"], 
                #3 [26, "逼格", "肥皂菌丨珉珉的猫咪丨", 78787, 398668, "", 0, 6809855, 398668, 6850801, 3, 1, 634131], 
                #4 [20, 0, 6406234, ">50000", 0], 
                #5 ["", ""], 
                #6 0, 
                #7 3, 
                #8 null, 
                #9 {"ts": 1647222920, "ct": "BF533560"}, 
                #10 0, 
                #11 0, 
                #12 null, 
                #13 null, 
                #14 0, 
                #15 105]
            # }
            if config.SAVE_LOG == 1:
                with open('logs/'+str(self._roomId)+'/DANMU_MSG.log','a+',encoding='utf8') as logger:
                    json.dump(dic,logger,ensure_ascii=False)
                    logger.write('\n')
            #print('RE:DANMU_MSG')
            commentText = dic['info'][1]
            commentUser = dic['info'][2][1]
            isAdmin = (str(dic['info'][2][2]) == '1')
            isVIP = (str(dic['info'][2][3]) == '1')
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
            if config.SAVE_LOG == 1:
                with open('logs/'+str(self._roomId)+'/WELCOME_GUARD.log','a+',encoding='utf8') as logger:
                    json.dump(dic,logger,ensure_ascii=False)
                    logger.write('\n')
            return
        if cmd == 'ENTRY_EFFECT' and config.TURN_WELCOME == 1:#欢迎舰长进入房间
            #{"cmd": "ENTRY_EFFECT", 
            # "data": {
                # "id": 4, 
                # "uid": 402002407, 
                # "target_id": 634131, 
                # "mock_effect": 0, 
                # "face": "https://i1.hdslb.com/bfs/face/2ef77fb4986d69ccd4e616a0286705f44ffcaebd.jpg", 
                # "privilege_type": 3, 
                # "copy_writing": "欢迎舰长 <%和光同尘WJ%> 进入直播间", 
                # "copy_color": "#ffffff", 
                # "highlight_color": "#E6FF00", 
                # "priority": 1, 
                # "basemap_url": "https://i0.hdslb.com/bfs/live/mlive/f34c7441cdbad86f76edebf74e60b59d2958f6ad.png", 
                # "show_avatar": 1, 
                # "effective_time": 2, 
                # "web_basemap_url": "https://i0.hdslb.com/bfs/live/mlive/f34c7441cdbad86f76edebf74e60b59d2958f6ad.png", 
                # "web_effective_time": 2, 
                # "web_effect_close": 0, 
                # "web_close_time": 0, 
                # "business": 1, 
                # "copy_writing_v2": "欢迎舰长 <%和光同尘WJ%> 进入直播间", 
                # "icon_list": [], 
                # "max_delay_time": 7, 
                # "trigger_time": 1647221966388526734, 
                # "identities": 6, 
                # "effect_silent_time": 300
                # }
            # }
            if config.SAVE_LOG == 1:
                with open('logs/'+str(self._roomId)+'/ENTRY_EFFECT.log','a+',encoding='utf8') as logger:
                    json.dump(dic,logger,ensure_ascii=False)
                    logger.write('\n')
            return

        # (疑似 WELCOME 消息已经被删除)
        # if cmd == 'WELCOME' and config.TURN_WELCOME == 1:#欢迎xxx进入房间
        #     if config.SAVE_LOG == 1:
        #         with open('logs/'+str(self._roomId)+'/WELCOME.log','a+',encoding='utf8') as logger:
        #             json.dump(dic,logger,ensure_ascii=False)
        #     commentUser = dic['data']['uname']
        #     try:
        #         print ('欢迎 ' + commentUser + ' 进入房间！')
        #     except:
        #         pass
        #     return

        if cmd == 'INTERACT_WORD' and config.TURN_WELCOME == 1:# 进场或关注消息，有用户进入或关注直播间时触发
            #{"cmd": "INTERACT_WORD", 
            # "data": {
                # "contribution": {"grade": 0}, 
                # "dmscore": 14, 
                # "fans_medal": {
                    # "anchor_roomid": 78787, 
                    # "guard_level": 0, 
                    # "icon_id": 0, 
                    # "is_lighted": 1, 
                    # "medal_color": 12478086, 
                    # "medal_color_border": 12478086, 
                    # "medal_color_end": 12478086, 
                    # "medal_color_start": 12478086, 
                    # "medal_level": 13, 
                    # "medal_name": "逼格", 
                    # "score": 40583, 
                    # "special": "", 
                    # "target_id": 634131
                    # }, 
                # "identities": [3, 1], 
                # "is_spread": 0, 
                # "msg_type": 1, 
                # "roomid": 78787, 
                # "score": 1647276834860, 
                # "spread_desc": "", 
                # "spread_info": "", 
                # "tail_icon": 0, 
                # "timestamp": 1647226251, 
                # "trigger_time": 1647226250812910300, 
                # "uid": 7341760, 
                # "uname": "墨孜", 
                # "uname_color": ""
                # }
            # }
            if config.SAVE_LOG == 1:
                with open('logs/'+str(self._roomId)+'/INTERACT_WORD.log','a+',encoding='utf8') as logger:
                    json.dump(dic,logger,ensure_ascii=False)
                    logger.write('\n')
            return

        if cmd == 'SUPER_CHAT_MESSAGE_JPN':#二个都是SC留言
            if config.SAVE_LOG == 1:
                with open('logs/'+str(self._roomId)+'/SUPER_CHAT_MESSAGE_JPN.log','a+',encoding='utf8') as logger:
                    json.dump(dic,logger,ensure_ascii=False)
                    logger.write('\n')
            return
        if cmd == 'SUPER_CHAT_MESSAGE':#二个都是SC留言
            if config.SAVE_LOG == 1:
                with open('logs/'+str(self._roomId)+'/SUPER_CHAT_MESSAGE.log','a+',encoding='utf8') as logger:
                    json.dump(dic,logger,ensure_ascii=False)
                    logger.write('\n')
            return

        # 2.礼物类
        if cmd == 'SEND_GIFT' and config.TURN_GIFT == 1:# 投喂礼物
            #{"cmd": "SEND_GIFT", 
            # "data": {
                # "action": "投喂", 
                # "batch_combo_id": "", 
                # "batch_combo_send": null, 
                # "beatId": "0", 
                # "biz_source": "Live", 
                # "blind_gift": null, 
                # "broadcast_id": 0, 
                # "coin_type": "silver", 
                # "combo_resources_id": 1, 
                # "combo_send": null, 
                # "combo_stay_time": 3, 
                # "combo_total_coin": 0, 
                # "crit_prob": 0, 
                # "demarcation": 1, 
                # "discount_price": 0, 
                # "dmscore": 36, 
                # "draw": 0, 
                # "effect": 0, 
                # "effect_block": 1, 
                # "face": "http://i0.hdslb.com/bfs/face/928e7bea48726a93c295119f8b584993da22a970.jpg", 
                # "float_sc_resource_id": 0, 
                # "giftId": 1, 
                # "giftName": "辣条", 
                # "giftType": 5, 
                # "gold": 0, 
                # "guard_level": 0, 
                # "is_first": true, 
                # "is_special_batch": 0, 
                # "magnification": 1, 
                # "medal_info": {
                    # "anchor_roomid": 0, 
                    # "anchor_uname": "", 
                    # "guard_level": 0, 
                    # "icon_id": 0, 
                    # "is_lighted": 1, 
                    # "medal_color": 12478086, 
                    # "medal_color_border": 12478086, 
                    # "medal_color_end": 12478086, 
                    # "medal_color_start": 12478086, 
                    # "medal_level": 16, 
                    # "medal_name": "逼格", 
                    # "special": "", 
                    # "target_id": 634131
                # }, 
                # "name_color": "", 
                # "num": 2, 
                # "original_gift_name": "", 
                # "price": 100, 
                # "rcost": 51536332, 
                # "remain": 0, 
                # "rnd": "1647221967110900002", 
                # "send_master": null, 
                # "silver": 0, 
                # "super": 0, 
                # "super_batch_gift_num": 0, 
                # "super_gift_num": 0, 
                # "svga_block": 0, 
                # "tag_image": "", 
                # "tid": "1647221967110900002", 
                # "timestamp": 1647221967, 
                # "top_list": null, 
                # "total_coin": 200, 
                # "uid": 36253089, 
                # "uname": "pcchang1961"
                # }
            # }
            if config.SAVE_LOG == 1:
                with open('logs/'+str(self._roomId)+'/SEND_GIFT.log','a+',encoding='utf8') as logger:
                    json.dump(dic,logger,ensure_ascii=False)
                    logger.write('\n')
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
            #{"cmd": "COMBO_SEND", 
            # "data": {
                # "action": "投喂", 
                # "batch_combo_id": "batch:gift:combo_id:278039498:634131:30607:1647222035.3414", 
                # "batch_combo_num": 10, 
                # "combo_id": "gift:combo_id:278039498:634131:30607:1647222035.3405", 
                # "combo_num": 10, 
                # "combo_total_coin": 0, 
                # "dmscore": 72, 
                # "gift_id": 30607, 
                # "gift_name": "小心心", 
                # "gift_num": 0, 
                # "is_show": 1, 
                # "medal_info": {
                    # "anchor_roomid": 0, 
                    # "anchor_uname": "", 
                    # "guard_level": 0, 
                    # "icon_id": 0, 
                    # "is_lighted": 1, 
                    # "medal_color": 12478086, 
                    # "medal_color_border": 12478086, 
                    # "medal_color_end": 12478086, 
                    # "medal_color_start": 12478086, 
                    # "medal_level": 16, 
                    # "medal_name": "逼格", 
                    # "special": "", 
                    # "target_id": 634131
                    # }, 
                # "name_color": "", 
                # "r_uname": "肥皂菌丨珉珉的猫咪丨", 
                # "ruid": 634131, 
                # "send_master": null, 
                # "total_num": 10, 
                # "uid": 278039498, 
                # "uname": "万众一鑫-鲸梦"
                # }
            # }
            if config.SAVE_LOG == 1:
                with open('logs/'+str(self._roomId)+'/COMBO_SEND.log','a+',encoding='utf8') as logger:
                    json.dump(dic,logger,ensure_ascii=False)
                    logger.write('\n')
            return
        # 3.天选之人类
        if cmd == 'ANCHOR_LOT_START':# 天选之人开始完整信息
            if config.SAVE_LOG == 1:
                with open('logs/'+str(self._roomId)+'/ANCHOR_LOT_START.log','a+',encoding='utf8') as logger:
                    json.dump(dic,logger,ensure_ascii=False)
                    logger.write('\n')
            
            return
        if cmd == 'ANCHOR_LOT_END':# 天选之人获奖id
            if config.SAVE_LOG == 1:
                with open('logs/'+str(self._roomId)+'/ANCHOR_LOT_END.log','a+',encoding='utf8') as logger:
                    json.dump(dic,logger,ensure_ascii=False)
                    logger.write('\n')
            return
        if cmd == 'ANCHOR_LOT_AWARD':# 天选之人获奖完整信息
            if config.SAVE_LOG == 1:
                with open('logs/'+str(self._roomId)+'/ANCHOR_LOT_AWARD.log','a+',encoding='utf8') as logger:
                    json.dump(dic,logger,ensure_ascii=False)
                    logger.write('\n')
            return
        # 4.上船类
        if cmd == 'GUARD_BUY':# 上舰长
            #{"cmd": "GUARD_BUY", 
            # "data": {
                # "uid": 396251741, 
                # "username": "Dr_科研兔", 
                # "guard_level": 3, 
                # "num": 1, 
                # "price": 198000, 
                # "gift_id": 10003, 
                # "gift_name": "舰长", 
                # "start_time": 1647224797, 
                # "end_time": 1647224797
                # }
            # }
            if config.SAVE_LOG == 1:
                with open('logs/'+str(self._roomId)+'/GUARD_BUY.log','a+',encoding='utf8') as logger:
                    json.dump(dic,logger,ensure_ascii=False)
                    logger.write('\n')
            return
        if cmd == 'USER_TOAST_MSG':# 续费了舰长
            #{"cmd": "USER_TOAST_MSG", 
            # "data": {
                # "anchor_show": true, 
                # "color": "#00D1F1", 
                # "dmscore": 90, 
                # "effect_id": 397, 
                # "end_time": 1647224797, 
                # "guard_level": 3, 
                # "is_show": 0, 
                # "num": 1, 
                # "op_type": 2, 
                # "payflow_id": "2203141025231762117410547", 
                # "price": 158000, 
                # "role_name": "舰长", 
                # "start_time": 1647224797, 
                # "svga_block": 0, 
                # "target_guard_count": 62, 
                # "toast_msg": "<%Dr_科研兔%> 续费了舰长", 
                # "uid": 396251741, 
                # "unit": "月", 
                # "user_show": true, 
                # "username": "Dr_科研兔"
                # }
            # }
            if config.SAVE_LOG == 1:
                with open('logs/'+str(self._roomId)+'/USER_TOAST_MSG.log','a+',encoding='utf8') as logger:
                    json.dump(dic,logger,ensure_ascii=False)
                    logger.write('\n')
            return
        if cmd == 'NOTICE_MSG':# 各类通知滚屏等消息
            # 在本房间续费了舰长
            #{"cmd": "NOTICE_MSG", 
            # "id": 207, 
            # "name": "舰长跑马灯", 
            # "full": {
                # "head_icon": "https://i0.hdslb.com/bfs/live/72337e86020b8d0874d817f15c48a610894b94ff.png", 
                # "tail_icon": "https://i0.hdslb.com/bfs/live/822da481fdaba986d738db5d8fd469ffa95a8fa1.webp", 
                # "head_icon_fa": "https://i0.hdslb.com/bfs/live/72337e86020b8d0874d817f15c48a610894b94ff.png", 
                # "tail_icon_fa": "https://i0.hdslb.com/bfs/live/38cb2a9f1209b16c0f15162b0b553e3b28d9f16f.png", 
                # "head_icon_fan": 1, 
                # "tail_icon_fan": 4, 
                # "background": "#FFB03CFF", 
                # "color": "#FFFFFFFF", 
                # "highlight": "#B25AC1FF", 
                # "time": 10
                # }, 
            # "half": {
                # "head_icon": "", 
                # "tail_icon": "", 
                # "background": "", 
                # "color": "", 
                # "highlight": "", 
                # "time": 0
                # }, 
            # "side": {
                # "head_icon": "https://i0.hdslb.com/bfs/live/31566d8cd5d468c30de8c148c5d06b3b345d8333.png", 
                # "background": "#FFE9C8FF", 
                # "color": "#EF903AFF", 
                # "highlight": "#D54900FF", 
                # "border": "#FFCFA4FF"
                # }, 
            # "roomid": 78787, 
            # "real_roomid": 78787, 
            # "msg_common": "", 
            # "msg_self": "<%Dr_科研兔%> 续费了主播的 <%舰长%>", 
            # "link_url": "", 
            # "msg_type": 3, 
            # "shield_uid": -1, 
            # "business_id": "", 
            # "scatter": {
                # "min": 0, 
                # "max": 0
                # }, 
            # "marquee_id": "", 
            # "notice_type": 0
            # }

            # 分区道具抽奖广播样式
            # {"cmd": "NOTICE_MSG", 
            # "id": 2, 
            # "name": "分区道具抽奖广播样式", 
            # "full": {"head_icon": "http://i0.hdslb.com/bfs/live/00f26756182b2e9d06c00af23001bc8e10da67d0.webp", "tail_icon": "http://i0.hdslb.com/bfs/live/822da481fdaba986d738db5d8fd469ffa95a8fa1.webp", "head_icon_fa": "http://i0.hdslb.com/bfs/live/77983005023dc3f31cd599b637c83a764c842f87.png", "tail_icon_fa": "http://i0.hdslb.com/bfs/live/38cb2a9f1209b16c0f15162b0b553e3b28d9f16f.png", "head_icon_fan": 36, "tail_icon_fan": 4, "background": "#6098FFFF", "color": "#FFFFFFFF", "highlight": "#FDFF2FFF", "time": 20}, 
            # "half": {"head_icon": "http://i0.hdslb.com/bfs/live/358cc52e974b315e83eee429858de4fee97a1ef5.png", "tail_icon": "", "background": "#7BB6F2FF", "color": "#FFFFFFFF", "highlight": "#FDFF2FFF", "time": 15}, 
            # "side": {"head_icon": "", "background": "", "color": "", "highlight": "", "border": ""}, 
            # "roomid": 24530579, 
            # "real_roomid": 24530579, 
            # "msg_common": "<%bili_43183757553%>投喂:<%bili_72472862653%>1个次元之城，点击前往TA的房间吧！", 
            # "msg_self": "<%bili_43183757553%>投喂:<%bili_72472862653%>1个次元之城，快来围观吧！", 
            # "link_url": "https://live.bilibili.com/24530579?accept_quality=%5B10000%5D&broadcast_type=1&current_qn=10000&current_quality=10000&is_room_feed=1&live_play_network=other&p2p_type=0&playurl_h264=http%3A%2F%2Fd1--cn-gotcha03.bilivideo.com%2Flive-bvc%2F743192%2Flive_1164334601_89637699.flv%3Fexpires%3D1647228458%26len%3D0%26oi%3D0%26pt%3D%26qn%3D150%26trid%3D10001967169754634807a7f1356bab536a1f%26sigparams%3Dcdn%2Cexpires%2Clen%2Coi%2Cpt%2Cqn%2Ctrid%26cdn%3Dcn-gotcha03%26sign%3D8ceb35d960b7ccc1b5670e710ac19ed3%26sk%3De30c4402e5320fd1c562fb56e462561f%26p2p_type%3D0%26src%3D4%26sl%3D1%26flowtype%3D0%26source%3Dbatch%26order%3D1%26machinezone%3Dylf%26pp%3Dsrt%26slot%3D0%26site%3D0095e7e5812c1cc5dfc7a75cab89fc8e&playurl_h265=&quality_description=%5B%7B%22qn%22%3A10000%2C%22desc%22%3A%22%E5%8E%9F%E7%94%BB%22%7D%5D&from=28003&extra_jump_from=28003&live_lottery_type=1", 
            # "msg_type": 2, 
            # "shield_uid": -1, 
            # "business_id": "31087", 
            # "scatter": {"min": 0, "max": 0}, 
            # "marquee_id": "", 
            # "notice_type": 0}

            # 超级战舰-BLS小分
            #{"cmd": "NOTICE_MSG", 
            # "id": 272, 
            # "name": "超级战舰-BLS小分", 
            # "full": {"head_icon": "https://i0.hdslb.com/bfs/live/caf93f24cb84ee33b97e9a92398197fe93553c08.webp", "tail_icon": "http://i0.hdslb.com/bfs/live/822da481fdaba986d738db5d8fd469ffa95a8fa1.webp", "head_icon_fa": "https://i0.hdslb.com/bfs/live/3937831db574dd8eb703b2ebb69a8f6aa8752d9b.png", "tail_icon_fa": "http://i0.hdslb.com/bfs/live/38cb2a9f1209b16c0f15162b0b553e3b28d9f16f.png", "head_icon_fan": 23, "tail_icon_fan": 4, "background": "#66A74EFF", "color": "#FFFFFFFF", "highlight": "#FDFF2FFF", "time": 20}, 
            # "half": {"head_icon": "https://i0.hdslb.com/bfs/live/ec9b374caec5bd84898f3780a10189be96b86d4e.png", "tail_icon": "", "background": "#85B971FF", "color": "#FFFFFFFF", "highlight": "#FDFF2FFF", "time": 15}, 
            # "side": {"head_icon": "", "background": "", "color": "", "highlight": "", "border": ""}, 
            # "roomid": 1539872, 
            # "real_roomid": 1539872, 
            # "msg_common": "<%Fx呆呆瓜%>投喂<%俊俊子会rap%>1个超级战舰，欧皇登场，快来围观吧！", 
            # "msg_self": "<%Fx呆呆瓜%>投喂<%俊俊子会rap%>1个超级战舰，欧皇登场，快来围观吧！", 
            # "link_url": "https://live.bilibili.com/1539872?accept_quality=%5B10000%2C150%5D&broadcast_type=0&current_qn=150&current_quality=150&is_room_feed=1&live_play_network=other&p2p_type=0&playurl_h264=http%3A%2F%2Fd1--cn-gotcha03.bilivideo.com%2Flive-bvc%2F601857%2Flive_1769578_4900197_1500.flv%3Fexpires%3D1647228091%26len%3D0%26oi%3D0%26pt%3D%26qn%3D150%26trid%3D1000b517831dc30640768355cfb13b2c67d9%26sigparams%3Dcdn%2Cexpires%2Clen%2Coi%2Cpt%2Cqn%2Ctrid%26cdn%3Dcn-gotcha03%26sign%3D5a4c8fb8548ffc1ea77625253f469787%26sk%3D2935686d6cb9146c7a6a6a0b4e120e2594e074fa0760377f1a7a2b2fa0ee6443%26p2p_type%3D0%26src%3D57349%26sl%3D1%26flowtype%3D1%26source%3Dbatch%26order%3D1%26machinezone%3Dylf%26pp%3Dsrt%26slot%3D0%26site%3D1c2e57e6694f7f18065a012a4e03d387&playurl_h265=&quality_description=%5B%7B%22qn%22%3A10000%2C%22desc%22%3A%22%E5%8E%9F%E7%94%BB%22%7D%2C%7B%22qn%22%3A150%2C%22desc%22%3A%22%E9%AB%98%E6%B8%85%22%7D%5D&from=28003&extra_jump_from=28003&live_lottery_type=1", 
            # "msg_type": 2, 
            # "shield_uid": -1, 
            # "business_id": "20009", 
            # "scatter": {"min": 0, "max": 0}, 
            # "marquee_id": "", 
            # "notice_type": 0}
            if config.SAVE_LOG == 1:
                with open('logs/'+str(self._roomId)+'/NOTICE_MSG.log','a+',encoding='utf8') as logger:
                    json.dump(dic,logger,ensure_ascii=False)
                    logger.write('\n')
            return
        # 5.分区排行类
        if cmd == 'ACTIVITY_BANNER_UPDATE_V2':# 小时榜变动
            if config.SAVE_LOG == 1:
                with open('logs/'+str(self._roomId)+'/ACTIVITY_BANNER_UPDATE_V2.log','a+',encoding='utf8') as logger:
                    json.dump(dic,logger,ensure_ascii=False)
                    logger.write('\n')
            return
        # 6.关注数变化类
        if cmd == 'ROOM_REAL_TIME_MESSAGE_UPDATE':# 粉丝关注变动
            #{"cmd": "ROOM_REAL_TIME_MESSAGE_UPDATE", 
            # "data": {
                # "roomid": 78787, 
                # "fans": 606946, 
                # "red_notice": -1, 
                # "fans_club": 882
                # }
            # }
            if config.SAVE_LOG == 1:
                with open('logs/'+str(self._roomId)+'/ROOM_REAL_TIME_MESSAGE_UPDATE.log','a+',encoding='utf8') as logger:
                    json.dump(dic,logger,ensure_ascii=False)
                    logger.write('\n')
            return
        
        # 7.其它，待分类
        if cmd == 'STOP_LIVE_ROOM_LIST':
            #{"cmd": "STOP_LIVE_ROOM_LIST", 
            # "data": {
                # "room_id_list": 
                # [11052349, 23239285, 1302602, 4491411, 22972835, 23491340, 24388860, 23711069, 24563740, 24538079, 22287710, 23148697, 23911157, 22513693, 22582520, 2895205, 23525746, 23794576, 3294354, 436394, 24355527, 6695795, 23426283, 23638670, 2871481, 14319458, 23239161, 22172750, 2859920, 186266, 24421074, 23615693, 24563590]
                # }
            # }
            if config.SAVE_LOG == 1:
                with open('logs/'+str(self._roomId)+'/STOP_LIVE_ROOM_LIST.log','a+',encoding='utf8') as logger:
                    json.dump(dic,logger,ensure_ascii=False)
                    logger.write('\n')
            return

        if cmd == 'LIVE_INTERACTIVE_GAME':
            #{"cmd": "LIVE_INTERACTIVE_GAME", 
            # "data": {
                # "type": 1, 
                # "uid": 2765492, 
                # "uname": "-靳玦-", 
                # "uface": "http://i2.hdslb.com/bfs/face/a909b7568b65748fa93fcee112e7a1f211173d65.jpg", 
                # "gift_id": 1, 
                # "gift_name": "辣条", 
                # "gift_num": 2, 
                # "price": 100, 
                # "paid": false, 
                # "msg": "", 
                # "fans_medal_level": 9, 
                # "guard_level": 0, 
                # "timestamp": 1647226337, 
                # "anchor_lottery": null, 
                # "pk_info": null, 
                # "anchor_info": {
                    # "uid": 634131, 
                    # "uname": "肥皂菌丨珉珉的猫咪丨", 
                    # "uface": "http://i0.hdslb.com/bfs/face/0fb6781e7ce82b748d3a9fda77e52c2210f96084.jpg"
                    # }
                # }
            # }
            #{"cmd": "LIVE_INTERACTIVE_GAME", 
            # "data": {
                # "type": 1, 
                # "uid": 474248076, 
                # "uname": "天刀宋阀主", 
                # "uface": "http://i0.hdslb.com/bfs/face/member/noface.jpg", 
                # "gift_id": 30607, 
                # "gift_name": "小心心", 
                # "gift_num": 1, 
                # "price": 0, 
                # "paid": false, 
                # "msg": "", 
                # "fans_medal_level": 15, 
                # "guard_level": 0, 
                # "timestamp": 1647226412, 
                # "anchor_lottery": null, 
                # "pk_info": null, 
                # "anchor_info": {
                    # "uid": 634131, 
                    # "uname": "肥皂菌丨珉珉的猫咪丨", 
                    # "uface": "http://i0.hdslb.com/bfs/face/0fb6781e7ce82b748d3a9fda77e52c2210f96084.jpg"
                    # }
                # }
            # }
            if config.SAVE_LOG == 1:
                with open('logs/'+str(self._roomId)+'/LIVE_INTERACTIVE_GAME.log','a+',encoding='utf8') as logger:
                    json.dump(dic,logger,ensure_ascii=False)
                    logger.write('\n')
            return
        
        if cmd == 'ONLINE_RANK_COUNT':
            #{"cmd": "ONLINE_RANK_COUNT", 
            # "data": {
                # "count": 116
                # }
            # }
            if config.SAVE_LOG == 1:
                with open('logs/'+str(self._roomId)+'/ONLINE_RANK_COUNT.log','a+',encoding='utf8') as logger:
                    json.dump(dic,logger,ensure_ascii=False)
                    logger.write('\n')
            return
        
        if cmd == 'WATCHED_CHANGE':
            #{"cmd": "WATCHED_CHANGE", 
            # "data": {
                # "num": 3179, 
                # "text_small": "3179", 
                # "text_large": "3179人看过"
                # }
            # }
            if config.SAVE_LOG == 1:
                with open('logs/'+str(self._roomId)+'/WATCHED_CHANGE.log','a+',encoding='utf8') as logger:
                    json.dump(dic,logger,ensure_ascii=False)
                    logger.write('\n')
            return
        
        if cmd == 'ONLINE_RANK_V2':
            #{"cmd": "ONLINE_RANK_V2", 
            # "data": {
                # "list": [
                    # {"uid": 396251741, 
                    # "face": "http://i2.hdslb.com/bfs/face/953743a1d24fe076837c4c47c31515903d06ee37.jpg", 
                    # "score": "1583", 
                    # "uname": "Dr_科研兔", 
                    # "rank": 1, 
                    # "guard_level": 3}, 
                    # {"uid": 358449490, "face": "http://i1.hdslb.com/bfs/face/633a95d29fb45ea4665b0a989bb323bba59bbc4f.jpg", "score": "20", "uname": "徐晨辰音饭", "rank": 2, "guard_level": 3}, 
                    # {"uid": 437055932, "face": "http://i2.hdslb.com/bfs/face/889d55a541ab4c8ebaec7603f8bf61224539c67c.jpg", "score": "16", "uname": "墨竹千影", "rank": 3, "guard_level": 0}, 
                    # {"uid": 37078372, "face": "http://i1.hdslb.com/bfs/face/e7125098f96607298ffcbd264709ca995ea9672f.jpg", "score": "10", "uname": "归尘hx", "rank": 4, "guard_level": 0}, 
                    # {"uid": 36124678, "face": "http://i1.hdslb.com/bfs/face/120ddc362ede13957f1544e33d083a127c4cfcd9.jpg", "score": "10", "uname": "羽无名", "rank": 5, "guard_level": 0}, 
                    # {"uid": 7374267, "face": "http://i0.hdslb.com/bfs/face/a1cdfecb68bc6eefbbdd84a47c211c847647cb72.jpg", "score": "10", "uname": "墨韵moyun的琴弦", "rank": 6, "guard_level": 0}, 
                    # {"uid": 19069448, "face": "http://i2.hdslb.com/bfs/face/5b619c365f5e3a006e6e4cbe4c30e4a7fbc12ca8.jpg", "score": "10", "uname": "叶若轻羽", "rank": 7, "guard_level": 0}
                    # ], 
                # "rank_type": "gold-rank"
                # }
            # }
            if config.SAVE_LOG == 1:
                with open('logs/'+str(self._roomId)+'/ONLINE_RANK_V2.log','a+',encoding='utf8') as logger:
                    json.dump(dic,logger,ensure_ascii=False)
                    logger.write('\n')
            return
        
        if cmd == 'HOT_RANK_CHANGED':
            if config.SAVE_LOG == 1:
                with open('logs/'+str(self._roomId)+'/HOT_RANK_CHANGED.log','a+',encoding='utf8') as logger:
                    json.dump(dic,logger,ensure_ascii=False)
                    logger.write('\n')
            return

        if cmd == 'HOT_RANK_CHANGED_V2':
            if config.SAVE_LOG == 1:
                with open('logs/'+str(self._roomId)+'/HOT_RANK_CHANGED_V2.log','a+',encoding='utf8') as logger:
                    json.dump(dic,logger,ensure_ascii=False)
                    logger.write('\n')
            return

        if cmd == 'ROOM_BLOCK_MSG':
            if config.SAVE_LOG == 1:
                with open('logs/'+str(self._roomId)+'/ROOM_BLOCK_MSG.log','a+',encoding='utf8') as logger:
                    json.dump(dic,logger,ensure_ascii=False)
                    logger.write('\n')
            return

        if cmd == 'WIDGET_BANNER':
            if config.SAVE_LOG == 1:
                with open('logs/'+str(self._roomId)+'/WIDGET_BANNER.log','a+',encoding='utf8') as logger:
                    json.dump(dic,logger,ensure_ascii=False)
                    logger.write('\n')
            return

        if cmd == 'ONLINE_RANK_TOP3':
            if config.SAVE_LOG == 1:
                with open('logs/'+str(self._roomId)+'/ONLINE_RANK_TOP3.log','a+',encoding='utf8') as logger:
                    json.dump(dic,logger,ensure_ascii=False)
                    logger.write('\n')
            return

        if cmd == 'PREPARING':
            if config.SAVE_LOG == 1:
                with open('logs/'+str(self._roomId)+'/PREPARING.log','a+',encoding='utf8') as logger:
                    json.dump(dic,logger,ensure_ascii=False)
                    logger.write('\n')
            return

        if cmd == 'HOT_RANK_SETTLEMENT_V2':
            if config.SAVE_LOG == 1:
                with open('logs/'+str(self._roomId)+'/HOT_RANK_SETTLEMENT_V2.log','a+',encoding='utf8') as logger:
                    json.dump(dic,logger,ensure_ascii=False)
                    logger.write('\n')
            return

        with open('logs/'+str(self._roomId)+'/except_cmd.log','a+')as logger:
            logger.write(cmd)
            logger.write('\n')

        # 心跳回应：内容是一个 4 字节的 Big Endian 的 整数，表示房间人气
        
        return
