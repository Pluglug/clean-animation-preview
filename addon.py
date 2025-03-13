import importlib
import inspect
import os
import pkgutil
import re
import sys
import traceback
from collections import defaultdict
from typing import Dict, List, Pattern, Set

import bpy

from .debug_utils import Log, DBG_INIT

# Global Settings
BACKGROUND = False
VERSION = (0, 0, 0)
BL_VERSION = (0, 0, 0)

# Addon Info
ADDON_PATH = os.path.dirname(os.path.abspath(__file__))
ADDON_ID = os.path.basename(ADDON_PATH)
TEMP_PREFS_ID = f"addon_{ADDON_ID}"
ADDON_PREFIX = "".join([s[0] for s in re.split(r"[_-]", ADDON_ID)]).upper()
ADDON_PREFIX_PY = ADDON_PREFIX.lower()

# Module Management
MODULE_NAMES: List[str] = []
MODULE_PATTERNS: List[Pattern] = []
ICON_ENUM_ITEMS = (
    bpy.types.UILayout.bl_rna.functions["prop"].parameters["icon"].enum_items
)

# Class Cache
_class_cache: List[bpy.types.bpy_struct] = None


# Preferences
def uprefs(context: bpy.types.Context = bpy.context) -> bpy.types.Preferences:
    preferences = getattr(context, "preferences", None)
    if preferences is not None:
        return preferences
    raise AttributeError("Failed to get preferences")


def prefs(context: bpy.types.Context = bpy.context) -> bpy.types.AddonPreferences:
    user_prefs = uprefs(context)
    addon_prefs = user_prefs.addons.get(ADDON_ID)
    if addon_prefs is not None:
        return addon_prefs.preferences
    raise KeyError(f"Failed to get addon preferences")


# Addon Initialization
def init_addon(
    module_patterns: List[str],
    use_reload: bool = False,
    background: bool = False,
    prefix: str = None,
    prefix_py: str = None,
    force_order: List[str] = None,
) -> None:
    global VERSION, BL_VERSION, ADDON_PREFIX, ADDON_PREFIX_PY, _class_cache

    _class_cache = None
    module = sys.modules[ADDON_ID]
    VERSION = module.bl_info.get("version", VERSION)
    BL_VERSION = module.bl_info.get("blender", BL_VERSION)

    if prefix:
        ADDON_PREFIX = prefix
    if prefix_py:
        ADDON_PREFIX_PY = prefix_py

    MODULE_PATTERNS[:] = [
        re.compile(f"^{ADDON_ID}\.{p.replace('*', '.*')}$") for p in module_patterns
    ]

    MODULE_PATTERNS.append(re.compile(f"^{ADDON_ID}$"))

    module_names = list(_collect_module_names())

    for module_name in module_names:
        try:
            if use_reload and module_name in sys.modules:
                importlib.reload(sys.modules[module_name])
            else:
                importlib.import_module(module_name)
        except Exception as e:
            Log.error(f"Failed to load module {module_name}: {str(e)}")

    if force_order:
        Log.header("Using forced module load order")
        sorted_modules = _resolve_forced_order(force_order, module_names)
    else:
        sorted_modules = _sort_modules(module_names)

    MODULE_NAMES[:] = sorted_modules

    if DBG_INIT:
        Log.header("Final module load order")
        for i, mod in enumerate(MODULE_NAMES, 1):
            short = short_name(mod)
            Log.info(f"{i:2d}. {short}")


# Module Sorting
def _resolve_forced_order(force_order: List[str], module_names: List[str]) -> List[str]:
    processed_order = []
    for mod in force_order:
        if not mod.startswith(ADDON_ID):
            full_name = f"{ADDON_ID}.{mod}"
        else:
            full_name = mod

        if full_name in module_names:
            processed_order.append(full_name)
        else:
            Log.warn(f"Warning: {full_name} not found in module names")

    remaining = [m for m in module_names if m not in processed_order]
    return processed_order + remaining


