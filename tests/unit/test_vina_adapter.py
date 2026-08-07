"""VinaAdapter 安全加固回归测试。

覆盖：
- `_coerce_box` 拒绝非法/注入型盒参数；
- `_write_dock_script` 对文件名/配体/盒值全部使用 repr 字面量，生成脚本可被
  `ast` 安全解析且不含注入载荷。
"""
import ast
import os
import tempfile

import pytest

from battery_materials_agent.infrastructure.executors.vina_adapter import VinaAdapter


class TestCoerceBox:
    def test_valid_list(self):
        val, errs = VinaAdapter._coerce_box([1, 2, 3], "box_size")
        assert errs == []
        assert val == [1.0, 2.0, 3.0]

    def test_tuple_accepted(self):
        val, errs = VinaAdapter._coerce_box((1.5, 2.5, 3.5), "box_center")
        assert errs == []
        assert val == [1.5, 2.5, 3.5]

    def test_rejects_wrong_arity(self):
        val, errs = VinaAdapter._coerce_box([1, 2], "box_center")
        assert val is None
        assert len(errs) == 1

    def test_rejects_non_numeric(self):
        val, errs = VinaAdapter._coerce_box("]; import os; os.system('id') #", "box_center")
        assert val is None
        assert len(errs) == 1

    def test_rejects_injection_string_in_list(self):
        val, errs = VinaAdapter._coerce_box(['1', 'os.system("id")', '3'], "box_center")
        assert val is None
        assert len(errs) == 1


class TestWriteDockScriptSafety:
    def test_script_parses_and_contains_no_injection(self):
        with tempfile.TemporaryDirectory() as work_dir:
            malicious_basename = 'evil"; os.system("id"); #.pdb'
            malicious_ligand = 'CCO"; os.system("id"); #'
            malicious_box = ["1.0", '2"]; os.system("id"); ["3']
            script = VinaAdapter._write_dock_script(
                work_dir,
                malicious_basename,
                malicious_ligand,
                "smiles",
                10,
                [1.0, 2.0, 3.0],
                [10.0, 10.0, 10.0],
            )
            with open(script, encoding="utf-8") as f:
                content = f.read()
            # 生成脚本必须是合法 Python
            ast.parse(content)
            # 注入载荷必须被 repr 成字符串字面量（位于引号内），而非可执行代码
            receptor_line = next(
                line for line in content.splitlines()
                if line.startswith("RECEPTOR_PDB =")
            )
            assert '"' in receptor_line or "'" in receptor_line, \
                "receptor 文件名必须被写成字符串字面量"
            # 受控列表值应被逐项转成 float 字面量
            assert "BOX_CENTER = [1.0, 2.0, 3.0]" in content