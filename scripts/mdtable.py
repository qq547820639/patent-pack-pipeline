#!/usr/bin/env python3
"""markdown 表格读取的唯一实现。三个判据脚本（check_evt / check_regulatory / verify_search_report）都要按列读表，
两处各写一份 split_row/col 迟早漂移——漂移的表现是同一个表在一边合规、在另一边判红。
"""
import re


def split_row(line):
    return [c.strip() for c in line.strip().strip('|').split('|')]


def is_separator(cells):
    return bool(cells) and set(''.join(cells)) <= set('-: ')


def col(header, *keys):
    """返回第一个包含任一关键字的列号；找不到返回 None。"""
    for idx, h in enumerate(header):
        if any(k in h for k in keys):
            return idx
    return None


def cols(header, *keys):
    """返回**所有**包含任一关键字的列号。'费用' 与 '周期' 常在一张表里并列，
    只取第一个会把后一列整列放过。"""
    return [idx for idx, h in enumerate(header) if any(k in h for k in keys)]


def table_blocks(text):
    """按顺序产出 (表头, [数据行])，不挑表——挑列的工作交给调用方。"""
    out = []
    lines = text.splitlines()
    i = 0
    while i < len(lines):
        if not lines[i].strip().startswith('|'):
            i += 1
            continue
        block = []
        while i < len(lines) and lines[i].strip().startswith('|'):
            block.append(lines[i])
            i += 1
        if len(block) < 2:
            continue
        header = split_row(block[0])
        rows = [split_row(b) for b in block[1:] if not is_separator(split_row(b))]
        out.append((header, rows))
    return out


def tables(text, *header_keys):
    """只保留表头含指定关键字之一的表。"""
    for header, rows in table_blocks(text):
        if col(header, *header_keys) is not None:
            yield header, rows


def heading_line(line):
    return bool(re.match(r'^#{1,6}\s', line))
