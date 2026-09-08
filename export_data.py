#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""由 data.json 生成前端 data.js。

数据源为 data.json，本脚本是唯一的 data -> js 转换器。
运行：python export_data.py
"""

import json
import os

BASE = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.join(BASE, 'data.json')
DST = os.path.join(BASE, 'data.js')


def j(obj):
    """序列化为合法 JS 字面量（JSON 是 JS 子集）。"""
    return json.dumps(obj, ensure_ascii=False, indent=2)


HEADER = """/* =========================================================================
 * 全国算力中心看板 · 数据层
 * -------------------------------------------------------------------------
 * 本文件由 data.json 自动生成，请勿直接手改（会丢失对 data.json 的同步）。
 * 生成方式：python export_data.py
 * 读取约定：内嵌 <script src="data.js"> 后，前导 window.* 全局变量即可用。
 * ========================================================================= */"""

PROJECT_DOC = """/* =========================================================================
 * 算力中心项目数据
 * 字段说明：
 *   id         稳定主键（增量刷新匹配用），格式：{adcode}-{类型缩写}-{三位序号}
 *   createdAt  首次收录时间(YYYY-MM-DD)
 *   updatedAt  最近一次变更时间(YYYY-MM-DD)，无变更为 null
 *   name       项目名称
 *   province   省份（简称，如'陕西'）
 *   city       地市（如'西安市'）
 *   district   区县/园区（如'长安区·航天基地'）
 *   type       类型：'超算中心' | '智算中心' | '运营商IDC' | '通用·云'
 *   stage      阶段：'已建成' | '在建' | '规划'（'在建'+'规划'归并为「在建及规划」）
 *   scaleText  规模文字（展示用，如'峰值180PFlops / 存储100PB'）
 *   level      气泡等级 1-5，决定地图气泡大小
 *   aiP        AI 算力(P)，仅智算中心 —— 与 hpcP / racks 三量纲互斥
 *   hpcP       超算算力(PFlops)，仅超算中心
 *   racks      机架数(架)，仅运营商IDC
 *   vendor     智算芯片厂商(仅智算)：昇腾/NVIDIA/寒武纪/海光/阿里/百度/混合/其他
 *   year       关键年份
 *   announced  公开报道月(YYYY-MM)
 *   estimated  是否预估(true 时规模列显示 [预估] 标签)
 *   coord      经纬度坐标 [lng, lat]
 *   intro      项目简介
 *   source     来源链接(可空，空字符串表示待补充)
 *   sourceName 出处名称
 * ========================================================================= */"""

POLICY_DOC = """/* =========================================================================
 * 算力 / 人工智能产业政策数据
 * 字段说明：
 *   id         稳定主键（增量刷新匹配用），格式：pol-{三位序号}
 *   createdAt  首次收录时间(YYYY-MM-DD)
 *   updatedAt  最近一次变更时间(YYYY-MM-DD)，无变更为 null
 *   title      政策名称
 *   level      政策层级标签：'国家级' | '省级' | '市级'
 *   region     归属/适用范围：'全国'(国家级政策) 或 具体省名简写(如'陕西')
 *              —— 二者区分：level 决定"层级标签"显示，region 决定该政策在哪个区域维度下展示
 *   publisher  发文单位
 *   date       发文/生效时间(YYYY-MM)
 *   content    政策要点摘要
 *   category   类别：'算力' | '人工智能'
 *   link       原文链接(可空，空字符串表示待补充)
 * 说明：全国维度展示部委政策；省维度展示对应省、市政策。
 * ========================================================================= */"""


def main():
    with open(SRC, encoding='utf-8') as f:
        data = json.load(f)

    meta = data['meta']
    c = data['constants']

    out = []
    out.append(HEADER)
    out.append('')
    out.append('/* ---------------- 刷新机制元信息（后端刷新时更新此对象） ---------------- */')
    out.append('window.DATA_META = ' + j(meta) + ';')
    out.append('')
    out.append('/* ---------------- 类型 / 厂商常量 ---------------- */')
    out.append('window.TYPE_COLOR = ' + j(c['TYPE_COLOR']) + ';')
    out.append('window.TYPE_LIST = ' + j(c['TYPE_LIST']) + ';')
    out.append('window.SIZE_BY_LEVEL = ' + j(c['SIZE_BY_LEVEL']) + ';')
    out.append('window.STAGES = ' + j(c['STAGES']) + ';')
    out.append('')
    out.append('/* 智算芯片厂商（用于份额饼图） */')
    out.append('window.VENDOR_LIST = ' + j(c['VENDOR_LIST']) + ';')
    out.append('window.VENDOR_COLOR = ' + j(c['VENDOR_COLOR']) + ';')
    out.append('')
    out.append('/* ---------------- 省份元数据（简/全称 + adcode 映射） ---------------- */')
    out.append('window.PROVINCES = ' + j(c['PROVINCES']) + ';')
    out.append('')
    out.append(PROJECT_DOC)
    out.append('window.PROJECTS = ' + j(data['projects']) + ';')
    out.append('')
    out.append(POLICY_DOC)
    out.append('window.POLICIES = ' + j(data['policies']) + ';')
    out.append('')

    with open(DST, 'w', encoding='utf-8') as f:
        f.write('\n'.join(out))

    print('generated:', DST)
    print('projects:', len(data['projects']), '| policies:', len(data['policies']))


if __name__ == '__main__':
    main()