def _analyze_dependencies(module_names: List[str]) -> Dict[str, Set[str]]:
    import_graph = _analyze_imports(module_names)

    graph = defaultdict(set)
    pdtype = bpy.props._PropertyDeferred

    for mod_name, deps in import_graph.items():
        graph[mod_name].update(deps)

    for mod_name in module_names:
        mod = sys.modules.get(mod_name)
        if not mod:
            continue

        for _, cls in inspect.getmembers(mod, _is_bpy_class):
            for prop in getattr(cls, "__annotations__", {}).values():
                if isinstance(prop, pdtype) and prop.function in [
                    bpy.props.PointerProperty,
                    bpy.props.CollectionProperty,
                ]:
                    dep_cls = prop.keywords.get("type")
                    if not dep_cls:
                        continue

                    dep_mod = dep_cls.__module__

                    if dep_mod == mod_name:
                        continue

                    if dep_mod in module_names:
                        graph[dep_mod].add(mod_name)

        if hasattr(mod, "DEPENDS_ON"):
            for dep in mod.DEPENDS_ON:
                dep_full = f"{ADDON_ID}.{dep}"
                if dep_full in module_names:
                    graph[dep_full].add(mod_name)

    if DBG_INIT:
        Log.header("Dependency details")
        for mod, deps in sorted(graph.items()):
            if deps:
                Log.info(f"{mod} depends on:")
                for d in sorted(deps):
                    Log.info(f"  → {d}")

    return graph


def _analyze_imports(module_names: List[str]) -> Dict[str, Set[str]]:
    import ast

    graph = defaultdict(set)

    for mod_name in module_names:
        mod = sys.modules.get(mod_name)
        if not mod:
            continue

        if not hasattr(mod, "__file__") or not mod.__file__:
            continue

        try:
            with open(mod.__file__, "r", encoding="utf-8") as f:
                content = f.read()

            tree = ast.parse(content)

            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    for name in node.names:
                        imported_name = name.name

                        if imported_name.startswith(ADDON_ID):
                            graph[mod_name].add(imported_name)

                        else:
                            parts = imported_name.split(".")
                            for i in range(1, len(parts)):
                                prefix = ".".join(parts[: i + 1])
                                full_name = f"{ADDON_ID}.{prefix}"
                                if full_name in module_names:
                                    graph[mod_name].add(full_name)

                elif isinstance(node, ast.ImportFrom):
                    if node.module:
                        module_path = node.module

                        if node.level > 0:
                            parent_parts = mod_name.split(".")
                            if node.level > len(parent_parts) - 1:
                                continue
                            base_path = ".".join(parent_parts[: -node.level])
                            if module_path:
                                module_path = f"{base_path}.{module_path}"
                            else:
                                module_path = base_path

                        full_import = f"{module_path}"
                        if not full_import.startswith(ADDON_ID) and module_path:
                            full_import = f"{ADDON_ID}.{module_path}"

                        if full_import in module_names:
                            graph[mod_name].add(full_import)

                        for name in node.names:
                            if name.name != "*":
                                full_submodule = f"{full_import}.{name.name}"
                                if full_submodule in module_names:
                                    graph[mod_name].add(full_submodule)

        except Exception as e:
            Log.error(f"Import analysis error ({mod_name}): {str(e)}")

    return graph


