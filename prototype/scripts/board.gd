extends Control
## 《疯狂渔场》可玩验证原型 v0.1
##
## 目的：验证"摆放组合"本身是否好玩。只做 3 件事：
##   1. 3×3 木筏格盘
##   2. 建筑放置 / 拆除
##   3. 位置效果实时计算 + 高亮 + 悬停看结算明细
## 不含战斗、不含资源消耗。
##
## 操作：左侧点选建筑 → 点击格子放置；右键或未选中建筑时点击已占格 = 拆除；悬停格子看结算。

const GRID_SIZE: int = 3
const CELL_COUNT: int = GRID_SIZE * GRID_SIZE
const CELL_SIZE: Vector2 = Vector2(116.0, 116.0)

# 分类颜色
var _col_attack: Color = Color("#c9553f")
var _col_resource: Color = Color("#4e9b6a")
var _col_skill: Color = Color("#4a7fbf")
var _col_special: Color = Color("#8e6cc9")

var _col_bg_empty: Color = Color("#0f1d26")
var _col_border_idle: Color = Color("#2b4553")
var _col_border_focus: Color = Color("#ffd166")
var _col_border_link: Color = Color("#42d6c4")

# ---- 数据 ----
var _catalog: Array[BuildingData] = []
var _by_id: Dictionary = {}
var _grid: Array[BuildingData] = []

# ---- 界面 ----
var _cells: Array[Panel] = []
var _sb: Array[StyleBoxFlat] = []
var _name_labels: Array[Label] = []
var _power_labels: Array[Label] = []
var _mod_labels: Array[Label] = []
var _palette_buttons: Array[Button] = []
var _info_label: Label
var _stats_label: Label

var _selected: int = -1
var _hover: int = -1

# 预览通道：不写入 _grid，避免渲染过程中改动真实数据
var _preview_index: int = -1
var _preview_building: BuildingData = null


func _ready() -> void:
	_apply_cjk_theme()
	_build_catalog()
	_grid.resize(CELL_COUNT)
	_grid.fill(null)
	_build_ui()
	_refresh()


# ============================================================
# 初始化
# ============================================================

## Godot 默认字体不含中文字形，这里挂载系统中文字体，否则界面全是方块。
func _apply_cjk_theme() -> void:
	var paths: Array[String] = [
		"C:/Windows/Fonts/msyh.ttc",
		"C:/Windows/Fonts/msyhl.ttc",
		"C:/Windows/Fonts/simhei.ttf",
		"C:/Windows/Fonts/Deng.ttf",
		"C:/Windows/Fonts/simsun.ttc",
	]
	for p in paths:
		if not FileAccess.file_exists(p):
			continue
		var font := FontFile.new()
		if font.load_dynamic_font(p) != OK:
			continue
		var t := Theme.new()
		t.default_font = font
		t.default_font_size = 15
		theme = t
		return
	push_warning("未找到中文字体，界面中文可能显示为方块。")


func _build_catalog() -> void:
	_add("ballista", "弩炮", "attack", 10.0, "none", "基础攻击建筑，本身没有位置效果。")
	_add("harpoon", "鱼叉", "attack", 6.0, "none", "低数值攻击建筑，适合铺边角。")
	_add("net", "捕鱼网", "resource", 5.0, "none", "资源产出，本身没有位置效果。")
	_add("purifier", "海水净化器", "resource", 4.0, "none", "资源产出，本身没有位置效果。")
	_add("ammo", "弹药架", "skill", 0.0, "adjacent_attack_flat", "相邻（上下左右）的攻击建筑 +5。")
	_add("beacon", "灯塔", "special", 0.0, "adjacent_mult", "相邻（上下左右）的建筑 ×1.5。")
	_add("coral", "珊瑚礁", "special", 3.0, "range_flat", "周围 3×3 范围（含斜向）的其他建筑 +2。")
	_add("shield", "护盾塔", "skill", 3.0, "none", "提供护盾数值，本身没有位置效果。")


func _add(id: String, display_name: String, category: String, power: float, effect: String, desc: String) -> void:
	var b := BuildingData.new()
	b.category = category
	b.display_name = display_name
	b.base_power = power
	b.effect = effect
	b.effect_desc = desc
	_catalog.append(b)
	_by_id[id] = b


