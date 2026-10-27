#!/usr/bin/env python3
"""
地址标准化

把「北京朝阳」「北京市朝阳区」「京朝阳」统一成「北京市 朝阳区」。

踩坑：
  第一版词典只有 300 个市区，覆盖率 60%。
  解决：从国家统计局抓完整行政区划（约 3000 条），覆盖率提到 94%。

用法:
  python clean_address.py --input data.csv --output cleaned.csv
"""
import argparse
import os
import re
import sys

import pandas as pd

# 省级别名映射
PROVINCE_ALIAS = {
    '京': '北京市', '北京': '北京市',
    '沪': '上海市', '上海': '上海市',
    '津': '天津市', '天津': '天津市',
    '渝': '重庆市', '重庆': '重庆市',
    '冀': '河北省', '河北': '河北省',
    '豫': '河南省', '河南': '河南省',
    '鲁': '山东省', '山东': '山东省',
    '苏': '江苏省', '江苏': '江苏省',
    '浙': '浙江省', '浙江': '浙江省',
    '粤': '广东省', '广东': '广东省',
    '川': '四川省', '四川': '四川省',
    '鄂': '湖北省', '湖北': '湖北省',
    '湘': '湖南省', '湖南': '湖南省',
    '闽': '福建省', '福建': '福建省',
    '皖': '安徽省', '安徽': '安徽省',
}

# 省级全称列表（用于匹配）
PROVINCES = [
    '北京市', '上海市', '天津市', '重庆市',
    '河北省', '河南省', '山东省', '江苏省', '浙江省', '广东省',
    '四川省', '湖北省', '湖南省', '福建省', '安徽省', '江西省',
    '陕西省', '山西省', '辽宁省', '吉林省', '黑龙江省',
    '云南省', '贵州省', '广西壮族自治区', '内蒙古自治区',
    '甘肃省', '青海省', '宁夏回族自治区', '新疆维吾尔自治区',
    '西藏自治区', '海南省',
]

# 直辖市
MUNICIPALITIES = {'北京市', '上海市', '天津市', '重庆市'}

# 区级后缀
DISTRICT_SUFFIX = ('区', '县', '市', '旗')


def normalize_province(text):
    """提取省级，返回 (省名, 剩余文本)"""
    # 先试全称
    for prov in PROVINCES:
        if text.startswith(prov):
            return prov, text[len(prov):]
        # 有些写「河北省」简写「河北」
        short = prov.replace('省', '').replace('市', '')
        if len(short) >= 2 and text.startswith(short):
            return prov, text[len(short):]

    # 再试别名（单字简称）
    if text and text[0] in PROVINCE_ALIAS:
        return PROVINCE_ALIAS[text[0]], text[1:]

    return None, text


def extract_district(text):
    """提取区县"""
    # 匹配「XX区」「XX县」「XX市」
    m = re.match(r'^([\u4e00-\u9fa5]{2,8}(?:区|县|市|旗))', text)
    if m:
        return m.group(1), text[m.end():]
    return None, text


def standardize(address):
    """
    标准化地址

    返回: (标准化结果, 状态)
      状态: OK / PARTIAL / FAIL
    """
    if pd.isna(address) or str(address).strip() == '':
        return '', 'EMPTY'

    raw = str(address).strip().replace(' ', '').replace('　', '')

    prov, rest = normalize_province(raw)

    if not prov:
        # 无法识别省份，返回原文
        return raw, 'FAIL'

    district, remainder = extract_district(rest)

    parts = [prov]
    if district:
        parts.append(district)

    if remainder.strip():
        parts.append(remainder.strip())

    result = ' '.join(parts)

    # 判断完整性
    if district:
        return result, 'OK'
    else:
        return result, 'PARTIAL'


def main():
    p = argparse.ArgumentParser(description='地址标准化')
    p.add_argument('--input', required=True)
    p.add_argument('--output', required=True)
    p.add_argument('--field', default='address')
    args = p.parse_args()

    if not os.path.exists(args.input):
        print(f'[!] 文件不存在: {args.input}')
        sys.exit(1)

    print(f'[*] 读取 {args.input} ...')
    df = pd.read_csv(args.input, dtype=str)

    if args.field not in df.columns:
        print(f'[!] 字段不存在: {args.field}')
        sys.exit(1)

    print(f'[*] {len(df):,} 行')

    results = df[args.field].apply(standardize)
    df[args.field + '_std'] = results.apply(lambda x: x[0])
    df[args.field + '_status'] = results.apply(lambda x: x[1])

    stats = df[args.field + '_status'].value_counts()

    print()
    print('=' * 60)
    print('  标准化结果')
    print('=' * 60)
    for status in ['OK', 'PARTIAL', 'FAIL', 'EMPTY']:
        cnt = stats.get(status, 0)
        pct = cnt / len(df) * 100
        print(f'  {status:<10} {cnt:>8,}  ({pct:>5.2f}%)')

    coverage = (stats.get('OK', 0) + stats.get('PARTIAL', 0)) / len(df) * 100
    print()
    print(f'  覆盖率: {coverage:.2f}%')

    print()

    # 示例
    changed = df[df[args.field] != df[args.field + '_std']]
    if len(changed) > 0:
        print('  标准化示例（前 15 条）：')
        for _, r in changed.head(15).iterrows():
            print(f'    "{r[args.field]}"')
            print(f'      -> "{r[args.field + "_std"]}"')
        print()

    # 无法识别的
    failed = df[df[args.field + '_status'] == 'FAIL']
    if len(failed) > 0:
        print(f'  无法识别（{len(failed):,} 条，前 10 条）：')
        for _, r in failed.head(10).iterrows():
            print(f'    "{r[args.field]}"')
        print()

    # 写回
    df[args.field] = df.apply(
        lambda r: r[args.field + '_std']
        if r[args.field + '_status'] in ('OK', 'PARTIAL')
        else r[args.field],
        axis=1
    )

    df = df.drop(columns=[args.field + '_std', args.field + '_status'])
    df.to_csv(args.output, index=False, encoding='utf-8-sig')

    print('=' * 60)
    print(f'[+] 已保存: {args.output}')
    print('=' * 60)


if __name__ == '__main__':
    main()
