# -*- coding: utf-8 -*-
"""敏感字段加密 Mixin（AES-256-GCM + 密钥分离 + 掩码 + 权限 + 等值检索）。

用法（以 AbstractModel 混入，与 tour.accounting.mixin 同款模式）：

    class SomeModel(models.Model):
        _name = 'tour.some'
        _inherit = ['mail.thread', 'tour.encrypted.field.mixin']

        # 需加密的字段集合；每个字段必须配有同名 <field>_hash 与 <field>_masked
        _encrypted_fields = {'id_num': True, 'account_no': True}

        id_num = fields.Char('身份证号', help='🔴 已 AES-256-GCM 加密存储')
        id_num_hash = fields.Char('检索散列', index=True, copy=False)
        id_num_masked = fields.Char('掩码', compute='_compute_masked')

注意：扩展已有模型（无 _name 的扩展类）时必须显式声明 _name 等于被扩展模型名，
否则 Odoo 会把类名自动转成新 _name（例如 TourPartner -> tour.partner），
导致凭空多出一个继承 res.partner 的模型并触发 channel_ids 冲突：

    class TourPartner(models.Model):
        _name = 'res.partner'            # 显式等于被扩展模型
        _inherit = ['res.partner', 'tour.encrypted.field.mixin']
        _encrypted_fields = {...}

行为：
- create/write：明文 -> 密文落盘（同时同步 HMAC-SHA256 检索散列）；掩码值（****…）
  视为"未修改"忽略，防止把掩码回存覆盖真实值；已是密文的值保持不变。
- read：完整值查看组（tour_base.group_tour_sensitive_data，可用 config_parameter 覆盖）
  / sudo / 管理员 -> 解密完整值；其余用户 -> 掩码（****后4位）。
  密钥缺失或解密失败 -> 返回密文，绝不泄漏明文。
- export_data：与 read 同一套权限口径（默认掩码，出纳完整）。
- _search：把敏感字段的精确匹配（= / == / in / != / not in）翻译到 <field>_hash
  等值检索列；模糊匹配（ilike/like）不支持，直接报错（避免静默返回错误结果）。
- 日志：本模块任何 logger 均不输出完整敏感值。
"""
import logging

from odoo import api, models
from odoo.exceptions import UserError

from . import field_crypto

_logger = logging.getLogger(__name__)

# 可查看完整敏感值的默认权限组（XML ID）；解析失败时回退到系统管理员组。
# 默认指向 tour_base 自己的「敏感数据完整值查看组」，不依赖任何业务模块（避免反向依赖）。
# 可通过 ir.config_parameter 'tms.sensitive_data_group_xmlid' 覆盖（见 res.config.settings）。
DEFAULT_FULL_ACCESS_GROUP_XMLID = 'tour_base.group_tour_sensitive_data'
FALLBACK_GROUP_XMLID = 'base.group_system'
_PARAM_FULL_ACCESS_GROUP = 'tms.sensitive_data_group_xmlid'

# 不支持模糊搜索的操作符（密文无法做 like）
_FUZZY_OPS = ('ilike', 'like', 'not ilike', 'not like', '=ilike', '=like')