# ============================================================
# 界面搭建
# ============================================================

func _build_ui() -> void:
	var root := MarginContainer.new()
	root.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	root.add_theme_constant_override("margin_left", 22)
	root.add_theme_constant_override("margin_right", 22)
	root.add_theme_constant_override("margin_top", 20)
	root.add_theme_constant_override("margin_bottom", 20)
	add_child(root)

	var row := HBoxContainer.new()
	row.add_theme_constant_override("separation", 26)
	root.add_child(row)

	row.add_child(_build_side_panel())
	row.add_child(_build_board_area())


func _build_side_panel() -> PanelContainer:
	var side := PanelContainer.new()
	side.custom_minimum_size = Vector2(300.0, 0.0)
	var panel_style := StyleBoxFlat.new()
	panel_style.bg_color = Color("#0c1a22")
	panel_style.border_color = Color("#22404e")
	panel_style.set_border_width_all(1)
	panel_style.set_corner_radius_all(10)
	panel_style.set_content_margin_all(16)
	side.add_theme_stylebox_override("panel", panel_style)

	var vb := VBoxContainer.new()
	vb.add_theme_constant_override("separation", 9)
	side.add_child(vb)

	var title := Label.new()
	title.text = "建筑工具箱"
	title.add_theme_font_size_override("font_size", 19)
	vb.add_child(title)

	var tip := Label.new()
	tip.text = "点选建筑 → 点格子放置｜右键拆除"
	tip.add_theme_font_size_override("font_size", 12)
	tip.add_theme_color_override("font_color", Color("#7d99a6"))
	vb.add_child(tip)

	var pg := GridContainer.new()
	pg.columns = 2
	pg.add_theme_constant_override("h_separation", 6)
	pg.add_theme_constant_override("v_separation", 6)
	vb.add_child(pg)

	for i in _catalog.size():
		var b: BuildingData = _catalog[i]
		var btn := Button.new()
		btn.text = "%s %s" % [b.display_name, _fmt_power(b.base_power)]
		btn.custom_minimum_size = Vector2(0.0, 34.0)
		btn.tooltip_text = b.effect_desc
		btn.add_theme_color_override("font_color", _cat_color(b.category))
		btn.pressed.connect(_on_palette_pressed.bind(i))
		pg.add_child(btn)
		_palette_buttons.append(btn)

	vb.add_child(HSeparator.new())

	var preset_title := Label.new()
	preset_title.text = "快速组合（验证用）"
	preset_title.add_theme_font_size_override("font_size", 13)
	preset_title.add_theme_color_override("font_color", Color("#7d99a6"))
	vb.add_child(preset_title)

	var preset_row := HBoxContainer.new()
	preset_row.add_theme_constant_override("separation", 6)
	vb.add_child(preset_row)

	var p1 := Button.new()
	p1.text = "灯塔弩炮阵"
	p1.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	p1.pressed.connect(_apply_preset.bind(0))
	preset_row.add_child(p1)

	var p2 := Button.new()
	p2.text = "珊瑚渔场"
	p2.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	p2.pressed.connect(_apply_preset.bind(1))
	preset_row.add_child(p2)

	var gap := Control.new()
	gap.size_flags_vertical = Control.SIZE_EXPAND_FILL
	vb.add_child(gap)

	_stats_label = Label.new()
	_stats_label.add_theme_font_size_override("font_size", 15)
	vb.add_child(_stats_label)

	var clear_btn := Button.new()
	clear_btn.text = "清空木筏"
	clear_btn.pressed.connect(_clear_board)
	vb.add_child(clear_btn)

	return side


func _build_board_area() -> VBoxContainer:
	var vb := VBoxContainer.new()
	vb.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	vb.add_theme_constant_override("separation", 14)

	var center := CenterContainer.new()
	center.size_flags_vertical = Control.SIZE_EXPAND_FILL
	vb.add_child(center)

	var grid := GridContainer.new()
	grid.columns = GRID_SIZE
	grid.add_theme_constant_override("h_separation", 8)
	grid.add_theme_constant_override("v_separation", 8)
	center.add_child(grid)

	for i in CELL_COUNT:
		grid.add_child(_make_cell(i))

	_info_label = Label.new()
	_info_label.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	_info_label.custom_minimum_size = Vector2(0.0, 96.0)
	_info_label.vertical_alignment = VERTICAL_ALIGNMENT_TOP
	_info_label.add_theme_font_size_override("font_size", 14)
	vb.add_child(_info_label)

	return vb


