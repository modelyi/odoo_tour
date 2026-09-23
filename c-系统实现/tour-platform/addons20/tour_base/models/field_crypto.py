# -*- coding: utf-8 -*-
"""字段级 AES-256-GCM 加密工具（[内控-数据安全] 落盘加密）。

落盘格式：base64url( version(1B) + nonce(12B) + ciphertext + auth_tag(16B) )。
字段仍为 Char 存密文，不改变列类型。

密钥分离：
- 优先从环境变量 TMS_FIELD_ENCRYPT_KEY 读取（32 字节，hex 或 base64）。
- 兜底 ir.config_parameter 'tms.field_encrypt_key'（不硬编码进代码/git）。
- 密钥为空 -> 降级为明文 + 写一次 warning 日志（保证不因缺密钥崩溃）。

安全约定：
- 任何 logger/日志不得输出完整敏感值（本模块只输出脱敏/计数信息）。
- 掩码 mask() 只保留末尾 4 位，前面以 **** 代替。
"""
import base64
import binascii
import hashlib
import hmac
import logging
import os

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

_logger = logging.getLogger(__name__)

_PREFIX = b'\x01'          # 密文版本号（1 字节），便于未来升级算法
_NONCE_LEN = 12            # GCM 推荐 96-bit nonce
_TAG_LEN = 16             # GCM 128-bit auth tag（AESGCM.encrypt 返回 ciphertext||tag）

_ENV_KEY = 'TMS_FIELD_ENCRYPT_KEY'
_PARAM_KEY = 'tms.field_encrypt_key'

_warned_missing_key = False


def _decode_key(raw):
    """把 hex / base64 / 原始字节 解析为 32 字节密钥；非法返回 None。"""
    if not raw:
        return None
    raw = raw.strip()
    if isinstance(raw, str):
        raw = raw.encode('utf-8')
    # hex
    try:
        candidate = bytes.fromhex(raw.decode('ascii'))
        if len(candidate) == 32:
            return candidate
    except (ValueError, UnicodeDecodeError):
        pass
    # base64
    try:
        candidate = base64.b64decode(raw, validate=True)
        if len(candidate) == 32:
            return candidate
    except (ValueError, binascii.Error):
        pass
    # 原始 32 字节
    if len(raw) == 32:
        return raw
    return None


def get_key(env):
    """获取 32 字节加密密钥；无密钥返回 None（调用方降级明文）。

    密钥缺失只告警一次，避免日志刷屏。
    """
    raw = os.environ.get(_ENV_KEY) or ''
    if not raw and env is not None:
        try:
            raw = env['ir.config_parameter'].sudo().get_str(_PARAM_KEY) or ''
        except Exception:
            raw = ''
    key = _decode_key(raw)
    global _warned_missing_key
    if not key and not _warned_missing_key:
        _logger.warning(
            '字段加密密钥缺失（环境变量 %s 或 ir.config_parameter %s 均未配置 32 字节密钥），'
            '敏感字段将降级为明文存储。请尽快配置密钥并执行回填脚本。',
            _ENV_KEY, _PARAM_KEY,
        )
        _warned_missing_key = True
    return key


def encrypt(plaintext, key):
    """明文 -> base64url(nonce + ciphertext + tag)。key 必须为 32 字节。"""
    if plaintext is None:
        return None
    if isinstance(plaintext, str):
        plaintext = plaintext.encode('utf-8')
    aesgcm = AESGCM(key)
    nonce = os.urandom(_NONCE_LEN)
    ciphertext = aesgcm.encrypt(nonce, plaintext, None)  # 返回值 = ciphertext || tag
    return base64.urlsafe_b64encode(_PREFIX + nonce + ciphertext).decode('ascii')


def decrypt(ciphertext_b64, key):
    """base64url(nonce + ciphertext + tag) -> 明文；失败返回 None（绝不抛异常）。"""
    if not ciphertext_b64 or not key:
        return None
    try:
        raw = base64.urlsafe_b64decode(ciphertext_b64.encode('ascii'))
    except (ValueError, binascii.Error, AttributeError):
        return None
    if len(raw) < 1 + _NONCE_LEN + _TAG_LEN:
        return None
    nonce = raw[1:1 + _NONCE_LEN]
    data = raw[1 + _NONCE_LEN:]
    try:
        aesgcm = AESGCM(key)
        plaintext = aesgcm.decrypt(nonce, data, None)
        return plaintext.decode('utf-8')
    except Exception:
        _logger.warning('字段解密失败（密文与密钥不匹配或数据损坏），已按不可读处理。')
        return None


def is_encrypted(value):
    """判断值是否已是本模块产出的密文（以 version+nonce 结构开头）。"""
    if not value:
        return False
    if not isinstance(value, str):
        return False
    try:
        raw = base64.urlsafe_b64decode(value.encode('ascii'))
    except Exception:
        return False
    return raw[:1] == _PREFIX and len(raw) >= 1 + _NONCE_LEN + _TAG_LEN


def hash_value(plaintext, key):
    """HMAC-SHA256(密钥, 明文) -> hex，用于等值检索辅助列。

    用密钥做 HMAC 而非裸 SHA-256，防止对低熵值（身份证/卡号）的离线爆破。
    """
    if plaintext is None or not key:
        return None
    if isinstance(plaintext, str):
        plaintext = plaintext.encode('utf-8')
    return hmac.new(key, plaintext, hashlib.sha256).hexdigest()


def mask(value, keep=4):
    """掩码：只保留末尾 keep 位，前面以 **** 代替。与既有 acc_number_masked 口径一致。"""
    value = (value or '').strip()
    if value and len(value) >= keep:
        return '*' * keep + value[-keep:]
    if value:
        return '*' * keep
    return ''
