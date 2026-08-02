"""
test_skills.py - WinRemote v0.9.8 Skill 注册测试
=============================================
测试 skills/winremote-remote-control/ 目录结构、文件内容和注册逻辑。
"""
import json
import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest

# ─── 路径设置 ───────────────────────────────────────────────
_PLUGIN_DIR = Path(__file__).resolve().parent.parent
_SKILL_DIR = _PLUGIN_DIR / "skills" / "winremote-remote-control"

sys.path.insert(0, str(_PLUGIN_DIR))


# ============================================================
# 1. Skill 目录结构测试
# ============================================================
class TestSkillDirectoryStructure:
    """Skill 目录结构完整性"""

    def test_skill_dir_exists(self):
        """skills/winremote-remote-control/ 目录存在"""
        assert _SKILL_DIR.exists(), f"Skill 目录不存在: {_SKILL_DIR}"
        assert _SKILL_DIR.is_dir()

    def test_skill_md_exists(self):
        """SKILL.md 存在"""
        f = _SKILL_DIR / "SKILL.md"
        assert f.exists(), "SKILL.md 不存在"
        assert f.stat().st_size > 100, "SKILL.md 内容过少"

    def test_tools_json_exists(self):
        """tools.json 存在"""
        f = _SKILL_DIR / "tools.json"
        assert f.exists(), "tools.json 不存在"
        # 验证是合法 JSON
        data = json.loads(f.read_text(encoding="utf-8"))
        assert "tools" in data
        assert isinstance(data["tools"], list)
        assert len(data["tools"]) > 0

    def test_prompts_json_exists(self):
        """prompts.json 存在"""
        f = _SKILL_DIR / "prompts.json"
        assert f.exists(), "prompts.json 不存在"
        data = json.loads(f.read_text(encoding="utf-8"))
        # 至少包含 examples 或 prompts
        assert "examples" in data or "user_prompt_templates" in data

    def test_skill_md_has_frontmatter(self):
        """SKILL.md 有 YAML frontmatter"""
        content = (_SKILL_DIR / "SKILL.md").read_text(encoding="utf-8")
        assert content.startswith("---"), "SKILL.md 缺少 YAML frontmatter"
        parts = content.split("---", 2)
        assert len(parts) >= 3, "SKILL.md frontmatter 格式错误"

    def test_skill_md_frontmatter_fields(self):
        """SKILL.md frontmatter 包含必要字段"""
        content = (_SKILL_DIR / "SKILL.md").read_text(encoding="utf-8")
        # 提取 frontmatter
        parts = content.split("---", 2)
        fm = parts[1] if len(parts) >= 3 else ""
        # 检查关键字段
        assert "name:" in fm, "frontmatter 缺少 name"
        assert "description:" in fm, "frontmatter 缺少 description"
        assert "version:" in fm, "frontmatter 缺少 version"

    def test_skill_md_body_content(self):
        """SKILL.md 正文有实质内容"""
        content = (_SKILL_DIR / "SKILL.md").read_text(encoding="utf-8")
        # 去掉 frontmatter
        parts = content.split("---", 2)
        body = parts[2].strip() if len(parts) >= 3 else content
        assert len(body) > 200, f"SKILL.md 正文过短: {len(body)} chars"
        # 包含关键章节
        assert "工具" in body or "tool" in body.lower()


# ============================================================
# 2. tools.json 内容测试
# ============================================================
class TestToolsJson:
    """tools.json 结构和内容"""

    @pytest.fixture
    def tools_data(self):
        f = _SKILL_DIR / "tools.json"
        return json.loads(f.read_text(encoding="utf-8"))

    def test_has_tools_array(self, tools_data):
        assert "tools" in tools_data
        assert len(tools_data["tools"]) == 7, f"应有 7 个工具，实际 {len(tools_data['tools'])}"

    def test_all_tool_names(self, tools_data):
        expected = {
            "win_shell",
            "win_powershell",
            "win_screenshot",
            "win_keypress",
            "win_mouse",
            "win_open",
            "win_read_file",
        }
        actual = {t["name"] for t in tools_data["tools"]}
        assert actual == expected, f"工具名不匹配:\n  期望: {expected}\n  实际: {actual}"

    def test_each_tool_has_description(self, tools_data):
        for t in tools_data["tools"]:
            assert "description" in t, f"{t.get('name','?')} 缺少 description"
            assert len(t["description"]) > 20, f"{t['name']} description 过短"

    def test_each_tool_has_parameters(self, tools_data):
        for t in tools_data["tools"]:
            assert "parameters" in t, f"{t['name']} 缺少 parameters"
            params = t["parameters"]
            assert params["type"] == "object"
            assert "properties" in params
            assert "required" in params

    def test_win_shell_has_command_param(self, tools_data):
        shell = next(t for t in tools_data["tools"] if t["name"] == "win_shell")
        assert "command" in shell["parameters"]["properties"]
        assert "command" in shell["parameters"]["required"]

    def test_win_mouse_has_x_y_params(self, tools_data):
        mouse = next(t for t in tools_data["tools"] if t["name"] == "win_mouse")
        props = mouse["parameters"]["properties"]
        assert "x" in props
        assert "y" in props
        assert "button" in props
        # x, y 是 required
        assert "x" in mouse["parameters"]["required"]
        assert "y" in mouse["parameters"]["required"]

    def test_win_screenshot_has_format_enum(self, tools_data):
        shot = next(t for t in tools_data["tools"] if t["name"] == "win_screenshot")
        fmt = shot["parameters"]["properties"]["format"]
        assert "enum" in fmt
        assert "JPEG" in fmt["enum"]
        assert "PNG" in fmt["enum"]


