#!/usr/bin/env python3
"""
数据画像

清洗之前先摸清问题。输出每个字段的：
  - 总数、非空数、缺失率
  - 唯一值数、重复率
  - 格式错误数（针对有格式要求的字段）

用法:
  python profile.py --input samples/sample_customers.csv
"""
import argparse
import os
import re
import sys

import pandas as pd

# 字段格式规则
FORMAT_RULES = {
    'phone': (r'^1[3-9]\d{9}$', '手机号应为 11 位，1 开头'),
    'tax_no': (r'^[0-9A-Z]{15,20}$', '税号应为 15-20 位大写字母或数字'),
    'email': (r'^[\w.+-]+@[\w-]+\.[\w.]+$', '邮箱格式'),
}


def profile_column(series, col_name):
    """画像单个字段"""
    total = len(series)
    non_null = series.notna().sum()
    missing = total - non_null
    missing_rate = missing / total * 100 if total else 0

    # 唯一值（排除空值）
    non_null_series = series.dropna()
    unique = non_null_series.nunique()
    dup_count = len(non_null_series) - unique
    dup_rate = dup_count / total * 100 if total else 0

    # 格式检查
    format_errors = 0
    format_msg = ''
    if col_name in FORMAT_RULES:
        pattern, msg = FORMAT_RULES[col_name]
        # 只检查非空值
        mask = non_null_series.astype(str).str.match(pattern)
        format_errors = int((~mask).sum())
        format_msg = msg

    format_rate = format_errors / non_null * 100 if non_null else 0

    return {
        'column': col_name,
        'total': total,
        'non_null': non_null,
        'missing': missing,
        'missing_rate': round(missing_rate, 2),
        'unique': unique,
        'dup_count': dup_count,
        'dup_rate': round(dup_rate, 2),
        'format_errors': format_errors,
        'format_rate': round(format_rate, 2),
        'format_msg': format_msg,
    }


def print_profile(profiles):
    """打印画像结果"""
    print()
    print('=' * 100)
    print('  数据画像结果')
    print('=' * 100)
    print()

    header = (f'{"字段名":<20} {"总数":>9} {"缺失":>9} {"缺失率":>8} '
              f'{"唯一值":>9} {"重复":>9} {"格式错误":>9} {"错误率":>8}')
    print(header)
    print('-' * 100)

    for p in profiles:
        line = (f'{p["column"]:<20} {p["total"]:>9,} {p["missing"]:>9,} '
                f'{p["missing_rate"]:>7.2f}% {p["unique"]:>9,} '
                f'{p["dup_count"]:>9,} {p["format_errors"]:>9,} '
                f'{p["format_rate"]:>7.2f}%')
        print(line)

    print()

    # 问题汇总
    print('=' * 100)
    print('  问题汇总（按严重程度排序）')
    print('=' * 100)
    print()

    issues = []
    for p in profiles:
        if p['missing_rate'] > 10:
            issues.append((p['missing_rate'], '缺失率过高',
                           p['column'], f'缺失 {p["missing"]:,} 条 ({p["missing_rate"]}%)'))
        if p['format_rate'] > 0.5:
            issues.append((p['format_rate'], '格式错误',
                           p['column'], f'{p["format_errors"]:,} 条 ({p["format_rate"]}%)，{p["format_msg"]}'))
        if p['dup_rate'] > 1:
            issues.append((p['dup_rate'], '重复值',
                           p['column'], f'{p["dup_count"]:,} 条 ({p["dup_rate"]}%)'))

    issues.sort(reverse=True)

    if not issues:
        print('  未发现严重问题')
    else:
        for rate, kind, col, msg in issues:
            print(f'  [{kind}] {col}: {msg}')

    print()


def main():
    p = argparse.ArgumentParser(description='数据画像')
    p.add_argument('--input', required=True, help='CSV 文件')
    p.add_argument('--output', default=None, help='输出画像结果到 CSV')
    args = p.parse_args()

    if not os.path.exists(args.input):
        print(f'[!] 文件不存在: {args.input}')
        sys.exit(1)

    print(f'[*] 读取 {args.input} ...')
    df = pd.read_csv(args.input, dtype=str)
    print(f'[*] 共 {len(df):,} 行，{len(df.columns)} 列')
    print(f'[*] 字段: {", ".join(df.columns)}')

    profiles = []
    for col in df.columns:
        profiles.append(profile_column(df[col], col))

    print_profile(profiles)

    # 导出
    if args.output:
        out_df = pd.DataFrame(profiles)
        out_df.to_csv(args.output, index=False, encoding='utf-8-sig')
        print(f'[+] 画像结果已导出: {args.output}')

    # 结论
    total_missing = sum(p['missing'] for p in profiles)
    total_format_err = sum(p['format_errors'] for p in profiles)
    print('=' * 100)
    print(f'  合计：缺失 {total_missing:,} 个字段值，格式错误 {total_format_err:,} 个')
    print('=' * 100)
    print()
    print('  下一步：')
    print('    python src/rules.py --input', args.input)


if __name__ == '__main__':
    main()
