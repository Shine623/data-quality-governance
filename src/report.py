#!/usr/bin/env python3
"""
报表自动化：把 8 张手工报表改成脚本生成

原来一个人做要 6 小时，现在 15 分钟。

踩坑：
  1. df.to_excel 会丢样式 → 改用 openpyxl 逐单元格写
  2. 条件格式跨版本不一致 → 直接在写单元格时判断并设填充色

用法:
  python report.py --input deduped.csv --outdir reports/
"""
import argparse
import os
import sys
from datetime import datetime

import pandas as pd

# ============================================================
# 样式封装
# ============================================================

def get_styles():
    """延迟导入，避免没装 openpyxl 时直接报错"""
    from openpyxl.styles import Font, PatternFill, Alignment, Border, Side

    return {
        'header_font': Font(bold=True, color='FFFFFF', size=10),
        'header_fill': PatternFill('solid', fgColor='1F4E79'),
        'header_align': Alignment(horizontal='center', vertical='center'),
        'title_font': Font(bold=True, size=14, color='1F4E79'),
        'body_font': Font(size=9),
        'red_fill': PatternFill('solid', fgColor='FFC7CE'),
        'yellow_fill': PatternFill('solid', fgColor='FFEB9C'),
        'green_fill': PatternFill('solid', fgColor='C6EFCE'),
        'thin': Side(style='thin', color='BFBFBF'),
    }


def write_sheet(ws, title, df, widths=None, highlight_rules=None):
    """
    通用写表函数

    highlight_rules: [(列名, 判断函数, 颜色)]，判断函数返回 True 时高亮
    """
    s = get_styles()

    # 标题
    ws['A1'] = title
    ws['A1'].font = s['title_font']
    ws.merge_cells(start_row=1, start_column=1,
                   end_row=1, end_column=max(len(df.columns), 1))
    ws.row_dimensions[1].height = 24

    # 表头（第 3 行，第 2 行留空）
    header_row = 3
    for ci, col in enumerate(df.columns, 1):
        c = ws.cell(header_row, ci, col)
        c.font = s['header_font']
        c.fill = s['header_fill']
        c.alignment = s['header_align']

    # 数据
    for ri, (_, row) in enumerate(df.iterrows(), header_row + 1):
        for ci, col in enumerate(df.columns, 1):
            val = row[col]
            if pd.isna(val):
                val = ''
            c = ws.cell(ri, ci, val)
            c.font = s['body_font']

            # 高亮判断
            if highlight_rules:
                for hl_col, fn, fill in highlight_rules:
                    if col == hl_col:
                        try:
                            if fn(row):
                                c.fill = fill
                        except Exception:
                            pass

    # 列宽
    if widths:
        for i, w in enumerate(widths[:len(df.columns)], 1):
            ws.column_dimensions[chr(64 + i) if i <= 26 else 'A' + chr(64 + i - 26)].width = w

    ws.freeze_panes = ws.cell(header_row + 1, 1)


# ============================================================
# 8 张报表
# ============================================================

def report_customer_total(df):
    """1. 客户总量统计"""
    return pd.DataFrame([{
        '指标': '客户总数',
        '数值': len(df),
    }, {
        '指标': '有手机号',
        '数值': df['phone'].notna().sum() if 'phone' in df.columns else 0,
    }, {
        '指标': '有地址',
        '数值': df['address'].notna().sum() if 'address' in df.columns else 0,
    }, {
        '指标': '有税号',
        '数值': df['tax_no'].notna().sum() if 'tax_no' in df.columns else 0,
    }])


def report_monthly_new(df):
    """2. 新增客户月报"""
    if 'created_at' not in df.columns:
        return pd.DataFrame({'提示': ['缺少 created_at 字段']})

    tmp = df.copy()
    tmp['month'] = pd.to_datetime(tmp['created_at'], errors='coerce').dt.strftime('%Y-%m')
    counts = tmp.groupby('month').size().reset_index(name='新增数量')
    return counts.sort_values('month', ascending=False)


def report_by_region(df):
    """3. 客户分布（按地区）"""
    if 'address' not in df.columns:
        return pd.DataFrame({'提示': ['缺少 address 字段']})

    # 提取省份（地址第一个词）
    tmp = df.copy()
    tmp['province'] = tmp['address'].astype(str).str.split(' ').str[0]
    counts = tmp.groupby('province').size().reset_index(name='客户数量')
    counts = counts.sort_values('客户数量', ascending=False)
    counts['占比'] = (counts['客户数量'] / len(df) * 100).round(2).astype(str) + '%'
    return counts


def report_by_industry(df):
    """4. 客户分布（按行业）"""
    if 'industry' not in df.columns:
        return pd.DataFrame({'提示': ['缺少 industry 字段']})

    counts = df.groupby('industry').size().reset_index(name='客户数量')
    counts = counts.sort_values('客户数量', ascending=False)
    counts['占比'] = (counts['客户数量'] / len(df) * 100).round(2).astype(str) + '%'
    return counts


