#!/usr/bin/env python3
"""
手机号清洗

踩坑：最初写了个脚本把「所有 11 位以下手机号补 0」，
     结果把一些座机号也改了。
     解决：先做字段语义判断（11 位且 1 开头才是手机号），
           不确定的标记为「待确认」而不是直接改。

用法:
  python clean_phone.py --input data.csv --output cleaned.csv
"""
import argparse
import os
import re
import sys

import pandas as pd

PHONE_PATTERN = re.compile(r'^1[3-9]\d{9}$')


def clean_phone(value):
    """
    清洗单个手机号

    返回: (清洗后值, 状态)
      状态: OK / FIXED / INVALID / EMPTY
    """
    if pd.isna(value) or str(value).strip() == '':
        return '', 'EMPTY'

    raw = str(value).strip()

    # 去掉所有非数字字符（空格、横线、括号、+86 前缀等）
    digits = re.sub(r'\D', '', raw)

    # 去掉 +86 / 0086 前缀
    if digits.startswith('86') and len(digits) == 13:
        digits = digits[2:]
    if digits.startswith('0086') and len(digits) == 15:
        digits = digits[4:]

    # 正好 11 位且 1 开头 → 有效
    if PHONE_PATTERN.match(digits):
        if digits == raw:
            return digits, 'OK'
        return digits, 'FIXED'

    # 11 位但 1 开头不对（比如 2 开头）→ 无效
    if len(digits) == 11:
        return raw, 'INVALID'

    # 位数不对 → 无效，但保留原值供人工判断
    return raw, 'INVALID'


def main():
    p = argparse.ArgumentParser(description='手机号清洗')
    p.add_argument('--input', required=True)
    p.add_argument('--output', required=True)
    p.add_argument('--field', default='phone', help='手机号字段名')
    args = p.parse_args()

    if not os.path.exists(args.input):
        print(f'[!] 文件不存在: {args.input}')
        sys.exit(1)

    print(f'[*] 读取 {args.input} ...')
    df = pd.read_csv(args.input, dtype=str)

    if args.field not in df.columns:
        print(f'[!] 字段不存在: {args.field}')
        print(f'    可用字段: {", ".join(df.columns)}')
        sys.exit(1)

    print(f'[*] {len(df):,} 行')

    # 清洗
    results = df[args.field].apply(clean_phone)
    df[args.field + '_cleaned'] = results.apply(lambda x: x[0])
    df[args.field + '_status'] = results.apply(lambda x: x[1])

    # 统计
    stats = df[args.field + '_status'].value_counts()

    print()
    print('=' * 60)
    print('  清洗结果')
    print('=' * 60)
    for status in ['OK', 'FIXED', 'INVALID', 'EMPTY']:
        cnt = stats.get(status, 0)
        pct = cnt / len(df) * 100
        print(f'  {status:<10} {cnt:>8,}  ({pct:>5.2f}%)')

    print()

    # 显示修复示例
    fixed = df[df[args.field + '_status'] == 'FIXED']
    if len(fixed) > 0:
        print('  修复示例（前 10 条）：')
        for _, r in fixed.head(10).iterrows():
            print(f'    "{r[args.field]}" -> "{r[args.field + "_cleaned"]}"')
        print()

    # 显示无效示例
    invalid = df[df[args.field + '_status'] == 'INVALID']
    if len(invalid) > 0:
        print(f'  无效号码示例（共 {len(invalid):,} 条，前 10 条）：')
        for _, r in invalid.head(10).iterrows():
            print(f'    "{r[args.field]}"')
        print()

    # 写回原字段（只替换有效和已修复的）
    df[args.field] = df.apply(
        lambda r: r[args.field + '_cleaned']
        if r[args.field + '_status'] in ('OK', 'FIXED')
        else r[args.field],
        axis=1
    )

    df = df.drop(columns=[args.field + '_cleaned', args.field + '_status'])
    df.to_csv(args.output, index=False, encoding='utf-8-sig')

    print('=' * 60)
    print(f'[+] 已保存: {args.output}')
    print('=' * 60)


if __name__ == '__main__':
    main()