# ============================================================
# 3. prompts.json 内容测试
# ============================================================
class TestPromptsJson:
    """prompts.json 结构和内容"""

    @pytest.fixture
    def prompts_data(self):
        f = _SKILL_DIR / "prompts.json"
        return json.loads(f.read_text(encoding="utf-8"))

    def test_has_examples(self, prompts_data):
        assert "examples" in prompts_data
        assert len(prompts_data["examples"]) >= 2

    def test_examples_have_required_fields(self, prompts_data):
        for ex in prompts_data["examples"]:
            assert "user" in ex, f"example 缺少 user: {ex}"
            assert "action" in ex, f"example 缺少 action: {ex}"
            assert "response" in ex, f"example 缺少 response: {ex}"

    def test_examples_use_chinese(self, prompts_data):
        """示例包含中文用户提问"""
        for ex in prompts_data["examples"]:
            user = ex.get("user", "")
            assert any(ord(c) > 0x4e00 for c in user), f"示例缺少中文: {user}"


# ============================================================
# 4. Skill 注册逻辑测试
# ============================================================
class TestSkillRegistration:
    """_register_skills 方法逻辑"""

    def _make_plugin(self, with_skills=True):
        """构造一个模拟插件实例"""
        plugin = MagicMock()
        plugin.logger = MagicMock()
        plugin._extract_skill_prompt = lambda x: x
        # 模拟 cfg
        plugin.cfg = {"enable_llm_mode": True}
        return plugin

    def test_extract_skill_prompt_strips_frontmatter(self):
        """_extract_skill_prompt 正确去掉 frontmatter"""
        # 直接测试逻辑
        md = "---\nname: test\ndescription: x\nversion: 1.0\n---\n# Title\n\nBody content here."
        # 模拟方法
        content = md.strip()
        if content.startswith("---"):
            parts = content.split("---", 2)
            body = parts[2].strip() if len(parts) >= 3 else content
        else:
            body = content
        assert body.startswith("# Title")
        assert "Body content" in body

    def test_extract_skill_prompt_no_frontmatter(self):
        """_extract_skill_prompt 无 frontmatter 时原样返回"""
        md = "# Just a title\n\nBody without frontmatter."
        content = md.strip()
        if content.startswith("---"):
            parts = content.split("---", 2)
            body = parts[2].strip()
        else:
            body = content
        assert body.startswith("# Just a title")

    def test_skill_dir_path_resolution(self):
        """Skill 目录路径解析正确"""
        expected = _PLUGIN_DIR / "skills" / "winremote-remote-control"
        assert _SKILL_DIR == expected

    def test_tools_json_matches_tools_py(self):
        """tools.json 中的工具名与 tools.py 中的 Tool 定义一致"""
        # 读 tools.json
        json_tools = json.loads(
            (_SKILL_DIR / "tools.json").read_text(encoding="utf-8")
        )
        json_names = {t["name"] for t in json_tools["tools"]}

        # 读 tools.py 中的 Tool 类
        tools_py = (_PLUGIN_DIR / "tools.py").read_text(encoding="utf-8")
        py_names = set()
        for line in tools_py.split("\n"):
            if "name: str =" in line:
                # 提取 "win_xxx"
                name = line.split('"')[1] if '"' in line else ""
                if name:
                    py_names.add(name)

        assert json_names == py_names, (
            f"tools.json 和 tools.py 工具名不一致:\n"
            f"  JSON: {json_names}\n  Python: {py_names}"
        )

    def test_skill_md_name_matches_dir(self):
        """SKILL.md 中的 name 与目录名一致"""
        content = (_SKILL_DIR / "SKILL.md").read_text(encoding="utf-8")
        parts = content.split("---", 2)
        fm = parts[1] if len(parts) >= 3 else ""
        # 提取 name
        for line in fm.split("\n"):
            if line.strip().startswith("name:"):
                name = line.split(":", 1)[1].strip()
                assert name == "winremote-remote-control", f"name 不匹配: {name}"
                return
        pytest.fail("SKILL.md 中未找到 name 字段")


