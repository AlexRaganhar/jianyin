"""Conservative local Chinese PII supplement for the English-centric model."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from importlib.resources import files
from pathlib import Path
from typing import Any, Mapping

from ..config import ChineseRuleOptions
from ..errors import RuleError
from .base import (
    CancelCheck,
    Detection,
    DetectionBatch,
    ProgressCallback,
    check_cancelled,
)

_ID_WEIGHTS = (7, 9, 10, 5, 8, 4, 2, 1, 6, 3, 7, 9, 10, 5, 8, 4, 2)
_ID_CHECK_CODES = "10X98765432"
_ID_RE = re.compile(
    r"(?<!\d)([1-9]\d{5}(?:18|19|20)\d{2}(?:0[1-9]|1[0-2])(?:0[1-9]|[12]\d|3[01])\d{3}[\dXx])(?!\d)"
)
_MOBILE_RE = re.compile(r"(?<!\d)(1[3-9]\d{9})(?!\d)")
_BANK_RE = re.compile(r"(?<!\d)(\d{16,19})(?!\d)")
_LANDLINE_RE = re.compile(r"(?<!\d)(0\d{2,3}[-\s]?\d{7,8})(?!\d)")
_DATE_RE = re.compile(
    r"(?<!\d)((?:19|20)\d{2}年(?:0?[1-9]|1[0-2])月(?:0?[1-9]|[12]\d|3[01])日)(?!\d)"
)
_ADDRESS_RE = re.compile(
    r"(?<![\u4e00-\u9fff])("
    r"(?:[\u4e00-\u9fff]{2,12}(?:省|市|自治区|自治州|区|县|镇|乡|街道)){1,3}"
    r"[\u4e00-\u9fff0-9A-Za-z\-]{2,40}"
    r"(?:路|街|巷|号|栋|幢|单元|室|楼)"
    r")"
)

_NAME_CONTEXT_RE = re.compile(
    r"(?:被告人|犯罪嫌疑人|被害人|证人|当事人|申请人|被申请人|原告|被告|第三人|"
    r"上诉人|被上诉人|再审申请人|辩护人|诉讼代理人|委托代理人|法定代理人|"
    r"法定代表人|负责人|联系人|经营者|实际控制人|股东|员工|姓名|我叫|化名|绰号)"
    r"[：:\s，,]*([\u4e00-\u9fff·]{2,10})"
)
_NAME_LINE_RE = re.compile(r"(?m)^[ \t]*([\u4e00-\u9fff]{2,4})[，,]\s*(?:男|女)")

_NAME_STOPWORDS = (
    "法院",
    "检察院",
    "公安",
    "派出所",
    "公司",
    "有限",
    "银行",
    "医院",
    "大学",
    "学院",
    "学校",
    "政府",
    "委员会",
    "事务所",
    "律师",
    "代理",
    "辩护",
    "被告",
    "原告",
    "证人",
    "被害人",
    "犯罪",
    "嫌疑",
    "人民",
    "中级",
    "高级",
    "基层",
    "第一",
    "第二",
    "第三",
    "住所",
    "住址",
    "户籍",
    "身份",
    "电话",
    "手机",
    "邮箱",
    "账号",
    "合同",
    "协议",
    "项目",
    "工程",
    "部门",
    "中心",
    "集团",
    "工厂",
    "商店",
    "经营部",
    "工作室",
)
_NAME_TRAILING_CHARS = set("系于在现住男女的了向与和为是有被将已经因从到等其该本我你他她它们者等及以之")
_NAME_LEADING_CHARS = set("系于在现住男女的了向与和为是有被将已经因从到等其该本我你他她它们者及以之")
_NAME_PUNCT = set("，。；：、,.;:：·")

_FALLBACK_SURNAMES = (
    "赵钱孙李周吴郑王冯陈褚卫蒋沈韩杨朱秦尤许何吕施张孔曹严华金魏陶姜戚谢邹喻柏水窦章云苏潘葛奚范彭郎鲁韦昌马苗凤花方俞任袁柳酆鲍史唐费廉岑薛雷贺倪汤滕殷罗毕郝邬安常乐于时傅皮卞齐康伍余元卜顾孟平黄和穆萧尹姚邵湛汪祁毛禹狄米贝明臧计伏成戴谈宋茅庞熊纪舒屈项祝董梁杜阮蓝闵席季麻强贾路娄危江童颜郭梅盛林刁钟徐邱骆高夏蔡田樊胡凌霍虞万支柯管卢莫经房裘缪干解应宗丁宣贲邓郁单杭洪包诸左石崔吉龚程嵇邢裴陆荣翁荀羊甄曲家封芮羿储靳汲邴糜松井段富巫乌焦巴弓牧隗山谷车侯宓蓬全郗班仰秋仲伊宫宁仇栾暴甘钭厉戎祖武符刘景詹束龙叶幸司韶郜黎蓟薄印宿白怀蒲邰从鄂索咸籍赖卓蔺屠蒙池乔阴胥能苍双闻莘党翟谭贡劳逄姬申扶堵冉宰郦雍却璩桑桂濮牛寿通边扈燕冀浦尚农温别庄晏柴瞿阎充慕连茹习宦艾鱼容向古易慎戈廖庾终暨居衡步都耿满弘匡国文寇广禄阙东欧殳沃利蔚越夔隆师巩厍聂晁勾敖融冷訾辛阚那简饶空曾毋沙乜养鞠须丰巢关蒯相查后荆红游竺权逯盖益桓公"
)
_COMPOUND_SURNAMES = (
    "欧阳",
    "司马",
    "上官",
    "诸葛",
    "东方",
    "皇甫",
    "尉迟",
    "公孙",
    "慕容",
    "司徒",
    "令狐",
    "宇文",
    "长孙",
    "夏侯",
    "轩辕",
    "端木",
    "独孤",
    "南宫",
    "西门",
    "百里",
    "呼延",
    "东郭",
    "太史",
)


def _load_surnames() -> tuple[set[str], set[str]]:
    single = set(_FALLBACK_SURNAMES)
    compound = set(_COMPOUND_SURNAMES)
    try:
        resource = files("jianyin_app").joinpath("data").joinpath("chinese_surnames.txt")
        text = resource.read_text(encoding="utf-8")
    except Exception:
        text = ""
    for line in text.splitlines():
        value = line.strip()
        if not value or value.startswith("#"):
            continue
        if len(value) == 2:
            compound.add(value)
        elif len(value) == 1:
            single.add(value)
    return single, compound


def load_surnames() -> tuple[set[str], set[str]]:
    """Return ``(single_surnames, compound_surnames)`` from bundled data."""
    return _load_surnames()


@dataclass(frozen=True)
class _RuleSpec:
    rule_id: str
    label: str
    category: str
    subtype: str
    priority: int
    default_enabled: bool


def load_chinese_rule_payload(path: str | Path | None = None) -> Mapping[str, Any]:
    try:
        if path is None:
            resource = files("jianyin_app").joinpath("data").joinpath("chinese_rules.json")
            payload = json.loads(resource.read_text(encoding="utf-8"))
        else:
            payload = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise RuleError("无法读取中文规则配置。") from error
    if not isinstance(payload, Mapping):
        raise RuleError("中文规则配置必须是 JSON 对象。")
    return payload


def _specs_from_payload(payload: Mapping[str, Any]) -> dict[str, _RuleSpec]:
    raw_rules = payload.get("rules")
    if not isinstance(raw_rules, Mapping):
        raise RuleError("中文规则配置缺少 rules。")
    specs: dict[str, _RuleSpec] = {}
    for rule_id, raw in raw_rules.items():
        if not isinstance(rule_id, str) or not isinstance(raw, Mapping):
            raise RuleError("中文规则配置格式无效。")
        specs[rule_id] = _RuleSpec(
            rule_id=rule_id,
            label=str(raw.get("label", rule_id)),
            category=str(raw.get("category", "other")),
            subtype=str(raw.get("subtype", rule_id)),
            priority=int(raw.get("priority", 50)),
            default_enabled=bool(raw.get("default_enabled", False)),
        )
    return specs


def valid_cn_id(value: str) -> bool:
    if len(value) != 18 or not _ID_RE.fullmatch(value):
        return False
    total = sum(int(value[index]) * _ID_WEIGHTS[index] for index in range(17))
    return value[-1].upper() == _ID_CHECK_CODES[total % 11]


def luhn_valid(value: str) -> bool:
    if not value.isdigit() or not 16 <= len(value) <= 19:
        return False
    total = 0
    parity = len(value) % 2
    for index, character in enumerate(value):
        digit = int(character)
        if index % 2 == parity:
            digit *= 2
            if digit > 9:
                digit -= 9
        total += digit
    return total % 10 == 0


class ChineseRuleDetector:
    """Deterministic regex/checksum detector for common Chinese identifiers."""

    def __init__(
        self,
        options: ChineseRuleOptions | None = None,
        *,
        config_path: str | Path | None = None,
    ) -> None:
        self.options = options or ChineseRuleOptions()
        payload = load_chinese_rule_payload(config_path)
        self._specs = _specs_from_payload(payload)
        self._single_surnames, self._compound_surnames = _load_surnames()

    @property
    def metadata(self) -> dict[str, Any]:
        return {
            "runtime": "chinese-rules",
            "enabled_rules": list(self.options.enabled_rule_ids()),
        }

    def detect(
        self,
        text: str,
        *,
        progress: ProgressCallback | None = None,
        cancel: CancelCheck | None = None,
    ) -> DetectionBatch:
        check_cancelled(cancel)
        detections: list[Detection] = []
        counts: dict[str, int] = {}
        for rule_id in self.options.enabled_rule_ids():
            check_cancelled(cancel)
            spec = self._specs.get(rule_id)
            if spec is None:
                continue
            found = self._run_rule(rule_id, spec, text)
            if found:
                detections.extend(found)
                counts[rule_id] = len(found)
        detections.sort(key=lambda item: (item.start, item.end, item.category))
        return DetectionBatch(
            text=text,
            detections=tuple(detections),
            stats={"runtime": "chinese-rules", "by_rule": counts},
        )

    def _run_rule(self, rule_id: str, spec: _RuleSpec, text: str) -> list[Detection]:
        if rule_id == "cn_id":
            return self._detect_id(text, spec)
        if rule_id == "cn_mobile":
            return self._detect_mobile(text, spec)
        if rule_id == "cn_bank_card":
            return self._detect_bank_card(text, spec)
        if rule_id == "cn_name_context":
            return self._detect_names(text, spec)
        if rule_id == "cn_landline":
            return self._detect_simple(text, spec, _LANDLINE_RE)
        if rule_id == "cn_date":
            return self._detect_simple(text, spec, _DATE_RE)
        if rule_id == "cn_address":
            return self._detect_simple(text, spec, _ADDRESS_RE)
        return []

    def _make(self, spec: _RuleSpec, start: int, end: int, text: str) -> Detection:
        return Detection(
            category=spec.category,
            start=start,
            end=end,
            text=text[start:end],
            source=f"rule:{spec.subtype}",
            subtype=spec.subtype,
            priority=spec.priority,
        )

    def _detect_id(self, text: str, spec: _RuleSpec) -> list[Detection]:
        result = []
        for match in _ID_RE.finditer(text):
            value = match.group(1)
            if valid_cn_id(value):
                result.append(self._make(spec, match.start(1), match.end(1), text))
        return result

    def _detect_mobile(self, text: str, spec: _RuleSpec) -> list[Detection]:
        result = []
        for match in _MOBILE_RE.finditer(text):
            value = match.group(1)
            if _ID_RE.fullmatch(value) or _BANK_RE.fullmatch(value):
                continue
            result.append(self._make(spec, match.start(1), match.end(1), text))
        return result

    def _detect_bank_card(self, text: str, spec: _RuleSpec) -> list[Detection]:
        result = []
        for match in _BANK_RE.finditer(text):
            value = match.group(1)
            if _ID_RE.fullmatch(value) or _MOBILE_RE.fullmatch(value):
                continue
            if luhn_valid(value):
                result.append(self._make(spec, match.start(1), match.end(1), text))
        return result

    def _detect_simple(self, text: str, spec: _RuleSpec, pattern: re.Pattern[str]) -> list[Detection]:
        return [
            self._make(spec, match.start(1), match.end(1), text)
            for match in pattern.finditer(text)
            if match.group(1).strip()
        ]

    def _detect_names(self, text: str, spec: _RuleSpec) -> list[Detection]:
        found: list[Detection] = []
        seen: set[tuple[int, int]] = set()
        for pattern in (_NAME_CONTEXT_RE, _NAME_LINE_RE):
            for match in pattern.finditer(text):
                candidate = match.group(1)
                cleaned = self._clean_name(candidate)
                if cleaned is None:
                    continue
                name, offset = cleaned
                start = match.start(1) + offset
                end = start + len(name)
                if (start, end) in seen:
                    continue
                if not self._is_name_like(name):
                    continue
                seen.add((start, end))
                found.append(self._make(spec, start, end, text))
        return found

    @staticmethod
    def _clean_name(candidate: str) -> tuple[str, int] | None:
        value = candidate.strip()
        offset = len(candidate) - len(candidate.lstrip())
        while value and value[0] in _NAME_PUNCT:
            value = value[1:]
            offset += 1
        while value and value[-1] in _NAME_PUNCT:
            value = value[:-1]
        if not value:
            return None
        for suffix in ("先生", "女士", "同志", "等人", "等"):
            if value.endswith(suffix) and len(value) > len(suffix) + 1:
                value = value[: -len(suffix)]
                break
        while len(value) > 2 and value[-1] in _NAME_TRAILING_CHARS:
            value = value[:-1]
        while len(value) > 2 and value[0] in _NAME_LEADING_CHARS:
            value = value[1:]
            offset += 1
        if "·" in value:
            if len(value) > 10:
                return None
            return value, offset
        if len(value) > 4:
            return None
        return value, offset

    def _is_name_like(self, name: str) -> bool:
        if len(name) < 2 or len(name) > 10:
            return False
        if not all("\u4e00" <= character <= "\u9fff" or character == "·" for character in name):
            return False
        if "某" in name:
            return False
        if any(stopword in name for stopword in _NAME_STOPWORDS):
            return False
        if "·" in name:
            return len(name) >= 3
        prefix = name[:2]
        if prefix in self._compound_surnames:
            return len(name) >= 3 or "·" in name
        if name[0] in self._single_surnames:
            return len(name) >= 2
        return False