def _sort_modules(module_names: List[str]) -> List[str]:
    graph = _analyze_dependencies(module_names)

    filtered_graph = {
        n: {d for d in deps if d in module_names}
        for n, deps in graph.items()
        if n in module_names
    }

    base_module = ADDON_ID
    for mod_name in module_names:
        if mod_name == base_module and base_module not in filtered_graph:
            filtered_graph[base_module] = set()

    for mod_name in module_names:
        if mod_name not in filtered_graph:
            filtered_graph[mod_name] = set()

    try:
        sorted_modules = _topological_sort(filtered_graph)

        if DBG_INIT:
            Log.header("Module load order")
            for idx, mod in enumerate(sorted_modules):
                deps = filtered_graph.get(mod, set())
                dep_str = ", ".join(short_name(d) for d in deps) if deps else "-"
                Log.info(f"{idx+1:2d}. {short_name(mod)} (Dependencies: {dep_str})")

            try:
                mermaid = _visualize_dependencies(graph)

                debug_dir = os.path.join(ADDON_PATH, "debug")
                os.makedirs(debug_dir, exist_ok=True)
                viz_path = os.path.join(debug_dir, "module_dependencies.mmd")
                with open(viz_path, "w", encoding="utf-8") as f:
                    f.write(mermaid)
                Log.info(f"Dependency graph generated: {viz_path}")
            except Exception as e:
                Log.error(f"Dependency graph generation error: {str(e)}")

    except ValueError as e:
        Log.warn(f"Warning: {str(e)}")
        Log.warn("Using alternative sort method to resolve circular dependencies...")
        sorted_modules = _alternative_sort(filtered_graph, module_names)

    remaining = [m for m in module_names if m not in sorted_modules]
    if remaining:
        Log.info(f"\nUnprocessed modules added: {', '.join(remaining)}")
        sorted_modules.extend(remaining)

    return sorted_modules


def short_name(module_name: str) -> str:
    prefix = f"{ADDON_ID}."
    return module_name[len(prefix) :] if module_name.startswith(prefix) else module_name


def _topological_sort(graph: Dict[str, List[str]]) -> List[str]:
    in_degree = defaultdict(int)
    for node in graph:
        for neighbor in graph[node]:
            in_degree[neighbor] += 1

    queue = [node for node in graph if in_degree[node] == 0]
    sorted_order = []

    while queue:
        node = queue.pop(0)
        sorted_order.append(node)

        for neighbor in graph.get(node, []):
            in_degree[neighbor] -= 1
            if in_degree[neighbor] == 0:
                queue.append(neighbor)

    if len(sorted_order) != len(graph):
        cyclic = set(graph.keys()) - set(sorted_order)
        raise ValueError(f"Cyclic dependency detected: {', '.join(cyclic)}")

    return list(reversed(sorted_order))


def _alternative_sort(graph: Dict[str, Set[str]], module_names: List[str]) -> List[str]:
    try:
        cycles = _detect_cycles(graph)
        if cycles:
            Log.header("Detected cycles")
            for i, cycle in enumerate(cycles, 1):
                Log.warn(
                    f"Cycle {i}: {' → '.join(short_name(m) for m in cycle)} → {short_name(cycle[0])}"
                )
    except Exception as e:
        Log.error(f"Cycle detection error: {str(e)}")
        cycles = []

    base_priority = {
        ADDON_ID: 0,
    }

    outdegree = {node: len(deps) for node, deps in graph.items()}

    priority_groups = defaultdict(list)

    for mod in module_names:
        if mod in base_priority:
            priority = base_priority[mod]
        elif ".utils." in mod or mod.endswith(".utils"):
            priority = 1
        elif ".core." in mod or mod.endswith(".core"):
            priority = 2
        else:
            priority = 10 + outdegree.get(mod, 0)

        priority_groups[priority].append(mod)

    result = []
    for priority in sorted(priority_groups.keys()):
        result.extend(sorted(priority_groups[priority]))

    return result


def _detect_cycles(graph: Dict[str, Set[str]]) -> List[List[str]]:
    visited = set()
    stack = []
    on_stack = set()
    index_map = {}
    low_link = {}
    index = 0
    cycles = []

    def strong_connect(node):
        nonlocal index
        index_map[node] = index
        low_link[node] = index
        index += 1
        stack.append(node)
        on_stack.add(node)
        visited.add(node)

        for neighbor in graph.get(node, []):
            if neighbor not in visited:
                strong_connect(neighbor)
                low_link[node] = min(low_link[node], low_link[neighbor])
            elif neighbor in on_stack:
                low_link[node] = min(low_link[node], index_map[neighbor])

        if low_link[node] == index_map[node]:
            component = []
            while True:
                w = stack.pop()
                on_stack.remove(w)
                component.append(w)
                if w == node:
                    break

            if len(component) > 1:
                cycles.append(component)

    for node in graph:
        if node not in visited:
            strong_connect(node)

    return cycles