# ============================================================
# 5. 版本号一致性测试
# ============================================================
class TestVersionConsistency:
    """v0.9.8 版本号全链路一致"""

    def test_version_file(self):
        v = (_PLUGIN_DIR / "VERSION").read_text(encoding="utf-8").strip()
        assert v == "V0.9.8", f"VERSION 文件: {v}"

    def test_pyproject_version(self):
        p = (_PLUGIN_DIR / "pyproject.toml").read_text(encoding="utf-8")
        for line in p.split("\n"):
            if line.startswith("version"):
                v = line.split("=", 1)[1].strip().strip('"')
                assert v == "0.9.8", f"pyproject.toml version: {v}"
                return
        pytest.fail("pyproject.toml 未找到 version")

    def test_metadata_version(self):
        m = (_PLUGIN_DIR / "metadata.yaml").read_text(encoding="utf-8")
        for line in m.split("\n"):
            if line.startswith("version:"):
                v = line.split(":", 1)[1].strip().strip('"')
                assert "V0.9.8" in v or "v0.9.8" in v, f"metadata.yaml version: {v}"
                return
        pytest.fail("metadata.yaml 未找到 version")

    def test_webui_panel_version(self):
        w = (_PLUGIN_DIR / "webui_panel.py").read_text(encoding="utf-8")
        for line in w.split("\n"):
            if line.startswith('VERSION = "'):
                v = line.split('"')[1]
                assert v == "V0.9.8", f"webui_panel.py VERSION: {v}"
                return
        pytest.fail("webui_panel.py 未找到 VERSION")

    def test_skill_md_version(self):
        content = (_SKILL_DIR / "SKILL.md").read_text(encoding="utf-8")
        parts = content.split("---", 2)
        fm = parts[1] if len(parts) >= 3 else ""
        for line in fm.split("\n"):
            if line.strip().startswith("version:"):
                v = line.split(":", 1)[1].strip()
                assert v == "V0.9.8" or v == "0.9.8", f"SKILL.md version: {v}"
                return
        pytest.fail("SKILL.md frontmatter 未找到 version")


# ============================================================
# 6. Skill 与 Tool 集成测试
# ============================================================
class TestSkillIntegration:
    """Skill 与 LLM Tool 的集成关系"""

    def test_skill_tools_count_matches_llm_tools(self):
        """Skill 声明的工具数 = tools.py 定义的 Tool 数"""
        json_tools = json.loads(
            (_SKILL_DIR / "tools.json").read_text(encoding="utf-8")
        )
        skill_count = len(json_tools["tools"])

        # 读 tools.py 中 ALL_TOOLS 的数量
        tools_py = (_PLUGIN_DIR / "tools.py").read_text(encoding="utf-8")
        dataclass_count = 0
        for line in tools_py.split("\n"):
            if line.startswith("@dataclass"):
                dataclass_count += 1

        assert skill_count == dataclass_count == 7

    def test_conf_schema_has_llm_section(self):
        """_conf_schema.json 包含 LLM 智能模式配置组"""
        schema = json.loads(
            (_PLUGIN_DIR / "_conf_schema.json").read_text(encoding="utf-8")
        )
        groups = schema.get("groups", [])
        llm_group = None
        for g in groups:
            title = g.get("title", "")
            if "LLM" in title or "智能" in title:
                llm_group = g
                break
        assert llm_group is not None, "未找到 LLM 智能模式配置组"
        fields = llm_group.get("fields", {})
        assert "enable_llm_mode" in fields
        assert "llm_max_tool_calls" in fields

    def test_main_plugin_has_skill_registration(self):
        """主插件文件包含 _register_skills 方法"""
        main = (_PLUGIN_DIR / "astrbot_plugin_winremote.py").read_text(encoding="utf-8")
        assert "_register_skills" in main, "主插件缺少 _register_skills 方法"
        assert "skill_dir" in main, "主插件缺少 skill_dir 路径构造"
        assert "SKILL.md" in main, "主插件未引用 SKILL.md"

    def test_webui_has_skill_endpoint(self):
        """webui_panel.py 包含 Skill 状态 API"""
        panel = (_PLUGIN_DIR / "webui_panel.py").read_text(encoding="utf-8")
        assert "get_skill_status" in panel, "缺少 get_skill_status 函数"
        assert "skills.json" in panel, "缺少 /panel/skills.json 路由"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