func _make_cell(index: int) -> Panel:
	var cell := Panel.new()
	cell.custom_minimum_size = CELL_SIZE

	var sb := StyleBoxFlat.new()
	sb.bg_color = _col_bg_empty
	sb.border_color = _col_border_idle
	sb.set_border_width_all(2)
	sb.set_corner_radius_all(10)
	cell.add_theme_stylebox_override("panel", sb)
	_sb.append(sb)

	var margin := MarginContainer.new()
	margin.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	margin.add_theme_constant_override("margin_left", 8)
	margin.add_theme_constant_override("margin_right", 8)
	margin.add_theme_constant_override("margin_top", 8)
	margin.add_theme_constant_override("margin_bottom", 8)
	margin.mouse_filter = Control.MOUSE_FILTER_IGNORE
	cell.add_child(margin)

	var vb := VBoxContainer.new()
	vb.mouse_filter = Control.MOUSE_FILTER_IGNORE
	vb.add_theme_constant_override("separation", 0)
	margin.add_child(vb)

	var name_label := Label.new()
	name_label.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	name_label.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	name_label.add_theme_font_size_override("font_size", 13)
	vb.add_child(name_label)

	var power_label := Label.new()
	power_label.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	power_label.vertical_alignment = VERTICAL_ALIGNMENT_CENTER
	power_label.size_flags_vertical = Control.SIZE_EXPAND_FILL
	power_label.add_theme_font_size_override("font_size", 30)
	vb.add_child(power_label)

	var mod_label := Label.new()
	mod_label.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	mod_label.add_theme_font_size_override("font_size", 12)
	mod_label.add_theme_color_override("font_color", Color("#ffd166"))
	vb.add_child(mod_label)

	_name_labels.append(name_label)
	_power_labels.append(power_label)
	_mod_labels.append(mod_label)
	_cells.append(cell)

	cell.gui_input.connect(_on_cell_input.bind(index))
	cell.mouse_entered.connect(_on_cell_hover.bind(index, true))
	cell.mouse_exited.connect(_on_cell_hover.bind(index, false))

	return cell


# ============================================================
# 交互
# ============================================================

func _on_palette_pressed(index: int) -> void:
	_selected = -1 if _selected == index else index
	_refresh()


func _on_cell_input(event: InputEvent, index: int) -> void:
	var mb := event as InputEventMouseButton
	if mb == null or not mb.pressed:
		return
	if mb.button_index == MOUSE_BUTTON_LEFT:
		_grid[index] = _catalog[_selected] if _selected >= 0 else null
	elif mb.button_index == MOUSE_BUTTON_RIGHT:
		_grid[index] = null
	else:
		return
	_refresh()


func _on_cell_hover(index: int, entered: bool) -> void:
	if entered:
		_hover = index
		_refresh()
	elif _hover == index:
		_hover = -1
		_refresh()


func _apply_preset(kind: int) -> void:
	_grid.fill(null)
	_selected = -1
	if kind == 0:
		# 灯塔挂在中间，四角吃相邻倍率
		_place(4, "beacon")
		_place(1, "ballista")
		_place(3, "ballista")
		_place(5, "ballista")
		_place(7, "harpoon")
		_place(0, "ammo")
	else:
		_place(4, "coral")
		_place(0, "net")
		_place(2, "purifier")
		_place(6, "purifier")
		_place(8, "net")
	_refresh()


func _place(index: int, id: String) -> void:
	var b: BuildingData = _by_id.get(id)
	if b != null:
		_grid[index] = b


func _clear_board() -> void:
	_grid.fill(null)
	_refresh()


# ============================================================
# 位置效果结算
# ============================================================

## 读取格子：若该格处于预览状态，返回将要放下的建筑
func _grid_at(index: int) -> BuildingData:
	if index == _preview_index and _preview_building != null:
		return _preview_building
	return _grid[index]