def _visualize_dependencies(graph: Dict[str, Set[str]], file_path: str = None) -> str:
    all_modules = set(graph.keys())
    for deps in graph.values():
        all_modules.update(deps)

    edges = []
    for module, deps in graph.items():
        for dep in deps:
            edges.append((module, dep))

    prefix_len = len(f"{ADDON_ID}.")
    short_names = {
        mod: mod[prefix_len:] if mod.startswith(f"{ADDON_ID}.") else mod
        for mod in all_modules
    }

    mermaid = "---\n"
    mermaid += "config:\n"
    mermaid += "  theme: default\n"
    mermaid += "  flowchart:\n"
    mermaid += "    curve: basis\n"
    mermaid += "---\n"
    mermaid += "flowchart TD\n"

    for module in sorted(all_modules):
        short = short_names[module]
        node_id = short.replace(".", "_")

        if "." not in short:
            mermaid += f"    {node_id}[{short}]\n"
        else:
            mermaid += f"    {node_id}({short})\n"

    for src, dst in edges:
        src_id = short_names[src].replace(".", "_")
        dst_id = short_names[dst].replace(".", "_")
        mermaid += f"    {src_id} --> {dst_id}\n"

    if file_path:
        with open(file_path, "w", encoding="utf-8") as f:
            f.write(mermaid)

    return mermaid


# Registration
def register_modules() -> None:
    if BACKGROUND and bpy.app.background:
        return

    classes = _get_classes()
    success = True

    for cls in classes:
        try:
            _validate_class(cls)
            bpy.utils.register_class(cls)
            if DBG_INIT:
                Log.info(f"✓ Registration completed: {cls.__name__}")
        except Exception as e:
            success = False
            Log.error(f"✗ Class registration failed: {cls.__name__}")
            Log.error(f"   Reason: {str(e)}")
            Log.error(f"   Module: {cls.__module__}")
            if hasattr(cls, "__annotations__"):
                Log.error(f"   Annotations: {list(cls.__annotations__.keys())}")

    for mod_name in MODULE_NAMES:
        try:
            mod = sys.modules[mod_name]
            if hasattr(mod, "register"):
                mod.register()
                if DBG_INIT:
                    Log.info(f"✓ Initialization completed: {mod_name}")
        except Exception as e:
            success = False
            Log.error(f"✗ Module initialization failed: {mod_name}")
            Log.error(f"   Reason: {str(e)}")
            Log.error("   Stack trace:")
            Log.error("   " + traceback.format_exc().replace("\n", "\n   "))

    if not success:
        Log.warn("Warning: Some components failed to initialize")


def unregister_modules() -> None:
    if BACKGROUND and bpy.app.background:
        return

    for mod_name in reversed(MODULE_NAMES):
        try:
            mod = sys.modules[mod_name]
            if hasattr(mod, "unregister"):
                mod.unregister()
        except Exception as e:
            Log.error(f"✗ Module unregister failed: {mod_name}")
            Log.error(f"   Reason: {str(e)}")
            Log.error("   Stack trace:")
            Log.error("   " + traceback.format_exc().replace("\n", "\n   "))

    for cls in reversed(_get_classes()):
        try:
            bpy.utils.unregister_class(cls)
        except Exception as e:
            Log.error(f"✗ Class unregister failed: {cls.__name__}")
            Log.error(f"   Reason: {str(e)}")
            Log.error("   Stack trace:")
            Log.error("   " + traceback.format_exc().replace("\n", "\n   "))


# Module Collection
def _collect_module_names() -> List[str]:
    def is_masked(name: str) -> bool:
        """Check if the module name matches the pattern"""
        return any(p.match(name) for p in MODULE_PATTERNS)

    def scan(path: str, package: str) -> List[str]:
        """Recursively search for modules in the specified path"""
        modules = []
        for _, name, is_pkg in pkgutil.iter_modules([path]):
            if name.startswith("_"):
                continue

            full_name = f"{package}.{name}"

            if is_pkg:
                modules.extend(scan(os.path.join(path, name), full_name))

            if is_masked(full_name):
                modules.append(full_name)
        return modules

    return scan(ADDON_PATH, ADDON_ID)


