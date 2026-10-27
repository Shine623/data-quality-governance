#!/usr/bin/env python3
"""
模糊去重

三级判定策略：
  1. 精确匹配：手机号相同 → 判定重复
  2. 强规则：手机号相同 + 姓名去空格相同 → 判定重复
  3. 弱规则：姓名编辑距离 ≤ 1 且地址相似 → 标记疑似，人工确认

踩坑：
  纯编辑距离不行——「张三丰/张三峰」编辑距离 1 但可能是两个人；
  「李四/李斯」也是。必须结合手机号、地址等辅助字段。

用法:
  python dedupe.py --input data.csv --output deduped.csv
"""
import argparse
import os
import sys
from difflib import SequenceMatcher

import pandas as pd


def edit_distance(a, b):
    """计算编辑距离（Levenshtein）"""
    if a == b:
        return 0
    if not a:
        return len(b)
    if not b:
        return len(a)

    # 滚动数组优化空间
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        cur = [i]
        for j, cb in enumerate(b, 1):
            cur.append(min(
                prev[j] + 1,           # 删除
                cur[j - 1] + 1,        # 插入
                prev[j - 1] + (ca != cb)  # 替换
            ))
        prev = cur
    return prev[-1]


def similarity(a, b):
    """字符串相似度 0-1"""
    if not a or not b:
        return 0.0
    return SequenceMatcher(None, a, b).ratio()


def normalize_name(name):
    """姓名归一化：去空格、去点"""
    if pd.isna(name):
        return ''
    return str(name).replace(' ', '').replace('　', '').replace('·', '').strip()


def find_duplicates(df):
    """
    找出重复组

    返回: [(group_id, [行索引列表], 判定方式)]
    """
    groups = []
    used = set()

    # ---------- 1. 手机号精确匹配 ----------
    if 'phone' in df.columns:
        phone_groups = df.groupby('phone').groups
        for phone, idxs in phone_groups.items():
            if pd.isna(phone) or str(phone).strip() == '':
                continue
            idxs = list(idxs)
            if len(idxs) > 1:
                groups.append((len(groups) + 1, idxs, '手机号相同'))
                used.update(idxs)

    # ---------- 2. 姓名 + 地址 模糊匹配 ----------
    # 只处理未被手机号判定过的记录
    remaining = [i for i in df.index if i not in used]

    if 'customer_name' in df.columns:
        # 按归一化后的姓名分组，减少比较次数
        name_map = {}
        for i in remaining:
            n = normalize_name(df.loc[i, 'customer_name'])
            if n:
                name_map.setdefault(n, []).append(i)

        # 同名的检查是否地址也相似
        for name, idxs in name_map.items():
            if len(idxs) < 2:
                continue

            # 两两比较地址
            matched = []
            for a in range(len(idxs)):
                for b in range(a + 1, len(idxs)):
                    i, j = idxs[a], idxs[b]
                    if i in used or j in used:
                        continue

                    addr_i = str(df.loc[i, 'address']) if 'address' in df.columns else ''
                    addr_j = str(df.loc[j, 'address']) if 'address' in df.columns else ''

                    sim = similarity(addr_i, addr_j)
                    if sim > 0.8:
                        matched.append((i, j, sim))

            # 并查集合并
            parent = {i: i for i in idxs}

            def find(x):
                while parent[x] != x:
                    parent[x] = parent[parent[x]]
                    x = parent[x]
                return x

            def union(x, y):
                rx, ry = find(x), find(y)
                if rx != ry:
                    parent[ry] = rx

            for i, j, _ in matched:
                union(i, j)

            # 按根节点分组
            comp = {}
            for i in idxs:
                if i in used:
                    continue
                root = find(i)
                comp.setdefault(root, []).append(i)

            for root, members in comp.items():
                if len(members) > 1:
                    groups.append((len(groups) + 1, members, '姓名+地址相似'))
                    used.update(members)

    # ---------- 3. 疑似（编辑距离 1） ----------
    remaining = [i for i in df.index if i not in used]
    if 'customer_name' in df.columns:
        names = [(i, normalize_name(df.loc[i, 'customer_name'])) for i in remaining]
        names = [(i, n) for i, n in names if len(n) >= 2]

        suspected = []
        for a in range(len(names)):
            for b in range(a + 1, len(names)):
                i, ni = names[a]
                j, nj = names[b]
                if abs(len(ni) - len(nj)) > 1:
                    continue
                d = edit_distance(ni, nj)
                if d == 1:
                    suspected.append((i, j, ni, nj))

        if suspected:
            print()
            print(f'  [!] 发现 {len(suspected)} 组「疑似重复」（编辑距离=1），需人工确认：')
            for i, j, ni, nj in suspected[:15]:
                print(f'      行{i+2} "{ni}"  <->  行{j+2} "{nj}"')
            if len(suspected) > 15:
                print(f'      ... 还有 {len(suspected) - 15} 组')

    return groups


def main():
    p = argparse.ArgumentParser(description='模糊去重')
    p.add_argument('--input', required=True)
    p.add_argument('--output', required=True)
    p.add_argument('--keep', default='first', choices=['first', 'last'],
                   help='保留哪一条')
    p.add_argument('--mark-only', action='store_true',
                   help='只标记不删除（输出带 dup_group 列）')
    args = p.parse_args()

    if not os.path.exists(args.input):
        print(f'[!] 文件不存在: {args.input}')
        sys.exit(1)

    print(f'[*] 读取 {args.input} ...')
    df = pd.read_csv(args.input, dtype=str)
    print(f'[*] {len(df):,} 行')

    groups = find_duplicates(df)

    print()
    print('=' * 70)
    print('  去重结果')
    print('=' * 70)
    print(f'  发现重复组: {len(groups)}')

    total_dup = sum(len(g[1]) for g in groups)
    redundant = total_dup - len(groups)
    print(f'  涉及记录:   {total_dup}')
    print(f'  可删除:     {redundant}')
    print()

    # 按判定方式汇总
    by_type = {}
    for gid, idxs, reason in groups:
        by_type[reason] = by_type.get(reason, 0) + 1
    for reason, cnt in by_type.items():
        print(f'    {reason}: {cnt} 组')
    print()

    if args.mark_only:
        # 只标记
        df['dup_group'] = ''
        df['dup_reason'] = ''
        for gid, idxs, reason in groups:
            for i in idxs:
                df.loc[i, 'dup_group'] = f'G{gid:04d}'
                df.loc[i, 'dup_reason'] = reason

        df.to_csv(args.output, index=False, encoding='utf-8-sig')
        print(f'[+] 已标记（未删除）: {args.output}')
    else:
        # 删除冗余
        to_drop = []
        for gid, idxs, reason in groups:
            if args.keep == 'first':
                to_drop.extend(idxs[1:])
            else:
                to_drop.extend(idxs[:-1])

        result = df.drop(index=to_drop)
        result.to_csv(args.output, index=False, encoding='utf-8-sig')
        print(f'[+] 删除 {len(to_drop)} 条冗余记录')
        print(f'    剩余 {len(result):,} 行')
        print(f'    已保存: {args.output}')

    print('=' * 70)


if __name__ == '__main__':
    main()
