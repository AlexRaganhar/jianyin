# 映射与草稿数据契约

## 1. 分层

- **draft-rules.json**：分析阶段的候选规则，供人工审阅；包含原文和替换值。
- **case-redaction.json**：应用后的最终映射，包含每处命中的脱敏前后偏移；用于还原。
- 两者都只应保存在本地受控工作区，不能当普通材料外发。

## 2. 规则草稿 `draft-rules.json`

顶层：

| 字段 | 说明 |
|---|---|
| `schema_version` | 当前为 `1` |
| `scope` | `case` 或 `file` |
| `tool` | 固定 `jianyin` |
| `product` | `笺隐` |
| `sensitive` / `local_only` | 固定 `true` |
| `created_at` | UTC ISO 时间 |
| `case` | 案件级草稿的 `{id, name}` |
| `source_name` | 单文件草稿的输入名 |
| `model` | 模型运行时、revision、窗口参数 |
| `detection` | 模型开关和中文规则开关 |
| `rules` | 策略名称/版本 |
| `summary` | 文档数、命中数、候选规则数、按类别/来源统计 |
| `candidates` | 候选规则数组 |
| `draft_sha256` | 用于判断最终映射是否过期 |

候选规则：

| 字段 | 说明 |
|---|---|
| `id` | 草稿内唯一 |
| `category` | 官方 8 类或 `organization`/`other` |
| `subtype` | `cn_id`/`cn_mobile`/`cn_bank_card`/`cn_name` 等 |
| `source` / `target` | 原文值 / 替换值 |
| `enabled` | 是否应用 |
| `target_edited` | 替换值是否被人工修改 |
| `apply_all` | 是否应用到案件内所有精确出现位置 |
| `match_mode` | `auto`/`literal`/`ascii_word`/`digit_boundary` |
| `detection_sources` | `model`、`manual`、`rule:*` 的组合 |
| `detected_count` | 检测阶段命中次数 |
| `literal_count` | 全案件字面命中次数 |
| `note` | 审阅备注 |
| `occurrences` | 检测阶段的 `{document_id,start,end,source}` |

## 3. 最终映射 `case-redaction.json`

`mapping.schema_version` 当前为 `3`。

```json
{
  "schema_version": 3,
  "scope": "case",
  "tool": "jianyin",
  "created_at": "...",
  "case": {"id": "...", "name": "..."},
  "model": {"runtime": "onnxruntime-q4", "model_revision": "..."},
  "detection": {"model_enabled": true, "chinese_rules": {}},
  "rules": {"name": "default-safe-redaction", "schema_version": 2},
  "draft_sha256": "...",
  "summary": {
    "document_count": 2,
    "applied_rule_count": 8,
    "applied_occurrence_count": 12,
    "skipped_overlap_count": 0,
    "by_category": {},
    "by_source": {}
  },
  "documents": [
    {
      "id": "...",
      "source_name": "材料.pdf",
      "display_name": "材料.pdf",
      "source_type": "pdf",
      "extraction_method": "pdf-text",
      "page_count": 12,
      "redacted_md": "outputs/redacted/<id>.md",
      "redacted_docx": "outputs/redacted/<id>.docx"
    }
  ],
  "mappings": [
    {
      "id": 1,
      "type": "fixed",
      "category": "private_person",
      "subtype": null,
      "source": "张三",
      "target": "张某",
      "source_kind": "model+rule:cn_name",
      "rule_id": 1,
      "occurrences": [
        {
          "document_id": "...",
          "source_start": 10,
          "source_end": 12,
          "redacted_start": 10,
          "redacted_end": 12
        }
      ]
    }
  ]
}
```

### 偏移语义

- `source_start/source_end`：原文（提取文本）中的字符偏移，`[start, end)`。
- `redacted_start/redacted_end`：脱敏 Markdown 中的字符偏移。
- 偏移按 Python 字符串的 Unicode 码点计数。
- occurrence 在同一文档内不得重叠。

### 还原规则

1. 读取映射，校验版本、文档 ID、偏移非负、target 非空。
2. 逐处检查 `redacted_text[redacted_start:redacted_end] == target`。
3. 任一处不匹配：整次还原失败，不写任何文件。
4. 全部匹配：按升序拼接原文，生成还原 Markdown。
5. 还原输出是提取文本的重排，不是原始 PDF/Word 二进制。

### 归档

每次重新应用脱敏前，旧 `case-redaction.json` 会复制到 `rules/archive/case-redaction-<时间>.json`，最多保留 5 份。归档同样包含原始敏感值。

### 版本兼容

- 只接受 `schema_version: 3`。
- 旧版 schema 2 映射明确拒绝；请继续使用旧工具或重新导入原件后应用。
- 策略规则 `schema_version: 1/2` 均可读取。