# Class Collection
def _get_classes(force: bool = True) -> List[bpy.types.bpy_struct]:
    global _class_cache
    if not force and _class_cache:
        return _class_cache

    class_deps = defaultdict(set)
    pdtype = getattr(bpy.props, "_PropertyDeferred", tuple)

    all_classes = []
    for mod_name in MODULE_NAMES:
        mod = sys.modules[mod_name]
        for _, cls in inspect.getmembers(mod, _is_bpy_class):
            deps = set()
            for prop in getattr(cls, "__annotations__", {}).values():
                if isinstance(prop, pdtype):
                    pfunc = getattr(prop, "function", None) or prop[0]
                    if pfunc in (
                        bpy.props.PointerProperty,
                        bpy.props.CollectionProperty,
                    ):
                        if dep_cls := prop.keywords.get("type"):
                            if dep_cls.__module__.startswith(ADDON_ID):
                                deps.add(dep_cls)
            class_deps[cls] = deps
            all_classes.append(cls)

    ordered = []
    visited = set()
    stack = []

    def visit(cls):
        if cls in stack:
            cycle = " → ".join([c.__name__ for c in stack])
            raise ValueError(f"Class cycle detected: {cycle}")
        if cls not in visited:
            stack.append(cls)
            visited.add(cls)

            for dep in class_deps.get(cls, []):
                visit(dep)
            stack.pop()
            ordered.append(cls)

    for cls in all_classes:
        if cls not in visited:
            visit(cls)

    if DBG_INIT:
        Log.header("Registered classes")
        for cls in ordered:
            Log.info(f" - {cls.__name__}")

    _class_cache = ordered
    return ordered


def _is_bpy_class(obj) -> bool:
    return (
        inspect.isclass(obj)
        and issubclass(obj, bpy.types.bpy_struct)
        and obj.__base__ is not bpy.types.bpy_struct
    )


def _validate_class(cls: bpy.types.bpy_struct) -> None:
    if not hasattr(cls, "bl_rna"):
        raise ValueError(f"Class {cls.__name__} does not have a bl_rna attribute")
    if not issubclass(cls, bpy.types.bpy_struct):
        raise TypeError(f"Invalid class type: {cls.__name__}")


# Timeout Operator
class Timeout(bpy.types.Operator):
    bl_idname = f"{ADDON_PREFIX_PY}.timeout"
    bl_label = ""
    bl_options = {"INTERNAL"}

    idx: bpy.props.IntProperty(options={"SKIP_SAVE", "HIDDEN"})
    delay: bpy.props.FloatProperty(default=0.0001, options={"SKIP_SAVE", "HIDDEN"})

    _data: Dict[int, tuple] = dict()
    _timer = None
    _finished = False

    def modal(self, context, event):
        if event.type == "TIMER":
            if self._finished:
                context.window_manager.event_timer_remove(self._timer)
                del self._data[self.idx]
                return {"FINISHED"}

            if self._timer.time_duration >= self.delay:
                self._finished = True
                try:
                    func, args = self._data[self.idx]
                    func(*args)
                except Exception as e:
                    Log.error(f"Timeout error: {str(e)}")
        return {"PASS_THROUGH"}

    def execute(self, context):
        self._finished = False
        context.window_manager.modal_handler_add(self)
        self._timer = context.window_manager.event_timer_add(
            self.delay, window=context.window
        )
        return {"RUNNING_MODAL"}


def timeout(func: callable, *args) -> None:
    idx = len(Timeout._data)
    while idx in Timeout._data:
        idx += 1
    Timeout._data[idx] = (func, args)
    getattr(bpy.ops, ADDON_PREFIX_PY).timeout(idx=idx)
