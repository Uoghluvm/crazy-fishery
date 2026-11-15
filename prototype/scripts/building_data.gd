class_name BuildingData
extends Resource
## 单个建筑的数据定义。
## 原型阶段用代码 new() 生成；正式版建议改为 .tres 资源文件，在编辑器里配置。

## 建筑分类：attack / resource / skill / special
@export var category: String = "attack"

## 显示名称
@export var display_name: String = ""

## 基础数值（攻击建筑的伤害、资源建筑的产出，辅助建筑可为 0）
@export var base_power: float = 0.0

## 位置效果类型，见 board.gd 的 _compute()
## none / adjacent_attack_flat / adjacent_mult / range_flat
@export var effect: String = "none"

## 效果说明，显示在 UI 上
@export_multiline var effect_desc: String = ""