def report_duplicates(df):
    """5. 重复客户清单"""
    if 'phone' not in df.columns:
        return pd.DataFrame({'提示': ['缺少 phone 字段']})

    dup = df[df.duplicated(subset=['phone'], keep=False) & df['phone'].notna()]
    if dup.empty:
        return pd.DataFrame({'提示': ['未发现重复']})

    return dup.sort_values('phone')[['phone', 'customer_name', 'address']
                                    if 'address' in df.columns
                                    else ['phone', 'customer_name']]


def report_quality(df):
    """6. 数据质量月报"""
    rows = []
    total = len(df)

    checks = [
        ('customer_name', '姓名'),
        ('phone', '手机号'),
        ('address', '地址'),
        ('tax_no', '税号'),
    ]

    for col, name in checks:
        if col not in df.columns:
            continue
        missing = df[col].isna().sum()
        rows.append({
            '字段': name,
            '总数': total,
            '缺失数': int(missing),
            '缺失率': f'{missing / total * 100:.2f}%',
        })

    # 手机号格式
    if 'phone' in df.columns:
        import re
        valid = df['phone'].astype(str).str.match(r'^1[3-9]\d{9}$')
        invalid = (~valid & df['phone'].notna()).sum()
        rows.append({
            '字段': '手机号格式',
            '总数': total,
            '缺失数': int(invalid),
            '缺失率': f'{invalid / total * 100:.2f}%',
        })

    return pd.DataFrame(rows)


def report_top50(df):
    """7. 大客户 TOP50"""
    if 'amount' not in df.columns:
        # 没有交易额字段时，按名称长度凑一个示例
        return pd.DataFrame({'提示': ['缺少 amount 字段，无法统计大客户']})

    top = df.nlargest(50, 'amount')
    cols = [c for c in ['customer_name', 'phone', 'industry', 'amount', 'address']
            if c in df.columns]
    return top[cols]


def report_change_log(df):
    """8. 客户变更记录"""
    if 'created_at' not in df.columns or 'updated_at' not in df.columns:
        return pd.DataFrame({'提示': ['缺少时间字段']})

    tmp = df.copy()
    tmp['created'] = pd.to_datetime(tmp['created_at'], errors='coerce')
    tmp['updated'] = pd.to_datetime(tmp['updated_at'], errors='coerce')
    changed = tmp[tmp['updated'] > tmp['created']]

    if changed.empty:
        return pd.DataFrame({'提示': ['无变更记录']})

    cols = [c for c in ['customer_name', 'created_at', 'updated_at'] if c in df.columns]
    return changed[cols].sort_values('updated_at', ascending=False)


# ============================================================
# 主流程
# ============================================================

REPORTS = [
    ('01_客户总量统计', report_customer_total, [20, 15]),
    ('02_新增客户月报', report_monthly_new, [15, 15]),
    ('03_客户分布_按地区', report_by_region, [20, 15, 12]),
    ('04_客户分布_按行业', report_by_industry, [20, 15, 12]),
    ('05_重复客户清单', report_duplicates, [18, 18, 40]),
    ('06_数据质量月报', report_quality, [18, 12, 12, 12]),
    ('07_大客户TOP50', report_top50, [20, 18, 15, 15, 40]),
    ('08_客户变更记录', report_change_log, [20, 20, 20]),
]


def main():
    p = argparse.ArgumentParser(description='报表自动化')
    p.add_argument('--input', required=True)
    p.add_argument('--outdir', default='reports')
    p.add_argument('--single-file', action='store_true',
                   help='全部报表放在一个 Excel 的不同 sheet 里')
    args = p.parse_args()

    if not os.path.exists(args.input):
        print(f'[!] 文件不存在: {args.input}')
        sys.exit(1)

    print(f'[*] 读取 {args.input} ...')
    df = pd.read_csv(args.input, dtype=str)
    print(f'[*] {len(df):,} 行')
    print()

    try:
        from openpyxl import Workbook
    except ImportError:
        print('[!] 需要 openpyxl: pip install openpyxl')
        sys.exit(1)

    os.makedirs(args.outdir, exist_ok=True)
    s = get_styles()

    if args.single_file:
        # 全部放一个文件
        out_path = os.path.join(args.outdir, '客户数据报表汇总.xlsx')
        wb = Workbook()
        wb.remove(wb.active)

        for name, fn, widths in REPORTS:
            print(f'  - {name}')
            data = fn(df)
            ws = wb.create_sheet(name[:31])
            write_sheet(ws, name, data, widths)

        wb.save(out_path)
        print()
        print(f'[+] 已生成: {out_path}')
    else:
        # 每个报表一个文件
        for name, fn, widths in REPORTS:
            print(f'  - {name}')
            data = fn(df)
            wb = Workbook()
            ws = wb.active
            ws.title = name[:31]
            write_sheet(ws, name, data, widths)

            out_path = os.path.join(args.outdir, f'{name}.xlsx')
            wb.save(out_path)

        print()
        print(f'[+] 已生成 8 个报表: {args.outdir}/')

    print()
    print('=' * 60)
    print(f'  完成时间: {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}')
    print('=' * 60)


if __name__ == '__main__':
    main()