class EncryptedFieldMixin(models.AbstractModel):
    _name = 'tour.encrypted.field.mixin'
    _description = '敏感字段落盘加密 + 掩码展示 Mixin'

    # 子类覆盖：{ 字段名: True }。True 表示同时维护 <field>_hash 等值检索列。
    _encrypted_fields = {}

    # ---------- 密钥与权限 ----------
    def _encrypt_key(self):
        return field_crypto.get_key(self.env)

    def _full_access_group_xmlid(self):
        """当前生效的完整敏感值查看权限组 XML ID。

        优先取 ir.config_parameter 覆盖值（系统设置「敏感数据查看组」），
        未配置时回退到 tour_base 自带的默认组。
        """
        try:
            xmlid = (self.env['ir.config_parameter'].sudo()
                     .get_param(_PARAM_FULL_ACCESS_GROUP) or '').strip()
        except Exception:
            xmlid = ''
        return xmlid or DEFAULT_FULL_ACCESS_GROUP_XMLID

    def _user_has_full_access(self):
        """当前用户是否可查看完整敏感值。"""
        if self.env.su:
            return True
        user = self.env.user
        try:
            return user.has_group(self._full_access_group_xmlid())
        except ValueError:
            return user.has_group(FALLBACK_GROUP_XMLID)

    # ---------- 明文 / 掩码 取值助手 ----------
    def _encrypt_plain(self, fname):
        """返回字段明文（从缓存密文解密；存量明文原样返回；无值/解密失败返回 ''）。"""
        raw = self[fname]
        if not raw:
            return ''
        if field_crypto.is_encrypted(raw):
            key = self._encrypt_key()
            if key:
                plain = field_crypto.decrypt(raw, key)
                if plain is not None:
                    return plain
            return ''  # 无密钥或解密失败：不泄漏，返回空
        return raw

    def _encrypt_mask(self, fname):
        return field_crypto.mask(self._encrypt_plain(fname))

    # ---------- 写入：明文 -> 密文 ----------
    def _encrypt_vals(self, vals):
        enc = self._encrypted_fields or {}
        if not enc:
            return
        key = self._encrypt_key()
        fields_meta = self._fields
        for fname in enc:
            if fname not in vals:
                continue
            value = vals[fname]
            hash_fname = fname + '_hash'
            has_hash = hash_fname in fields_meta
            # 掩码值（****…）视为"未修改"，忽略写入
            if isinstance(value, str) and value.startswith('*'):
                vals.pop(fname)
                continue
            # 清空
            if value in (None, '', False):
                vals[fname] = False
                if has_hash:
                    vals[hash_fname] = False
                continue
            # 已是密文（复制/回填脚本等传入），保持不变
            if field_crypto.is_encrypted(value):
                continue
            # 明文 -> 加密（密钥为空则降级明文）
            if key:
                vals[fname] = field_crypto.encrypt(value, key)
            if has_hash:
                vals[hash_fname] = field_crypto.hash_value(value, key)

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            self._encrypt_vals(vals)
        return super().create(vals_list)

    def write(self, vals):
        vals = dict(vals)
        self._encrypt_vals(vals)
        return super().write(vals)

    # ---------- 读取：按权限解密 / 掩码 ----------
    def _decrypt_read_result(self, result):
        enc = self._encrypted_fields or {}
        if not enc or not result:
            return result
        key = self._encrypt_key()
        full_access = self._user_has_full_access()
        for row in result:
            for fname in enc:
                if fname not in row:
                    continue
                raw = row[fname]
                if not raw:
                    continue
                if field_crypto.is_encrypted(raw):
                    if key:
                        plain = field_crypto.decrypt(raw, key)
                        if plain is not None:
                            row[fname] = plain if full_access else field_crypto.mask(plain)
                            continue
                    # 无密钥或解密失败：保持密文（不泄漏明文）
                    row[fname] = raw
                else:
                    # 存量明文（未回填）
                    row[fname] = raw if full_access else field_crypto.mask(raw)
        return result

    def read(self, fields=None, load='_classic_read'):
        result = super().read(fields=fields, load=load)
        return self._decrypt_read_result(result)

    def export_data(self, fields_to_export):
        result = super().export_data(fields_to_export)
        datas = result.get('datas')
        enc = self._encrypted_fields or {}
        if not datas or not enc:
            return result
        key = self._encrypt_key()
        full_access = self._user_has_full_access()
        # 建立导出列 -> 敏感字段 的映射（列顺序与 fields_to_export 一一对应）
        idx_map = {}
        for i, f in enumerate(fields_to_export):
            if isinstance(f, (list, tuple)):
                fname = f[0] if f else None
            else:
                fname = (f or '').lstrip('/').split('/')[0]
            if fname in enc:
                idx_map[i] = fname
        if not idx_map:
            return result
        for row in datas:
            for i, fname in idx_map.items():
                if i >= len(row):
                    continue
                val = row[i]
                if val is None or val == '':
                    continue
                if field_crypto.is_encrypted(val):
                    plain = field_crypto.decrypt(val, key) if key else None
                    row[i] = (plain if full_access else field_crypto.mask(plain)) if plain is not None else val
                else:
                    row[i] = val if full_access else field_crypto.mask(val)
        return result

    # ---------- 搜索：精确匹配走 hash 辅助列 ----------
    def _translate_encrypted_domain(self, domain):
        enc = self._encrypted_fields or {}
        if not enc or not isinstance(domain, (list, tuple)) or not domain:
            return domain

        def translate_leaf(leaf):
            if not isinstance(leaf, (list, tuple)) or not leaf:
                return leaf
            fname = leaf[0]
            if fname not in enc:
                return leaf
            op = leaf[1] if len(leaf) > 1 else '='
            value = leaf[2] if len(leaf) > 2 else True
            key = self._encrypt_key()
            if not key:
                return leaf  # 明文模式：原样搜索
            hash_fname = fname + '_hash'
            if op in ('=', '=='):
                if not value:
                    return (fname, '=', False)
                return (hash_fname, '=', field_crypto.hash_value(value, key))
            if op == 'in':
                vals = list(value) if isinstance(value, (list, tuple)) else [value]
                return (hash_fname, 'in', [field_crypto.hash_value(v, key) for v in vals])
            if op in ('!=', '<>'):
                if not value:
                    return (fname, '!=', False)
                return (hash_fname, '!=', field_crypto.hash_value(value, key))
            if op == 'not in':
                vals = list(value) if isinstance(value, (list, tuple)) else [value]
                return (hash_fname, 'not in', [field_crypto.hash_value(v, key) for v in vals])
            if op in _FUZZY_OPS:
                raise UserError(
                    '敏感字段 %s 已加密存储，不支持模糊搜索（%s）；请改用精确匹配。' % (fname, op))
            return leaf

        def walk(i):
            out = []
            while i < len(domain):
                token = domain[i]
                if token == '!':
                    out.append('!')
                    sub, i = walk(i + 1)
                    out.append(sub)
                elif token in ('&', '|'):
                    out.append(token)
                    left, i = walk(i + 1)
                    right, i = walk(i)
                    out.append(left)
                    out.append(right)
                else:
                    out.append(translate_leaf(token))
                    i += 1
            return out, i

        result, _ = walk(0)
        return result

    @api.model
    def _search(self, domain, offset=0, limit=None, order=None, *,
                active_test=True, bypass_access=False):
        domain = self._translate_encrypted_domain(domain)
        return super()._search(
            domain, offset=offset, limit=limit, order=order,
            active_test=active_test, bypass_access=bypass_access,
        )

    # ---------- 存量明文回填 ----------
    def encrypt_existing_plaintext(self):
        """把存量明文加密为密文并同步检索散列（迁移时用，需已配置密钥）。

        用法（odoo shell）：
            env['tour.vehicle'].encrypt_existing_plaintext()
            env['res.partner'].encrypt_existing_plaintext()
        """
        key = self._encrypt_key()
        if not key:
            _logger.warning('无加密密钥，跳过 %s 存量回填（字段仍为明文）', self._name)
            return 0
        enc = self._encrypted_fields or {}
        total = 0
        for rec in self.with_context(active_test=False).search([]):
            vals = {}
            for fname in enc:
                raw = rec[fname]
                if not raw or field_crypto.is_encrypted(raw):
                    continue
                vals[fname] = field_crypto.encrypt(raw, key)
                hash_fname = fname + '_hash'
                if hash_fname in self._fields:
                    vals[hash_fname] = field_crypto.hash_value(raw, key)
            if vals:
                rec.write(vals)
                total += 1
        _logger.info('%s 存量回填完成：加密 %s 条记录', self._name, total)
        return total
