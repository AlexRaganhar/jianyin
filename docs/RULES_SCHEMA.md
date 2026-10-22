# 规则格式

## 1. 策略规则（类别 → 替换策略）

内置文件：`jianyin_app/data/default_rules.json`，`schema_version: 2`。

```json
{
  "schema_version": 2,
  "name": "default-safe-redaction",
  "review_required": true,
  "default": {"strategy": "placeholder", "placeholder": "[敏感信息{n}]"},
  "categories": {
    "private_person": {
      "strategy": "person_alias",
      "chinese_suffix": "某",
      "collision_suffix": true,
      "fallback_template": "[姓名{n}]"
    },
    "private_phone": {
      "strategy": "mask_middle",
      "keep_start": 3,
      "keep_end": 3,
      "mask_char": "*"
    }
  }
}
```

策略：

| strategy | 字段 | 行为 |
|---|---|---|
| `placeholder` | `placeholder` | 使用占位符；`{n}` 替换为类别内编号 |
| `mask_middle` | `keep_start`、`keep_end`、`mask_char` | 保留首尾，中间遮蔽；不改变长度 |
| `person_alias` | `chinese_suffix`、`collision_suffix`、`fallback_template` | 中文保留姓/复姓 + 某；同姓冲突编号；非中文用模板 |

- `{n}` 是可选编号；没有 `{n}` 时所有同类值使用同一个固定占位符，兼容旧规则。
- 旧版 `schema_version: 1` 的 `fallback_prefix`/`fallback_suffix` 仍可读取。
- 类别可自定义；未定义的类别走 `default`。

## 2. 中文补强配置

内置文件：`jianyin_app/data/chinese_rules.json`。

```json
{
  "schema_version": 1,
  "name": "chinese-pii-supplement",
  "rules": {
    "cn_id": {
      "label": "身份证号",
      "category": "account_number",
      "subtype": "cn_id",
      "priority": 80,
      "default_enabled": true
    }
  }
}
```

可用规则：

- `cn_id`：18 位身份证 + 校验码。
- `cn_mobile`：11 位大陆手机号。
- `cn_bank_card`：16–19 位 + Luhn。
- `cn_name_context`：角色/姓名上下文 + 姓氏表 + 停用词。
- `cn_landline`：区号 + 7–8 位（默认关）。
- `cn_date`：中文日期（默认关）。
- `cn_address`：省市区 + 街道/路/号（默认关）。

GUI 的“设置”会逐项覆盖开关；`--no-chinese` 关闭全部中文补强。姓名线索是低置信规则，检测来源显示为 `rule:cn_name`，必须在规则清单中复核。

## 3. 草稿中的人工编辑

- 修改 `target`：`target_edited` 置为 `true`，重新分析时保留。
- 手工添加：`detection_sources` 包含 `manual`，`occurrences` 可为空，`apply_all=true` 时按原文全案件扫描。
- `apply_all=false`：只应用检测阶段记录的 occurrence。
- `match_mode`：
  - `auto`：全数字用数字边界，纯 ASCII 单词用英文词边界，其余精确匹配；
  - `literal`：精确字符串；
  - `ascii_word`：`(?<![A-Za-z0-9_])...(?![A-Za-z0-9_])`；
  - `digit_boundary`：`(?<!\d)...(?!\d)`。

## 4. 校验与安全

- 替换值不能为空、不能含换行、不能与原文完全相同；人工替换值不能包含完整原文。
- 规则原文不能为空或含换行。
- 所有规则文件都只应写本地工作区；草稿和映射包含原始敏感值。
- 规则命中与 `<!-- PDF page N -->` 页标记相交时会被跳过，避免破坏分页结构。
