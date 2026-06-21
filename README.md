# Fluent Solution 参数化建模模板

本仓库提供一个轻量级 Python 模板，用于为 ANSYS Fluent Solution 批量生成和运行参数化工况。
模板优先使用 Fluent 的 named expressions 来承载参数，因此可以把网格、边界和求解设置保留在
基准 `*.cas.h5` 文件中，只在批处理时替换参数值。

## 文件说明

- `fluent_parametric_solution.py`：参数矩阵展开、journal 生成、PyFluent 启动与执行入口。
- `examples/parameters.json`：示例参数配置，可直接复制后改成你的 Fluent 工程参数。

## 快速开始

1. 在 Fluent 中准备一个基准 case，例如 `baseline.cas.h5`。
2. 在 Fluent 中创建 named expressions，例如 `inlet_velocity_expr`、`outlet_pressure_expr`。
3. 修改 `examples/parameters.json` 中的 `case_file`、`parameters` 和 `named_expressions`。
4. 先生成 journal 检查命令：

   ```bash
   python fluent_parametric_solution.py --config examples/parameters.json --dry-run
   ```

5. 在安装了 PyFluent 和 ANSYS Fluent 的环境中实际运行：

   ```bash
   python fluent_parametric_solution.py --config examples/parameters.json --output-dir runs
   ```

## 配置结构

```json
{
  "case_file": "baseline.cas.h5",
  "launch": {
    "precision": "double",
    "processor_count": 4,
    "mode": "solver"
  },
  "parameters": {
    "inlet_velocity": [5.0, 10.0, 15.0],
    "outlet_pressure": [0.0]
  },
  "named_expressions": {
    "inlet_velocity_expr": "inlet_velocity",
    "outlet_pressure_expr": "outlet_pressure"
  },
  "solution": {
    "initialize": true,
    "iterations": 500
  }
}
```

- `parameters` 会自动展开为笛卡尔积工况。
- 如果你不想用笛卡尔积，也可以改用 `design_points` 显式定义每个工况。
- `launch` 会原样传给 `ansys.fluent.core.launch_fluent(...)`。
- 每个工况会生成独立的 `*.jou`、`*.cas.h5` 输出路径，并在输出目录写入 `design_points.csv`。

## 适配你的模型

不同 Fluent 版本和模型的 TUI 命令可能略有差异。推荐做法是：

1. 先在 Fluent GUI 中完成一次手动设置。
2. 导出或录制 journal。
3. 把录制到的关键 TUI 命令替换到 `render_journal()` 中。
4. 保留本模板的参数展开、输出目录和 manifest 逻辑。

如果你的参数属于几何或网格阶段，而不是 Solution 阶段，建议在 Workbench、SpaceClaim 或 Meshing
阶段先生成多个 case 文件，再把生成的 case 文件作为本脚本的输入批量求解。
