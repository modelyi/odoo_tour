# -*- coding: utf-8 -*-
"""V20 跨模块共享常量（ta_* 统一 import 引用）。

约定同 BS-02 §5：BIZ_MODE 字典数据在 ta.biz.mode 装载，
此处保留键表供测试与数据脚本使用。
"""

# 业务模式 15 项（含 3 别名码：2→DT、15→DSN、52→自由行），源自易途 BizModeID。
BIZ_MODE_DATA = [
    ('1', '团队输单 (DT)', False),
    ('2', '团队输单 (DT·别名)', True),
    ('12', '团期计划 (DSK)', False),
    ('13', '散客单组 (DSS)', False),
    ('14', '散客并团 (DSN)', False),
    ('15', '散客并团 (DSN·别名)', True),
    ('16', '内部流转', False),
    ('17', '产品计划', False),
    ('18', '关键字并团', False),
    ('21', '组团团队 (DTO)', False),
    ('31', '组团散客 (DSO)', False),
    ('41', '代订项目 (DD)', False),
    ('51', '自由行', False),
    ('52', '自由行·别名', True),
    ('71', '共享协议报名', False),
]

# 供应商/资源方类型（BS-03 计调用）。
SUP_TYPE = [
    ('ditch', '地接社'),
    ('hotel', '酒店'),
    ('meal', '餐厅'),
    ('vehicle_comp', '车队'),
    ('ticket', '票务'),
    ('scenic', '景区'),
    ('other', '其他'),
]

SEX = [
    ('male', '男'),
    ('female', '女'),
]