## 返回 { flat: Array[float], mult: Array[float], total: Array[float] }
## 结算顺序：先叠固定加成，再乘倍率。
func _compute() -> Dictionary:
	var flat: Array[float] = []
	var mult: Array[float] = []
	flat.resize(CELL_COUNT)
	mult.resize(CELL_COUNT)
	flat.fill(0.0)
	mult.fill(1.0)

	for i in CELL_COUNT:
		var b: BuildingData = _grid_at(i)
		if b == null:
			continue
		match b.effect:
			"adjacent_attack_flat":
				for n in _neighbors(i):
					var target: BuildingData = _grid_at(n)
					if target != null and target.category == "attack":
						flat[n] = flat[n] + 5.0
			"adjacent_mult":
				for n in _neighbors(i):
					if _grid_at(n) != null:
						mult[n] = mult[n] * 1.5
			"range_flat":
				for c in _cells_in_range(i):
					if c != i and _grid_at(c) != null:
						flat[c] = flat[c] + 2.0

	var total: Array[float] = []
	total.resize(CELL_COUNT)
	for i in CELL_COUNT:
		var b2: BuildingData = _grid_at(i)
		if b2 == null:
			total[i] = 0.0
		else:
			total[i] = (b2.base_power + float(flat[i])) * float(mult[i])

	return {"flat": flat, "mult": mult, "total": total}


func _neighbors(index: int) -> Array[int]:
	var x: int = index % GRID_SIZE
	var y: int = index / GRID_SIZE
	var out: Array[int] = []
	if x > 0:
		out.append(index - 1)
	if x < GRID_SIZE - 1:
		out.append(index + 1)
	if y > 0:
		out.append(index - GRID_SIZE)
	if y < GRID_SIZE - 1:
		out.append(index + GRID_SIZE)
	return out


func _cells_in_range(index: int) -> Array[int]:
	var cx: int = index % GRID_SIZE
	var cy: int = index / GRID_SIZE
	var out: Array[int] = []
	for dy in [-1, 0, 1]:
		for dx in [-1, 0, 1]:
			var nx: int = cx + dx
			var ny: int = cy + dy
			if nx < 0 or ny < 0 or nx >= GRID_SIZE or ny >= GRID_SIZE:
				continue
			out.append(ny * GRID_SIZE + nx)
	return out


## 该格建筑会影响到的格子（用于高亮）
func _effect_targets(index: int) -> Array[int]:
	var out: Array[int] = []
	var b: BuildingData = _grid_at(index)
	if b == null:
		return out
	match b.effect:
		"adjacent_attack_flat", "adjacent_mult":
			for n in _neighbors(index):
				out.append(n)
		"range_flat":
			for c in _cells_in_range(index):
				if c != index:
					out.append(c)
	return out


## 有哪些建筑正在影响 focus 这一格
func _contributors(focus: int) -> PackedStringArray:
	var out: PackedStringArray = []
	for i in CELL_COUNT:
		if i == focus:
			continue
		var b: BuildingData = _grid_at(i)
		if b == null:
			continue
		if not _effect_targets(i).has(focus):
			continue
		match b.effect:
			"adjacent_attack_flat":
				out.append("%s +5" % b.display_name)
			"adjacent_mult":
				out.append("%s ×1.5" % b.display_name)
			"range_flat":
				out.append("%s +2" % b.display_name)
	return out


# ============================================================
# 界面刷新
# ============================================================

func _refresh() -> void:
	# 选中建筑 + 悬停空格 = 该格进入预览状态（不写入 _grid）
	_preview_index = -1
	_preview_building = null
	if _selected >= 0 and _hover >= 0 and _grid[_hover] == null:
		_preview_index = _hover
		_preview_building = _catalog[_selected]

	var result: Dictionary = _compute()
	var flat: Array = result["flat"]
	var mult: Array = result["mult"]
	var total: Array = result["total"]

	var focus: int = _hover
	var targets: Array[int] = []
	var sources: Array[int] = []
	if focus >= 0 and _grid_at(focus) != null:
		targets = _effect_targets(focus)
		for i in CELL_COUNT:
			if i != focus and _effect_targets(i).has(focus):
				sources.append(i)

	for i in CELL_COUNT:
		var b: BuildingData = _grid_at(i)
		var sb: StyleBoxFlat = _sb[i]

		sb.bg_color = _col_bg_empty if b == null else _col_bg_empty.lerp(_cat_color(b.category), 0.32)

		if i == focus:
			sb.border_color = _col_border_focus
			sb.set_border_width_all(3)
		elif targets.has(i) or sources.has(i):
			sb.border_color = _col_border_link
			sb.set_border_width_all(3)
		else:
			sb.border_color = _col_border_idle
			sb.set_border_width_all(2)

		if b == null:
			_name_labels[i].text = "空"
			_name_labels[i].add_theme_color_override("font_color", Color("#3f5a66"))
			_power_labels[i].text = ""
			_mod_labels[i].text = ""
			continue

		_name_labels[i].text = b.display_name
		_name_labels[i].add_theme_color_override("font_color", Color("#cfe3ec"))
		_power_labels[i].text = _fmt_power(float(total[i]))
		var diff: float = float(total[i]) - b.base_power
		if diff > 0.01:
			_power_labels[i].add_theme_color_override("font_color", Color("#ffd166"))
		elif diff < -0.01:
			_power_labels[i].add_theme_color_override("font_color", Color("#e2705f"))
		else:
			_power_labels[i].add_theme_color_override("font_color", Color("#e8f4f8"))
		_mod_labels[i].text = _mod_text(flat[i], mult[i])

	_info_label.text = _describe(focus, flat, mult, total)
	_stats_label.text = _stats_text(total)
	_refresh_palette_state()


func _refresh_palette_state() -> void:
	for i in _palette_buttons.size():
		var btn: Button = _palette_buttons[i]
		btn.modulate = Color(1, 1, 1) if i == _selected else Color(0.66, 0.72, 0.76)


func _mod_text(flat_value: float, mult_value: float) -> String:
	var parts: PackedStringArray = []
	if flat_value != 0.0:
		parts.append("+%d" % int(flat_value))
	if mult_value != 1.0:
		parts.append("×%.1f" % mult_value)
	return " ".join(parts)


func _describe(focus: int, flat: Array, mult: Array, total: Array) -> String:
	var default_hint := "把左边任一建筑放到格子上试试：相邻／范围的加成立刻反映在数字上。"
	if focus < 0:
		return default_hint

	var b: BuildingData = _grid_at(focus)
	if b == null:
		return "%d 号格 · 空格\n%s" % [focus + 1, default_hint]

	var head: String = "【预览】" if focus == _preview_index else ""
	head += "%d 号格 · %s" % [focus + 1, b.display_name]

	var calc: String = "基础 %d" % int(b.base_power)
	if float(flat[focus]) != 0.0:
		calc += "  +%d" % int(flat[focus])
	if float(mult[focus]) != 1.0:
		calc += "  ×%.1f" % mult[focus]
	calc += "  = %d" % int(round(total[focus]))

	var text: String = "%s\n%s\n%s" % [head, calc, b.effect_desc]
	var who: PackedStringArray = _contributors(focus)
	if who.size() > 0:
		text += "\n受到：%s" % "，".join(who)
	return text


func _stats_text(total: Array) -> String:
	var atk: float = 0.0
	var res: float = 0.0
	var sup: float = 0.0
	var used: int = 0
	for i in CELL_COUNT:
		var b: BuildingData = _grid_at(i)
		if b == null:
			continue
		used += 1
		match b.category:
			"attack":
				atk += float(total[i])
			"resource":
				res += float(total[i])
			_:
				sup += float(total[i])
	return "攻击 %d   资源 %d   辅助 %d\n已用格子 %d / %d" % [
		int(round(atk)), int(round(res)), int(round(sup)), used, CELL_COUNT
	]


func _fmt_power(value: float) -> String:
	if value <= 0.0:
		return "—"
	return "%d" % int(round(value))


func _cat_color(category: String) -> Color:
	match category:
		"attack":
			return _col_attack
		"resource":
			return _col_resource
		"skill":
			return _col_skill
		_:
			return _col_special
